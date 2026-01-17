from flask import render_template, jsonify, Response, request, current_app
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

    @app.route("/api/rov/command", methods=["POST"])
    def set_rov_command():
        """
        JSON body: any subset of
        surge,sway,heave,roll,pitch,yaw ([-128..127]), light,manip ([0..255])
        or normalized axes in [-1..1] via "axes": and optional "rate_hz"
        """
        data = request.get_json(force=True, silent=True) or {}
        bm = current_app.config["BITMASK"]

        # allow normalized axes
        axes = data.get("axes")
        if isinstance(axes, dict):
            bm.set_from_axes(**axes)

        # allow raw fields
        allowed = {"surge","sway","heave","roll","pitch","yaw","light","manip"}
        raw = {k:int(v) for k,v in data.items() if k in allowed}
        if raw:
            bm.set_command(**raw)

        # optional live rate change
        if "rate_hz" in data:
            try:
                rate = float(data["rate_hz"])
                bm.period = 1.0 / rate if rate > 0 else 0.0
            except Exception:
                pass

        return jsonify({"ok": True, "now": bm.get_command()})

    @app.route("/api/rov/status", methods=["GET"])
    def get_rov_status():
        bm = current_app.config["BITMASK"]
        return jsonify({"ok": True, "command": bm.get_command()})

    @app.route("/api/9dof/status", methods=["GET"])
    def get_ninedof_status():
        """API route for 9DOF receiver statistics."""
        ninedof = current_app.config.get("NINEDOF")
        if ninedof:
            return jsonify({"ok": True, "stats": ninedof.get_stats()})
        return jsonify({"ok": False, "error": "9DOF receiver not running"})