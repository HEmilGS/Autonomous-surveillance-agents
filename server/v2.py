from .models.ee import EventEmitter
from enum import Enum
from dotenv import load_dotenv
from openai import OpenAI
import hashlib
import random
import argparse
import logging
import datetime
import time
import os
import base64
from PIL import Image
import imagehash
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    # ALARM event is triggered when an alarm is triggered
    # by the drone,
    # data: "time"
    ALARM = "alarm"

    # Events for stats tracking
    ALARM_TRIGGERED = "alarm_triggered"
    SUSPICIOUS_ACTIVITY_STARTED = "suspicious_activity_started"


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
        self.camera_locations = {}
        self.score_cache = {}
        self.image_hashes = {}  # Store perceptual hashes of images
        self.hash_cutoff = 0    # Maximum bits that could be different between hashes
        self.messages = []
        self.mode = DroneMode.AUTONOMOUS
        self.status = DroneState.IDLE
        self.drone_camera = None
        self.guard: 'GuardAgent' | None = None
        self.oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.thread_pool = ThreadPoolExecutor(max_workers=10)  # Increased to 10 workers for more parallelism
        print("[DEBUG] DroneAgent initialized")

    def get_image_hash(self, b64img: str) -> imagehash.ImageHash:
        """Calculate perceptual hash of a base64 encoded image."""
        try:
            # Convert base64 to image
            img_data = base64.b64decode(b64img)
            img = Image.open(io.BytesIO(img_data))
            # Calculate perceptual hash
            return imagehash.average_hash(img)
        except Exception as e:
            print(f"[ERROR] Failed to calculate image hash: {e}")
            return None

    def step(self):
        print("[DEBUG] DroneAgent.step() - Starting execution cycle")
        self.update_status()

        if self.status == DroneState.BUSY:
            print("[DEBUG] DroneAgent.step() - Drone is busy, skipping execution cycle")
            return

        if self.mode == DroneMode.AUTONOMOUS:
            self.handle_camera_events()
            self.analyze_images()

            riskiest_camera = None
            for camera_id, score in self.analisis_scores.items():
                if riskiest_camera is None or score > self.analisis_scores[riskiest_camera]:
                    riskiest_camera = camera_id

            if riskiest_camera is not None and riskiest_camera in self.analisis_scores and self.analisis_scores[riskiest_camera] >= 0.5:
                self.report_suspicious_activity(riskiest_camera)

            self.handle_connection_request()

        if self.mode == DroneMode.CONTROLLED:
            self.handle_connection_close()


    def move_to(self, camera_id):
        x, y, z, xrot, yrot, zrot = self.camera_locations[camera_id]
        self.serverconn.send_event(Events.MOVE_TO.value, [x, y, z, xrot, yrot, zrot, camera_id])
        self.status = DroneState.BUSY


    def update_status(self):
        while self.serverconn.check_event(Events.DRONE_STATUS_UPDATE.value):
            event = self.serverconn.get_event(Events.DRONE_STATUS_UPDATE.value)
            if event == "IDLE":
                print("[DEBUG] DroneAgent.update_status() - Changing status to IDLE")
                self.status = DroneState.IDLE
            elif event == "BUSY":
                print("[DEBUG] DroneAgent.update_status() - Changing status to BUSY")
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
                print("[DEBUG] DroneAgent.handle_connection_request() - Control request received - switching to CONTROLLED mode")
                self.mode = DroneMode.CONTROLLED
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def handle_connection_close(self):
        # Check if there is a connection close event
        while self.messages:
            msg = self.messages.pop(0)
            if msg.code == MessageCode.CONTROL_ENDED:
                print("[DEBUG] DroneAgent.handle_connection_close() - Control ended received - switching to AUTONOMOUS mode")
                self.mode = DroneMode.AUTONOMOUS
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def handle_camera_events(self):
        print("[DEBUG] DroneAgent.handle_camera_events() - Handling camera events")
        # This method should load the latest images from
        # the serverconn, so we can run vision on them
        while self.serverconn.check_event(Events.CAMERA_CAPTURE.value):
            event = self.serverconn.get_event(Events.CAMERA_CAPTURE.value)
            camera_id, x, y, z, xrot, yrot, zrot, b64img = event.split(",")
            self.camera_locations[camera_id] = (x, y, z, xrot, yrot, zrot)
            self.images[camera_id] = b64img

        while self.serverconn.check_event(Events.DRONE_CAMERA_CAPTURE.value):
            event = self.serverconn.get_event(Events.DRONE_CAMERA_CAPTURE.value)
            camera_id, x, y, z, xrot, yrot, zrot, b64img = event.split(",")
            self.camera_locations[camera_id] = (x, y, z, xrot, yrot, zrot)
            self.images[camera_id] = b64img
            self.drone_camera = camera_id
            
  
        
    def analyze_single_image(self, camera_id: str, image: str) -> tuple[str, float]:
        """Analyze a single image and return its camera_id and score."""
        current_hash = self.get_image_hash(image)
        if current_hash is None:
            print(f"[ERROR] Could not calculate hash for camera {camera_id}, forcing analysis")
            score = self.analyze_picture(image)
            return camera_id, score

        # Check if we have a previous hash for this camera
        if camera_id in self.image_hashes and camera_id in self.score_cache:
            prev_hash = self.image_hashes[camera_id]
            hash_diff = current_hash - prev_hash
            
            if hash_diff < self.hash_cutoff:
                print(f"[DEBUG] Images similar for camera {camera_id} (diff: {hash_diff}) - Using cached score")
                return camera_id, self.score_cache[camera_id]
            else:
                print(f"[DEBUG] Significant change detected for camera {camera_id} (diff: {hash_diff})")

        # If we reach here, we need to analyze the image
        print(f"[DEBUG] Analyzing new image from camera {camera_id}")
        score = self.analyze_picture(image)
        
        # Update caches
        self.score_cache[camera_id] = score
        self.image_hashes[camera_id] = current_hash
        
        return camera_id, score

    def analyze_images(self):
        print("[DEBUG] DroneAgent.analyze_images() - Analyzing images in parallel")
        
        # Submit all image analysis tasks to the thread pool
        future_to_camera = {
            self.thread_pool.submit(self.analyze_single_image, camera_id, image): camera_id
            for camera_id, image in self.images.items()
        }

        # Collect results as they complete
        for future in as_completed(future_to_camera):
            try:
                camera_id, score = future.result()
                self.analisis_scores[camera_id] = score
            except Exception as e:
                camera_id = future_to_camera[future]
                print(f"[ERROR] Analysis failed for camera {camera_id}: {str(e)}")
                # Set a default score or handle the error as needed
                self.analisis_scores[camera_id] = 0.0

    def analyze_picture(self, b64img: str) -> float:
        start_time = time.time()
        print("[DEBUG] DroneAgent.analyze_picture() - Analyzing picture")

        response = self.oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this surveillance image and detect any suspicious activities. Rate the suspicion level from 0 to 1, where 0 is completely normal and 1 is highly suspicious. Only respond with a number between 0 and 1. Ratings over 0.5 means something is suspicious. Magenta men are suspicious."
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

        print("[DEBUG] DroneAgent.analyze_picture() - Result:", response.choices[0].message.content)
        print("[DEBUG] DroneAgent.analyze_picture() - Time taken:", time.time() - start_time)
        
        return float(response.choices[0].message.content)


    def report_suspicious_activity(self, camera_id):
        print("[DEBUG] DroneAgent.report_suspicious_activity() - Reporting suspicious activity in camera", camera_id)

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
        print("[DEBUG] GuardAgent initialized")


    def step(self):
        print("[DEBUG] GuardAgent.step() - Starting execution cycle")
        if self.state == GuardState.IDLE:
            self.handle_suspicious_report()

        if self.state == GuardState.INVESTIGATING:
            # move the drone to the suspicious camera
            if self.drone.status == DroneState.IDLE and not self.moved_drone:
                print("[DEBUG] GuardAgent.step() - Moving drone to suspicious camera")
                # call this once to start moving
                self.moved_drone = True
                self.drone.move_to(self.suspicious_camera)

            if self.drone.status == DroneState.IDLE and self.moved_drone:
                print("[DEBUG] GuardAgent.step() - Drone moved to suspicious camera")
                self.moved_drone = False # reset

                # this means the drone has moved to the expected location
                # so we can look at the images and make a decision\
                print("[DEBUG] GuardAgent.step() - Analyzing images")
                self.drone.handle_camera_events()
                self.drone.analyze_images()

                score = self.drone.analisis_scores[self.drone.drone_camera]
                # only check drone camera to confirm
                if score > 0.5:
                    print("[DEBUG] GuardAgent.step() - Suspicious activity detected in drone camera")
                    # alarm should be triggered
                    self.trigger_alarm()

                print("[DEBUG] GuardAgent.step() - Sending control ended message")
                # let the drone know we're done
                msg = Message(
                    code=MessageCode.CONTROL_ENDED,
                    message="",
                    sender=self
                )             

                print("[DEBUG] GuardAgent.step() - Changing state to IDLE")
                self.drone.message_box_append(msg)
                self.state = GuardState.IDLE   
    
    def trigger_alarm(self):
        self.serverconn.send_event(Events.ALARM.value, ["17"])
        self.serverconn.send_event(Events.ALARM_TRIGGERED.value, [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])


    def handle_suspicious_report(self):
        while self.messages:
            msg = self.messages.pop(0)
            if msg.code == MessageCode.SUSPICIOUS_ACTIVITY:
                print("[DEBUG] GuardAgent.handle_suspicious_report() - Handling suspicious report")
                self.state = GuardState.INVESTIGATING
                self.suspicious_camera = msg.message
                # request control of the drone
                msg = Message(
                    code=MessageCode.CONTROL_REQUEST,
                    message="",
                    sender=self
                )
                self.drone.message_box_append(msg)
                self.serverconn.send_event(Events.SUSPICIOUS_ACTIVITY_STARTED.value, [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg.message])
            else:
                print("[WARN]: Unknown message code:", msg.code)


    def message_box_append(self, message):
        self.messages.append(message)


