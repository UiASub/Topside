import json
import struct

import pytest

import lib.control_telemetry as control_telem
import lib.depth_receiver as depth_telem
import lib.ninedof_receiver as ninedof
import lib.resource_receiver as resource_telem
from lib import axis_config_sender, bitmask, crc, net_transport, pid_config_client, system_control_client
from lib.json_data_handler import JSONDataHandler


class DummyHandler:
    def __init__(self):
        self.last_update = None

    def update_data(self, payload):
        self.last_update = payload


class DummyDepthReceiver:
    def __init__(self):
        self.last_payload = None

    def process_payload(self, payload):
        self.last_payload = payload


def test_crc32_ieee_standard_vector():
    # Known-good IEEE 802.3 vector
    assert crc.crc32_ieee(b"123456789") == 0xCBF43926


def test_bitmask_packet_big_endian():
    seq = 0x12345678
    payload = 0x0123456789ABCDEF
    pkt = bitmask.build_packet(seq, payload)
    assert len(pkt) == 16
    assert pkt[:4] == struct.pack("!I", seq)
    assert pkt[4:12] == struct.pack("!Q", payload)
    expected_crc = crc.crc32_ieee(struct.pack("!IQ", seq, payload))
    assert pkt[12:] == struct.pack("!I", expected_crc)


def test_bitmask_manipulator_is_signed_in_top_byte():
    assert (bitmask.encode_payload(bitmask.Command(manip=-127)) >> 56) & 0xFF == 1
    assert (bitmask.encode_payload(bitmask.Command(manip=0)) >> 56) & 0xFF == 128
    assert (bitmask.encode_payload(bitmask.Command(manip=127)) >> 56) & 0xFF == 255


def test_system_reset_packet_crc():
    pkt = system_control_client.build_reset_packet(0x01020304)
    assert pkt[:4] == b"RST1"
    assert pkt[4:8] == struct.pack("!I", 0x01020304)
    expected_crc = crc.crc32_ieee(pkt[:8])
    assert pkt[8:] == struct.pack("!I", expected_crc)


def test_network_defaults_use_current_mcu_address():
    assert net_transport.DEFAULT_ROV_HOST == "10.77.0.2"
    assert net_transport.DEFAULT_BROADCAST == "10.77.0.255"
    assert bitmask.NUCLEO_HOST == net_transport.DEFAULT_ROV_HOST
    assert axis_config_sender.NUCLEO_HOST == net_transport.DEFAULT_ROV_HOST
    assert pid_config_client.MCU_IP == net_transport.DEFAULT_ROV_HOST


def test_control_telemetry_history(monkeypatch, tmp_path):
    monkeypatch.setattr(control_telem, "LOG_DIR", tmp_path)
    monkeypatch.setattr(control_telem, "CONTROL_LOG", tmp_path / "control_telemetry.ndjson")
    handler = DummyHandler()
    receiver = control_telem.ControlTelemetryReceiver(data_handler=handler)
    receiver.disable_capture()

    sequence = 0x11223344
    setpoints = [0.1 * idx for idx in range(6)]
    outputs = [value + 0.05 for value in setpoints]
    errors = [output - value for value, output in zip(setpoints, outputs)]
    body = struct.pack("!I", sequence) + struct.pack("<" + "f" * 18, *(setpoints + outputs + errors))
    body += struct.pack("<fH", 12.5, 1625)
    crc_value = crc.crc32_ieee(body)
    packet = body + struct.pack("!I", crc_value)

    receiver._handle_packet(packet, ("127.0.0.1", 5005))  # pylint: disable=protected-access

    latest = receiver.get_latest()
    assert latest["sequence"] == sequence
    for axis, value in zip(control_telem.AXES, setpoints):
        assert latest["setpoint"][axis] == pytest.approx(value, rel=1e-4)
    assert latest["manipulator"] == {"deg": 12.5, "pulse_us": 1625}
    history = receiver.get_history(limit=5)
    assert len(history) == 1
    assert history[0]["sequence"] == sequence
    assert handler.last_update is not None


def test_control_telemetry_includes_manipulator_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(control_telem, "LOG_DIR", tmp_path)
    monkeypatch.setattr(control_telem, "CONTROL_LOG", tmp_path / "control_telemetry.ndjson")
    receiver = control_telem.ControlTelemetryReceiver(data_handler=DummyHandler())
    receiver.disable_capture()

    sequence = 3
    setpoints = [0.0] * 6
    outputs = [0.0] * 6
    errors = [0.0] * 6
    body = (
        struct.pack("!I", sequence)
        + struct.pack("<" + "f" * 18, *(setpoints + outputs + errors))
        + struct.pack("<fH", -12.5, 1375)
    )
    packet = body + struct.pack("!I", crc.crc32_ieee(body))

    receiver._handle_packet(packet, ("127.0.0.1", 5005))  # pylint: disable=protected-access

    latest = receiver.get_latest()
    assert latest["sequence"] == sequence
    assert latest["manipulator"] == {"deg": -12.5, "pulse_us": 1375}


