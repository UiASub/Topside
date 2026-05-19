import json
import math
import re
from pathlib import Path

from flask import Response, current_app, jsonify, render_template, request, send_from_directory

from lib.axis_config_sender import send_axis_config
from lib.camera import generate_frames, generate_ip_camera_frames, generate_rpi_frames
from lib.json_data_handler import JSONDataHandler
from lib.pid_config_client import AXES as PID_AXES
from lib.pid_config_client import request_pid_gains, send_pid_gains
from lib.runtime_paths import data_path

PID_CONFIGS_FILE = data_path("pid_configs.json")
PROJECT_ROOT = Path(__file__).resolve().parent


def _load_pid_configs():
    if PID_CONFIGS_FILE.exists():
        with open(PID_CONFIGS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_pid_configs(configs):
    PID_CONFIGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_CONFIGS_FILE, "w") as f:
        json.dump(configs, f, indent=2)


# Initialize required components
data_handler = JSONDataHandler()
config_handler = JSONDataHandler(file_path=data_path("config.json"))

# Defaults for axis configs
_DEFAULT_IMU_AXES = {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}
_DEFAULT_ACCEL_AXES = {"x": "+x", "y": "+y", "z": "+z"}
_DEFAULT_OFFSET = {"x": 0.0, "y": 0.0, "z": 0.0}
ATTITUDE_LIMITS_DEG = {"roll": 180.0, "pitch": 90.0, "yaw": 180.0}
CONTROL_AXES = ("surge", "sway", "heave", "roll", "pitch", "yaw")
ATTITUDE_AXES = ("roll", "pitch", "yaw")


def _clamp(value, lower, upper):
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _normalize_angle_deg(value):
    wrapped = ((float(value) + 180.0) % 360.0) - 180.0
    if wrapped == -180.0 and float(value) > 0:
        return 180.0
    return wrapped


def _neutral_axis_values():
    return {axis: 0.0 for axis in CONTROL_AXES}


def _zero_pid_gains():
    return {axis: {"kp": 0.0, "ki": 0.0, "kd": 0.0} for axis in PID_AXES}


def _coerce_attitude_setpoints(data):
    axes = {}
    for axis in ATTITUDE_AXES:
        if axis not in data:
            continue
        try:
            value = float(data[axis])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        limit = ATTITUDE_LIMITS_DEG[axis]
        if axis in ("roll", "yaw"):
            value = _normalize_angle_deg(value)
        axes[axis] = _clamp(value, -limit, limit)
    return axes


def _neutralize_thruster_command():
    """Force topside manual command output to neutral axes."""
    neutral = _neutral_axis_values()
    ctrl = current_app.config.get("CONTROLLER")
    if ctrl:
        ctrl.set_debug_override(neutral)
    bm = current_app.config.get("BITMASK")
    if bm:
        bm.set_from_axes(**neutral)
    return neutral


