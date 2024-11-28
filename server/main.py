from enum import Enum
from models.camera import Camera
from models.ee import MockEmitter, EventEmitter
from time import sleep
from uuid import uuid4
import base64
import os
from openai import OpenAI
from dotenv import load_dotenv
import datetime
from typing import Any
import hashlib
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Position():
    def __init__(self, x: int, y: int, z: int):
        self.x = x
        self.y = y
        self.z = z 

class Vector():
    def __init__(self, i: int, j: int, k: int):
        self.i = i
        self.j = j
        self.k = k

    def add(self, other: 'Vector') -> 'Vector':
        return Vector(self.i + other.i, self.j + other.j, self.k + other.k)

class Message():
    def __init__(self, type: str, message: str, sender: Any):
        self.type = type
        self.message = message
        self.timestamp = datetime.datetime.now()
        self.sender = sender


class DroneStep(Enum):
    TAKE_PICTURE = "TAKE_PICTURE"
    ANALYZE_PICTURE = "ANALYZE_PICTURE"
    REPORT_SUSPICIOUS_ACTIVITY = "REPORT_SUSPICIOUS_ACTIVITY"
    ACCEPT_CONTROL_REQUEST = "ACCEPT_CONTROL_REQUEST"
    CHECK_FIXED_CAMERAS = "CHECK_FIXED_CAMERAS"
    MOVE_TO_POSITION = "MOVE_TO_POSITION"

class MessageType(Enum):
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    CONTROL_REQUEST = "CONTROL_REQUEST"
    CONTROL_ACCEPTED = "CONTROL_ACCEPTED"
    CONTROL_ENDED = "CONTROL_ENDED"

class Step():
    def __init__(self, step: DroneStep, args: list[Any]):
        self.step = step
        self.args = args

class DroneOperationMode(Enum):
    AUTONOMOUS = "AUTONOMOUS"
    CONTROLLED = "CONTROLLED"

serverconn = EventEmitter()

class Agent():
    """
    Class that provides the common agent structure for
    polymorphism purposes. This will allow to map over a
    list of agents and call agent.run() on each.
    """
    def __init__(self):
        self.message_queue: list[Message] = []

    def perceive(self) -> None:
        """
        The task of the perceive function is to gather all neccesary
        information from the environments via available sensors, and 
        update the internal state in a way that can be accesed later
        in the plan() method
        """
        raise Exception("Virtual method not implemented")

    def plan(self) -> None:
        """
        The task of the plan function is given the current state of
        the object, plan the next step/s to be executed in the step()
        method. The first step on the plan MUST BE VALID. This means
        We need to check the feasibility of step one before finishing
        """
        raise Exception("Virtual method not implemented")
    
    def step(self) -> None:
        """
        The task of the step function is to execute the selected plan.
        At this point, step one should be safe, so we can execute it 
        with no checks
        """
        raise Exception("Virtual method not implemented")

    def receive_message(self, message: Message):
        self.message_queue.append(message)

    def process_message(self) -> Message:
        return self.message_queue.pop(0)

    def check_message(self) -> bool:
        return not len(self.message_queue) == 0

    def run(self) -> None:
        self.perceive()
        self.plan()
        self.step()
    