def test_resource_telemetry_updates_json_handler(monkeypatch, tmp_path):
    monkeypatch.setattr(resource_telem, "LOG_DIR", tmp_path)
    monkeypatch.setattr(resource_telem, "RESOURCE_LOG", tmp_path / "resource_monitor.ndjson")
    handler = DummyHandler()
    receiver = resource_telem.ResourceReceiver(data_handler=handler)

    body = struct.pack(
        ">IIBBHHBBII",
        7,  # sequence
        1234,  # uptime_ms
        4,  # cpu_percent
        1,  # heap_used_percent
        502,  # heap_free_kb
        512,  # heap_total_kb
        19,  # thread_count
        0,  # reserved
        84,  # udp_rx_count
        0,  # udp_rx_errors
    )
    packet = body + struct.pack(">I", crc.crc32_ieee(body))

    receiver._process_packet(packet, ("10.77.0.2", 12346))  # pylint: disable=protected-access

    assert handler.last_update == {
        "resources": {
            "sequence": 7,
            "uptime_ms": 1234,
            "cpu_percent": 4,
            "heap_used_percent": 1,
            "heap_free_kb": 502,
            "heap_total_kb": 512,
            "thread_count": 19,
            "udp_rx_count": 84,
            "udp_rx_errors": 0,
        }
    }
    assert receiver.get_udp_counters() == (84, 0)


def test_depth_receiver_normalizes_ms5837_payload():
    handler = DummyHandler()
    receiver = depth_telem.DepthTelemetryReceiver(data_handler=handler)

    result = receiver.process_payload(
        {
            "dpt": "1.234",
            "dptSet": 2,
            "pressure_mbar": 1013.26,
            "temperature_c": "18.5",
            "valid": "true",
            "age_ms": 42.4,
            "addr": 118,
            "last_probe_addr": 118,
            "last_error": -5,
            "probe_error_0x76": 0,
            "probe_error_0x77": -5,
            "scl_idle": 1,
            "sda_idle": 1,
            "transport_error": 4,
            "transport_mode": 1,
            "fw_depth_rev": 202605139,
            "scan_count": 1,
            "scan_first_addr": 118,
            "scan_last_addr": 118,
            "scan_has_0x76": 1,
            "scan_has_0x77": 0,
            "init_attempts": 3,
            "read_errors": 1,
        }
    )

    assert result == {
        "dpt": 1.23,
        "dptSet": 2.0,
        "pressure_mbar": 1013.3,
        "temperature_c": 18.5,
        "valid": True,
        "age_ms": 42.0,
        "addr": 118.0,
        "last_probe_addr": 118.0,
        "last_error": -5.0,
        "probe_error_0x76": 0.0,
        "probe_error_0x77": -5.0,
        "scl_idle": 1.0,
        "sda_idle": 1.0,
        "transport_error": 4.0,
        "transport_mode": 1.0,
        "fw_depth_rev": 202605139.0,
        "scan_count": 1.0,
        "scan_first_addr": 118.0,
        "scan_last_addr": 118.0,
        "scan_has_0x76": 1.0,
        "scan_has_0x77": 0.0,
        "init_attempts": 3.0,
        "read_errors": 1.0,
    }
    assert handler.last_update == {"depth": result}


def test_imu_receiver_delegates_depth_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(ninedof, "IMU_LOG", tmp_path / "imu_raw.ndjson")
    handler = DummyHandler()
    depth_receiver = DummyDepthReceiver()
    receiver = ninedof.IMUReceiver(data_handler=handler, depth_receiver=depth_receiver)

    depth_payload = {
        "dpt": 0.0,
        "dptSet": 0.0,
        "pressure_mbar": 0.0,
        "temperature_c": 0.0,
        "valid": False,
        "age_ms": -1,
        "addr": 0,
        "last_probe_addr": 119,
        "last_error": -5,
        "probe_error_0x76": -5,
        "probe_error_0x77": -5,
        "init_attempts": 39,
        "read_errors": 0,
    }
    packet = json.dumps(
        {
            "imu": {
                "yaw": -126.98,
                "pitch": -5.45,
                "roll": 179.55,
                "yr": 0.03,
                "pr": 0.0,
                "rr": 0.1,
                "ax": -0.002,
                "ay": 0.001,
                "az": -0.002,
            },
            "depth": depth_payload,
        }
    ).encode("utf-8")

    receiver._process_packet(packet, ("10.77.0.2", 5002))  # pylint: disable=protected-access

    assert handler.last_update["imu"]["yaw"] == -126.98
    assert depth_receiver.last_payload == depth_payload


def test_json_data_handler_creates_parent_and_preserves_sections(tmp_path):
    data_file = tmp_path / "nested" / "data.json"
    handler = JSONDataHandler(file_path=data_file)

    handler.update_data({"imu": {"yaw": 12.5}})
    handler.update_data({"resources": {"cpu_percent": 4}})

    assert handler.get_section("imu") == {"yaw": 12.5}
    assert handler.get_section("resources") == {"cpu_percent": 4}
