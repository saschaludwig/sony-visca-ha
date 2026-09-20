"""Tests for high-level VISCA command validation."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.sony_visca.visca import ViscaClient, ViscaError


def test_invalid_preset_rejected() -> None:
    client = ViscaClient("127.0.0.1", 52381, 1)
    with pytest.raises(ViscaError, match="Preset"):
        asyncio.run(client.recall_preset(0))
    with pytest.raises(ViscaError, match="Preset"):
        asyncio.run(client.save_preset(65))


def test_invalid_direction_rejected() -> None:
    client = ViscaClient("127.0.0.1", 52381, 1)

    async def _connect_and_move() -> None:
        # Direction is validated before send().
        await client.pan_tilt("sideways")

    with pytest.raises(ViscaError, match="Unknown PTZ direction"):
        asyncio.run(_connect_and_move())


def test_invalid_zoom_action_rejected() -> None:
    client = ViscaClient("127.0.0.1", 52381, 1)
    with pytest.raises(ViscaError, match="Unknown zoom action"):
        asyncio.run(client.zoom("sideways"))


def test_invalid_focus_action_rejected() -> None:
    client = ViscaClient("127.0.0.1", 52381, 1)
    with pytest.raises(ViscaError, match="Unknown focus action"):
        asyncio.run(client.focus("sideways"))


def test_send_hex_rejects_invalid_input() -> None:
    client = ViscaClient("127.0.0.1", 52381, 1)
    with pytest.raises(ViscaError, match="hexadecimal"):
        asyncio.run(client.send_hex_command("not-hex"))
    with pytest.raises(ViscaError, match="empty"):
        asyncio.run(client.send_hex_command(""))


def test_payload_builders() -> None:
    from custom_components.sony_visca.visca import build_payload, build_pt_position_payload, nibble_bytes

    assert nibble_bytes(0x4000, 4) == (0x04, 0x00, 0x00, 0x00)
    assert build_payload(1, 0x01, 0x04, 0x38, 0x02) == bytes.fromhex("81 01 04 38 02 FF")
    payload = build_pt_position_payload(1, 0x02, 12, 0x0100, 0x0020, "0617")
    assert payload[:4] == bytes.fromhex("81 01 06 02")
    assert payload[4] == 12
    assert payload[-1] == 0xFF
