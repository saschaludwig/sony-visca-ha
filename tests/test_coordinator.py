"""Coordinator polling tests with a fake VISCA client."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.sony_visca.choices import CameraChoices
from custom_components.sony_visca.coordinator import SonyViscaCoordinator
from custom_components.sony_visca.visca import ViscaError


class _FakeHass:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.data: dict = {}
        self.config = SimpleNamespace(latitude=0, longitude=0)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, ...]] = []

    async def inquire(self, *command_bytes: int) -> bytes:
        self.calls.append(command_bytes)
        if command_bytes[:3] == (0x09, 0x7E, 0x7E) and command_bytes[3] == 0x00:
            return bytes.fromhex("90 50 04 00 00 00 01 00 0F 00 00 00 00 01 00 00")
        if command_bytes[:3] == (0x09, 0x7E, 0x7E) and command_bytes[3] == 0x02:
            return bytes.fromhex("90 50 01 00 00 00 00 00 07 00 00 00 00 00 00 00")
        return bytes.fromhex("90 50 00 00 00 00 00 00 00 00 00 00 00 00 00 00")

    async def inquire_pan_tilt(self) -> tuple[int, int]:
        return 123, 45

    async def inquire_power(self) -> bool:
        raise ViscaError("should not be needed when block 02 reports power")


def test_coordinator_merges_block_and_pan_tilt() -> None:
    async def _run() -> None:
        hass = _FakeHass()
        client = _FakeClient()
        coordinator = SonyViscaCoordinator(hass, client, "srg_x400", CameraChoices("1a", "60"))  # type: ignore[arg-type]
        data = await coordinator._async_update_data()
        assert data["zoom_position"] == 0x4000
        assert data["focus_mode"] == "auto"
        assert data["power"] is True
        assert data["pan_position"] == 123
        assert data["tilt_position"] == 45
        assert any(call[:3] == (0x09, 0x7E, 0x7E) for call in client.calls)

    asyncio.run(_run())
