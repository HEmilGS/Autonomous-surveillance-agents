import random
import os
import base64
import uuid
from openai import OpenAI

from enum import Enum
from typing import Any
from copy import copy
from dotenv import load_dotenv

from models.storage import Storage
from models.eventemmiter import EventEmitter
from models.object import Object

class InsufficientStorage(Exception):
    pass

class InvalidHeight(Exception):
    pass

class SpaceState(Enum):
    FREE_SPACE = 1
    OUT_OF_BOUNDS = 2

class Warehouse():
    def __init__(self, dimensions: tuple[int, int, int], ee: EventEmitter):
        self.dimensions = dimensions
        x, y, z = dimensions
        self.capacity = 0
        self.ee = ee
        self.agents: list[Agent] = []
        self.storages: list[Storage] = [] 
        self.step_n = 0
        self.id = str(uuid.uuid4())
        
        # a list of points, (step, objects in the floor)
        self.time_series: list[tuple[int, int]] = []

        # generate an empty map. may contain none, storage or object
        # to access a given floor map, use self.map[level]
        # to access a given position, use self.map[level][x][y]
        self.map: list[list[list[SpaceState | Storage | Object | Agent]]] = [[[SpaceState.FREE_SPACE for _ in range(y)] for _ in range(x)] for _ in range(z)]

        # generate a static map that will never be modified. This
        # is what is going to be handed out to the agents initially
        self.static_map: list[list[list[SpaceState | Storage | Object | Agent]]] = [[[SpaceState.FREE_SPACE for _ in range(y)] for _ in range(x)] for _ in range(z)]
        
        # emit an event to notify client of
        # warehouse being attached
        self.ee.send_event("warehouse_attached", [self.id, x, y, z])

    def count_objects_floor(self):
        base_map = self.map[0]
        count = 0
        for row in base_map:
            for element in row:
                if isinstance(element, Object):
                    count += 1

        return count

    def is_sorted(self):
        base_map = self.map[0]
        global are_there_objects
        global agents_have_objects

        are_there_objects = False

        for row in base_map:
            for element in row:
                if isinstance(element, Object):
                    are_there_objects = True

        agents_have_objects = False
        for agent in self.agents:
            if agent.inventory is not None:
                agents_have_objects = True

        return not are_there_objects and not agents_have_objects

    # Attaches a storage to it's specified location
    # and keeps capacity information up to date
    def attach_storage(self, s: Storage):
        x, y, z = s.location

        # if we are going to overwrite, subtract capacity
        if self.map[z][x][y] != SpaceState.FREE_SPACE:
            raise Exception("Placing storage in occupied space")
        
        self.storages.append(s)

        # add storage to the map and update capacity
        self.update_maps((x, y, z), s)
        self.capacity += s.capacity

        # emit an event to notify client of storage being
        # attached
        self.ee.send_event("storage_attached", [s.id, x, y, z])

    # Method to seed a certain amount of objects
    # makes sure that there is enough capacity to
    # store given objects
    def seed_objects(self, object_count: int):
        # make sure we can actually fit all of the objects we
        # are seeding with our current capacity
        if object_count > self.capacity:
            raise InsufficientStorage(f"Make sure to attach more storage with attach_storage before seeding")

        object_srcs = os.listdir("server/objects")
        # the sources to the images 
        x, y, _ = self.dimensions

        # generate random positions for the objects in z = 0
        for _ in range(object_count):
            xrandom = random.choice(range(x))
            yrandom = random.choice(range(y))

            # keep trying combinations if some are busy
            while self.map[0][xrandom][yrandom] != SpaceState.FREE_SPACE:
                xrandom = random.choice(range(x))
                yrandom = random.choice(range(y))

            obj = Object((xrandom, yrandom, 0), random.choice(object_srcs))

            self.update_maps((xrandom, yrandom, 0), obj)
            
            # emit an event to notify the client of a
            # random object being placed
            self.ee.send_event("object_attached", [obj.id, obj.image_src.split(".")[0], xrandom, yrandom, 0])

    def seed_agents(self, agent_count: int):
        x, y, _ = self.dimensions

        for i in range(agent_count):
            xrandom = random.choice(range(x))
            yrandom = random.choice(range(y))

            while self.map[0][xrandom][yrandom] != SpaceState.FREE_SPACE:
                xrandom = random.choice(range(x))
                yrandom = random.choice(range(y))

            agent = Agent(self, (xrandom, yrandom, 0), i)
            
            self.agents.append(agent)
            self.map[0][xrandom][yrandom] = agent

            # emit an event to notify the client of a
            # random object being placed
            self.ee.send_event("agent_attached", [agent.id, xrandom, yrandom, 0])

    def get_surroundings(self, position: tuple[int, int, int]):
        x, y, _ = position
        x_space, y_space, z_space = self.dimensions

        if z_space > len(self.map):
            raise InvalidHeight("Provided height was higher than map height")
        
        # each array represents the columns of things around the position
        left = [self.map[z][x - 1][y] for z in range(z_space)] if x - 1 >= 0 and x - 1 < x_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        right = [self.map[z][x + 1][y] for z in range(z_space)] if x + 1 >= 0 and x + 1 < x_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        front = [self.map[z][x][y + 1] for z in range(z_space)] if y + 1 >= 0 and y + 1 < y_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        back = [self.map[z][x][y - 1] for z in range(z_space)] if y - 1 >= 0 and y - 1 < y_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]

        return {
            "front": front,
            "back": back,
            "left": left,
            "right": right
        }
    
    # advance the warehouse simulation by one step
    def step(self):
        for agent in self.agents:
            surroundings = self.get_surroundings(agent.position)

            agent.perceive(surroundings) # perceive the relevant part of the map
            agent.plan() # decide what to do
            agent.step() # execute the last decision made

        # emit an event to notify the client of
        # a step being completed
        self.ee.send_event("step_completed", [self.step_n])

        self.step_n += 1

        self.time_series.append((self.step_n, self.count_objects_floor()))

    def update_maps(self, position: tuple[int, int, int], v: Any):
        x, y, z = position
        self.static_map[z][x][y] = v
        self.map[z][x][y] = v

    def create_stats_graph(self):
        import matplotlib.pyplot as plt

        x = [t[0] for t in self.time_series]
        y = [t[1] for t in self.time_series]

        plt.plot(x, y)
        plt.xlabel("Steps")
        plt.ylabel("Objects in floor")
        plt.title("Objects in floor over time")
        plt.gca().yaxis.get_major_locator().set_params(integer=True)
        plt.savefig("global_stats.png")
        plt.close()

        # create a different graph using the .time_series property
        # of each agent but showing all agents in the same graph.
        # this time_series has the format (step, picked_objects)
        plt.figure(figsize=(10, 5))
        for agent in self.agents:
            x = [t[0] for t in agent.time_series]
            y = [t[1] for t in agent.time_series]
            plt.plot(x, y, label=f"Agent {agent.id[:6]}")
        
        plt.xlabel("Steps")
        plt.ylabel("Objects picked")
        plt.title("Objects picked over time")
        plt.gca().yaxis.get_major_locator().set_params(integer=True)
        plt.legend()
        plt.savefig("agent_stats.png")
        plt.close()

        # make an agent_efficiency.png graph. This can be a barchart
        # with the efficiency value of each agent.
        efficiencies = [(agent.id[:6], agent.move_count / agent.store_count) for agent in self.agents]
        agents, values = zip(*efficiencies)

        colors = plt.cm.get_cmap('tab10', len(agents))
        plt.bar(agents, values, color=[colors(i) for i in range(len(agents))])
        plt.xlabel("Agent")
        plt.ylabel("Efficiency")
        plt.title("Moves per object stored (Lower is better)")

        # Add efficiency values on top of each bar
        for i, value in enumerate(values):
            plt.text(i, value, f'{value:.2f}', ha='center', va='bottom')

        # Calculate and plot the average efficiency
        avg_efficiency = sum(values) / len(values)
        plt.axhline(y=avg_efficiency, color='r', linestyle='--', label=f'Average: {avg_efficiency:.2f}')
        plt.legend()

        plt.savefig("agent_efficiency.png")
        plt.close()
        
