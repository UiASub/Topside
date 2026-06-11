from flask import Flask

import routes
from lib.json_data_handler import JSONDataHandler


class FakeIPCamera:
    def __init__(self, url):
        self.url = url
        self.stopped = False

    def stop(self):
        self.stopped = True

    def get_status(self):
        return {"connected": True, "url": self.url}


def make_client(monkeypatch, tmp_path):
    config_handler = JSONDataHandler(file_path=tmp_path / "config.json")
    monkeypatch.setattr(routes, "config_handler", config_handler)

    app = Flask(__name__)
    camera = FakeIPCamera("rtsp://10.77.0.4:554/stream1")
    app.config["IP_CAMERA"] = camera
    app.config["IP_CAMERA_ACTIVE_IP"] = "10.77.0.4"
    app.config["IP_CAMERA_ACTIVE_URL"] = camera.url
    app.config["IP_CAMERA_SETTINGS"] = {
        "out_width": 320,
        "out_height": 240,
        "jpeg_quality": 70,
        "flip_180": False,
    }
    routes.register_routes(app)
    return app, app.test_client(), camera


def test_ip_camera_preset_save_and_delete(monkeypatch, tmp_path):
    _app, client, _camera = make_client(monkeypatch, tmp_path)

    res = client.post("/api/ip_camera/configs", json={"name": "Pool", "ip": "10.77.0.5"})
    assert res.status_code == 200
    assert res.get_json()["presets"] == [{"name": "Pool", "ip": "10.77.0.5"}]

    res = client.get("/api/ip_camera/configs")
    assert res.status_code == 200
    assert res.get_json()["presets"] == [{"name": "Pool", "ip": "10.77.0.5"}]

    res = client.delete("/api/ip_camera/configs/Pool")
    assert res.status_code == 200
    assert res.get_json()["presets"] == []


def test_ip_camera_reassign_restarts_fake_receiver(monkeypatch, tmp_path):
    app, client, old_camera = make_client(monkeypatch, tmp_path)
    created = []

    def fake_init_ip_camera(**kwargs):
        camera = FakeIPCamera(kwargs["url"])
        created.append((camera, kwargs))
        return camera

    monkeypatch.setattr(routes, "init_ip_camera", fake_init_ip_camera)

    res = client.post("/api/ip_camera/reassign", json={"ip": "10.77.0.9"})

    assert res.status_code == 200
    data = res.get_json()
    assert data["active_ip"] == "10.77.0.9"
    assert data["active_url"] == "rtsp://10.77.0.9:554/stream1"
    assert old_camera.stopped is True
    assert len(created) == 1
    assert created[0][1]["url"] == "rtsp://10.77.0.9:554/stream1"
    assert created[0][1]["out_width"] == 320
    assert app.config["IP_CAMERA"] is created[0][0]
