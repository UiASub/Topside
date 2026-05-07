import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Topside"
DATA_FILE_NAME = "data.json"


def app_root() -> Path:
    override = os.getenv("TOPSIDE_APP_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _windows_app_data_root() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        return Path(base).expanduser().resolve() / APP_NAME

    home = Path.home()
    return home / "AppData" / "Local" / APP_NAME


def writable_app_root() -> Path:
    if _is_frozen() and _is_windows() and not os.getenv("TOPSIDE_APP_ROOT"):
        return _windows_app_data_root()
    return app_root()


def data_dir() -> Path:
    override = os.getenv("TOPSIDE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return writable_app_root() / "data"


def logs_dir() -> Path:
    override = os.getenv("TOPSIDE_LOG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return writable_app_root() / "logs"


def _starter_data_candidates() -> list[Path]:
    candidates = []

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "data")

    if _is_frozen():
        candidates.append(Path(sys.executable).resolve().parent / "data")

    candidates.append(app_root() / "data")
    return candidates


def starter_data_dir() -> Path | None:
    target = data_dir().resolve()
    for candidate in _starter_data_candidates():
        candidate = candidate.expanduser().resolve()
        if candidate == target:
            continue
        if candidate.is_dir():
            return candidate
    return None


def _merge_missing_values(current, template):
    if isinstance(current, dict) and isinstance(template, dict):
        merged = dict(current)
        changed = False
        for key, template_value in template.items():
            if key not in merged:
                merged[key] = template_value
                changed = True
                continue
            merged_value, child_changed = _merge_missing_values(merged[key], template_value)
            if child_changed:
                merged[key] = merged_value
                changed = True
        return merged, changed

    return current, False


def _fill_missing_json_values(destination: Path, template: Path) -> None:
    try:
        current_data = json.loads(destination.read_text(encoding="utf-8"))
        template_data = json.loads(template.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    merged, changed = _merge_missing_values(current_data, template_data)
    if not changed:
        return

    temp_file = destination.with_name(f".{destination.name}.tmp")
    temp_file.write_text(json.dumps(merged, indent=4) + "\n", encoding="utf-8")
    os.replace(temp_file, destination)


def ensure_data_dir() -> Path:
    target = data_dir()
    target.mkdir(parents=True, exist_ok=True)

    starter = starter_data_dir()
    template = starter / DATA_FILE_NAME if starter is not None else None

    data_file = target / DATA_FILE_NAME
    if template is not None and template.is_file():
        if data_file.exists():
            _fill_missing_json_values(data_file, template)
        else:
            shutil.copy2(template, data_file)

    if starter is not None:
        for item in starter.iterdir():
            destination = target / item.name
            if destination.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

    return target


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)


def log_path(*parts: str) -> Path:
    return logs_dir().joinpath(*parts)
