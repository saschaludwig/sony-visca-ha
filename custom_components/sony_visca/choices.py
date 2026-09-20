"""Iris/gain/shutter/brightness choice tables."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .const import DEFAULT_FRAME_RATE

_DATA_PATH = Path(__file__).with_name("choices_data.json")
_GROUP_TABLES: dict[str, Any] = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

EXPOSURE_COMPENSATION: tuple[tuple[str, str], ...] = (
    ("0E", "+7"),
    ("0D", "+6"),
    ("0C", "+5"),
    ("0B", "+4"),
    ("0A", "+3"),
    ("09", "+2"),
    ("08", "+1"),
    ("07", "0"),
    ("06", "-1"),
    ("05", "-2"),
    ("04", "-3"),
    ("03", "-4"),
    ("02", "-5"),
    ("01", "-6"),
    ("00", "-7"),
)

# Inquiry-block offset 7 is centered at 7, so 0 maps to -7 EV.
EXPOSURE_COMP_OFFSET_TO_ID = {index - 7: hex_id for index, (hex_id, _label) in enumerate(EXPOSURE_COMPENSATION)}
EXPOSURE_COMP_ID_TO_OFFSET = {hex_id: offset for offset, hex_id in EXPOSURE_COMP_OFFSET_TO_ID.items()}


@dataclass(frozen=True)
class ViscaChoice:
    """A labeled VISCA option value."""

    value: str
    label: str


def _as_choices(items: list[dict[str, Any]] | None) -> tuple[ViscaChoice, ...]:
    if not items:
        return ()
    return tuple(ViscaChoice(str(item["id"]).upper(), str(item["label"])) for item in items)


def group_tables(group: str) -> dict[str, Any]:
    """Return the raw choice tables for an inquiry group."""
    if group in _GROUP_TABLES:
        return _GROUP_TABLES[group]
    if group in {"3c", "3d"}:
        return _GROUP_TABLES["3b"]
    return _GROUP_TABLES.get("1a", {})


class CameraChoices:
    """Resolved iris/gain/shutter/brightness choices for one camera."""

    def __init__(self, group: str, frame_rate: str = DEFAULT_FRAME_RATE) -> None:
        tables = group_tables(group)
        rate = frame_rate if frame_rate in tables else "50" if "50" in tables else "60"
        rate_tables = tables.get(rate) or tables.get(int(rate) if rate.isdigit() else rate) or {}
        if not rate_tables:
            # JSON keys for 60/50/24 were stored as strings.
            rate_tables = tables.get(str(rate), {})
        self.group = group
        self.frame_rate = str(rate)
        self.iris = _as_choices(tables.get("IRIS"))
        self.gain = _as_choices(tables.get("GAIN"))
        self.gain_limit = _as_choices(tables.get("GAIN_LIMIT"))
        self.brightness = _as_choices(tables.get("BRIGHTNESS"))
        self.shutter = _as_choices(rate_tables.get("SHUTTER"))
        self.max_shutter = _as_choices(rate_tables.get("MAX_SHUTTER"))

    def lookup(self, kind: str, raw: int) -> str:
        """Return the hex option id for a raw inquiry byte, or the hex fallback."""
        hex_id = f"{raw:02X}"
        table = getattr(self, kind, ())
        for choice in table:
            if choice.value == hex_id:
                return hex_id
        return hex_id

    def label(self, kind: str, value: str) -> str:
        """Return the human label for a stored option id."""
        needle = value.upper()
        for choice in getattr(self, kind, ()):
            if choice.value == needle:
                return choice.label
        return value
