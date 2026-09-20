"""Constants for the Sony VISCA integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sony_visca"

DEFAULT_PORT: Final = 52381
DEFAULT_CAMERA_ID: Final = 1
DEFAULT_MODEL: Final = "other"
DEFAULT_PAN_SPEED: Final = 0x0C
DEFAULT_TILT_SPEED: Final = 0x0C
DEFAULT_ZOOM_SPEED: Final = 1
DEFAULT_FOCUS_SPEED: Final = 1
DEFAULT_PRESET: Final = 1
DEFAULT_FRAME_RATE: Final = "60"
TALLY_KEEPALIVE_S: Final = 10.0

CONF_CAMERA_ID: Final = "camera_id"
CONF_MODEL: Final = "model"
CONF_VISCA_MODEL_ID: Final = "visca_model_id"
CONF_FRAME_RATE: Final = "frame_rate"

MANUFACTURER: Final = "Sony"

# VISCA over IP payload types
TYPE_COMMAND: Final = bytes((0x01, 0x00))
TYPE_INQUIRY: Final = bytes((0x01, 0x10))
TYPE_CONTROL: Final = bytes((0x02, 0x00))

# Control packet that resets the camera sequence counter.
SEQUENCE_RESET: Final = bytes.fromhex("020000010000000001")

TIMEOUT_MS: Final = 2000
COMMAND_COMPLETION_TIMEOUT_MS: Final = 30000
MAX_CONSECUTIVE_TIMEOUTS: Final = 10
INQUIRY_POLL_INTERVAL_S: Final = 2.0

SERVICE_PTZ: Final = "ptz"
SERVICE_ZOOM: Final = "zoom"
SERVICE_FOCUS: Final = "focus"
SERVICE_RECALL_PRESET: Final = "recall_preset"
SERVICE_SAVE_PRESET: Final = "save_preset"
SERVICE_PTZ_ABSOLUTE: Final = "ptz_absolute"
SERVICE_PTZ_RELATIVE: Final = "ptz_relative"
SERVICE_SEND_COMMAND: Final = "send_command"

ATTR_DIRECTION: Final = "direction"
ATTR_PAN_SPEED: Final = "pan_speed"
ATTR_TILT_SPEED: Final = "tilt_speed"
ATTR_ACTION: Final = "action"
ATTR_SPEED: Final = "speed"
ATTR_PRESET: Final = "preset"
ATTR_PAN: Final = "pan"
ATTR_TILT: Final = "tilt"
ATTR_UNITS: Final = "units"
ATTR_COMMAND: Final = "command"

FRAME_RATES: Final = ("60", "50", "24")
FOCUS_ACTIONS: Final = ("near", "far", "stop")
PTZ_UNITS: Final = ("raw", "degrees")

FOCUS_MODES: Final = ("auto", "manual")
ZOOM_MODES: Final = ("optical", "digital", "clear_image")
AF_MODES: Final = ("normal", "interval", "zoom_trigger")
AF_SENSITIVITIES: Final = ("normal", "low")
EXPOSURE_MODES: Final = (
    "auto",
    "manual",
    "shutter_priority",
    "iris_priority",
    "gain_priority",
    "bright",
)
WB_MODES: Final = ("auto1", "indoor", "outdoor", "one_push", "auto2", "manual")
ZOOM_SPEED_TYPES: Final = ("normal", "extended")
PRESET_SPEED_MODES: Final = ("compatible", "separate", "common")
PRESET_MODES: Final = ("mode1", "mode2", "trace")
WDR_MODES: Final = ("off", "low", "mid", "high")
PICTURE_EFFECTS: Final = ("off", "neg_art", "black_white")
TALLY_LEVELS: Final = ("off", "low", "high")

ZOOM_MODE_BYTES: Final[dict[str, int]] = {
    "digital": 0x02,
    "optical": 0x03,
    "clear_image": 0x04,
}
EXPOSURE_MODE_BYTES: Final[dict[str, int]] = {
    "auto": 0x00,
    "manual": 0x03,
    "shutter_priority": 0x0A,
    "iris_priority": 0x0B,
    "gain_priority": 0x0E,
    "bright": 0x0D,
}
WB_MODE_BYTES: Final[dict[str, int]] = {
    "auto1": 0x00,
    "indoor": 0x01,
    "outdoor": 0x02,
    "one_push": 0x03,
    "auto2": 0x04,
    "manual": 0x05,
}
AF_MODE_BYTES: Final[dict[str, int]] = {
    "normal": 0x00,
    "interval": 0x01,
    "zoom_trigger": 0x02,
}
WDR_MODE_BYTES: Final[dict[str, int]] = {
    "off": 0x00,
    "low": 0x01,
    "mid": 0x02,
    "high": 0x03,
}
PICTURE_EFFECT_BYTES: Final[dict[str, int]] = {
    "off": 0x00,
    "neg_art": 0x02,
    "black_white": 0x04,
}
TALLY_LEVEL_BYTES: Final[dict[str, int]] = {
    "off": 0x00,
    "low": 0x04,
    "high": 0x05,
}
PRESET_SPEED_MODE_BYTES: Final[dict[str, int]] = {
    "compatible": 0x00,
    "separate": 0x01,
    "common": 0x02,
}
PRESET_MODE_BYTES: Final[dict[str, int]] = {
    "mode1": 0x00,
    "mode2": 0x01,
    "trace": 0x10,
}
ZOOM_SPEED_TYPE_BYTES: Final[dict[str, int]] = {
    "normal": 0x08,
    "extended": 0x04,
}

PTZ_DIRECTIONS: Final[dict[str, tuple[int, int]]] = {
    "left": (0x01, 0x03),
    "right": (0x02, 0x03),
    "up": (0x03, 0x01),
    "down": (0x03, 0x02),
    "up_left": (0x01, 0x01),
    "up_right": (0x02, 0x01),
    "down_left": (0x01, 0x02),
    "down_right": (0x02, 0x02),
    "stop": (0x03, 0x03),
}

ZOOM_ACTIONS: Final = ("in", "out", "stop")

VISCA_ERRORS: Final[dict[int, str]] = {
    0x01: "Message length error",
    0x02: "Syntax error",
    0x03: "Command buffer full",
    0x04: "Command cancelled",
    0x05: "No socket",
    0x41: "Command not executable",
}
