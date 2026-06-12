import ipaddress
import json
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Response, current_app, jsonify, render_template, request, send_from_directory

from lib.axis_config_sender import send_axis_config
from lib.camera import generate_frames, generate_ip_camera_frames, generate_rpi_frames, init_ip_camera
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
TRANSLATIONAL_AXES = ("surge", "sway", "heave")
ATTITUDE_AXES = ("roll", "pitch", "yaw")
DEFAULT_PID_SETPOINT_RATES = {axis: 90.0 for axis in ATTITUDE_AXES}
DEFAULT_IP_CAMERA_IP = "10.77.0.4"


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


def _attitude_pid_gains(gains):
    return {axis: gains.get(axis, {"kp": 0.0, "ki": 0.0, "kd": 0.0}) for axis in ATTITUDE_AXES}


def _mcu_pid_gains(gains):
    packet = _zero_pid_gains()
    for axis in ATTITUDE_AXES:
        axis_gains = gains.get(axis, {}) if isinstance(gains, dict) else {}
        cleaned = {}
        for key in ("kp", "ki", "kd"):
            try:
                cleaned[key] = float(axis_gains.get(key, 0.0))
            except (AttributeError, TypeError, ValueError):
                cleaned[key] = 0.0
        packet[axis] = {
            "kp": cleaned["kp"],
            "ki": cleaned["ki"],
            "kd": cleaned["kd"],
        }
    return packet


def _clean_pid_rates(data):
    rates = {}
    for axis in ATTITUDE_AXES:
        try:
            value = float(data.get(axis, DEFAULT_PID_SETPOINT_RATES[axis]))
        except (AttributeError, TypeError, ValueError):
            value = DEFAULT_PID_SETPOINT_RATES[axis]
        if not math.isfinite(value):
            value = DEFAULT_PID_SETPOINT_RATES[axis]
        rates[axis] = _clamp(value, 0.0, 90.0)
    return rates


def _load_pid_rates():
    return _clean_pid_rates(config_handler.get_section("pid_setpoint_rates") or {})


def _save_pid_rates(rates):
    cleaned = _clean_pid_rates(rates)
    config_handler.update_data({"pid_setpoint_rates": cleaned})
    ctrl = current_app.config.get("CONTROLLER")
    if ctrl and hasattr(ctrl, "set_pid_rates"):
        ctrl.set_pid_rates(cleaned)
    return cleaned


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


def _imu_attitude_sanity(stats):
    age_ms = stats.get("age_ms")
    raw = stats.get("last_data") or {}
    reasons = []
    numeric = {}

    if age_ms is None:
        reasons.append("IMU data is missing")
    elif age_ms > 2000:
        reasons.append("IMU data is stale")

    for axis in ATTITUDE_AXES:
        value = raw.get(axis)
        try:
            value = float(value)
        except (TypeError, ValueError):
            reasons.append(f"{axis} is missing or not numeric")
            continue
        if not math.isfinite(value):
            reasons.append(f"{axis} is NaN or infinite")
            continue
        limit = ATTITUDE_LIMITS_DEG[axis]
        if value < -limit or value > limit:
            reasons.append(f"{axis} is outside -{limit:.0f}..{limit:.0f}")
        numeric[axis] = value

    setpoints = _coerce_attitude_setpoints(numeric)
    usable = len(setpoints) == len(ATTITUDE_AXES)
    return {
        "ok": usable and not reasons,
        "usable": usable,
        "reason": "; ".join(reasons),
        "raw": raw,
        "age_ms": age_ms,
        "setpoints": setpoints,
    }


def _send_active_pid_setpoints(ctrl, client):
    setpoints = ctrl.get_pid_setpoints() if ctrl and hasattr(ctrl, "get_pid_setpoints") else {}
    if not client:
        return {}
    client.clear_override()
    if setpoints:
        return client.send_override(setpoints, replay_attempts=5, replay_delay=0.1)
    return client.get_state()


def _git_info():
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        ).strip()
    except Exception:
        branch = "unknown"
    return {"branch": branch}


