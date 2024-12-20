from typing import Callable, Any
import socket
import json
import threading
from queue import Queue

class MockEmitter():
    def __init__(self):
        self.event_queues: dict[str, Queue] = {}

    def register_event_type(self, type: str):
        """Register a new event type with its own queue"""
        if type not in self.event_queues:
            self.event_queues[type] = Queue()

    def get_event(self, type: str) -> str:
        """Get the next event of the specified type from its queue"""
        if type not in self.event_queues:
            self.register_event_type(type)
        
        return self.event_queues[type].get_nowait()

    def check_event(self, type: str) -> bool:
        """Check if there are events available without removing them from the queue"""
        if type not in self.event_queues:
            self.register_event_type(type)
        
        return not self.event_queues[type].empty()

    def send_event(self, type: str, data: list[str]):
        """
        Send an event through the queue system.
        Args:
            type: Event type identifier
            data: List of strings to be joined with commas
        """
        if type not in self.event_queues:
            self.register_event_type(type)
            
        self.event_queues[type].put(",".join(data))

    def close(self):
        pass

class EventEmitter():
    def __init__(self, port=65432, host="localhost"):
        self.event_queues: dict[str, Queue] = {}
        self.running = True
        # Configura el socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((host, port))
        self.sock.listen()

        print("Esperando conexión...")
        self.conn, self.addr = self.sock.accept()

        if self.conn:
            print('Conectado por', self.addr)
            # Start event handling thread
            self.event_thread = threading.Thread(target=self.handle_events)
            self.event_thread.daemon = True
            self.event_thread.start()

    def register_event_type(self, type: str):
        """Register a new event type with its own queue"""
        if type not in self.event_queues:
            self.event_queues[type] = Queue()

    def get_event(self, type: str) -> str:
        """Get the next event of the specified type from its queue"""
        if type not in self.event_queues:
            self.register_event_type(type)
        
        return self.event_queues[type].get_nowait()

    def check_event(self, type: str) -> bool:
        """Check if there are events available without removing them from the queue"""
        if type not in self.event_queues:
            self.register_event_type(type)
        
        return not self.event_queues[type].empty()

    def send_event(self, type: str, data: list[str]):
        """
        Send an event through current TCP connection.
        Args:
            type: Event type identifier
            data: List of strings to be joined with commas
        """
        event = {
            "type": type,
            "data": ",".join(data)
        }

        message = json.dumps(event) + "\n"
        self.conn.sendall(message.encode('utf-8'))

    def handle_events(self):
        """Listen for and handle incoming events."""
        buffer = ""  # Accumulate partial data here
        while self.running:
            try:
                # Read data from the connection
                data = self.conn.recv(1024).decode('utf-8')
                if not data:
                    continue

                # Append incoming data to the buffer
                buffer += data

                # Process complete messages in the buffer
                while '\n' in buffer:
                    # Extract the first complete message
                    message, buffer = buffer.split('\n', 1)
                    try:
                        event = json.loads(message)
                        event_type = event.get('type')
                        event_data = event.get('data')

                        # Add event to the appropriate queue
                        if event_type not in self.event_queues:
                            self.register_event_type(event_type)
                        
                        self.event_queues[event_type].put(event_data)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON received")
            except Exception as e:
                if self.running:
                    print(f"Error handling events: {e}")


    def close(self):
        self.running = False
        self.sock.close()
        self.conn.close()