class Stats:
    def __init__(self, serverconn):
        self.serverconn = serverconn
        self.alarm_events = []
        self.suspicious_activities = []
        print("[DEBUG] Stats tracking initialized")
    
    def update_stats(self):
        # Check for alarm events
        while self.serverconn.check_event(Events.ALARM_TRIGGERED.value):
            data = self.serverconn.get_event(Events.ALARM_TRIGGERED.value).split(',')
            timestamp = data[0]  # First element is the timestamp
            self.alarm_events.append({
                'timestamp': datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S'),
                'data': data
            })
            print(f"[STATS] Alarm triggered at {timestamp}")
        
        # Check for suspicious activity events
        while self.serverconn.check_event(Events.SUSPICIOUS_ACTIVITY_STARTED.value):
            data = self.serverconn.get_event(Events.SUSPICIOUS_ACTIVITY_STARTED.value).split(',')
            timestamp = data[0]  # First element is the timestamp
            self.suspicious_activities.append({
                'timestamp': datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S'),
                'data': data
            })
            print(f"[STATS] Suspicious activity detected at {timestamp}")
    
    def get_stats_summary(self):
        return {
            'total_alarms': len(self.alarm_events),
            'total_suspicious_activities': len(self.suspicious_activities),
            'alarm_events': self.alarm_events,
            'suspicious_activities': self.suspicious_activities
        }

    def create_response_time_graph(self):
        """Creates a graph showing response times between suspicious activities and alarms"""
        import matplotlib.pyplot as plt
        from datetime import timedelta

        response_times = []
        false_positives = []
        matched_alarms = set()

        # Calculate response times and identify false positives
        for alarm in self.alarm_events:
            alarm_time = alarm['timestamp']
            # Find the closest previous suspicious activity
            closest_activity = None
            min_time_diff = timedelta(minutes=5)  # Max 5 minutes response time threshold

            for activity in self.suspicious_activities:
                if activity['timestamp'] < alarm_time:
                    time_diff = alarm_time - activity['timestamp']
                    if time_diff < min_time_diff:
                        min_time_diff = time_diff
                        closest_activity = activity

            if closest_activity:
                response_times.append((len(response_times), min_time_diff.total_seconds()))
                matched_alarms.add(alarm_time)
            else:
                false_positives.append(alarm_time)

        # Create response time graph
        plt.figure(figsize=(12, 6))
        if response_times:
            x, y = zip(*response_times)
            plt.plot(x, y, 'b-', label='Response Time')
            
            # Calculate and plot average response time
            avg_response_time = sum(y) / len(y)
            plt.axhline(y=avg_response_time, color='r', linestyle='--', 
                       label=f'Average: {avg_response_time:.2f}s')
        
        plt.xlabel("Alarm Number")
        plt.ylabel("Response Time (seconds)")
        plt.title("Alarm Response Times")
        plt.legend()
        plt.grid(True)
        plt.savefig("response_times.png")
        plt.close()

        # Create false positives graph
        plt.figure(figsize=(8, 6))
        labels = ['Valid Alarms', 'False Positives']
        sizes = [len(matched_alarms), len(false_positives)]
        colors = ['lightgreen', 'lightcoral']
        
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%')
        plt.title("Alarm Accuracy Analysis")
        plt.savefig("false_positives.png")
        plt.close()

        return {
            'average_response_time': sum(y for _, y in response_times) / len(response_times) if response_times else 0,
            'false_positive_rate': len(false_positives) / len(self.alarm_events) if self.alarm_events else 0,
            'total_alarms': len(self.alarm_events),
            'valid_alarms': len(matched_alarms),
            'false_positives': len(false_positives)
        }


