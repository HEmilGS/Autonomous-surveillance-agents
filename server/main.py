from enum import Enum
from models.camera import Camera
from models.ee import MockEmitter
from time import sleep

import datetime
from typing import Any

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
        

class DroneOperationMode(Enum):
    AUTONOMOUS = "AUTONOMOUS"
    CONTROLLED = "CONTROLLED"

serverconn = MockEmitter()

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
        self.initial_position = initial_position
        self.position = initial_position
        self.operationMode = DroneOperationMode.AUTONOMOUS
        self.cameras: list[Camera] = [] + (initial_cameras if initial_cameras is not None else [])
        self.temperature = 0.5
        self.current_picture: str | None = None
        self.current_drift: Vector(0, 0, 0)

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
            v = serverconn.get_event("drone_drift_update")
            total_drift = total_drift.add(v)

        return total_drift

    def perceive(self):
        # update drift information (because of wind)
        self.current_drift = self.get_client_drift()

        # update position information
        new_position = self.get_client_position()

        if new_position != self.position:
            self.position = new_position

        self.current_picture = self.get_picture()
        

    def plan(self):
        return
    
    def step(self):
        return

    def get_picture(self) -> str | None:
        picture = None

        while serverconn.check_event("drone_picture_taken"):
            picture = serverconn.check_event("drone_picture_taken")
            
        return picture

    def analyze_picture(self, b64img: str):
        return 0.5 # score
    
    def report_suspicious_activity(self, position: Position):
        return

    def accept_control_request(self):
        return

    def check_fixed_cameras(self):
        return

class GuardAgent(Agent):
    def __init__(self, initial_position: Position, drone: DroneAgent):
        self.initial_position = initial_position
        self.position = initial_position
        self.drone = drone

    def perceive(self):
        return

    def plan(self):
        return

    def step(self):
        return

    def take_picture(self):
        return

    def analyze_picture(self):
        return

    def sound_alarm(self):
        return

    def request_drone_control(self):
        return

    def start_drone_control(self):
        return

class Simulation():
    def __init__(self, guard: GuardAgent, drone: DroneAgent, iterations=1000, dt=0.1):
        self.drone = drone
        self.guard = guard
        self.iterations = iterations
        self.current_iterations = 0
        self.dt = dt
        self.all_agents: list[Agent] = [guard, drone]

    def run(self):
        for i in range(self.iterations):
            self.current_iterations += 1
            for a in self.all_agents:
                a.run()
            
            # sleep(self.dt)

            

drone = DroneAgent(Position(0, 0, 0), None)
guard = GuardAgent(Position(1, 1, 1), drone)

sim = Simulation(guard, drone)
sim.run()
