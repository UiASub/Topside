import json

from lib import runtime_paths


def _clear_path_env(monkeypatch):
    for name in (
        "APPDATA",
        "LOCALAPPDATA",
        "TOPSIDE_APP_ROOT",
        "TOPSIDE_DATA_DIR",
        "TOPSIDE_LOG_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def test_source_data_dir_uses_app_root_override(monkeypatch, tmp_path):
    _clear_path_env(monkeypatch)
    monkeypatch.setattr(runtime_paths.sys, "frozen", False, raising=False)
    monkeypatch.setenv("TOPSIDE_APP_ROOT", str(tmp_path))

    assert runtime_paths.data_dir() == tmp_path / ".runtime" / "data"


def test_source_ensure_data_dir_seeds_from_repo_data(monkeypatch, tmp_path):
    _clear_path_env(monkeypatch)
    starter_dir = tmp_path / "data"
    starter_dir.mkdir(parents=True)
    (starter_dir / "data.json").write_text('{"starter": true}', encoding="utf-8")
    (starter_dir / "config.json").write_text('{"imu_axes": {"yaw": "+yaw"}}', encoding="utf-8")

    monkeypatch.setattr(runtime_paths.sys, "frozen", False, raising=False)
    monkeypatch.setenv("TOPSIDE_APP_ROOT", str(tmp_path))

    target = runtime_paths.ensure_data_dir()

    assert target == tmp_path / ".runtime" / "data"
    assert (target / "data.json").read_text(encoding="utf-8") == '{"starter": true}'
    assert (target / "config.json").exists()


def test_windows_frozen_data_dir_uses_local_appdata(monkeypatch, tmp_path):
    _clear_path_env(monkeypatch)
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(runtime_paths.sys, "executable", str(tmp_path / "Install" / "Topside.exe"))

    assert runtime_paths.data_dir() == tmp_path / "LocalAppData" / "Topside" / "data"


def test_ensure_data_dir_seeds_from_packaged_data_without_overwriting(monkeypatch, tmp_path):
    _clear_path_env(monkeypatch)
    install_dir = tmp_path / "Install"
    starter_dir = install_dir / "data"
    starter_dir.mkdir(parents=True)
    (starter_dir / "data.json").write_text('{"starter": true}', encoding="utf-8")
    (starter_dir / "config.json").write_text('{"imu_axes": {"yaw": "+yaw"}}', encoding="utf-8")

    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "platform", "win32")
    monkeypatch.setattr(runtime_paths.sys, "executable", str(install_dir / "Topside.exe"))
    monkeypatch.delattr(runtime_paths.sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    target = runtime_paths.ensure_data_dir()
    assert target == tmp_path / "LocalAppData" / "Topside" / "data"
    assert (target / "data.json").read_text(encoding="utf-8") == '{"starter": true}'
    assert (target / "config.json").exists()

    (target / "data.json").write_text('{"operator": true}', encoding="utf-8")
    runtime_paths.ensure_data_dir()

    data = json.loads((target / "data.json").read_text(encoding="utf-8"))
    assert data["operator"] is True
    assert data["starter"] is True


def test_ensure_data_dir_fills_missing_data_json_values(monkeypatch, tmp_path):
    _clear_path_env(monkeypatch)
    install_dir = tmp_path / "Install"
    starter_dir = install_dir / "data"
    starter_dir.mkdir(parents=True)
    (starter_dir / "data.json").write_text(
        '{"imu": {"yaw": 0, "pitch": 0}, "battery": 0, "thrusters": {"T1": {"power": 0, "temp": 20}}}',
        encoding="utf-8",
    )

    existing_dir = tmp_path / "LocalAppData" / "Topside" / "data"
    existing_dir.mkdir(parents=True)
    (existing_dir / "data.json").write_text('{"imu": {"yaw": 12.5}}', encoding="utf-8")

    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "platform", "win32")
    monkeypatch.setattr(runtime_paths.sys, "executable", str(install_dir / "Topside.exe"))
    monkeypatch.delattr(runtime_paths.sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    runtime_paths.ensure_data_dir()

    handler = json.loads((existing_dir / "data.json").read_text(encoding="utf-8"))
    assert handler["imu"]["yaw"] == 12.5
    assert handler["imu"]["pitch"] == 0
    assert handler["battery"] == 0
    assert handler["thrusters"]["T1"] == {"power": 0, "temp": 20}
