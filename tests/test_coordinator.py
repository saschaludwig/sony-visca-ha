"""Coordinator polling tests with a fake VISCA client."""

from __future__ import annotations

import asyncio
import pytest

pytest.importorskip("homeassistant")

from custom_components.sony_visca.choices import CameraChoices
from custom_components.sony_visca.coordinator import SonyViscaCoordinator, _LOW_PRIORITY_CAPS
from custom_components.sony_visca.inquiries import LOW_PRIORITY_INQUIRIES, inquiry_blocks_for_group
from custom_components.sony_visca.model_caps import has_capability
from custom_components.sony_visca.models import inquiry_group_for_model
from custom_components.sony_visca.visca import ViscaError


def _coordinator(client: object, data: dict | None = None) -> SonyViscaCoordinator:
    """Build a coordinator without Home Assistant's DataUpdateCoordinator init."""
    coordinator = SonyViscaCoordinator.__new__(SonyViscaCoordinator)
    coordinator.client = client  # type: ignore[assignment]
    coordinator.model = "srg_x400"
    coordinator.choices = CameraChoices("1a", "60")
    coordinator.group = inquiry_group_for_model("srg_x400")
    coordinator.blocks = inquiry_blocks_for_group(coordinator.group)
    coordinator._low_priority = [
        inquiry
        for inquiry in LOW_PRIORITY_INQUIRIES
        if has_capability("srg_x400", _LOW_PRIORITY_CAPS.get(inquiry.key))
    ]
    coordinator._low_index = 0
    coordinator.data = data
    return coordinator


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
        self.calls.append((0x09, 0x04, 0x00))
        return True


def test_coordinator_merges_block_and_pan_tilt() -> None:
    async def _run() -> None:
        client = _FakeClient()
        coordinator = _coordinator(client)
        data = await coordinator._async_update_data()
        assert data["zoom_position"] == 0x4000
        assert data["focus_mode"] == "auto"
        assert data["power"] is True
        assert data["pan_position"] == 123
        assert data["tilt_position"] == 45
        assert any(call[:3] == (0x09, 0x7E, 0x7E) for call in client.calls)

    asyncio.run(_run())


class _StandbyClient(_FakeClient):
    def __init__(self, power_on: bool = False, power_error: bool = False) -> None:
        super().__init__()
        self.power_on = power_on
        self.power_error = power_error
        self.power_calls = 0

    async def inquire(self, *command_bytes: int) -> bytes:
        self.calls.append(command_bytes)
        raise ViscaError("standby: block inquiry not answered")

    async def inquire_pan_tilt(self) -> tuple[int, int]:
        raise ViscaError("standby: pan/tilt not answered")

    async def inquire_power(self) -> bool:
        self.power_calls += 1
        if self.power_error:
            raise ViscaError("standby: power inquiry timeout")
        return self.power_on


def test_coordinator_standby_skips_block_inquiries() -> None:
    async def _run() -> None:
        client = _StandbyClient(power_on=False)
        coordinator = _coordinator(client, {"power": False, "zoom_position": 0x4000})
        data = await coordinator._async_update_data()
        assert data == {"power": False}
        assert client.calls == []
        assert client.power_calls == 1

    asyncio.run(_run())


def test_coordinator_standby_timeout_keeps_power_off() -> None:
    async def _run() -> None:
        client = _StandbyClient(power_error=True)
        coordinator = _coordinator(client, {"power": False})
        data = await coordinator._async_update_data()
        assert data == {"power": False}
        assert client.calls == []
        assert client.power_calls == 1

    asyncio.run(_run())


def test_coordinator_wakes_from_standby_and_polls_blocks() -> None:
    async def _run() -> None:
        client = _FakeClient()
        coordinator = _coordinator(client, {"power": False})

        async def _power_on() -> bool:
            return True

        client.inquire_power = _power_on  # type: ignore[method-assign]
        data = await coordinator._async_update_data()
        assert data["power"] is True
        assert data["pan_position"] == 123
        assert any(call[:3] == (0x09, 0x7E, 0x7E) for call in client.calls)

    asyncio.run(_run())


class _BlockFailClient(_FakeClient):
    async def inquire(self, *command_bytes: int) -> bytes:
        self.calls.append(command_bytes)
        raise ViscaError("timeout")

    async def inquire_pan_tilt(self) -> tuple[int, int]:
        raise ViscaError("timeout")

    async def inquire_power(self) -> bool:
        return False


def test_coordinator_waking_aborts_block_poll_after_first_timeout() -> None:
    async def _run() -> None:
        client = _BlockFailClient()

        async def _power_on() -> bool:
            return True

        client.inquire_power = _power_on  # type: ignore[method-assign]
        coordinator = _coordinator(client, {"power": True})
        data = await coordinator._async_update_data()
        assert data["power"] is True
        assert len(client.calls) == 1
        assert client.calls[0][:3] == (0x09, 0x7E, 0x7E)

    asyncio.run(_run())


def test_coordinator_full_poll_checks_power_before_blocks() -> None:
    async def _run() -> None:
        client = _BlockFailClient()
        coordinator = _coordinator(client, {"power": True, "zoom_position": 1})
        data = await coordinator._async_update_data()
        assert data == {"power": False}
        assert client.calls == []

    asyncio.run(_run())
