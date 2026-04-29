"""CRC utilities shared across topside networking modules.

Implements IEEE 802.3 CRC-32 (polynomial 0x04C11DB7) in the same bitwise
orientation used by Ethernet, Zephyr, and the embedded `crc32_calc()` helper.
This module exposes both convenience functions and a small streaming helper so
callers can avoid re-implementing the lookup-table each time they need to
checksum a packet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Ethernet / IEEE 802.3 parameters
_POLY_REFLECTED = 0xEDB88320
_INIT = 0xFFFFFFFF
_XOROUT = 0xFFFFFFFF

# Lazily-built lookup table so import cost stays low for modules that do not end
# up hashing any payloads.
_crc_table: Optional[list[int]] = None


def _ensure_table() -> list[int]:
    global _crc_table
    if _crc_table is not None:
        return _crc_table
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ _POLY_REFLECTED
            else:
                crc >>= 1
        table.append(crc & 0xFFFFFFFF)
    _crc_table = table
    return table


def crc32_ieee(data: bytes, initial: int = _INIT) -> int:
    """Return the IEEE 802.3 CRC-32 of *data*.

    Args:
        data: Raw bytes to checksum.
        initial: Optional starting value allowing streaming CRCs.

    Returns:
        Unsigned 32-bit checksum with the standard XOR-out applied.
    """

    table = _ensure_table()
    crc = initial & 0xFFFFFFFF
    for byte in data:
        idx = (crc ^ byte) & 0xFF
        crc = (crc >> 8) ^ table[idx]
    return crc ^ _XOROUT


def crc32_continue(crc: int, data: bytes) -> int:
    """Continue a CRC calculation with more data (no XOR-out applied).

    This helper mirrors the `crc32_ieee` implementation but returns the raw
    internal state so callers can feed multiple chunks before applying the final
    XOR. Most modules can call :func:`crc32_ieee` directly; this function mainly
    exists for tooling that needs to build a CRC over segmented payloads.
    """

    table = _ensure_table()
    state = crc & 0xFFFFFFFF
    for byte in data:
        idx = (state ^ byte) & 0xFF
        state = (state >> 8) ^ table[idx]
    return state


@dataclass
class CRC32:
    """Incremental CRC helper.

    Example::

        crc = CRC32()
        crc.update(header)
        crc.update(payload)
        digest = crc.digest()
    """

    _state: int = _INIT

    def update(self, data: bytes | bytearray | memoryview) -> None:
        table = _ensure_table()
        state = self._state
        for byte in data:
            idx = (state ^ byte) & 0xFF
            state = (state >> 8) ^ table[idx]
        self._state = state

    def digest(self) -> int:
        return self._state ^ _XOROUT

    def hexdigest(self) -> str:
        return f"{self.digest():08x}"

    def reset(self) -> None:
        self._state = _INIT
