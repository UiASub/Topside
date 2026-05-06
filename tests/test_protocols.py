import json
import struct

import pytest

import lib.control_telemetry as control_telem
import lib.ninedof_receiver as imu_telem
import lib.resource_receiver as resource_telem
from lib import axis_config_sender, bitmask, crc, net_transport, pid_config_client, system_control_client
from lib.json_data_handler import JSONDataHandler


class DummyHandler:
    def __init__(self):
        self.last_update = None

    def update_data(self, payload):
        self.last_update = payload


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
    crc_value = crc.crc32_ieee(body)
    packet = body + struct.pack("!I", crc_value)

    receiver._handle_packet(packet, ("127.0.0.1", 5005))  # pylint: disable=protected-access

    latest = receiver.get_latest()
    assert latest["sequence"] == sequence
    for axis, value in zip(control_telem.AXES, setpoints):
        assert latest["setpoint"][axis] == pytest.approx(value, rel=1e-4)
    history = receiver.get_history(limit=5)
    assert len(history) == 1
    assert history[0]["sequence"] == sequence
    assert handler.last_update is not None


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


def test_imu_receiver_accepts_crc_trailer(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(imu_telem, "IMU_LOG", tmp_path / "imu_raw.ndjson")
    handler = DummyHandler()
    receiver = imu_telem.IMUReceiver(data_handler=handler)
    body = json.dumps(
        {
            "imu": {
                "yaw": 1.25,
                "pitch": -2.5,
                "roll": 3.75,
                "yr": 0.1,
                "pr": 0.2,
                "rr": 0.3,
                "ax": 4.0,
                "ay": 5.0,
                "az": 6.0,
            }
        },
        separators=(",", ":"),
    ).encode()
    packet = body + struct.pack("!I", crc.crc32_ieee(body))

    receiver._process_packet(packet, ("10.77.0.2", 5002))  # pylint: disable=protected-access

    assert capsys.readouterr().out == ""
    assert handler.last_update["imu"]["yaw"] == 1.25
    assert handler.last_update["imu"]["pitch"] == -2.5
    assert handler.last_update["imu"]["roll"] == 3.75
    assert receiver.get_stats()["packet_count"] == 1
    assert receiver.get_stats()["crc_errors"] == 0


def test_imu_receiver_keeps_legacy_json_without_crc(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(imu_telem, "IMU_LOG", tmp_path / "imu_raw.ndjson")
    handler = DummyHandler()
    receiver = imu_telem.IMUReceiver(data_handler=handler)
    packet = json.dumps({"imu": {"yaw": 4.0, "pitch": 5.0, "roll": 6.0}}, separators=(",", ":")).encode()

    receiver._process_packet(packet, ("10.77.0.2", 5002))  # pylint: disable=protected-access

    assert capsys.readouterr().out == ""
    assert handler.last_update["imu"]["yaw"] == 4.0
    assert handler.last_update["imu"]["pitch"] == 5.0
    assert handler.last_update["imu"]["roll"] == 6.0
    assert receiver.get_stats()["packet_count"] == 1
    assert receiver.get_stats()["crc_errors"] == 0


def test_imu_receiver_discards_bad_crc(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(imu_telem, "IMU_LOG", tmp_path / "imu_raw.ndjson")
    handler = DummyHandler()
    receiver = imu_telem.IMUReceiver(data_handler=handler)
    body = json.dumps({"imu": {"yaw": 10.0, "pitch": 20.0, "roll": 30.0}}, separators=(",", ":")).encode()
    packet = body + struct.pack("!I", crc.crc32_ieee(body) ^ 0xFFFFFFFF)

    receiver._process_packet(packet, ("10.77.0.2", 5002))  # pylint: disable=protected-access

    assert handler.last_update is None
    stats = receiver.get_stats()
    assert stats["packet_count"] == 0
    assert stats["crc_errors"] == 1
    assert "IMU: CRC mismatch" in capsys.readouterr().out


def test_json_data_handler_creates_parent_and_preserves_sections(tmp_path):
    data_file = tmp_path / "nested" / "data.json"
    handler = JSONDataHandler(file_path=data_file)

    handler.update_data({"imu": {"yaw": 12.5}})
    handler.update_data({"resources": {"cpu_percent": 4}})

    assert handler.get_section("imu") == {"yaw": 12.5}
    assert handler.get_section("resources") == {"cpu_percent": 4}
