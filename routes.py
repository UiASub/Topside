from flask import render_template, jsonify, Response, request, current_app
from lib.json_data_handler import JSONDataHandler
from lib.camera import init_camera, generate_frames, generate_rpi_frames

# Initialize required components
data_handler = JSONDataHandler()
config_handler = JSONDataHandler(file_path="data/config.json")
camera = init_camera()

# Default resource data (used when no telemetry received)
DEFAULT_RESOURCES = {
    "sequence": 0,
    "uptime_ms": 0,
    "cpu_percent": 0,
    "heap_used_percent": 0,
    "heap_free_kb": 0,
    "heap_total_kb": 0,
    "thread_count": 0,
    "udp_rx_count": 0,
    "udp_rx_errors": 0
}


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

    @app.route("/pilot")
    def pilot():
        """Render the pilot monitoring screen."""
        return render_template("pilot.html")

    @app.route("/debug")
    def debug():
        """Render the debug slider page."""
        return render_template("debug.html")

    @app.route("/graphs")
    def graphs():
        """Render the IMU graphs page."""
        return render_template("graphs.html")

    @app.route("/rpi_video_feed")
    def rpi_video_feed():
        """Return a streaming MJPEG response from the RPi camera."""
        rpi_cam = current_app.config.get("RPI_CAMERA")
        if rpi_cam is None:
            return "RPi camera not initialized", 503
        resp = Response(
            generate_rpi_frames(rpi_cam),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.route("/api/rpi_camera/status")
    def rpi_camera_status():
        """Return RPi camera connection status."""
        rpi_cam = current_app.config.get("RPI_CAMERA")
        if rpi_cam:
            if hasattr(rpi_cam, "get_status"):
                return jsonify(rpi_cam.get_status())
            return jsonify({"connected": rpi_cam.is_connected})
        return jsonify({"connected": False})

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
        """API route for IMU sensor data (yaw/pitch/roll)."""
        return jsonify(data_handler.get_section("imu"))

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

    @app.route("/api/resources", methods=["GET"])
    def get_resources():
        """API route for resource monitor data (CPU, memory, etc.)."""
        resources = data_handler.get_section("resources")
        if resources is None:
            return jsonify(DEFAULT_RESOURCES)
        return jsonify(resources)

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

    @app.route("/api/imu/status", methods=["GET"])
    def get_imu_status():
        """API route for IMU receiver statistics."""
        imu = current_app.config.get("IMU")
        if imu:
            return jsonify({"ok": True, "stats": imu.get_stats()})
        return jsonify({"ok": False, "error": "IMU receiver not running"})

    @app.route("/api/imu/tare", methods=["POST"])
    def imu_tare():
        """Set current IMU orientation as zero reference."""
        imu = current_app.config.get("IMU")
        if not imu:
            return jsonify({"ok": False, "error": "IMU receiver not running"}), 503
        imu.tare()
        return jsonify({"ok": True, "tare_offset": imu.get_stats()["tare_offset"]})

    @app.route("/api/imu/tare", methods=["DELETE"])
    def imu_clear_tare():
        """Clear the tare offset."""
        imu = current_app.config.get("IMU")
        if not imu:
            return jsonify({"ok": False, "error": "IMU receiver not running"}), 503
        imu.clear_tare()
        return jsonify({"ok": True})

    @app.route("/api/imu/offset", methods=["GET"])
    def get_imu_offset():
        """Get IMU mass center offset (X, Y, Z in mm)."""
        offset = config_handler.get_section("imu_offset")
        if not offset:
            offset = {"x": 0.0, "y": 0.0, "z": 0.0}
        return jsonify({"ok": True, "offset": offset})

    @app.route("/api/imu/offset", methods=["POST"])
    def set_imu_offset():
        """Set IMU mass center offset. JSON: {x, y, z} in mm."""
        data = request.get_json(force=True, silent=True) or {}
        offset = config_handler.get_section("imu_offset") or {"x": 0.0, "y": 0.0, "z": 0.0}
        for axis in ("x", "y", "z"):
            if axis in data:
                offset[axis] = round(float(data[axis]), 1)
        config_handler.update_data({"imu_offset": offset})
        return jsonify({"ok": True, "offset": offset})

    @app.route("/api/imu/axes", methods=["GET"])
    def get_imu_axes():
        """Get IMU axis mapping. Each ROV axis maps to a sensor output with sign."""
        axes = config_handler.get_section("imu_axes")
        if not axes:
            axes = {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}
        return jsonify({"ok": True, "axes": axes})

    @app.route("/api/imu/axes", methods=["POST"])
    def set_imu_axes():
        """Set IMU axis mapping. JSON: {yaw, pitch, roll} each like '+yaw','-pitch', etc."""
        data = request.get_json(force=True, silent=True) or {}
        axes = config_handler.get_section("imu_axes") or {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}
        valid = {"+yaw", "-yaw", "+pitch", "-pitch", "+roll", "-roll"}
        for key in ("yaw", "pitch", "roll"):
            if key in data and data[key] in valid:
                axes[key] = data[key]
        config_handler.update_data({"imu_axes": axes})
        # Update the receiver's axis mapping
        imu = current_app.config.get("IMU")
        if imu:
            imu.set_axis_mapping(axes)
        return jsonify({"ok": True, "axes": axes})

    # --- Debug override endpoints ---
    @app.route("/api/debug/override", methods=["POST"])
    def debug_override():
        """Set debug override axes. Expects JSON with surge,sway,heave,roll,pitch,yaw in [-1..1]."""
        data = request.get_json(force=True, silent=True) or {}
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        axes = {}
        for key in ("surge", "sway", "heave", "roll", "pitch", "yaw"):
            if key in data:
                axes[key] = max(-1.0, min(1.0, float(data[key])))
        ctrl.set_debug_override(axes)
        return jsonify({"ok": True, "override": axes})

    @app.route("/api/debug/clear", methods=["POST"])
    def debug_clear():
        """Clear debug override; return control to physical controller."""
        ctrl = current_app.config.get("CONTROLLER")
        if ctrl:
            ctrl.clear_debug_override()
        return jsonify({"ok": True})

    # --- Gain endpoints ---
    @app.route("/api/controller/gains", methods=["GET"])
    def get_gains():
        """Return current gain settings."""
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        return jsonify({"ok": True, "gains": ctrl.get_gains()})

    @app.route("/api/controller/gains", methods=["POST"])
    def set_gains():
        """Set gain values. JSON body: master (0-1), surge, sway, heave, roll, pitch, yaw (0-1)."""
        data = request.get_json(force=True, silent=True) or {}
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        master = data.get("master")
        axis_gains = {k: float(data[k]) for k in ("surge", "sway", "heave", "roll", "pitch", "yaw") if k in data}
        ctrl.set_gains(master=master, **axis_gains)
        return jsonify({"ok": True, "gains": ctrl.get_gains()})