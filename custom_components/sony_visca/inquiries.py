"""VISCA block-inquiry parser."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .choices import CameraChoices
from .visca import nibble_concat

WB_MODES = {
    0x00: "auto1",
    0x01: "indoor",
    0x02: "outdoor",
    0x03: "one_push",
    0x04: "auto2",
    0x05: "manual",
}
EXPOSURE_MODES = {
    0x00: "auto",
    0x03: "manual",
    0x0A: "shutter_priority",
    0x0B: "iris_priority",
    0x0D: "bright",
    0x0E: "gain_priority",
}
COLOR_MATRIX = {
    0: "std",
    1: "off",
    2: "high_sat",
    3: "fl_light",
    4: "movie",
    5: "still",
    6: "cinema",
    7: "pro",
    8: "itu709",
    9: "bw",
}
GAMMA_VALUES = {
    0: "std",
    1: "straight",
    2: "pattern",
    8: "movie",
    9: "still",
    0x0A: "cine1",
    0x0B: "cine2",
    0x0C: "cine3",
    0x0D: "cine4",
    0x0E: "itu709",
}
ZOOM_MODES = {0: "optical", 1: "digital", 2: "clear_image"}
AF_MODES = {0: "normal", 1: "interval", 2: "zoom_trigger"}
VE_MODES = {0: "off", 2: "on", 3: "manual"}
VE_BRIGHTNESS = {0: "very_dark", 1: "dark", 2: "standard", 3: "bright"}
BLACK_GAMMA_RANGE = {0: "low", 1: "mid", 2: "high"}
DETAIL_BANDWIDTH = {0: "standard", 1: "low", 2: "mid", 3: "high", 4: "wide"}
FR7_WB_MODES = {0x04: "atw", 0x05: "memory_a", 0x0A: "preset"}

ON_OFF_KEYS = frozenset(
    {
        "power",
        "high_resolution",
        "visibility_enhancer",
        "backlight_comp",
        "exposure_comp",
        "spotlight_comp",
        "flicker_cancel",
        "image_stabilizer",
        "icr",
        "wide_dynamic",
        "high_sensitivity",
        "image_flip",
        "defog",
        "knee_setting",
        "tele_convert",
        "tally_red",
        "auto_framing",
        "preset_recall_executing",
        "focus_cmd_executing",
        "zoom_cmd_executing",
    }
)


ExtractFn = Callable[[bytes], Any]


def _color_matrix_correction(resp: bytes, byte_high: int, byte_low: int) -> int:
    return (((resp[byte_high] << 4) & 0xF0) | (resp[byte_low] & 0x0F)) - 99


CUSTOM: dict[str, ExtractFn] = {
    "focus_near_limit": lambda r: (((r[6] & 0x0F) << 4) | (r[7] & 0x0F)) << 8,
    "picture_effect": lambda r: r[5] & 0x0F,
    "camera_id_reported": lambda r: f"{nibble_concat(r, [8, 9, 10, 11]):04X}",
    "color_rg": lambda r: _color_matrix_correction(r, 3, 4),
    "color_rb": lambda r: _color_matrix_correction(r, 5, 6),
    "color_gr": lambda r: _color_matrix_correction(r, 7, 8),
    "color_gb": lambda r: _color_matrix_correction(r, 9, 10),
    "color_br": lambda r: _color_matrix_correction(r, 11, 12),
    "color_bg": lambda r: _color_matrix_correction(r, 13, 14),
    "detail_hv_balance": lambda r: ((r[11] >> 3) & 0x07) - 2,
    "detail_bw_balance": lambda r: r[12] & 0x07,
    "black_level": lambda r: ((r[3] & 0x0F) << 4) | ((r[4] >> 3) & 0x0F),
    "gamma_offset": lambda r: (
        -((((r[7] >> 1) & 0x07) << 4) | ((r[8] >> 2) & 0x0F))
        if (r[7] >> 4) & 0x01
        else ((((r[7] >> 1) & 0x07) << 4) | ((r[8] >> 2) & 0x0F))
    ),
    "zoom_mode": lambda r: ZOOM_MODES.get(((r[13] >> 5) & 0x02) | ((r[13] >> 1) & 0x01)),
    "af_mode": lambda r: AF_MODES.get((r[13] >> 3) & 0x03),
    "wb_mode": lambda r: WB_MODES.get(r[6] & 0x0F),
    "exposure_mode": lambda r: EXPOSURE_MODES.get(r[8] & 0x0F),
    "color_matrix": lambda r: COLOR_MATRIX.get(((r[8] >> 5) & 0x03) | ((r[14] >> 2) & 0x1C)),
    "gamma": lambda r: GAMMA_VALUES.get((r[10] & 0x78) | ((r[13] >> 4) & 0x07)),
    "gamma_legacy": lambda r: GAMMA_VALUES.get((r[13] >> 4) & 0x07),
    "ve_mode": lambda r: VE_MODES.get(r[2] & 0x03),
    "ve_brightness_comp": lambda r: VE_BRIGHTNESS.get(r[5] & 0x03),
    "black_gamma_range": lambda r: BLACK_GAMMA_RANGE.get((r[7] >> 5) & 0x03),
    "detail_bandwidth": lambda r: DETAIL_BANDWIDTH.get(r[14] & 0x07),
    "fr7_on_off": lambda r: (r[2] & 0x0F) == 0x02,
    "fr7_focus_mode": lambda r: "auto" if (r[2] & 0x0F) == 0x02 else "manual",
    "fr7_wb_mode": lambda r: FR7_WB_MODES.get(r[2] & 0x0F),
}


@dataclass(frozen=True)
class InquiryField:
    """One field extracted from a VISCA inquiry payload."""

    variable: str
    kind: str
    indices: tuple[int, ...] = ()
    byte: int = 0
    bit: int = 0
    on: Any = True
    off: Any = False
    shift: int = 0
    mask: int = 0xFF
    center: int = 0
    mapping: dict[int, Any] | None = None
    choice_key: str | None = None
    custom: str | None = None


@dataclass(frozen=True)
class InquiryBlock:
    """A named inquiry block or single inquiry."""

    key: str
    name: str
    min_length: int
    command: tuple[int, ...]
    fields: tuple[InquiryField, ...]


def _flag(variable: str, byte: int, bit: int, on: Any = True, off: Any = False) -> InquiryField:
    return InquiryField(variable, "flag", byte=byte, bit=bit, on=on, off=off)


def _bits(variable: str, byte: int, shift: int = 0, mask: int = 0xFF) -> InquiryField:
    return InquiryField(variable, "bits", byte=byte, shift=shift, mask=mask)


def _offset(variable: str, byte: int, mask: int = 0x0F, center: int = 7, shift: int = 0) -> InquiryField:
    return InquiryField(variable, "offset", byte=byte, mask=mask, center=center, shift=shift)


def _nibble(variable: str, *indices: int) -> InquiryField:
    return InquiryField(variable, "nibble", indices=indices)


def _choice(variable: str, byte: int, mask: int, choice_key: str) -> InquiryField:
    return InquiryField(variable, "choice", byte=byte, mask=mask, choice_key=choice_key)


def _custom(variable: str, name: str) -> InquiryField:
    return InquiryField(variable, "custom", custom=name)


BLOCK_00_LENS = (
    _nibble("zoom_position", 2, 3, 4, 5),
    _custom("focus_near_limit", "focus_near_limit"),
    _nibble("focus_position", 8, 9, 10, 11),
    _flag("focus_mode", 13, 0, on="auto", off="manual"),
    _custom("zoom_mode", "zoom_mode"),
    _custom("af_mode", "af_mode"),
    _flag("af_sensitivity", 13, 2, on="normal", off="low"),
    _flag("preset_recall_executing", 14, 2),
    _flag("focus_cmd_executing", 14, 1),
    _flag("zoom_cmd_executing", 14, 0),
)

BLOCK_01_X400 = (
    _nibble("red_gain", 2, 3),
    _nibble("blue_gain", 4, 5),
    _custom("wb_mode", "wb_mode"),
    _bits("wb_speed", 7, 4, 0x07),
    _offset("detail_level", 7),
    _custom("color_matrix", "color_matrix"),
    _custom("exposure_mode", "exposure_mode"),
    _flag("high_resolution", 9, 5),
    _flag("visibility_enhancer", 9, 4),
    _flag("backlight_comp", 9, 2),
    _flag("exposure_comp", 9, 1),
    _flag("slow_shutter", 9, 0, on=True, off=False),
    _choice("shutter", 10, 0x3F, "shutter"),
    _choice("iris", 11, 0x1F, "iris"),
    _bits("iris_raw", 11, 0, 0x1F),
    _choice("gain", 12, 0x1F, "gain"),
    _offset("exposure_comp_level", 14),
)

BLOCK_01_X40UH = (
    _nibble("red_gain", 2, 3),
    _nibble("blue_gain", 4, 5),
    _custom("wb_mode", "wb_mode"),
    _bits("wb_speed", 7, 4, 0x07),
    _offset("detail_level", 7),
    _custom("exposure_mode", "exposure_mode"),
    _flag("high_sensitivity", 9, 5),
    _flag("visibility_enhancer", 9, 4),
    _flag("backlight_comp", 9, 2),
    _flag("exposure_comp", 9, 1),
    _flag("slow_shutter", 9, 0),
    _choice("shutter", 10, 0x3F, "shutter"),
    _choice("iris", 11, 0x1F, "iris"),
    _bits("iris_raw", 11, 0, 0x1F),
    _choice("gain", 12, 0x1F, "gain"),
    _offset("exposure_comp_level", 14),
)

BLOCK_01_X1000 = (
    _nibble("red_gain", 2, 3),
    _nibble("blue_gain", 4, 5),
    _custom("wb_mode", "wb_mode"),
    _custom("exposure_mode", "exposure_mode"),
    _flag("wide_dynamic", 9, 4),
    _flag("backlight_comp", 9, 2),
    _flag("exposure_comp", 9, 1),
    _choice("shutter", 10, 0x1F, "shutter"),
    _choice("iris", 11, 0x1F, "iris"),
    _bits("iris_raw", 11, 0, 0x1F),
    _choice("gain", 12, 0x1F, "gain"),
    _offset("exposure_comp_level", 14),
)

BLOCK_01_LEGACY = (
    _nibble("red_gain", 2, 3),
    _nibble("blue_gain", 4, 5),
    _custom("wb_mode", "wb_mode"),
    _custom("exposure_mode", "exposure_mode"),
    _flag("high_resolution", 9, 5),
    _flag("wide_dynamic", 9, 4),
    _flag("backlight_comp", 9, 2),
    _flag("exposure_comp", 9, 1),
    _flag("slow_shutter", 9, 0),
    _choice("shutter", 10, 0x1F, "shutter"),
    _choice("iris", 11, 0x1F, "iris"),
    _bits("iris_raw", 11, 0, 0x1F),
    _choice("gain", 12, 0x0F, "gain"),
    _choice("brightness", 13, 0x1F, "brightness"),
    _offset("exposure_comp_level", 14),
)

BLOCK_01_300H = (
    _nibble("red_gain", 2, 3),
    _nibble("blue_gain", 4, 5),
    _custom("wb_mode", "wb_mode"),
    _bits("aperture_gain", 7, 0, 0x0F),
    _custom("exposure_mode", "exposure_mode"),
    _flag("high_resolution", 9, 5),
    _flag("wide_dynamic", 9, 4),
    _flag("backlight_comp", 9, 2),
    _flag("exposure_comp", 9, 1),
    _flag("slow_shutter", 9, 0),
    _choice("shutter", 10, 0x3F, "shutter"),
    _choice("iris", 11, 0x1F, "iris"),
    _bits("iris_raw", 11, 0, 0x1F),
    _choice("gain", 12, 0x1F, "gain"),
    _choice("brightness", 13, 0x1F, "brightness"),
    _offset("exposure_comp_level", 14),
)

BLOCK_02_X400 = (
    _flag("spotlight_comp", 2, 5),
    _flag("flicker_cancel", 2, 4),
    _flag("auto_icr", 2, 2),
    _flag("power", 2, 0),
    _flag("image_stabilizer", 3, 6),
    _flag("icr", 3, 4),
    _custom("picture_effect", "picture_effect"),
    _offset("wb_offset", 7),
    _custom("camera_id_reported", "camera_id_reported"),
    _flag("knee_mode_manual", 13, 4),
    _offset("knee_slope", 13),
    _flag("knee_setting", 14, 4),
    _bits("knee_point", 14, 0, 0x0F),
)

BLOCK_02_X40UH = (
    _flag("spotlight_comp", 2, 5),
    _flag("flicker_cancel", 2, 4),
    _flag("auto_icr", 2, 2),
    _flag("power", 2, 0),
    _flag("image_stabilizer", 3, 6),
    _flag("icr", 3, 4),
    _offset("wb_offset", 7),
    _custom("camera_id_reported", "camera_id_reported"),
)

BLOCK_02_X1000 = (
    _flag("spotlight_comp", 2, 5),
    _flag("flicker_cancel", 2, 4),
    _flag("power", 2, 0),
    _flag("icr", 3, 4),
    _custom("picture_effect", "picture_effect"),
    _offset("wb_offset", 7),
    _flag("image_stabilizer", 12, 1),
    _flag("knee_mode_manual", 13, 4),
    _offset("knee_slope", 13),
    _flag("knee_setting", 14, 4),
    _bits("knee_point", 14, 0, 0x0F),
)

BLOCK_02_120DH = (
    _flag("power", 2, 0),
    _custom("picture_effect", "picture_effect"),
    _custom("camera_id_reported", "camera_id_reported"),
)

BLOCK_02_300SE = (
    _flag("auto_icr", 2, 2),
    _flag("power", 2, 0),
    _flag("image_stabilizer", 3, 6),
    _flag("icr", 3, 4),
    _custom("picture_effect", "picture_effect"),
    _custom("camera_id_reported", "camera_id_reported"),
)

BLOCK_02_300H = (
    _flag("auto_icr", 2, 2),
    _flag("power", 2, 0),
    _flag("image_stabilizer", 3, 6),
    _flag("image_stabilizer_hold", 3, 5),
    _flag("icr", 3, 4),
    _custom("picture_effect", "picture_effect"),
    _custom("camera_id_reported", "camera_id_reported"),
)

BLOCK_03_X400 = (
    _nibble("af_op_time", 4, 5),
    _nibble("af_stay_time", 6, 7),
    _bits("nr_2d_level", 8, 4, 0x07),
    _bits("nr_3d_level", 9, 4, 0x07),
    _custom("gamma", "gamma"),
    _flag("image_flip", 10, 0),
    _bits("color_gain", 11, 3, 0x0F),
    _bits("ae_speed", 12, 0, 0x3F),
    _flag("high_sensitivity", 13, 3),
    _bits("nr_level", 13, 0, 0x07),
    _bits("chroma_suppress", 14, 4, 0x07),
    _choice("gain_limit", 14, 0x0F, "gain"),
)

BLOCK_03_X40UH = (
    _nibble("af_op_time", 4, 5),
    _nibble("af_stay_time", 6, 7),
    _bits("nr_2d_level", 8, 4, 0x07),
    _bits("nr_3d_level", 9, 4, 0x07),
    _flag("image_flip", 10, 0),
    _bits("ae_speed", 12, 0, 0x3F),
    _flag("high_sensitivity", 13, 3),
    _bits("nr_level", 13, 0, 0x07),
)

BLOCK_03_X1000 = (
    _bits("nr_2d_level", 8, 4, 0x07),
    _bits("nr_3d_level", 9, 4, 0x07),
    _custom("gamma", "gamma"),
    _flag("image_flip", 10, 0),
    _bits("color_gain", 11, 3, 0x0F),
    _bits("ae_speed", 12, 0, 0x3F),
    _bits("nr_level", 13, 0, 0x07),
    _bits("chroma_suppress", 14, 4, 0x07),
    _choice("gain_limit", 14, 0x0F, "gain"),
)

BLOCK_03_A40 = (
    _nibble("af_op_time", 4, 5),
    _nibble("af_stay_time", 6, 7),
    _bits("nr_2d_level", 8, 4, 0x07),
    _bits("nr_3d_level", 9, 4, 0x07),
    _flag("image_flip", 10, 0),
    _bits("ae_speed", 12, 0, 0x3F),
    _flag("high_sensitivity", 13, 3),
    _bits("nr_level", 13, 0, 0x07),
    _bits("chroma_suppress", 14, 4, 0x07),
    _choice("gain_limit", 14, 0x0F, "gain"),
)

BLOCK_03_LEGACY = (
    _nibble("digital_zoom_pos", 2, 3),
    _nibble("af_op_time", 4, 5),
    _nibble("af_stay_time", 6, 7),
    _bits("color_gain", 11, 3, 0x0F),
    _custom("gamma", "gamma_legacy"),
    _flag("high_sensitivity", 13, 3),
    _bits("nr_level", 13, 0, 0x07),
    _bits("chroma_suppress", 14, 4, 0x07),
    _choice("gain_limit", 14, 0x0F, "gain"),
)

BLOCK_03_300H = (
    _nibble("af_op_time", 4, 5),
    _nibble("af_stay_time", 6, 7),
    _bits("color_gain", 11, 0, 0x0F),
    _custom("gamma", "gamma_legacy"),
    _flag("high_sensitivity", 13, 3),
    _bits("nr_level", 13, 0, 0x07),
    _bits("chroma_suppress", 14, 4, 0x07),
    _choice("gain_limit", 14, 0x0F, "gain"),
)

BLOCK_04_X400 = (
    _custom("ve_mode", "ve_mode"),
    _custom("black_level", "black_level"),
    _bits("ve_level", 4, 0, 0x07),
    _offset("black_gamma_level", 5, shift=2),
    _custom("ve_brightness_comp", "ve_brightness_comp"),
    _offset("gamma_level", 6, shift=2),
    _bits("ve_comp_level", 6, 0, 0x03),
    _custom("black_gamma_range", "black_gamma_range"),
    _custom("gamma_offset", "gamma_offset"),
    _flag("defog", 7, 0),
    _bits("defog_level", 8, 0, 0x03),
    _choice("min_shutter", 9, 0x3F, "shutter"),
    _choice("max_shutter", 10, 0x3F, "shutter"),
    _custom("detail_hv_balance", "detail_hv_balance"),
    _bits("detail_crispening", 11, 0, 0x07),
    _bits("detail_limit", 12, 3, 0x07),
    _custom("detail_bw_balance", "detail_bw_balance"),
    _bits("detail_highlight", 13, 3, 0x07),
    _bits("detail_super_low", 13, 0, 0x07),
    _flag("detail_mode_manual", 14, 3),
    _custom("detail_bandwidth", "detail_bandwidth"),
)

BLOCK_04_X40UH = (
    _custom("ve_mode", "ve_mode"),
    _bits("ve_level", 4, 0, 0x07),
    _custom("ve_brightness_comp", "ve_brightness_comp"),
    _bits("ve_comp_level", 6, 0, 0x03),
    _choice("min_shutter", 9, 0x3F, "shutter"),
    _choice("max_shutter", 10, 0x3F, "shutter"),
    _custom("detail_hv_balance", "detail_hv_balance"),
    _bits("detail_crispening", 11, 0, 0x07),
    _bits("detail_limit", 12, 3, 0x07),
    _custom("detail_bw_balance", "detail_bw_balance"),
    _bits("detail_highlight", 13, 3, 0x07),
    _bits("detail_super_low", 13, 0, 0x07),
    _flag("detail_mode_manual", 14, 3),
    _custom("detail_bandwidth", "detail_bandwidth"),
)

BLOCK_04_A40 = (
    _custom("ve_mode", "ve_mode"),
    _bits("ve_level", 4, 0, 0x07),
    _custom("ve_brightness_comp", "ve_brightness_comp"),
    _bits("ve_comp_level", 6, 0, 0x03),
    _flag("defog", 7, 0),
    _bits("defog_level", 8, 0, 0x03),
    _choice("min_shutter", 9, 0x3F, "shutter"),
    _choice("max_shutter", 10, 0x3F, "shutter"),
    _custom("detail_hv_balance", "detail_hv_balance"),
    _bits("detail_crispening", 11, 0, 0x07),
    _bits("detail_limit", 12, 3, 0x07),
    _custom("detail_bw_balance", "detail_bw_balance"),
    _bits("detail_highlight", 13, 3, 0x07),
    _bits("detail_super_low", 13, 0, 0x07),
    _flag("detail_mode_manual", 14, 3),
    _custom("detail_bandwidth", "detail_bandwidth"),
)

BLOCK_04_LEGACY = (_flag("defog", 7, 0),)
BLOCK_05_LEGACY = (_offset("color_hue", 2),)
BLOCK_05_X400 = (
    _offset("color_hue", 2),
    _custom("color_rg", "color_rg"),
    _custom("color_rb", "color_rb"),
    _custom("color_gr", "color_gr"),
    _custom("color_gb", "color_gb"),
    _custom("color_br", "color_br"),
    _custom("color_bg", "color_bg"),
)


def _block(key: str, name: str, fields: tuple[InquiryField, ...], command: tuple[int, ...]) -> InquiryBlock:
    return InquiryBlock(key=key, name=name, min_length=16, command=command, fields=fields)


def _block_inq(block: int) -> tuple[int, ...]:
    return (0x09, 0x7E, 0x7E, block)


def _group_blocks(
    block01: tuple[InquiryField, ...],
    block02: tuple[InquiryField, ...],
    block03: tuple[InquiryField, ...] | None = None,
    block04: tuple[InquiryField, ...] | None = None,
    block05: tuple[InquiryField, ...] | None = None,
) -> tuple[InquiryBlock, ...]:
    blocks = [
        _block("097e7e00", "Lens Control", BLOCK_00_LENS, _block_inq(0x00)),
        _block("097e7e01", "Camera Control", block01, _block_inq(0x01)),
        _block("097e7e02", "Other", block02, _block_inq(0x02)),
    ]
    if block03 is not None:
        blocks.append(_block("097e7e03", "Enlargement 1", block03, _block_inq(0x03)))
    if block04 is not None:
        blocks.append(_block("097e7e04", "Enlargement 2", block04, _block_inq(0x04)))
    if block05 is not None:
        blocks.append(_block("097e7e05", "Enlargement 3", block05, _block_inq(0x05)))
    return tuple(blocks)


BLOCKS_X400 = _group_blocks(BLOCK_01_X400, BLOCK_02_X400, BLOCK_03_X400, BLOCK_04_X400, BLOCK_05_X400)
BLOCKS_X40UH = _group_blocks(BLOCK_01_X40UH, BLOCK_02_X40UH, BLOCK_03_X40UH, BLOCK_04_X40UH)
BLOCKS_X1000 = _group_blocks(BLOCK_01_X1000, BLOCK_02_X1000, BLOCK_03_X1000)
BLOCKS_A40 = _group_blocks(BLOCK_01_X40UH, BLOCK_02_X40UH, BLOCK_03_A40, BLOCK_04_A40)
BLOCKS_120DH = _group_blocks(BLOCK_01_LEGACY, BLOCK_02_120DH, BLOCK_03_LEGACY, BLOCK_04_LEGACY, BLOCK_05_LEGACY)
BLOCKS_300SE = _group_blocks(BLOCK_01_LEGACY, BLOCK_02_300SE, BLOCK_03_LEGACY, BLOCK_04_LEGACY, BLOCK_05_LEGACY)
BLOCKS_360SHE = _group_blocks(BLOCK_01_LEGACY, BLOCK_02_300SE, BLOCK_03_LEGACY)
BLOCKS_300H = _group_blocks(BLOCK_01_300H, BLOCK_02_300H, BLOCK_03_300H, BLOCK_04_LEGACY, BLOCK_05_LEGACY)

BLOCKS_FR7 = (
    InquiryBlock("090447", "Zoom", 7, (0x09, 0x04, 0x47), (_nibble("zoom_position", 2, 3, 4, 5),)),
    InquiryBlock("090448", "Focus", 7, (0x09, 0x04, 0x48), (_nibble("focus_position", 2, 3, 4, 5),)),
    InquiryBlock("090438", "Focus Mode", 4, (0x09, 0x04, 0x38), (_custom("focus_mode", "fr7_focus_mode"),)),
    InquiryBlock("090400", "Power", 4, (0x09, 0x04, 0x00), (_custom("power", "fr7_on_off"),)),
    InquiryBlock("090435", "WB", 4, (0x09, 0x04, 0x35), (_custom("wb_mode", "fr7_wb_mode"),)),
    InquiryBlock("090433", "Backlight", 4, (0x09, 0x04, 0x33), (_custom("backlight_comp", "fr7_on_off"),)),
    InquiryBlock("09043a", "Spotlight", 4, (0x09, 0x04, 0x3A), (_custom("spotlight_comp", "fr7_on_off"),)),
)

GROUP_BLOCKS: dict[str, tuple[InquiryBlock, ...]] = {
    "1a": BLOCKS_X400,
    "1b": BLOCKS_X40UH,
    "2": BLOCKS_X1000,
    "3a": BLOCKS_120DH,
    "3b": BLOCKS_300SE,
    "3c": BLOCKS_360SHE,
    "3d": BLOCKS_300H,
    "4": BLOCKS_FR7,
    "5": BLOCKS_A40,
    "6": BLOCKS_FR7,
}


def inquiry_blocks_for_group(group: str) -> tuple[InquiryBlock, ...]:
    """Return high-priority inquiry blocks for a model group."""
    return GROUP_BLOCKS.get(group, BLOCKS_X400)


def uses_block_inquiries(group: str) -> bool:
    """Return True when the group polls 09 7E 7E block inquiries."""
    return group not in {"4", "6"}


def extract_field(field: InquiryField, payload: bytes, choices: CameraChoices | None) -> Any:
    """Extract one inquiry field from a VISCA payload."""
    if field.kind == "nibble":
        return nibble_concat(payload, list(field.indices))
    if field.kind == "flag":
        return field.on if (payload[field.byte] >> field.bit) & 0x01 else field.off
    if field.kind == "bits":
        return (payload[field.byte] >> field.shift) & field.mask
    if field.kind == "offset":
        return ((payload[field.byte] >> field.shift) & field.mask) - field.center
    if field.kind == "choice":
        raw = payload[field.byte] & field.mask
        if choices is None or field.choice_key is None:
            return f"{raw:02X}"
        return choices.lookup(field.choice_key, raw)
    if field.kind == "custom" and field.custom:
        extractor = CUSTOM[field.custom]
        return extractor(payload)
    return None


def parse_inquiry_block(
    block: InquiryBlock,
    payload: bytes,
    choices: CameraChoices | None = None,
) -> dict[str, Any]:
    """Parse an inquiry payload into coordinator state keys."""
    if len(payload) < block.min_length:
        return {}
    parsed: dict[str, Any] = {}
    for field in block.fields:
        try:
            value = extract_field(field, payload, choices)
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        if value is not None:
            parsed[field.variable] = value
    return parsed


def parse_on_off_inquiry(payload: bytes) -> bool | None:
    """Parse a 02=On / 03=Off inquiry reply."""
    if len(payload) < 4 or payload[1] != 0x50:
        return None
    value = payload[2] & 0x0F
    if value == 0x02:
        return True
    if value == 0x03:
        return False
    return None


@dataclass
class LowPriorityInquiry:
    """A rotating extra inquiry gated by a capability set."""

    key: str
    command: tuple[int, ...]
    capability: frozenset[str] | None
    apply: Callable[[bytes, dict[str, Any]], None]


def _apply_on_off(data_key: str, on_value: Any = True, off_value: Any = False):
    def _apply(payload: bytes, data: dict[str, Any]) -> None:
        if len(payload) < 4 or payload[1] != 0x50:
            return
        value = payload[2] & 0x0F
        if value == 0x02:
            data[data_key] = on_value
        elif value == 0x03:
            data[data_key] = off_value

    return _apply


def _apply_ramp(payload: bytes, data: dict[str, Any]) -> None:
    if len(payload) < 4 or payload[1] != 0x50:
        return
    data["ramp_curve"] = payload[2] & 0x0F


def _apply_near_limit(payload: bytes, data: dict[str, Any]) -> None:
    if len(payload) < 7 or payload[1] != 0x50:
        return
    data["focus_near_limit"] = nibble_concat(payload, [2, 3, 4, 5])


def _apply_auto_framing(payload: bytes, data: dict[str, Any]) -> None:
    if len(payload) < 4 or payload[1] != 0x50:
        return
    data["auto_framing"] = (payload[2] & 0x0F) == 0x01


LOW_PRIORITY_INQUIRIES: tuple[LowPriorityInquiry, ...] = (
    LowPriorityInquiry("090644", (0x09, 0x06, 0x44), None, _apply_on_off("pt_slow")),
    LowPriorityInquiry("090631", (0x09, 0x06, 0x31), None, _apply_ramp),
    LowPriorityInquiry("097e010a", (0x09, 0x7E, 0x01, 0x0A), None, _apply_on_off("tally_red")),
    LowPriorityInquiry("090428", (0x09, 0x04, 0x28), None, _apply_near_limit),
    LowPriorityInquiry("097e043a", (0x09, 0x7E, 0x04, 0x3A), None, _apply_auto_framing),
)