class DroneAgent(Agent):
    def __init__(self, initial_position: Position, initial_cameras: list[Camera] | None):
        super().__init__()
        self.initial_position = initial_position
        self.position = initial_position
        self.operationMode = DroneOperationMode.AUTONOMOUS
        self.cameras: list[Camera] = [] + (initial_cameras if initial_cameras is not None else [])
        self.temperature = 0.5
        self.pictures: dict[str, str] = {}
        self.analisis_scores: dict[str, float] = {}
        self.current_drift = Vector(0, 0, 0)
        self.steps: list[DroneStep] = []
        # Cache for image analysis results
        self._analysis_cache: dict[str, float] = {}
        self.guard: GuardAgent | None = None

    def set_guard(self, guard: 'GuardAgent'):
        """Set the guard agent that this drone will report to"""
        self.guard = guard

    def get_client_position(self) -> Position:
        """
        function that consumes all `drone_position_update` events from the
        server, discards all positions but the last one, and updates the
        current position. If no event updates were found on the server, the
        function returns the current known position
        """
        last_position = None

        while serverconn.check_event("drone_position_update"):
            # TODO: Add data parsing
            last_position = serverconn.get_event("drone_position_update")

        return last_position if last_position is not None else self.position

    def get_client_drift(self) -> Vector:
        """
        function that consumes all `drone_drift_update` events from the
        server, and calculates the total drift, so the current drift state
        can be updated and a correction can be planned
        """
        total_drift = Vector(0, 0, 0)

        while serverconn.check_event("drone_drift_update"):
            # TODO: Add data parsing
            data = serverconn.get_event("drone_drift_update")
            total_drift = total_drift.add(data)

        return total_drift

    # perceive function should only update internal state
    # so the drone can decide what to do
    def perceive(self):
        # update drift information (because of wind)
        self.current_drift = self.get_client_drift()

        # update position information
        new_position = self.get_client_position()

        if new_position != self.position:
            self.position = new_position

        self.pictures = self.get_pictures()
        

    def plan(self):
        """
        Plan next steps based on current state and operation mode.
        In AUTONOMOUS mode: actively plan and execute surveillance
        In CONTROLLED mode: only check for control end message
        """
        # Clear previous steps
        self.steps.clear()
        
        # Check messages regardless of mode
        while self.check_message():
            msg = self.process_message()
            if msg.type == MessageType.CONTROL_ENDED.value and self.operationMode == DroneOperationMode.CONTROLLED:
                logging.info("Received control end message, returning to autonomous mode")
                self.operationMode = DroneOperationMode.AUTONOMOUS
                return  # Don't plan steps this cycle
            elif msg.type == MessageType.CONTROL_REQUEST.value:
                self.steps.append(Step(DroneStep.ACCEPT_CONTROL_REQUEST, []))
                return  # Don't plan other steps if we're about to be controlled

        # Only plan new steps if we're in autonomous mode
        if self.operationMode == DroneOperationMode.AUTONOMOUS:
            # Plan surveillance steps
            if len(self.pictures) > 0:
                # If we have pictures, analyze them
                for camera_id, picture in self.pictures.items():
                    analyze_step = Step(DroneStep.ANALYZE_PICTURE, [picture])
                    self.steps.append(analyze_step)
                
                # Clear pictures after planning analysis
                self.pictures.clear()
            
            # Handle drift correction if needed
            if self.current_drift != Vector(0, 0, 0):
                # Drone is drifting, we need to correct course
                # Calculate correction position by subtracting drift from current position
                correction = Position(
                    self.position.x - self.current_drift.i,
                    self.position.y - self.current_drift.j,
                    self.position.z - self.current_drift.k
                )
                correct_drift_step = Step(DroneStep.MOVE_TO_POSITION, [correction])
                self.steps.append(correct_drift_step)
                
                # Clear the drift state
                self.current_drift = Vector(0, 0, 0)
            
            # If we have analysis scores, check for suspicious activity
            if len(self.analisis_scores) > 0:
                for camera_id, score in self.analisis_scores.items():
                    if score > 0.7:  # Threshold for suspicious activity
                        report_step = Step(DroneStep.REPORT_SUSPICIOUS_ACTIVITY, [camera_id])
                        self.steps.append(report_step)
                
                # Clear the analysis state
                self.analisis_scores.clear()
            
            # Always check fixed cameras as part of routine
            self.steps.append(Step(DroneStep.CHECK_FIXED_CAMERAS, []))
            
            # Take pictures periodically
            self.steps.append(Step(DroneStep.TAKE_PICTURE, []))
            
            # Ensure we have at least one step planned
            if len(self.steps) == 0:
                raise Exception("No steps to execute in DroneAgent.plan()")
            
        elif self.operationMode == DroneOperationMode.CONTROLLED:
            logging.debug("Drone in controlled mode - no autonomous planning")
    
    def step(self):
        for step in self.steps:
            if step.step == DroneStep.TAKE_PICTURE:
                self.take_picture()
            elif step.step == DroneStep.ANALYZE_PICTURE:
                self.analyze_picture(step.args[0])
            elif step.step == DroneStep.REPORT_SUSPICIOUS_ACTIVITY:
                self.report_suspicious_activity(step.args[0])
            elif step.step == DroneStep.ACCEPT_CONTROL_REQUEST:
                self.accept_control_request()
            elif step.step == DroneStep.CHECK_FIXED_CAMERAS:
                self.check_fixed_cameras()
            elif step.step == DroneStep.MOVE_TO_POSITION:
                self.move_to_position(step.args[0])

    def take_picture(self) -> str | None:
        pic = None
    
        # consume all `drone_camera_capture` events
        while serverconn.check_event("drone_camera_capture"):
            pic = serverconn.get_event("drone_camera_capture")

            # update the picture state
            self.pictures["drone-camera"] = pic

        return pic
        

    def get_pictures(self) -> dict[str, str] | None:
        pictures = {}

        while serverconn.check_event("camera_capture"):
            data = serverconn.get_event("camera_capture")
            camera_id, b64img = data.split(",")
            pictures[camera_id] = b64img
            
        return pictures

    def analyze_picture(self, b64img: str) -> float:
        """
        Analyze a base64 encoded image using GPT-4-Vision to detect suspicious activities.
        Returns a suspicion score between 0 and 1. Results are cached by image hash.
        """
        # Create a hash of the image to use as cache key
        img_hash = hashlib.md5(b64img.encode()).hexdigest()
        
        # Check if we have a cached result
        if img_hash in self._analysis_cache:
            logging.info(f"Cache HIT for image {img_hash[:8]}... - Score: {self._analysis_cache[img_hash]}")
            return self._analysis_cache[img_hash]
        
        logging.info(f"Cache MISS for image {img_hash[:8]}... - Requesting analysis")
        
        try:
            # Create the message for GPT-4-Vision
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this surveillance image and detect any suspicious activities. Rate the suspicion level from 0 to 1, where 0 is completely normal and 1 is highly suspicious. Only respond with a number between 0 and 1."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64img}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=10  # We only need a number
            )
            
            # Extract the score from the response
            try:
                score = float(response.choices[0].message.content.strip())
                # Ensure score is between 0 and 1
                score = max(0.0, min(1.0, score))
                # Cache the result
                self._analysis_cache[img_hash] = score
                logging.info(f"Analysis complete for image {img_hash[:8]}... - Score: {score}")
                return score
            except ValueError:
                logging.error(f"Failed to parse GPT-4-Vision response as float for image {img_hash[:8]}...")
                return 0.5
                
        except Exception as e:
            logging.error(f"Error analyzing image {img_hash[:8]}...: {str(e)}")
            return 0.5  # Return neutral score on error

    def report_suspicious_activity(self, camera_id: str):
        """
        Report suspicious activity detected in a camera feed.
        Args:
            camera_id: ID of the camera that detected the activity
        """
        if self.guard is None:
            logging.error("No guard agent set - cannot report suspicious activity")
            return
            
        message = {
            "camera_id": camera_id,
            "drone_position": {
                "x": self.position.x,
                "y": self.position.y,
                "z": self.position.z
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        logging.info(f"Reporting suspicious activity from camera {camera_id}")
        
        # Create and send message directly to guard
        msg = Message(
            type=MessageType.SUSPICIOUS_ACTIVITY.value,
            message=str(message),
            sender=self
        )
        
        self.guard.receive_message(msg)

    def accept_control_request(self):
        """
        Accept a control request from the guard and switch to CONTROLLED mode.
        Sends confirmation back to guard.
        """
        logging.info("Drone accepting control request from guard")
        
        # Switch to controlled mode
        self.operationMode = DroneOperationMode.CONTROLLED
        
        # Clear any pending autonomous steps
        self.steps.clear()
        
        # Notify guard that control is accepted
        msg = Message(
            type=MessageType.CONTROL_ACCEPTED.value,
            message=str({
                "drone_position": {
                    "x": self.position.x,
                    "y": self.position.y,
                    "z": self.position.z
                },
                "timestamp": datetime.datetime.now().isoformat()
            }),
            sender=self
        )
        
        if self.guard:
            self.guard.receive_message(msg)
            logging.info("Control acceptance sent to guard")
        else:
            logging.error("No guard set - cannot confirm control acceptance")

    def check_fixed_cameras(self):
        """
        Check all fixed cameras for new images and add them to the pictures dictionary
        for later analysis.
        """
        while serverconn.check_event("fixed_camera_capture"):
            data = serverconn.get_event("fixed_camera_capture")
            camera_id, b64img = data.split(",")
            self.pictures[camera_id] = b64img

    def move_to_position(self, position: Position):
        """
        Send a movement command to the Unity client to move the drone to a specific position.
        """
        try:
            # Convert position to list of strings
            position_data = [str(position.x), str(position.y), str(position.z)]
            
            # Send movement command to Unity client
            serverconn.send_event("drone_move_command", position_data)
            logging.info(f"Sent move command to position ({position.x}, {position.y}, {position.z})")
            
            # Update our internal position state
            self.position = position
            
        except Exception as e:
            logging.error(f"Error sending move command: {e}")

class GuardAgent(Agent):
    def __init__(self, initial_position: Position, drone: DroneAgent):
        super().__init__()
        self.initial_position = initial_position
        self.position = initial_position
        self.drone = drone
        # Set this guard as the drone's guard
        drone.set_guard(self)
        # Track if we're controlling the drone
        self.controlling_drone = False

    def perceive(self):
        # Process any messages in the queue
        while self.check_message():
            msg = self.process_message()
            if msg.type == MessageType.SUSPICIOUS_ACTIVITY.value:
                logging.info(f"Guard received suspicious activity report")
            elif msg.type == MessageType.CONTROL_ACCEPTED.value:
                logging.info("Guard received control acceptance from drone")
                self.controlling_drone = True
                self.start_drone_control()

    def plan(self):
        return

    def step(self):
        print("guard step")
        last_event = None

        while serverconn.check_event("camera_capture"):
            last_event = serverconn.get_event("camera_capture")

        if last_event is not None:
            b64img = last_event.split(",")[1]
            image_data = base64.b64decode(b64img)
            filename = f"images/image_{uuid4()}.png"

            with open(filename, "wb") as f:
                f.write(image_data)

    def sound_alarm(self):
        return

    def request_drone_control(self):
        """Request control of the drone"""
        logging.info("Guard requesting drone control")
        msg = Message(
            type=MessageType.CONTROL_REQUEST.value,
            message=str({
                "guard_position": {
                    "x": self.position.x,
                    "y": self.position.y,
                    "z": self.position.z
                },
                "timestamp": datetime.datetime.now().isoformat()
            }),
            sender=self
        )
        self.drone.receive_message(msg)

    def start_drone_control(self):
        """
        Start controlling the drone after receiving acceptance.
        This will be called when we receive the CONTROL_ACCEPTED message.
        """
        if not self.controlling_drone:
            logging.warning("Attempted to start drone control without confirmation")
            return
            
        logging.info("Guard starting drone control")
        # Here we would typically start sending control commands to the drone
        # For now we just log that we're in control

class Simulation():
    def __init__(self, guard: GuardAgent, drone: DroneAgent, iterations=1000, dt=1):
        self.drone = drone
        self.guard = guard
        self.iterations = iterations
        self.current_iterations = 0
        self.dt = dt
        self.all_agents: list[Agent] = [guard, drone]

    def run(self):
        while True:
            self.current_iterations += 1
            for a in self.all_agents:
                a.run()
            
            sleep(self.dt)

drone = DroneAgent(Position(0, 0, 0), None)
guard = GuardAgent(Position(1, 1, 1), drone)

sim = Simulation(guard, drone)
sim.run()
