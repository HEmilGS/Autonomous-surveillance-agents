from ee import EventEmitter

class Camera():
    def __init__(self, server: EventEmitter):
        self.server = server
        server.register_handler("camera_shot", self.handle_receive_image)

    def check_for_images(self):
        """Check if there are any new images available"""
        images: list[str] = []

        while self.server.check_event("camera_shot"):
            im = self.server.get_event("camera_shot")
            images.append(im)