class AgentState(Enum):
    STANDBY = 1
    MOVING_TO_OBJECT = 2
    CARRYING_OBJECT = 3

class AgentAction(Enum):
    MOVE_FORWARD = 1
    ROTATE = 5
    WAIT = 6
    PICK_UP = 7
    STORE = 8
    CHANGE_STATE = 9

class Direction(Enum):
    FORWARD = 1
    RIGHT = 2
    BACKWARD = 3
    LEFT = 4

class Step():
    def __init__(self, action: AgentAction, params: dict[str, Any]):
        self.action = action
        self.params = params

class Agent():
    def __init__(self, warehouse: Warehouse, initial_position: tuple[int, int, int], n: int):
        self.map = copy(warehouse.static_map)
        self.initial_position = initial_position
        self.position = initial_position
        self.warehouse = warehouse
        self.state = AgentState.STANDBY
        self.planned_steps: list[Step] = []
        self.direction = Direction.FORWARD
        self.inventory: Object | None = None
        self.n = n
        self.id = str(uuid.uuid4())
        self.rotation = 0
        self.time_series: list[tuple[int, int]] = []
        self.store_count = 0
        self.move_count = 0

    # get the current perception at a given position, based on the 
    # current map the agent has
    def get_current_perception(self, position: tuple[int, int, int]):
        x, y, _ = position
        x_space, y_space, z_space = self.warehouse.dimensions

        if z_space > len(self.map):
            raise InvalidHeight("Provided height was higher than map height")
        
        # each array represents the columns of things around the position
        # there can be instances of 'Object', 'Storage' a 0 representing a
        # wall/limit and a 1 representing empty floor
        left = [self.map[z][x - 1][y] for z in range(z_space)] if x - 1 >= 0 and x - 1 < x_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        right = [self.map[z][x + 1][y] for z in range(z_space)] if x + 1 >= 0 and x + 1 < x_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        front = [self.map[z][x][y + 1] for z in range(z_space)] if y + 1 >= 0 and y + 1 < y_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]
        back = [self.map[z][x][y - 1] for z in range(z_space)] if y - 1 >= 0 and y - 1 < y_space else [SpaceState.OUT_OF_BOUNDS for _ in range(z_space)]

        return {
            "front": front,
            "back": back,
            "left": left,
            "right": right
        }

    # given new sensor data, compare the sensor data with expected data,
    # and update the map to match sensor data
    def perceive(self, surroundings: dict[str, list[SpaceState | Storage | Object, 'Agent']]):
        prev_surroundings = self.get_current_perception(self.position)

        current_left, previous_left = surroundings["left"], prev_surroundings["left"]
        current_right, previous_right = surroundings["right"], prev_surroundings["right"]
        current_front, previous_front = surroundings["front"], prev_surroundings["front"]
        current_back, previous_back = surroundings["back"], prev_surroundings["back"]

        _, _, z_space = self.warehouse.dimensions
        x, y, _ = self.position

        if current_left != previous_left:
            print(f"[A{self.id}] fixing left!")
            # we need to fix our perception at the left!
            for z in range(z_space):
                if current_left[z] != previous_left[z]:
                    # there should be no way this is out of bounds
                    if current_left[z] == SpaceState.OUT_OF_BOUNDS:
                        raise Exception("Unexpected out of bounds")
                    
                    # now we are absolutely sure, we update the map to the left
                    self.map[z][x - 1][y] = current_left[z]


        if current_right != previous_right:
            print(f"[A{self.id}] fixing right!")
            # we need to fix our perception at the right!
            for z in range(z_space):
                if current_right[z] != previous_right[z]:
                    # there should be no way this is out of bounds
                    if current_right[z] == SpaceState.OUT_OF_BOUNDS:
                        raise Exception("Unexpected out of bounds")
                    
                    # now we are absolutely sure, we update the map to the right
                    self.map[z][x + 1][y] = current_right[z]

        if current_front != previous_front:
            print(f"[A{self.id}] fixing front!")
            # we need to fix our perception at the front!
            for z in range(z_space):
                if current_front[z] != previous_front[z]:
                    # there should be no way this is out of bounds
                    if current_front[z] == SpaceState.OUT_OF_BOUNDS:
                        raise Exception("Unexpected out of bounds")
                    
                    # now we are absolutely sure, we update the map to the front
                    self.map[z][x][y + 1] = current_front[z]

        if current_back != previous_back:
            print(f"[A{self.id}] fixing back!")
            # we need to fix our perception at the back!
            for z in range(z_space):
                if current_back[z] != previous_back[z]:
                    # there should be no way this is out of bounds
                    if current_back[z] == SpaceState.OUT_OF_BOUNDS:
                        raise Exception("Unexpected out of bounds")
                    
                    # now we are absolutely sure, we update the map to the back
                    self.map[z][x][y - 1] = current_back[z]

        # at this point, all perceptions are fixed, and
        # map is up to date

    def plan(self):
        # this will use the available information
        # to make a plan or decision on what to do
        # this will depend on the current state of the agent
        print(f"Agent {self.id} is planning...")

        # if there are no planned steps
        if len(self.planned_steps) == 0:
            if self.state == AgentState.STANDBY:
                try:
                    path, object = self.get_path_to_object()
                except:
                    # we can probably safely exit?
                    self.planned_steps = [Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY }), Step(AgentAction.WAIT, None)]
                    return

                print("planning to go to object", object)
                print("path: ", path)

                initial_steps = [Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.MOVING_TO_OBJECT })]
                movement_steps = self.path_to_movement(path)
                pickup_steps = [
                    Step(AgentAction.PICK_UP, { "object": object }), # pick up the object
                    Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.CARRYING_OBJECT }) # change agent state to carrying object
                ]
                
                # set plan to be the combination of these steps
                # 1. change state to move to object
                # 2. move to object
                # 3. pickup object and set state to MOVING_OBJECT
                self.planned_steps = initial_steps + movement_steps + pickup_steps

                print("Planned steps")
                for step in self.planned_steps:
                    print(f"\t{step.action} - {step.params}")
            
            if self.state == AgentState.MOVING_TO_OBJECT:
                raise Exception("Invalid state. Agent should have at least one step if on this state")

            if self.state == AgentState.CARRYING_OBJECT:
                # check if path must be modified
                if self.inventory is None:
                    raise Exception("Invalid state. Agent should have an object in the inventory if on this state")

                path, storage = self.get_path_to_storage(self.inventory)

                print("Path to storage calculated:")
                print(path)
                print(storage)

                movement_steps = self.path_to_movement(path)
                store_steps = [
                    Step(AgentAction.STORE, { "storage": storage }),
                    Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY })
                ]

                # set the plan to be the combination of these steps
                # 1. Move to selected storage
                # 2. Store object and set new state to standby
                self.planned_steps = movement_steps + store_steps
                
                print("Planned steps")
                for step in self.planned_steps:
                    print(f"\t{step.action} - {step.params}")

            return # we have created an initial plan
    
        # this means there are planned steps, so we need to evaluate the next one
        # and make sure it is still possible
        next_step = self.planned_steps[0]
        
        if next_step.action == AgentAction.MOVE_FORWARD:
            feasible, reason = self.is_move_feasible(Direction.FORWARD)
            if feasible: return
            if isinstance(reason, Agent):
                # if an agent gets in the way wait random amount
                n = random.choice(range(5))
                wait_steps = [Step(AgentAction.WAIT, None) for _ in range(n)]

                self.planned_steps = []
                if self.state == AgentState.CARRYING_OBJECT:
                    print("Something went wrong, recalculating path to storage")
                    # check if path must be modified
                    if self.inventory is None:
                        raise Exception("Invalid state. Agent should have an object in the inventory if on this state")

                    path, storage = self.get_path_to_storage(self.inventory)

                    print("Path to storage calculated:")
                    print(path)
                    print(storage)

                    movement_steps = self.path_to_movement(path)
                    store_steps = [
                        Step(AgentAction.STORE, { "storage": storage }),
                        Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY })
                    ]

                    # set the plan to be the combination of these steps
                    # 1. Move to selected storage
                    # 2. Store object and set new state to standby
                    self.planned_steps = wait_steps + movement_steps + store_steps
                    
                    print("Planned steps")
                    for step in self.planned_steps:
                        print(f"\t{step.action} - {step.params}")
                    return

                if self.state == AgentState.MOVING_TO_OBJECT:
                    print("Something went wrong, recalculating path to object")
                    try:
                        path, object = self.get_path_to_object()
                    except:
                        # we can probably safely exit?
                        self.planned_steps = [Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY }), Step(AgentAction.WAIT, None)]
                        return

                    print("planning to go to object", object)
                    print("path: ", path)

                    movement_steps = self.path_to_movement(path)
                    pickup_steps = [
                        Step(AgentAction.PICK_UP, { "object": object }), # pick up the object
                        Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.CARRYING_OBJECT }) # change agent state to carrying object
                    ]
                    
                    # set plan to be the combination of these steps
                    # 2. move to object
                    # 3. pickup object and set state to MOVING_OBJECT
                    self.planned_steps = wait_steps + movement_steps + pickup_steps

                    print("Planned steps")
                    for step in self.planned_steps:
                        print(f"\t{step.action} - {step.params}")
                    return
            
            raise Exception("Unexpected error in MOVE_FORWARD:", reason)
        
        if next_step.action == AgentAction.PICK_UP:
            _, reason = self.is_move_feasible(Direction.FORWARD)
            if self.inventory is None and reason == next_step.params["object"]: return
            # at this point we pretty much just try another object
            self.planned_steps = []
            try:
                path, object = self.get_path_to_object()
            except:
                # we can probably safely exit?
                self.planned_steps = [Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY }), Step(AgentAction.WAIT, None)]
                return

            movement_steps = self.path_to_movement(path)
            pickup_steps = [
                Step(AgentAction.PICK_UP, { "object": object }), # pick up the object
                Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.CARRYING_OBJECT }) # change agent state to carrying object
            ]
            
            # set plan to be the combination of these steps
            # 1. change state to move to object
            # 2. move to object
            # 3. pickup object and set state to MOVING_OBJECT
            self.planned_steps = movement_steps + pickup_steps
            return

        
        if next_step.action == AgentAction.STORE:
            target_storage: Storage = next_step.params["storage"]
            _, reason = self.is_move_feasible(Direction.FORWARD, target_storage.location[2])
            if target_storage == reason and not target_storage.is_full(): return
            
            path, storage = self.get_path_to_storage(self.inventory)

            movement_steps = self.path_to_movement(path)
            store_steps = [
                Step(AgentAction.STORE, { "storage": storage }),
                Step(AgentAction.CHANGE_STATE, { "new_state": AgentState.STANDBY })
            ]

            # set the plan to be the combination of these steps
            # 1. Move to selected storage
            # 2. Store object and set new state to standby
            self.planned_steps = movement_steps + store_steps
            return


    def step(self):
        # this will execute the action at the top
        # of the agent's plan
        
        # handle all CHANGE_STATE events before executing        
        while self.planned_steps and self.planned_steps[0].action == AgentAction.CHANGE_STATE:
            step = self.planned_steps.pop(0)
            new_state = step.params["new_state"]
            self.state = new_state
            print("New agent state", self.state)

        if len(self.planned_steps) == 0:
            return # go to next iterations

        step = self.planned_steps.pop(0)

        print(f"[A{self.id}] Executing step", step.action, step.params)

        if step.action == AgentAction.MOVE_FORWARD:
            directions = {
                0: Direction.FORWARD,
                90: Direction.RIGHT,
                180: Direction.BACKWARD,
                270: Direction.LEFT, 
            }

            dir = directions[self.rotation]

            x, y, z = self.position

            if dir == Direction.FORWARD:
                # clear the space and update our position in the warehouse
                self.warehouse.map[0][x][y] = SpaceState.FREE_SPACE
                self.map[0][x][y] = SpaceState.FREE_SPACE
                self.warehouse.map[0][x][y + 1] = self
                
                # update the agent position (itself)
                self.position = (x, y + 1, z)
            
            if dir == Direction.RIGHT:
                # clear the space and update our position in the warehouse
                self.warehouse.map[0][x][y] = SpaceState.FREE_SPACE
                self.map[0][x][y] = SpaceState.FREE_SPACE
                self.warehouse.map[0][x + 1][y] = self
                
                # update the agent position (itself)
                self.position = (x + 1, y, z)

            if dir == Direction.BACKWARD:
                # clear the space and update our position in the warehouse
                self.warehouse.map[0][x][y] = SpaceState.FREE_SPACE
                self.map[0][x][y] = SpaceState.FREE_SPACE
                self.warehouse.map[0][x][y - 1] = self
                
                # update the agent position (itself)
                self.position = (x, y - 1, z)

            if dir == Direction.LEFT:
                # clear the space and update our position in the warehouse
                self.warehouse.map[0][x][y] = SpaceState.FREE_SPACE
                self.map[0][x][y] = SpaceState.FREE_SPACE
                self.warehouse.map[0][x - 1][y] = self
                
                # update the agent position (itself)
                self.position = (x - 1, y, z)

            self.warehouse.ee.send_event("forward", [self.id])
            self.move_count += 1
            return # FORWARD handled

        if step.action == AgentAction.PICK_UP:
            directions = {
                0: Direction.FORWARD,
                90: Direction.RIGHT,
                180: Direction.BACKWARD,
                270: Direction.LEFT, 
            }

            dir = directions[self.rotation]

            x, y, z = self.position

            if self.inventory is not None:
                raise Exception("Inventory was full and you tried to pickup an object")

            if dir == Direction.FORWARD:
                # get object reference, clear object space and store object in inventory
                obj = self.warehouse.map[0][x][y + 1]
                self.warehouse.map[0][x][y + 1] = SpaceState.FREE_SPACE
                self.map[0][x][y + 1] = SpaceState.FREE_SPACE
                self.inventory = obj
            
            if dir == Direction.RIGHT:
                # get object reference, clear object space and store object in inventory
                obj = self.warehouse.map[0][x + 1][y]
                self.warehouse.map[0][x + 1][y] = SpaceState.FREE_SPACE
                self.map[0][x + 1][y] = SpaceState.FREE_SPACE
                self.inventory = obj

            if dir == Direction.BACKWARD:
                # get object reference, clear object space and store object in inventory
                obj = self.warehouse.map[0][x][y - 1]
                self.warehouse.map[0][x][y - 1] = SpaceState.FREE_SPACE
                self.map[0][x][y - 1] = SpaceState.FREE_SPACE
                self.inventory = obj

            if dir == Direction.LEFT:
                # get object reference, clear object space and store object in inventory
                obj = self.warehouse.map[0][x - 1][y]
                self.warehouse.map[0][x - 1][y] = SpaceState.FREE_SPACE
                self.map[0][x - 1][y] = SpaceState.FREE_SPACE
                self.inventory = obj

            self.warehouse.ee.send_event("pickup", [self.id, obj.id, self.inventory.image_src.split(".")[0]] )
            return # PICK_UP handled
        
        if step.action == AgentAction.ROTATE:
            new_rotation = (self.rotation + step.params["degrees"] + 720) % 360
            self.rotation = new_rotation
            self.warehouse.ee.send_event("rotate", [self.id, step.params["degrees"]] )
            return
        
        if step.action == AgentAction.STORE:
            directions = {
                0: Direction.FORWARD,
                90: Direction.RIGHT,
                180: Direction.BACKWARD,
                270: Direction.LEFT, 
            }

            dir = directions[self.rotation]

            x, y, z = self.position

            if self.inventory is None:
                raise Exception("Inventory was empty and you tried to store an object")
            
            obj = self.inventory

            if dir == Direction.FORWARD:
                storage: Storage = step.params["storage"]
                if storage.is_full():
                    raise Exception("Storage is full")
                
                storage.store(obj)
                self.inventory = None
            
            if dir == Direction.RIGHT:
                storage: Storage = step.params["storage"]
                if storage.is_full():
                    raise Exception("Storage is full")
                
                storage.store(obj)
                self.inventory = None

            if dir == Direction.BACKWARD:
                storage: Storage = step.params["storage"]
                if storage.is_full():
                    raise Exception("Storage is full")
                
                storage.store(obj)
                self.inventory = None

            if dir == Direction.LEFT:
                storage: Storage = step.params["storage"]
                if storage.is_full():
                    raise Exception("Storage is full")
                
                storage.store(obj)
                self.inventory = None

            self.warehouse.ee.send_event("store", [self.id, obj.id, storage.id])

            self.store_count += 1
            self.time_series.append((self.warehouse.step_n, self.store_count))

            return # PICK_UP handled

        if step.action == AgentAction.WAIT:
            return # WAIT handled
        
        # handle all CHANGE_STATE events after executing
        while self.planned_steps and self.planned_steps[0].action == AgentAction.CHANGE_STATE:
            step = self.planned_steps.pop(0)
            new_state = step.params["new_state"]
            self.state = new_state
            print("New agent state", self.state)
        

    ## From here on out, all of these methods might be 
    ## specific to the actions that can be executed in step
    
    # function that finds a path to an object
    def get_path_to_object(self) -> tuple[list[tuple[int, int, int]], Object]:
        queue = []
        visited = set()
        
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # right, down, left, up

        initial_x, initial_y, _ = self.position
        initial_position = (initial_x, initial_y)

        queue.append(initial_position)
        visited.add(initial_position)

        floor_map = self.map[0]
        n, m, _ = self.warehouse.dimensions
        parents = {}

        def reconstruct_path(end: tuple[int, int]):
            path: list[tuple[int, int, int]] = []
            start = initial_position
            current = end
            while current != start:
                path.append((current[0], current[1], 0))
                current = parents[current]

            path.append((start[0], start[1], 0))  # Add the start position
            path.reverse()  # Reverse the path to go from start to end
            return path

        while queue:
            x, y = queue.pop(0)

            if isinstance(floor_map[x][y], Object):
                path = reconstruct_path((x, y))
                return path, floor_map[x][y]

            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < n and 0 <= ny < m and (nx, ny) not in visited:
                    if floor_map[nx][ny] == SpaceState.FREE_SPACE or isinstance(floor_map[nx][ny], Object):
                        queue.append((nx, ny))
                        visited.add((nx, ny))
                        parents[(nx, ny)] = (x, y)

        raise Exception("Path not found")

    def path_to_movement(self, path: list[tuple[int, int, int]]) -> list[Step]:
        current_rotation = self.rotation
        steps: list[Step] = []

        # function that calculates the rotation in degrees we need
        # to be facing in a global direction
        def calculate_rotation(dir: Direction):
            dir_to_angle = {
                Direction.FORWARD: 0,
                Direction.RIGHT: 90,
                Direction.BACKWARD: 180,
                Direction.LEFT: 270, 
            }

            new_angle = (dir_to_angle[dir] - current_rotation + 720) % 360

            return new_angle

        for i in range(len(path) - 1):
            a1, a2, _ = path[i + 1]
            b1, b2, _ = path[i]

            direction_delta = a1 - b1, a2 - b2

            delta_to_direction = {
                (1, 0): Direction.RIGHT,
                (-1, 0): Direction.LEFT,
                (0, 1): Direction.FORWARD,
                (0, -1): Direction.BACKWARD
            }

            if not direction_delta in delta_to_direction:
                raise Exception("Unexpected error while handling step generation")
            
            direction = delta_to_direction[direction_delta]
            rotation = calculate_rotation(direction)

            current_rotation = (current_rotation + rotation + 720) % 360

            if rotation != 0:
                steps.append(Step(AgentAction.ROTATE, { "degrees": rotation }))

            if i + 1 != len(path) - 1: # last iteration must not move forward
                steps.append(Step(AgentAction.MOVE_FORWARD, None))

        return steps

    def scan_object(self, object: Object) -> str:
        object_srcs = os.listdir("server/objects")
        object_names = [s.split(".")[0] for s in object_srcs]

        load_dotenv()

        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        image_path = os.path.join("server", "objects", object.image_src)
        base64_image = encode_image(image_path)

        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"You are a simple vision model. Your task is to see the image provided by the user and reply with the closest label on this list: {", ".join(object_names)}"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            model="gpt-4o-mini",
            max_completion_tokens=25,
            temperature=0.1,
        )

        maybe_response = completion.choices[0].message.content

        if maybe_response is None:
            raise Exception("Model response was empty")



        self.warehouse.ee.send_event("vision", [self.id, maybe_response])

        return maybe_response 

    def get_object_storage_location(self, external_key: str) -> Storage:
        object_srcs = os.listdir("server/objects")
        objects = len(object_srcs)
        spots = len(self.warehouse.storages)
        extras = spots % objects
        equals = (spots - extras) // objects

        counts = [0] * objects
        for i in range(objects):
            n = equals
            if extras != 0:
                extras -= 1
                n += 1
            counts[i] = n

        storage_map = {}
        start = 0
        for i, count in enumerate(counts):
            key = object_srcs[i].split(".")[0]
            storages = [self.warehouse.storages[j] for j in range(start, start + count)]
            start += count
            storage_map[key] = storages
            print("STORAGES: ", key)
            for s in storages:
                print("\t", s.location, s)


        suitable_storages = storage_map[external_key]
        for storage in suitable_storages:
            if not storage.is_full():
                return storage
            
        raise Exception("No space left")

    # function that finds a path to the place to store that object
    def get_path_to_storage(self, object: Object) -> tuple[list[tuple[int, int, int]], Storage]:
        key = self.scan_object(object)
        storage = self.get_object_storage_location(key)
        path_to_storage = self.calculate_path((storage.location[0], storage.location[1], 0))
        return path_to_storage, storage

    def calculate_path(self, target: tuple[int, int, int]) -> list[tuple[int, int, int]]:
        queue = []
        visited = set()

        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)] # right, down, left, up

        initial_x, initial_y, _ = self.position
        initial_position = (initial_x, initial_y)

        queue.append(initial_position)
        visited.add(initial_position)

        floor_map = self.map[0]
        n, m, _ = self.warehouse.dimensions
        parents = {}

        def reconstruct_path(end: tuple[int, int]):
            path: list[tuple[int, int, int]] = []
            start = initial_position
            current = end
            while current != start:
                path.append((current[0], current[1], 0))
                current = parents[current]

            path.append((start[0], start[1], 0))  # Add the start position
            path.reverse()  # Reverse the path to go from start to end
            return path
        
        while queue:
            x, y = queue.pop(0)

            if (x, y, 0) == target:
                path = reconstruct_path((x, y))
                return path

            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < n and 0 <= ny < m and (nx, ny) not in visited:
                    if floor_map[nx][ny] == SpaceState.FREE_SPACE or (nx, ny, 0) == target:
                        queue.append((nx, ny))
                        visited.add((nx, ny))
                        parents[(nx, ny)] = (x, y)

        raise Exception("Path not found")

    def is_move_feasible(self, move: Direction, z = 0):
        x, y, _ = self.position
        x_space, y_space, _ = self.warehouse.dimensions

        map = self.map[z]

        dir_to_angle = {
            Direction.FORWARD: 0,
            Direction.RIGHT: 90,
            Direction.BACKWARD: 180,
            Direction.LEFT: 270, 
        }

        angle_to_dir = {
            0: Direction.FORWARD,
            90: Direction.RIGHT,
            180: Direction.BACKWARD,
            270: Direction.LEFT, 
        }

        new_angle = (self.rotation + dir_to_angle[move] + 720) % 360
        move = angle_to_dir[new_angle]

        dx = 1 if move == Direction.RIGHT else -1 if move == Direction.LEFT else 0
        dy = 1 if move == Direction.FORWARD else -1 if move == Direction.BACKWARD else 0

        new_x, new_y = x + dx, y + dy

        if new_x >= 0 and new_x < x_space and new_y >= 0 and new_y < y_space:
            return map[new_x][new_y] == SpaceState.FREE_SPACE, map[new_x][new_y]

        return False, SpaceState.OUT_OF_BOUNDS    