"""Tests for model capability filtering."""

from __future__ import annotations

from custom_components.sony_visca.model_caps import (
    CAP_CLEAR_IMAGE_ZOOM,
    CAP_HIGH_RESOLUTION,
    CAP_PRESET_DRIVE_SPEED,
    CAP_SLOW_SHUTTER,
    CAP_SPOTLIGHT,
    CAP_TALLY,
    CAP_TELECONVERT,
    CAP_WB_ATW,
    CAP_WIDE_DYNAMIC,
    has_capability,
)
from custom_components.sony_visca.models import inquiry_group_for_model, resolve_model_key


def test_other_is_universal_only() -> None:
    assert has_capability("other", None) is True
    assert has_capability("other", CAP_TALLY) is False
    assert has_capability("other_min", CAP_TALLY) is False


def test_other_all_gets_gated_features() -> None:
    assert resolve_model_key("other_all") == "other_all"
    assert has_capability("other_all", CAP_TALLY) is True
    assert has_capability("other_all", CAP_TELECONVERT) is True


def test_spotlight_not_on_legacy_120dh() -> None:
    assert has_capability("srg_120dh", CAP_SPOTLIGHT) is False
    assert has_capability("srg_x400", CAP_SPOTLIGHT) is True
    assert has_capability("brc_x400", CAP_SPOTLIGHT) is True
    assert has_capability("srg_300se", CAP_SPOTLIGHT) is False


def test_tally_is_x400_not_srg_x400() -> None:
    assert has_capability("brc_x400", CAP_TALLY) is True
    assert has_capability("srg_x400", CAP_TALLY) is False


def test_extended_commands_hidden_on_legacy_120dh() -> None:
    assert has_capability("srg_120dh", CAP_PRESET_DRIVE_SPEED) is False
    assert has_capability("srg_x400", CAP_PRESET_DRIVE_SPEED) is True


def test_wdr_on_x1000_and_legacy() -> None:
    assert has_capability("srg_120dh", CAP_WIDE_DYNAMIC) is True
    assert has_capability("brc_x1000", CAP_WIDE_DYNAMIC) is True
    assert has_capability("srg_x400", CAP_WIDE_DYNAMIC) is False


def test_slow_shutter_not_on_x1000() -> None:
    assert has_capability("brc_x1000", CAP_SLOW_SHUTTER) is False
    assert has_capability("srg_120dh", CAP_SLOW_SHUTTER) is True
    assert has_capability("srg_x400", CAP_SLOW_SHUTTER) is True
    assert has_capability("srg_x40uh", CAP_SLOW_SHUTTER) is True


def test_clear_image_and_atw_are_modern_only() -> None:
    assert has_capability("srg_120dh", CAP_CLEAR_IMAGE_ZOOM) is False
    assert has_capability("srg_120dh", CAP_WB_ATW) is False
    assert has_capability("srg_x400", CAP_CLEAR_IMAGE_ZOOM) is True
    assert has_capability("srg_x400", CAP_WB_ATW) is True
    assert has_capability("brc_x1000", CAP_CLEAR_IMAGE_ZOOM) is True


def test_high_resolution_not_on_x40uh() -> None:
    assert has_capability("srg_x40uh", CAP_HIGH_RESOLUTION) is False
    assert has_capability("srg_x400", CAP_HIGH_RESOLUTION) is True
    assert has_capability("brc_x400", CAP_HIGH_RESOLUTION) is True
    assert has_capability("srg_120dh", CAP_HIGH_RESOLUTION) is False


def test_inquiry_groups() -> None:
    assert inquiry_group_for_model("srg_x400") == "1a"
    assert inquiry_group_for_model("srg_x40uh") == "1b"
    assert inquiry_group_for_model("brc_x1000") == "2"
    assert inquiry_group_for_model("srg_120dh") == "3a"
    assert inquiry_group_for_model("srg_a40") == "5"
