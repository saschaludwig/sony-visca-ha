"""Unit tests for VISCA packet encoding and inquiry parsing."""

from __future__ import annotations

import pytest

from custom_components.sony_visca.const import SEQUENCE_RESET, TYPE_COMMAND, TYPE_INQUIRY
from custom_components.sony_visca.visca import (
    ViscaError,
    ViscaVersion,
    build_packet,
    build_payload,
    camera_address,
    config_unique_id,
    nibble_concat,
    parse_ip_packet,
    parse_pan_tilt_response,
    parse_power_response,
    parse_version_response,
    parse_zoom_response,
    resolve_probe_models,
    to_signed,
)


def test_camera_address() -> None:
    assert camera_address(1) == 0x81
    assert camera_address(7) == 0x87
    with pytest.raises(ValueError):
        camera_address(0)
    with pytest.raises(ValueError):
        camera_address(8)


def test_build_payload_power_on() -> None:
    assert build_payload(1, 0x01, 0x04, 0x00, 0x02) == bytes.fromhex("81 01 04 00 02 FF")


def test_build_payload_preset_recall() -> None:
    assert build_payload(1, 0x01, 0x04, 0x3F, 0x02, 0) == bytes.fromhex("81 01 04 3F 02 00 FF")


def test_build_packet_header() -> None:
    payload = bytes.fromhex("81 09 04 00 FF")
    packet = build_packet(TYPE_INQUIRY, 1, payload)
    assert packet[:2] == TYPE_INQUIRY
    assert int.from_bytes(packet[2:4], "big") == 5
    assert int.from_bytes(packet[4:8], "big") == 1
    assert packet[8:] == payload


def test_sequence_reset_bytes() -> None:
    assert SEQUENCE_RESET == bytes.fromhex("02 00 00 01 00 00 00 00 01")


def test_parse_ip_packet() -> None:
    payload = bytes.fromhex("90 50 02 FF")
    packet = build_packet(TYPE_INQUIRY, 42, payload)
    parsed = parse_ip_packet(packet)
    assert parsed is not None
    sequence, visca = parsed
    assert sequence == 42
    assert visca == payload


def test_parse_ip_packet_rejects_short_or_wrong_address() -> None:
    assert parse_ip_packet(b"\x00") is None
    payload = bytes.fromhex("80 50 02 FF")
    packet = build_packet(TYPE_COMMAND, 1, payload)
    assert parse_ip_packet(packet) is None


def test_parse_power_on_and_standby() -> None:
    assert parse_power_response(bytes.fromhex("90 50 02 FF")) is True
    assert parse_power_response(bytes.fromhex("90 50 03 FF")) is False
    with pytest.raises(ViscaError):
        parse_power_response(bytes.fromhex("90 60 02 FF"))


def test_parse_zoom_nibbles() -> None:
    assert parse_zoom_response(bytes.fromhex("90 50 00 04 00 00 FF")) == 0x0400


def test_parse_pan_tilt_standard_4_plus_4() -> None:
    payload = bytes.fromhex("90 50 00 01 02 03 00 04 05 06 FF")
    pan, tilt = parse_pan_tilt_response(payload)
    assert pan == 0x0123
    assert tilt == 0x0456


def test_parse_pan_tilt_signed_16bit() -> None:
    payload = bytes.fromhex("90 50 0F 0F 0F 0F 0F 0F 0F 0E FF")
    pan, tilt = parse_pan_tilt_response(payload)
    assert pan == -1
    assert tilt == -2


def test_parse_pan_tilt_x1000_5_plus_4() -> None:
    payload = bytes.fromhex("90 50 00 00 01 02 03 00 04 05 06 FF")
    pan, tilt = parse_pan_tilt_response(payload)
    assert pan == 0x0123
    assert tilt == 0x0456


def test_parse_pan_tilt_fr7_5_plus_5() -> None:
    payload = bytes.fromhex("90 50 00 00 01 02 03 00 00 04 05 06 FF")
    pan, tilt = parse_pan_tilt_response(payload)
    assert pan == 0x0123
    assert tilt == 0x0456


def test_nibble_concat_and_signed() -> None:
    assert nibble_concat(bytes((0x00, 0x0A, 0x0B)), [1, 2]) == 0xAB
    assert to_signed(0x7FFF, 16) == 0x7FFF
    assert to_signed(0x8000, 16) == -0x8000


def test_config_unique_id() -> None:
    assert config_unique_id("192.168.0.100", 52381, 1) == "192.168.0.100:52381:1"


def test_parse_version_sony_format() -> None:
    version = parse_version_response(bytes.fromhex("90 50 00 01 05 1E 01 00 02 FF"))
    assert version.vendor_id == 0x0001
    assert version.model_id_hex == "051E"
    assert version.rom_version == 0x0100
    assert version.sockets == 0x02


def test_resolve_probe_models_unique_and_family() -> None:
    unique, key = resolve_probe_models(ViscaVersion(0x0001, 0x0617, 0, 2))
    assert key == "srg_x400"
    assert [model.name for model in unique] == ["SRG-X400"]

    family, family_key = resolve_probe_models(ViscaVersion(0x0001, 0x0516, 0, 2))
    assert family_key is None
    assert [model.name for model in family] == ["SRG-201SE", "SRG-300SE", "SRG-301SE"]

    unknown, unknown_key = resolve_probe_models(ViscaVersion(0x0001, 0xFFFF, 0, 2))
    assert unknown == ()
    assert unknown_key is None
