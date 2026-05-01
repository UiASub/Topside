import os
import sys
from pathlib import Path

APP_NAME = "Topside"


def app_root() -> Path:
    override = os.getenv("TOPSIDE_APP_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    override = os.getenv("TOPSIDE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return app_root() / "data"


def logs_dir() -> Path:
    override = os.getenv("TOPSIDE_LOG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return app_root() / "logs"


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)


def log_path(*parts: str) -> Path:
    return logs_dir().joinpath(*parts)