def _neutralize_thruster_command():
    """Force topside manual command output to neutral axes."""
    neutral = _neutral_axis_values()
    ctrl = current_app.config.get("CONTROLLER")
    manip = ctrl.get_manipulator()["setpoint_norm"] if ctrl else 0.0
    if ctrl:
        if hasattr(ctrl, "clear_debug_override"):
            ctrl.clear_debug_override()
        if hasattr(ctrl, "apply_manual_axes_once"):
            ctrl.apply_manual_axes_once(neutral, source="HTTP")
    bm = current_app.config.get("BITMASK")
    if bm and not ctrl:
        bm.set_from_axes(**neutral, manip=manip)
    return neutral


def _manipulator_payload(ctrl, receiver=None):
    state = ctrl.get_manipulator() if ctrl else {}
    latest = receiver.get_latest() if receiver else {}
    manip = latest.get("manipulator") if isinstance(latest, dict) else {}
    now = time.time()
    updated_at = state.get("updated_at")
    telem_ts = latest.get("timestamp") if isinstance(latest, dict) else None
    return {
        "ok": bool(ctrl),
        "target_deg": state.get("setpoint_deg", 0.0),
        "setpoint_deg": state.get("setpoint_deg", 0.0),
        "source": state.get("source", "unknown"),
        "updated_age_ms": None if updated_at is None else max(0.0, (now - updated_at) * 1000.0),
        "applied_deg": manip.get("deg") if isinstance(manip, dict) else None,
        "pulse_us": manip.get("pulse_us") if isinstance(manip, dict) else None,
        "telemetry_age_ms": None if telem_ts is None else max(0.0, (now - telem_ts) * 1000.0),
    }


def _send_full_axis_config():
    """Read all axis settings from config and send to MCU in one packet."""
    imu_axes = config_handler.get_section("imu_axes") or _DEFAULT_IMU_AXES
    accel_axes = config_handler.get_section("accel_axes") or _DEFAULT_ACCEL_AXES
    offset = config_handler.get_section("imu_offset") or _DEFAULT_OFFSET
    send_axis_config(imu_axes=imu_axes, accel_axes=accel_axes, offset=offset)


def _camera_url_for_ip(ip):
    return f"rtsp://{ip}:554/stream1"


def _coerce_ipv4(value):
    try:
        addr = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    if addr.version != 4:
        return None
    return str(addr)


def _ip_from_url(url):
    try:
        return _coerce_ipv4(urlparse(url).hostname)
    except Exception:
        return None


def _camera_status_payload():
    ip_cam = current_app.config.get("IP_CAMERA")
    status = ip_cam.get_status() if ip_cam else {"connected": False}
    active_url = status.get("url") or current_app.config.get("IP_CAMERA_ACTIVE_URL") or _camera_url_for_ip(DEFAULT_IP_CAMERA_IP)
    active_ip = current_app.config.get("IP_CAMERA_ACTIVE_IP") or _ip_from_url(active_url) or DEFAULT_IP_CAMERA_IP
    return active_ip, active_url, status


def _get_ip_camera_config():
    section = config_handler.get_section("ip_camera") or {}
    raw_presets = section.get("presets", [])
    presets = []
    if isinstance(raw_presets, dict):
        raw_presets = [{"name": name, "ip": ip} for name, ip in raw_presets.items()]
    if isinstance(raw_presets, list):
        for item in raw_presets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            ip = _coerce_ipv4(item.get("ip"))
            if name and ip:
                presets.append({"name": name, "ip": ip})
    active_ip = _coerce_ipv4(section.get("active_ip")) or DEFAULT_IP_CAMERA_IP
    return {"active_ip": active_ip, "presets": presets}