class Simulation():
    def __init__(self, iterations=1000, dt=1):
        self.serverconn = EventEmitter()
        self.drone = DroneAgent(self.serverconn)
        self.guard = GuardAgent(self.drone, self.serverconn)
        self.stats = Stats(self.serverconn)  # Initialize stats tracking
        self.iterations = iterations
        self.current_iterations = 0
        self.dt = dt
        print(f"[DEBUG] Simulation initialized with {iterations} iterations, dt={dt}")
    
    def run(self):
        print("[DEBUG] Starting simulation")
        
        while self.current_iterations < self.iterations:
            self.drone.step()
            self.guard.step()
            self.stats.update_stats()  # Update stats each iteration
            
            self.current_iterations += 1
            time.sleep(self.dt)

        stats_summary = self.stats.get_stats_summary()
        response_time_graph = self.stats.create_response_time_graph()
        print("[DEBUG] Simulation completed")
        
        # Print key metrics
        print("\n=== Simulation Results ===")
        print(f"Total Alarms: {response_time_graph['total_alarms']}")
        print(f"Valid Alarms: {response_time_graph['valid_alarms']}")
        print(f"False Positives: {response_time_graph['false_positives']}")
        print(f"False Positive Rate: {response_time_graph['false_positive_rate']*100:.1f}%")
        if response_time_graph['average_response_time'] > 0:
            print(f"Average Response Time: {response_time_graph['average_response_time']:.2f} seconds")
        print(f"Total Suspicious Activities: {stats_summary['total_suspicious_activities']}")
        print("=======================\n")
        
        return stats_summary, response_time_graph


if __name__ == "__main__":
    simulation = Simulation(50, 5)
    simulation.run()