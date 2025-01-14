from flask import render_template, jsonify, Response
from lib.json_data_handler import JSONDataHandler
from lib.camera import init_camera, generate_frames

# Initialize required components
data_handler = JSONDataHandler()
camera = init_camera()

def register_routes(app):

    @app.route("/")
    def dashboard():
        """Serve the main dashboard."""
        return render_template("layout.html")

    @app.route("/Camera1")
    def camera1():
        """Render the camera1.html template."""
        return render_template("camera1.html")

    @app.route("/Camera2")
    def camera2():
        """Render the camera2.html template."""
        return render_template("camera2.html")

    @app.route("/video_feed")
    def video_feed():
        """Return a streaming MJPEG response from the camera."""
        return Response(
            generate_frames(camera),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/api/thrusters", methods=["GET"])
    def get_thrusters():
        """API route for thrusters data."""
        return jsonify(data_handler.get_section("thrusters"))

    @app.route("/api/sensors", methods=["GET"])
    def get_sensors():
        """API route for sensor data."""
        return jsonify(data_handler.get_section("9dof"))

    @app.route("/api/lights", methods=["GET"])
    def get_lights():
        """API route for lights data."""
        return jsonify(data_handler.get_section("lights"))

    @app.route("/api/battery", methods=["GET"])
    def get_battery():
        """API route for battery status."""
        return jsonify({"battery": data_handler.get_section("battery")})

    @app.route("/api/depth", methods=["GET"])
    def get_depth():
        """API route for depth data."""
        return jsonify(data_handler.get_section("depth"))
