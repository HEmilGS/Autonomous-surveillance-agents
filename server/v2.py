from .models.ee import EventEmitter
from enum import Enum
from dotenv import load_dotenv
from openai import OpenAI
import hashlib
import random

def log(func):
    def wrapper(*args, **kwargs):
        print(f"Function {func.__name__} called with args: {args}, kwargs: {kwargs}")
        return func(*args, **kwargs)
    return wrapper


class Events(Enum):
    # CAMERA_CAPTURE event is triggered when a new
    # image is captured by a camera. 
    # data: "camera_id,b64img"
    CAMERA_CAPTURE = "camera_capture"

    # DRONE_CAMERA_CAPTURE event is an alias for
    # CAMERA_CAPTURE event, but for the drone camera
    # data: "camera_id,b64img"
    DRONE_CAMERA_CAPTURE = "drone_camera_capture"

    # DRONE_STATUS_UPDATE event is triggered when
    # an activity is completed by the drone
    # data: "status" -> "BUSY" or "IDLE"
    DRONE_STATUS_UPDATE = "drone_status_update"

    # MOVE_TO event is sent when the drone is requested
    # to move to a specific camera location
    # data: camera_id
    MOVE_TO = "move_to"
    

class MessageCode(Enum):
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    CONTROL_REQUEST = "CONTROL_REQUEST"
    CONTROL_ENDED = "CONTROL_ENDED"


class Message():
    def __init__(self, code, message, sender):
        self.message = message
        self.code = code
        self.timestamp = datetime.datetime.now()
        self.sender = sender


class DroneMode(Enum):
    AUTONOMOUS = "AUTONOMOUS"
    CONTROLLED = "CONTROLLED"

class DroneState(Enum):
    BUSY = "BUSY"
    IDLE = "IDLE"
    

class DroneAgent():
    def __init__(self, serverconn):
        self.analisis_scores = {}
        self.serverconn = serverconn
        self.images = {}
        self.score_cache = {}
        self.messages = []
        self.mode = DroneMode.AUTONOMOUS
        self.status = DroneState.IDLE
        self.guard: GuardAgent | None = None


    def step(self):
        self.update_status()

        if self.status == DroneState.BUSY:
            return

        if self.mode == DroneMode.AUTONOMOUS:
            self.handle_camera_events()
            self.analyze_images()

            for camera_id, score in self.analisis_scores.items():
                if score > 0.7:
                    self.report_suspicious_activity(camera_id)

            self.handle_connection_request()

        if self.mode == DroneMode.CONTROLLED:
            self.handle_connection_close()


    def move_to(self, camera_id):
        self.serverconn.send_event(Events.MOVE_TO.value, [camera_id])


    def update_status(self):
        while self.serverconn.check_event(Events.DRONE_STATUS_UPDATE.value):
            event = self.serverconn.get_event(Events.DRONE_STATUS_UPDATE.value)
            if event == "IDLE":
                self.status = DroneState.IDLE
            elif event == "BUSY":
                self.status = DroneState.BUSY
            else:
                raise Exception(f"Unknown event: {event}")


    def message_box_append(self, message):
        self.messages.append(message)


    def handle_connection_request(self):
        # Check if there is a connection request
        while self.messages:
            msg = self.messages.pop(0)
            if msg.code == MessageCode.CONTROL_REQUEST:
                self.mode = DroneMode.CONTROLLED
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def handle_connection_close(self):
        # Check if there is a connection close event
        while self.messages:
            msg = self.messages.pop(0)
            if msg.code == MessageCode.CONTROL_ENDED:
                self.mode = DroneMode.AUTONOMOUS
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def handle_camera_events(self):
        # This method should load the latest images from
        # the serverconn, so we can run vision on them
        while self.serverconn.check_event(Events.CAMERA_CAPTURE.value):
            event = self.serverconn.get_event(Events.CAMERA_CAPTURE.value)
            camera_id, b64img = event.split(",")
            self.images[camera_id] = b64img

        while self.serverconn.check_event(Events.DRONE_CAMERA_CAPTURE.value):
            event = self.serverconn.get_event(Events.DRONE_CAMERA_CAPTURE.value)
            camera_id, b64img = event.split(",")
            self.images[camera_id] = b64img
  
        
    def analyze_images(self):
        # This method uses the images loaded from the
        # `handle_camera_events` method, and uses gpt-4o-mini
        # to analyze them as images. it outputs a suspicion
        # score between 0 and 1 for each image. All activity
        # with a suspicion score > 0.7 is reported to the guard
        for camera_id, image in self.images.items():
            image_hash = hashlib.md5(image.encode()).hexdigest()

            # Check if we have a cached result
            if image_hash in self.score_cache:
                score = self.score_cache[image_hash]
                self.analisis_scores[camera_id] = score
                continue

            # Analyze the image and store the result
            score = self.analyze_picture(image)
            self.analisis_scores[camera_id] = score
            self.score_cache[image_hash] = score


    def analyze_picture(self, b64img: str) -> float:
        # TODO: This method should use GPT-4-Vision to analyze
        # the image and return a suspicion score between 0 and 1
        # for now, return a random number between 0 and 1
        return random.random()


    def report_suspicious_activity(self, camera_id):
        if self.guard is None:
            raise Exception("No guard agent set - cannot report suspicious activity")

        msg = Message(
            code=MessageCode.SUSPICIOUS_ACTIVITY,
            message=camera_id,
            sender=self
        )

        self.guard.message_box_append(msg)

    def _load_guard(self, guard):
        self.guard = guard