def _save_ip_camera_config(section):
    config_handler.update_data({"ip_camera": section})


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
        return render_template("ip_camera.html")

    @app.route("/pilot")
    def pilot():
        """Render the pilot monitoring screen."""
        return render_template("pilot.html")

    @app.route("/debug")
    def debug():
        """Render the debug slider page."""
        return render_template("debug.html", attitude_limits=ATTITUDE_LIMITS_DEG)

    @app.route("/tooling")
    def tooling():
        """Render the tooling controls page."""
        return render_template("tooling.html")

    @app.route("/config")
    def config():
        """Render the configuration page."""
        return render_template("config.html")

    @app.route("/ip-camera")
    def ip_camera():
        """Render the IP camera page."""
        return render_template("ip_camera.html")

    @app.route("/connection")
    def connection():
        """Render the connection status page."""
        return render_template("connection.html")

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

    @app.route("/api/ip_camera/configs", methods=["GET"])
    def get_ip_camera_configs():
        """Return active IP camera URL plus saved IP presets."""
        active_ip, active_url, status = _camera_status_payload()
        section = _get_ip_camera_config()
        return jsonify(
            {
                "ok": True,
                "active_ip": active_ip,
                "active_url": active_url,
                "presets": section["presets"],
                "status": status,
            }
        )

    @app.route("/api/ip_camera/configs", methods=["POST"])
    def save_ip_camera_config():
        """Save or update a named IP camera IPv4 preset."""
        data = request.get_json(force=True, silent=True) or {}
        name = str(data.get("name", "")).strip()
        ip = _coerce_ipv4(data.get("ip"))
        if not name or not re.match(r"^[\w\s\-\.]+$", name):
            return jsonify({"ok": False, "error": "Invalid preset name"}), 400
        if not ip:
            return jsonify({"ok": False, "error": "Invalid IPv4 address"}), 400

        section = _get_ip_camera_config()
        presets = [preset for preset in section["presets"] if preset["name"] != name]
        presets.append({"name": name, "ip": ip})
        presets.sort(key=lambda preset: preset["name"].lower())
        section["presets"] = presets
        _save_ip_camera_config(section)
        return jsonify({"ok": True, "name": name, "ip": ip, "presets": presets})

    @app.route("/api/ip_camera/configs/<name>", methods=["DELETE"])
    def delete_ip_camera_config(name):
        """Delete a named IP camera preset."""
        section = _get_ip_camera_config()
        presets = [preset for preset in section["presets"] if preset["name"] != name]
        if len(presets) == len(section["presets"]):
            return jsonify({"ok": False, "error": "Preset not found"}), 404
        section["presets"] = presets
        _save_ip_camera_config(section)
        return jsonify({"ok": True, "presets": presets})

    @app.route("/api/ip_camera/reassign", methods=["POST"])
    def reassign_ip_camera():
        """Restart only the IP camera receiver with a new RTSP URL."""
        data = request.get_json(force=True, silent=True) or {}
        ip = _coerce_ipv4(data.get("ip"))
        if not ip:
            return jsonify({"ok": False, "error": "Invalid IPv4 address"}), 400

        url = _camera_url_for_ip(ip)
        old_camera = current_app.config.get("IP_CAMERA")
        if old_camera:
            old_camera.stop()

        settings = current_app.config.get("IP_CAMERA_SETTINGS") or {}
        new_camera = init_ip_camera(
            url=url,
            out_width=settings.get("out_width", 960),
            out_height=settings.get("out_height", 540),
            jpeg_quality=settings.get("jpeg_quality", 70),
            flip_180=settings.get("flip_180", False),
            marker_logger=current_app.config.get("ARUCO_LOGGER"),
        )
        current_app.config["IP_CAMERA"] = new_camera
        current_app.config["IP_CAMERA_ACTIVE_IP"] = ip
        current_app.config["IP_CAMERA_ACTIVE_URL"] = url

        section = _get_ip_camera_config()
        section["active_ip"] = ip
        _save_ip_camera_config(section)
        active_ip, active_url, status = _camera_status_payload()
        return jsonify({"ok": True, "active_ip": active_ip, "active_url": active_url, "status": status})

    @app.route("/api/aruco-log", methods=["GET"])
    def aruco_log_status():
        """Return ordered ARUCO marker sightings for the pipeline challenge."""
        logger = current_app.config.get("ARUCO_LOGGER")
        if not logger:
            return jsonify({"ok": False, "error": "ARUCO logger unavailable"}), 503
        return jsonify({"ok": True, "log": logger.snapshot()})

    @app.route("/api/aruco-log/start", methods=["POST"])
    def start_aruco_log():
        """Start logging new ARUCO marker IDs."""
        logger = current_app.config.get("ARUCO_LOGGER")
        if not logger:
            return jsonify({"ok": False, "error": "ARUCO logger unavailable"}), 503
        return jsonify({"ok": True, "log": logger.start()})

    @app.route("/api/aruco-log/stop", methods=["POST"])
    def stop_aruco_log():
        """Stop logging new ARUCO marker IDs."""
        logger = current_app.config.get("ARUCO_LOGGER")
        if not logger:
            return jsonify({"ok": False, "error": "ARUCO logger unavailable"}), 503
        return jsonify({"ok": True, "log": logger.stop()})

    @app.route("/api/aruco-log/clear", methods=["POST"])
    def clear_aruco_log():
        """Clear the ordered ARUCO marker log."""
        logger = current_app.config.get("ARUCO_LOGGER")
        if not logger:
            return jsonify({"ok": False, "error": "ARUCO logger unavailable"}), 503
        return jsonify({"ok": True, "log": logger.clear()})

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
        """Return the current light brightness (percent) the controller is sending."""
        ctrl = current_app.config.get("CONTROLLER")
        level = ctrl.get_light() if ctrl else 0.0
        pct = round(level * 100)
        return jsonify({"level": pct, "light": pct})

    @app.route("/api/lights", methods=["POST"])
    def set_lights():
        """Set light brightness. JSON body: {"level": 0..100} (percent)."""
        data = request.get_json(force=True, silent=True) or {}
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        if "level" not in data:
            return jsonify({"ok": False, "error": "Missing 'level'"}), 400
        try:
            pct = float(data["level"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid 'level'"}), 400
        pct = max(0.0, min(100.0, pct))
        ctrl.set_light(pct / 100.0)
        pct = round(pct)
        return jsonify({"ok": True, "level": pct, "light": pct})

    @app.route("/api/manipulator", methods=["GET"])
    def get_manipulator():
        ctrl = current_app.config.get("CONTROLLER")
        receiver = current_app.config.get("CONTROL_TELEM")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        return jsonify(_manipulator_payload(ctrl, receiver))

    @app.route("/api/manipulator", methods=["POST"])
    def set_manipulator():
        data = request.get_json(force=True, silent=True) or {}
        ctrl = current_app.config.get("CONTROLLER")
        receiver = current_app.config.get("CONTROL_TELEM")
        if not ctrl:
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        if "setpoint_deg" not in data:
            return jsonify({"ok": False, "error": "Missing 'setpoint_deg'"}), 400
        try:
            setpoint = float(data["setpoint_deg"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid 'setpoint_deg'"}), 400
        if not math.isfinite(setpoint):
            return jsonify({"ok": False, "error": "Invalid 'setpoint_deg'"}), 400
        ctrl.set_manipulator(setpoint, source="gui")
        return jsonify(_manipulator_payload(ctrl, receiver))

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
        control_state = controller.get_control_state() if controller and hasattr(controller, "get_control_state") else {}
        return jsonify(
            {
                "ok": True,
                "uplink": uplink,
                "controller": controller_state,
                "control_state": control_state,
                "udp_rx_count": udp_rx,
                "udp_rx_errors": udp_err,
                "override": state,
            }
        )

    @app.route("/api/control/state", methods=["GET"])
    def control_state():
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl or not hasattr(ctrl, "get_control_state"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        return jsonify({"ok": True, "state": ctrl.get_control_state()})

    @app.route("/api/control/killswitch", methods=["POST"])
    def control_killswitch():
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl or not hasattr(ctrl, "kill"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        state = ctrl.kill()
        zero_gains = _zero_pid_gains()
        confirmed, attempts = send_pid_gains(zero_gains, timeout=0.5, max_retries=2)
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                client.clear_override()
            except Exception:
                pass
        return jsonify(
            {
                "ok": True,
                "state": state,
                "pid_gains_zeroed": confirmed is not None,
                "pid_zero_attempts": attempts,
                "pid_gains": _attitude_pid_gains(confirmed or zero_gains),
            }
        )

    @app.route("/api/control/rearm", methods=["POST"])
    def control_rearm():
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl or not hasattr(ctrl, "rearm"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        state = ctrl.rearm()
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                client.clear_override()
            except Exception:
                pass
        return jsonify({"ok": True, "state": state})

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

    @app.route("/api/system/git", methods=["GET"])
    def system_git():
        return jsonify({"ok": True, "git": _git_info()})

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
        surge,sway,heave,roll,pitch,yaw,manip ([-128..127]), light ([0..255])
        or normalized axes in [-1..1] via "axes": and optional "rate_hz"
        """
        data = request.get_json(force=True, silent=True) or {}
        bm = current_app.config.get("BITMASK")
        ctrl = current_app.config.get("CONTROLLER")

        if ctrl and hasattr(ctrl, "is_killed") and ctrl.is_killed():
            _neutralize_thruster_command()
            return jsonify({"ok": False, "error": "Controls are killed", "state": ctrl.get_control_state()}), 423

        # allow normalized axes
        axes = data.get("axes")
        if isinstance(axes, dict):
            axes = dict(axes)
            if ctrl and hasattr(ctrl, "apply_manual_axes_once"):
                ctrl.apply_manual_axes_once(axes, source="HTTP")
            elif bm:
                bm.set_from_axes(**axes)

        # allow raw fields
        allowed = {"surge", "sway", "heave", "roll", "pitch", "yaw", "light", "manip"}
        raw = {k: int(v) for k, v in data.items() if k in allowed}
        if raw:
            raw_axes = {axis: raw[axis] / 127.0 for axis in CONTROL_AXES if axis in raw}
            if raw_axes and ctrl and hasattr(ctrl, "apply_manual_axes_once"):
                ctrl.apply_manual_axes_once(raw_axes, source="HTTP")
            elif raw_axes and bm:
                bm.set_command(**{axis: raw[axis] for axis in raw_axes})
            non_axes = {key: value for key, value in raw.items() if key not in CONTROL_AXES}
            if non_axes and bm:
                bm.set_command(**non_axes)

        # optional live rate change
        if bm and "rate_hz" in data:
            try:
                rate = float(data["rate_hz"])
                bm.period = 1.0 / rate if rate > 0 else 0.0
            except Exception:
                pass

        now = bm.get_command() if bm else {}
        state = ctrl.get_control_state() if ctrl and hasattr(ctrl, "get_control_state") else {}
        return jsonify({"ok": True, "now": now, "state": state})

    @app.route("/api/rov/status", methods=["GET"])
    def get_rov_status():
        bm = current_app.config["BITMASK"]
        resource = current_app.config.get("RESOURCE")
        ctrl = current_app.config.get("CONTROLLER")
        udp_rx, udp_err = resource.get_udp_counters() if resource else (0, 0)
        return jsonify(
            {
                "ok": True,
                "command": bm.get_command(),
                "uplink": bm.get_uplink_status(),
                "control_state": ctrl.get_control_state() if ctrl and hasattr(ctrl, "get_control_state") else {},
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
        ctrl = current_app.config.get("CONTROLLER")
        if not bm and not ctrl:
            return jsonify({"ok": False, "error": "Bitmask client unavailable"}), 503
        if ctrl and hasattr(ctrl, "is_killed") and ctrl.is_killed():
            _neutralize_thruster_command()
            return jsonify({"ok": False, "error": "Controls are killed", "state": ctrl.get_control_state()}), 423
        axes = {}
        for key in ("surge", "sway", "heave", "roll", "pitch", "yaw"):
            if key in data:
                value = max(-1.0, min(1.0, float(data[key])))
                axes[key] = -value if key == "yaw" else value
        if not axes:
            return jsonify({"ok": False, "error": "No axes supplied"}), 400

        if ctrl and hasattr(ctrl, "set_debug_override"):
            ctrl.set_debug_override(axes)
        elif bm:
            bm.set_from_axes(**axes)

        state = ctrl.get_control_state() if ctrl and hasattr(ctrl, "get_control_state") else {}
        return jsonify({"ok": True, "override": axes, "state": state})

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

        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                if ctrl and hasattr(ctrl, "is_pid_enabled") and ctrl.is_pid_enabled():
                    _send_active_pid_setpoints(ctrl, client)
                else:
                    client.clear_override()
            except Exception:
                pass

        state = ctrl.get_control_state() if ctrl and hasattr(ctrl, "get_control_state") else {}
        return jsonify({"ok": True, "state": state})

    @app.route("/api/pid/start", methods=["POST"])
    def start_pid_hold():
        """Start PID tuning from the current attitude and neutral manual command axes."""
        data = request.get_json(force=True, silent=True) or {}
        force = bool(data.get("force"))
        imu = current_app.config.get("IMU")
        client = current_app.config.get("SETPOINT_OVERRIDE")
        ctrl = current_app.config.get("CONTROLLER")
        if not imu:
            return jsonify({"ok": False, "error": "IMU receiver not running"}), 503
        if not client:
            return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
        if not ctrl or not hasattr(ctrl, "start_pid"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        if ctrl.is_killed():
            return jsonify({"ok": False, "error": "Controls are killed", "state": ctrl.get_control_state()}), 423

        stats = imu.get_stats()
        sanity = _imu_attitude_sanity(stats)
        if not sanity["usable"]:
            return jsonify({"ok": False, "error": sanity["reason"] or "Current attitude is incomplete", "sanity": sanity}), 503
        if not sanity["ok"] and not force:
            return jsonify({"ok": False, "error": sanity["reason"], "sanity": sanity, "force_supported": True}), 409

        pending = ctrl.get_pid_setpoints() if hasattr(ctrl, "get_pid_setpoints") else {}
        setpoints = {**sanity["setpoints"], **pending}
        ctrl.start_pid(setpoints)
        try:
            client.clear_override()
            override_state = client.send_override(setpoints, replay_attempts=5, replay_delay=0.1)
        except Exception as exc:  # pylint: disable=broad-except
            client.set_error(str(exc))
            ctrl.stop_pid(clear=False)
            return jsonify({"ok": False, "error": str(exc), "sanity": sanity}), 503

        return jsonify(
            {
                "ok": True,
                "setpoints": setpoints,
                "state": ctrl.get_control_state(),
                "override_state": override_state,
                "sanity": sanity,
                "forced": force and not sanity["ok"],
                "units": "deg",
            }
        )

    @app.route("/api/pid/setpoints", methods=["POST"])
    def set_pid_attitude_setpoints():
        """Save roll/pitch/yaw PID attitude setpoints in VN-100 degrees."""
        data = request.get_json(force=True, silent=True) or {}
        client = current_app.config.get("SETPOINT_OVERRIDE")
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl or not hasattr(ctrl, "set_pid_setpoints"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        if ctrl.is_killed():
            return jsonify({"ok": False, "error": "Controls are killed", "state": ctrl.get_control_state()}), 423
        axes = _coerce_attitude_setpoints(data)
        if not axes:
            return jsonify({"ok": False, "error": "No valid attitude setpoints supplied"}), 400
        setpoints = ctrl.set_pid_setpoints(axes)
        pid_active = ctrl.is_pid_enabled() if hasattr(ctrl, "is_pid_enabled") else False
        if pid_active:
            if not client:
                return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
            try:
                state = client.send_override(setpoints, replay_attempts=5, replay_delay=0.1)
            except Exception as exc:  # pylint: disable=broad-except
                client.set_error(str(exc))
                return jsonify({"ok": False, "error": str(exc)}), 503
        else:
            state = client.get_state() if client and hasattr(client, "get_state") else {}
        return jsonify(
            {
                "ok": True,
                "sent": setpoints,
                "limits": ATTITUDE_LIMITS_DEG,
                "state": state,
                "control_state": ctrl.get_control_state(),
                "pid_active": pid_active,
                "units": "deg",
            }
        )

    @app.route("/api/pid/setpoints/<axis>", methods=["DELETE"])
    def clear_pid_attitude_setpoint(axis):
        """Clear one saved or live roll/pitch/yaw PID setpoint."""
        axis = axis.lower()
        if axis not in ATTITUDE_AXES:
            return jsonify({"ok": False, "error": "Invalid PID axis"}), 400
        ctrl = current_app.config.get("CONTROLLER")
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if not ctrl or not hasattr(ctrl, "clear_pid_setpoint"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        remaining = ctrl.clear_pid_setpoint(axis)
        pid_active = ctrl.is_pid_enabled() if hasattr(ctrl, "is_pid_enabled") else False
        if pid_active:
            if not client:
                return jsonify({"ok": False, "error": "Setpoint override client unavailable"}), 503
            try:
                state = _send_active_pid_setpoints(ctrl, client)
            except Exception as exc:  # pylint: disable=broad-except
                client.set_error(str(exc))
                return jsonify({"ok": False, "error": str(exc)}), 503
        else:
            state = client.get_state() if client and hasattr(client, "get_state") else {}
        return jsonify(
            {
                "ok": True,
                "cleared": axis,
                "remaining": remaining,
                "state": state,
                "control_state": ctrl.get_control_state(),
                "pid_active": pid_active,
            }
        )

    @app.route("/api/pid/stop", methods=["POST"])
    def stop_pid_hold():
        """Stop PID and optionally clear attitude setpoints."""
        data = request.get_json(force=True, silent=True) or {}
        clear = bool(data.get("clear", True))
        ctrl = current_app.config.get("CONTROLLER")
        if not ctrl or not hasattr(ctrl, "stop_pid"):
            return jsonify({"ok": False, "error": "Controller not available"}), 503
        state = ctrl.stop_pid(clear=clear)
        client = current_app.config.get("SETPOINT_OVERRIDE")
        if client:
            try:
                client.clear_override()
            except Exception:
                pass
        return jsonify({"ok": True, "state": state})

    @app.route("/api/pid/rates", methods=["GET", "POST"])
    def pid_setpoint_rates():
        """Get or update roll/pitch/yaw setpoint rates in deg/s."""
        if request.method == "GET":
            rates = _load_pid_rates()
            ctrl = current_app.config.get("CONTROLLER")
            if ctrl and hasattr(ctrl, "set_pid_rates"):
                ctrl.set_pid_rates(rates)
            return jsonify({"ok": True, "rates": rates, "units": "deg/s"})

        data = request.get_json(force=True, silent=True) or {}
        rates = _save_pid_rates(data)
        return jsonify({"ok": True, "rates": rates, "units": "deg/s"})

    @app.route("/api/pid/zero_all", methods=["POST"])
    def zero_all_pid():
        """Force neutral manual command axes and send zero PID gains to the MCU."""
        ctrl = current_app.config.get("CONTROLLER")
        if ctrl and hasattr(ctrl, "stop_pid"):
            ctrl.stop_pid()
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

    # --- PID config (MCU) endpoints ---
    @app.route("/api/pid/gains", methods=["GET"])
    def get_pid_gains():
        """Request current PID gains from the MCU via UDP."""
        gains = request_pid_gains(timeout=2.0)
        if gains is None:
            return jsonify({"ok": False, "error": "No response from MCU"}), 504
        return jsonify({"ok": True, "gains": _attitude_pid_gains(gains), "raw_gains": gains})

    @app.route("/api/pid/gains", methods=["POST"])
    def set_pid_gains():
        """Send PID gains to the MCU via UDP. Expects JSON: {axis: {kp, ki, kd}, ...}."""
        data = request.get_json(force=True, silent=True) or {}
        gains = _mcu_pid_gains(data)
        confirmed, attempts = send_pid_gains(gains, timeout=1.0, max_retries=3)
        if confirmed is None:
            return jsonify({"ok": False, "error": "No response from MCU after %d attempts" % attempts}), 504
        return jsonify({"ok": True, "gains": _attitude_pid_gains(confirmed), "raw_gains": confirmed, "attempts": attempts})

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
        configs[name] = _mcu_pid_gains(gains)
        _save_pid_configs(configs)
        return jsonify({"ok": True, "name": name})

    @app.route("/api/pid/configs/<name>", methods=["GET"])
    def load_pid_config(name):
        """Load a saved PID configuration by name."""
        configs = _load_pid_configs()
        if name not in configs:
            return jsonify({"ok": False, "error": "Config not found"}), 404
        return jsonify({"ok": True, "name": name, "gains": _attitude_pid_gains(configs[name]), "raw_gains": configs[name]})

    @app.route("/api/pid/configs/<name>", methods=["DELETE"])
    def delete_pid_config(name):
        """Delete a saved PID configuration."""
        configs = _load_pid_configs()
        if name not in configs:
            return jsonify({"ok": False, "error": "Config not found"}), 404
        del configs[name]
        _save_pid_configs(configs)
        return jsonify({"ok": True})
