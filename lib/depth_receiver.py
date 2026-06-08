from __future__ import annotations

from typing import Any

from lib.json_data_handler import JSONDataHandler


class DepthTelemetryReceiver:
    """Normalizes MS5837 depth telemetry from MCU sensor JSON packets."""

    def __init__(self, data_handler=None):
        self.data_handler = data_handler or JSONDataHandler()
        self._last_depth = {}

    def process_payload(self, depth: Any) -> dict | None:
        if not isinstance(depth, dict) or not depth:
            return None

        depth_update = normalize_depth_payload(depth)
        self._last_depth = depth_update
        self.data_handler.update_data({"depth": depth_update})
        return depth_update

    def get_latest(self) -> dict:
        return self._last_depth.copy()


def normalize_depth_payload(depth: dict) -> dict:
    return {
        "dpt": _coerce_json_number(_depth_val(depth, "dpt")),
        "dptSet": _coerce_json_number(_depth_val(depth, "dptSet")),
        "pressure_mbar": _coerce_json_number(_depth_val(depth, "pressure_mbar"), precision=1),
        "temperature_c": _coerce_json_number(_depth_val(depth, "temperature_c")),
        "valid": _coerce_json_bool(depth.get("valid", False)),
        "age_ms": _coerce_json_number(_depth_val(depth, "age_ms"), precision=0),
        "addr": _coerce_json_number(_depth_val(depth, "addr"), precision=0),
        "last_error": _coerce_json_number(_depth_val(depth, "last_error"), precision=0),
        "init_attempts": _coerce_json_number(_depth_val(depth, "init_attempts"), precision=0),
        "read_errors": _coerce_json_number(_depth_val(depth, "read_errors"), precision=0),
    }


def _depth_val(depth: dict, key: str, default: float = float("nan")) -> float:
    value = depth.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_json_number(value: float, precision: int = 2) -> Any:
    if value != value:  # NaN check
        return None
    return round(float(value), precision)


def _coerce_json_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