def _send_full_axis_config():
    """Read all axis settings from config and send to MCU in one packet."""
    imu_axes = config_handler.get_section("imu_axes") or _DEFAULT_IMU_AXES
    accel_axes = config_handler.get_section("accel_axes") or _DEFAULT_ACCEL_AXES
    offset = config_handler.get_section("imu_offset") or _DEFAULT_OFFSET
    send_axis_config(imu_axes=imu_axes, accel_axes=accel_axes, offset=offset)


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
    "udp_rx_errors": 0,
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
        return render_template("debug.html", attitude_limits=ATTITUDE_LIMITS_DEG)

    @app.route("/pid-tuning")
    def pid_tuning():
        """Render the PID tuning page."""
        return render_template("pid_tuning.html", attitude_limits=ATTITUDE_LIMITS_DEG)

    @app.route("/graphs")
    def graphs():
        """Render the IMU graphs page."""
        return render_template("graphs.html")

    @app.route("/docs")
    def api_documentation():
        """Render the interactive API documentation."""
        return render_template("swagger_docs.html")

    @app.route("/docs/swagger.yml")
    def api_spec():
        """Serve the Swagger specification."""
        docs_dir = PROJECT_ROOT / "docs"
        return send_from_directory(docs_dir, "swagger.yml", mimetype="application/yaml")

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
        default_cam = current_app.config.get("DEFAULT_CAMERA")
        if default_cam is None:
            return "Default camera not initialized", 503
        resp = Response(
            generate_frames(default_cam),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.route("/api/camera/status")
    def camera_status():
        """Return default camera connection status."""
        default_cam = current_app.config.get("DEFAULT_CAMERA")
        if default_cam:
            return jsonify(default_cam.get_status())
        return jsonify({"connected": False, "listening": False})

    @app.route("/ip_video_feed")
    def ip_video_feed():
        """Return a streaming MJPEG response from the IP camera."""
        ip_cam = current_app.config.get("IP_CAMERA")
        if ip_cam is None:
            return "IP camera not initialized", 503
        resp = Response(
            generate_ip_camera_frames(ip_cam),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.route("/api/ip_camera/status")
    def ip_camera_status():
        """Return IP camera connection status."""
        ip_cam = current_app.config.get("IP_CAMERA")
        if ip_cam:
            return jsonify(ip_cam.get_status())
        return jsonify({"connected": False})

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

    @app.route("/api/command/status", methods=["GET"])
    def get_command_status():
        bm = current_app.config.get("BITMASK")
        resource = current_app.config.get("RESOURCE")
        override = current_app.config.get("SETPOINT_OVERRIDE")
        controller = current_app.config.get("CONTROLLER")
        uplink = bm.get_uplink_status() if bm else {}
        udp_rx, udp_err = resource.get_udp_counters() if resource else (0, 0)
        state = override.get_state() if override else {}
        controller_state = controller.get_input_status() if controller else {}
        return jsonify(
            {
                "ok": True,
                "uplink": uplink,
                "controller": controller_state,
                "udp_rx_count": udp_rx,
                "udp_rx_errors": udp_err,
                "override": state,
            }
        )

    @app.route("/api/control/telemetry", methods=["GET"])
    def control_telemetry():
        receiver = current_app.config.get("CONTROL_TELEM")
        latest = receiver.get_latest() if receiver else data_handler.get_section("control_telemetry")
        return jsonify({"ok": bool(latest), "telemetry": latest or {}})

    @app.route("/api/control/telemetry/history", methods=["GET"])
    def control_telemetry_history():
        receiver = current_app.config.get("CONTROL_TELEM")
        limit = int(request.args.get("limit", "120"))
        if receiver:
            history = receiver.get_history(limit=limit)
            return jsonify({"ok": True, "history": history})
        return jsonify({"ok": False, "history": []}), 503

    @app.route("/api/logs/live", methods=["GET"])
    def live_logs():
        limit = int(request.args.get("limit", "100"))
        limit = max(1, min(500, limit))
        log_stream = current_app.config.get("LOG_STREAM")
        entries = log_stream.get_recent(limit) if log_stream else []
        return jsonify({"ok": True, "logs": entries})

    @app.route("/api/system/reset", methods=["POST"])
    def system_reset():
        client = current_app.config.get("SYSTEM_CONTROL")
        if not client:
            return jsonify({"ok": False, "error": "System control client unavailable"}), 503
        try:
            result = client.send_reset()
        except Exception as exc:  # pylint: disable=broad-except
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, "reset": result})

    @app.route("/api/setpoint/status", methods=["GET"])
    def setpoint_status():
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if not client:
            return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
        return jsonify({"ok": True, "state": client.get_state()})

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
        allowed = {"surge", "sway", "heave", "roll", "pitch", "yaw", "light", "manip"}
        raw = {k: int(v) for k, v in data.items() if k in allowed}
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
        resource = current_app.config.get("RESOURCE")
        udp_rx, udp_err = resource.get_udp_counters() if resource else (0, 0)
        return jsonify(
            {
                "ok": True,
                "command": bm.get_command(),
                "uplink": bm.get_uplink_status(),
                "resource": {
                    "udp_rx_count": udp_rx,
                    "udp_rx_errors": udp_err,
                },
            }
        )

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
        # Send updated offset to microcontroller for centripetal compensation
        _send_full_axis_config()
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
        # Update the receiver's axis mapping (topside display)
        imu = current_app.config.get("IMU")
        if imu:
            imu.set_axis_mapping(axes)
        # Send full config to microcontroller so PID uses correct orientation
        _send_full_axis_config()
        return jsonify({"ok": True, "axes": axes})

    @app.route("/api/imu/accel_axes", methods=["GET"])
    def get_accel_axes():
        """Get accelerometer axis mapping. Each ROV axis maps to a sensor output with sign."""
        axes = config_handler.get_section("accel_axes")
        if not axes:
            axes = {"x": "+x", "y": "+y", "z": "+z"}
        return jsonify({"ok": True, "accel_axes": axes})

    @app.route("/api/imu/accel_axes", methods=["POST"])
    def set_accel_axes():
        """Set accelerometer axis mapping. JSON: {x, y, z} each like '+x','-y', etc."""
        data = request.get_json(force=True, silent=True) or {}
        axes = config_handler.get_section("accel_axes") or {"x": "+x", "y": "+y", "z": "+z"}
        valid = {"+x", "-x", "+y", "-y", "+z", "-z"}
        for key in ("x", "y", "z"):
            if key in data and data[key] in valid:
                axes[key] = data[key]
        config_handler.update_data({"accel_axes": axes})
        # Update the receiver's accel mapping (topside display)
        imu = current_app.config.get("IMU")
        if imu:
            imu.set_accel_mapping(axes)
        # Send full config to microcontroller
        _send_full_axis_config()
        return jsonify({"ok": True, "accel_axes": axes})

    # --- Debug override endpoints ---
    @app.route("/api/debug/override", methods=["POST"])
    def debug_override():
        """Set debug override axes as raw virtual joystick input via the bitmask command link."""
        data = request.get_json(force=True, silent=True) or {}
        bm = current_app.config.get("BITMASK")
        if not bm:
            return jsonify({"ok": False, "error": "Bitmask client unavailable"}), 503
        axes = {}
        for key in ("surge", "sway", "heave", "roll", "pitch", "yaw"):
            if key in data:
                value = max(-1.0, min(1.0, float(data[key])))
                axes[key] = -value if key == "yaw" else value
        if not axes:
            return jsonify({"ok": False, "error": "No axes supplied"}), 400

        bm.set_from_axes(**axes)

        ctrl = current_app.config.get("CONTROLLER")
        if ctrl:
            ctrl.set_debug_override(axes)

        return jsonify({"ok": True, "override": axes})

    @app.route("/api/debug/attitude_setpoint", methods=["POST"])
    def debug_attitude_setpoint():
        """Send roll/pitch/yaw setpoints in physical degrees via the override client."""
        data = request.get_json(force=True, silent=True) or {}
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if not client:
            return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
        axes = _coerce_attitude_setpoints(data)
        if not axes:
            return jsonify({"ok": False, "error": "No valid attitude axes supplied"}), 400
        try:
            state = client.send_override(axes, replay_attempts=5, replay_delay=0.1)
        except Exception as exc:  # pylint: disable=broad-except
            client.set_error(str(exc))
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify(
            {
                "ok": True,
                "sent": axes,
                "limits": ATTITUDE_LIMITS_DEG,
                "state": state,
                "units": "deg",
            }
        )

    @app.route("/api/debug/clear", methods=["POST"])
    def debug_clear():
        """Clear debug override; return control to physical controller."""
        ctrl = current_app.config.get("CONTROLLER")
        if ctrl:
            ctrl.clear_debug_override()

        # Zero out the bitmask axes (slider override path)
        bm = current_app.config.get("BITMASK")
        if bm:
            bm.set_from_axes(surge=0, sway=0, heave=0, roll=0, pitch=0, yaw=0)

        # Clear any setpoint override on port 5007 (attitude override path)
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                client.clear_override()
            except Exception:
                pass

        return jsonify({"ok": True})

    @app.route("/api/pid/start", methods=["POST"])
    def start_pid_hold():
        """Start PID tuning from the current attitude and neutral manual command axes."""
        imu = current_app.config.get("IMU")
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if not imu:
            return jsonify({"ok": False, "error": "IMU receiver not running"}), 503
        if not client:
            return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503

        stats = imu.get_stats()
        age_ms = stats.get("age_ms")
        if age_ms is None or age_ms > 2000:
            return jsonify({"ok": False, "error": "IMU data is stale; PID start was blocked"}), 503

        attitude = stats.get("last_data") or {}
        try:
            attitude_setpoints = _coerce_attitude_setpoints({axis: float(attitude[axis]) for axis in ATTITUDE_AXES})
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "error": "Current attitude is incomplete"}), 503
        if len(attitude_setpoints) != len(ATTITUDE_AXES):
            return jsonify({"ok": False, "error": "Current attitude is incomplete"}), 503

        neutral = _neutralize_thruster_command()
        setpoints = {**neutral, **attitude_setpoints}
        try:
            client.clear_override()
            state = client.send_override(setpoints, replay_attempts=5, replay_delay=0.1)
        except Exception as exc:  # pylint: disable=broad-except
            client.set_error(str(exc))
            return jsonify({"ok": False, "error": str(exc), "neutralized": True}), 503

        return jsonify(
            {
                "ok": True,
                "setpoints": setpoints,
                "state": state,
                "neutralized": True,
                "units": "deg",
            }
        )

    @app.route("/api/pid/setpoints", methods=["POST"])
    def set_pid_attitude_setpoints():
        """Send roll/pitch/yaw PID attitude setpoints in VN-100 degrees."""
        data = request.get_json(force=True, silent=True) or {}
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if not client:
            return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
        axes = _coerce_attitude_setpoints(data)
        if not axes:
            return jsonify({"ok": False, "error": "No valid attitude setpoints supplied"}), 400
        try:
            state = client.send_override(axes, replay_attempts=5, replay_delay=0.1)
        except Exception as exc:  # pylint: disable=broad-except
            client.set_error(str(exc))
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify(
            {
                "ok": True,
                "sent": axes,
                "limits": ATTITUDE_LIMITS_DEG,
                "state": state,
                "units": "deg",
            }
        )

    @app.route("/api/pid/zero_all", methods=["POST"])
    def zero_all_pid():
        """Force neutral manual command axes and send zero PID gains to the MCU."""
        neutral = _neutralize_thruster_command()
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                client.clear_override()
            except Exception:
                pass

        zeros = _zero_pid_gains()
        confirmed, attempts = send_pid_gains(zeros, timeout=1.0, max_retries=3)
        if confirmed is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Thruster axes neutralized, but no PID zero confirmation from MCU after %d attempts"
                        % attempts,
                        "neutralized": True,
                        "override": neutral,
                    }
                ),
                504,
            )
        return jsonify(
            {
                "ok": True,
                "gains": confirmed,
                "attempts": attempts,
                "neutralized": True,
                "override": neutral,
            }
        )

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

    # --- PID config (MCU) endpoints ---
    @app.route("/api/pid/gains", methods=["GET"])
    def get_pid_gains():
        """Request current PID gains from the MCU via UDP."""
        gains = request_pid_gains(timeout=2.0)
        if gains is None:
            return jsonify({"ok": False, "error": "No response from MCU"}), 504
        return jsonify({"ok": True, "gains": gains})

    @app.route("/api/pid/gains", methods=["POST"])
    def set_pid_gains():
        """Send PID gains to the MCU via UDP. Expects JSON: {axis: {kp, ki, kd}, ...}."""
        data = request.get_json(force=True, silent=True) or {}
        gains = {}
        for axis in PID_AXES:
            if axis in data and isinstance(data[axis], dict):
                gains[axis] = {
                    "kp": float(data[axis].get("kp", 0.0)),
                    "ki": float(data[axis].get("ki", 0.0)),
                    "kd": float(data[axis].get("kd", 0.0)),
                }
            else:
                gains[axis] = {"kp": 0.0, "ki": 0.0, "kd": 0.0}
        confirmed, attempts = send_pid_gains(gains, timeout=1.0, max_retries=3)
        if confirmed is None:
            return jsonify({"ok": False, "error": "No response from MCU after %d attempts" % attempts}), 504
        return jsonify({"ok": True, "gains": confirmed, "attempts": attempts})

    # --- PID config save/load ---
    @app.route("/api/pid/configs", methods=["GET"])
    def list_pid_configs():
        """List all saved PID configurations."""
        configs = _load_pid_configs()
        return jsonify({"ok": True, "configs": list(configs.keys())})

    @app.route("/api/pid/configs", methods=["POST"])
    def save_pid_config():
        """Save current PID fields as a named configuration."""
        data = request.get_json(force=True, silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name or not re.match(r"^[\w\s\-\.]+$", name):
            return jsonify({"ok": False, "error": "Invalid config name"}), 400
        gains = data.get("gains")
        if not isinstance(gains, dict):
            return jsonify({"ok": False, "error": "Missing gains data"}), 400
        configs = _load_pid_configs()
        configs[name] = gains
        _save_pid_configs(configs)
        return jsonify({"ok": True, "name": name})

    @app.route("/api/pid/configs/<name>", methods=["GET"])
    def load_pid_config(name):
        """Load a saved PID configuration by name."""
        configs = _load_pid_configs()
        if name not in configs:
            return jsonify({"ok": False, "error": "Config not found"}), 404
        return jsonify({"ok": True, "name": name, "gains": configs[name]})

    @app.route("/api/pid/configs/<name>", methods=["DELETE"])
    def delete_pid_config(name):
        """Delete a saved PID configuration."""
        configs = _load_pid_configs()
        if name not in configs:
            return jsonify({"ok": False, "error": "Config not found"}), 404
        del configs[name]
        _save_pid_configs(configs)
        return jsonify({"ok": True})
