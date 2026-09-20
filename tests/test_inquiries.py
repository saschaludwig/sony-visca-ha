"""Tests for VISCA block-inquiry parsing."""

from __future__ import annotations

from custom_components.sony_visca.choices import CameraChoices
from custom_components.sony_visca.inquiries import (
    inquiry_blocks_for_group,
    parse_inquiry_block,
    uses_block_inquiries,
)


def _payload(hex_body: str) -> bytes:
    return bytes.fromhex(hex_body)


def test_group_1a_uses_block_inquiries() -> None:
    blocks = inquiry_blocks_for_group("1a")
    assert uses_block_inquiries("1a") is True
    assert [block.key for block in blocks] == [
        "097e7e00",
        "097e7e01",
        "097e7e02",
        "097e7e03",
        "097e7e04",
        "097e7e05",
    ]


def test_parse_block00_lens_group_1a() -> None:
    block = next(item for item in inquiry_blocks_for_group("1a") if item.key == "097e7e00")
    # y0 50 zz zz zz zz nn nn ff ff ff ff 00 flags exec FF  (16 bytes min)
    payload = _payload("90 50 04 00 00 00 01 00 0F 00 00 00 00 01 00 00")
    parsed = parse_inquiry_block(block, payload)
    assert parsed["zoom_position"] == 0x4000
    assert parsed["focus_position"] == 0xF000
    assert parsed["focus_mode"] == "auto"
    assert parsed["zoom_mode"] == "optical"


def test_parse_block01_camera_group_1a() -> None:
    block = next(item for item in inquiry_blocks_for_group("1a") if item.key == "097e7e01")
    choices = CameraChoices("1a", "60")
    payload = _payload("90 50 00 08 00 07 00 27 00 02 12 15 05 00 07 00")
    parsed = parse_inquiry_block(block, payload, choices)
    assert parsed["red_gain"] == 0x08
    assert parsed["blue_gain"] == 0x07
    assert parsed["wb_mode"] == "auto1"
    assert parsed["exposure_mode"] == "auto"
    assert parsed["exposure_comp"] is True
    assert parsed["shutter"] == "12"
    assert parsed["iris"] == "15"
    assert parsed["gain"] == "05"
    assert parsed["exposure_comp_level"] == 0


def test_parse_block02_power_group_1a() -> None:
    block = next(item for item in inquiry_blocks_for_group("1a") if item.key == "097e7e02")
    payload = _payload("90 50 01 00 00 00 00 00 07 00 00 00 00 00 00 00")
    parsed = parse_inquiry_block(block, payload)
    assert parsed["power"] is True


def test_parse_legacy_block01_group_3a() -> None:
    block = next(item for item in inquiry_blocks_for_group("3a") if item.key == "097e7e01")
    choices = CameraChoices("3a", "60")
    payload = _payload("90 50 00 04 00 05 05 00 03 10 0A 0C 04 11 07 00")
    parsed = parse_inquiry_block(block, payload, choices)
    assert parsed["wb_mode"] == "manual"
    assert parsed["exposure_mode"] == "manual"
    assert parsed["wide_dynamic"] is True
    assert "brightness" in parsed


def test_fr7_uses_individual_inquiries() -> None:
    assert uses_block_inquiries("4") is False
    blocks = inquiry_blocks_for_group("4")
    assert any(block.key == "090400" for block in blocks)