class GuardState(Enum):
    IDLE = "IDLE"
    INVESTIGATING = "INVESTIGATING"


class GuardAgent():
    def __init__(self, drone: DroneAgent, serverconn):
        self.messages = []
        self.state = GuardState.IDLE
        self.suspicious_camera = None
        self.moved_drone = False
        self.serverconn = serverconn

        self.drone = drone
        drone._load_guard(self)

    def step(self):
        if self.state == GuardState.IDLE:
            self.handle_suspicious_report()

        if self.state == GuardState.INVESTIGATING:
            # move the drone to the suspicious camera
            if self.drone.status == DroneState.IDLE and not self.moved_drone:
                # call this once to start moving
                self.moved_drone = True
                self.drone.move_to(self.suspicious_camera)

            if self.drone.status == DroneState.IDLE and self.moved_drone:
                self.moved_drone = False # reset

                # this means the drone has moved to the expected location
                # so we can look at the images and make a decision
                self.drone.handle_camera_events()
                self.drone.analyze_images()
                
                for camera_id, score in self.drone.analisis_scores.items():
                    if score > 0.8:
                        # alarm should be triggered
                        self.trigger_alarm()
                        break

                # let the drone know we're done
                msg = Message(
                    code=MessageCode.CONTROL_ENDED,
                    message="",
                    sender=self
                )             

                self.drone.message_box_append(msg)
                self.state = GuardState.IDLE   
    
    def trigger_alarm(self):
        self.serverconn.send_event(Events.ALARM.value, ["30"])


    def handle_suspicious_report(self):
        while self.messages:
            msg = self.messages.pop(0)
            if msg.code == MessageCode.SUSPICIOUS_ACTIVITY:
                self.state = GuardState.INVESTIGATING
                self.suspicious_camera = msg.message
                # request control of the drone
                msg = Message(
                    code=MessageCode.CONTROL_REQUEST,
                    message="",
                    sender=self
                )
                self.drone.message_box_append(msg)
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def message_box_append(self, message):
        self.messages.append(message)


class Simulation():
    def __init__(self, iterations=1000, dt=1):
        self.serverconn = EventEmitter()
        self.drone = DroneAgent(self.serverconn)
        self.guard = GuardAgent(self.drone, self.serverconn)
        self.iterations = iterations
        self.current_iterations = 0
        self.dt = dt
    
    def run(self):
        while self.current_iterations < self.iterations:
            self.current_iterations += 1
            self.drone.step()
            self.guard.step()
            sleep(self.dt)


if __name__ == "__main__":
    simulation = Simulation()
    simulation.run()