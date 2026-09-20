"""Button platform for Sony VISCA."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonyViscaConfigEntry
from .entity import SonyViscaEntity, SonyViscaRuntimeData
from .visca import ViscaClient, ViscaError


async def _home(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.pan_tilt_home()


async def _ptz_stop(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.pan_tilt_stop()


async def _zoom_stop(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.zoom_stop()


async def _preset_recall(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.recall_preset(client.speeds.preset)


async def _preset_save(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.save_preset(client.speeds.preset)


async def _focus_near(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.focus("near")


async def _focus_far(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.focus("far")


async def _focus_stop(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.focus("stop")


async def _focus_one_push(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.focus_one_push()


async def _focus_infinity(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.focus_infinity()


async def _wb_one_push(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.wb_one_push()


async def _pt_reset(client: ViscaClient, runtime: SonyViscaRuntimeData) -> None:
    await client.pan_tilt_reset()


@dataclass(kw_only=True)
class ViscaButtonEntityDescription(ButtonEntityDescription):
    """Button description with optional model gating."""

    capability: frozenset[str] | None = None


BUTTONS: tuple[
    tuple[ViscaButtonEntityDescription, Callable[[ViscaClient, SonyViscaRuntimeData], Awaitable[None]]],
    ...,
] = (
    (ViscaButtonEntityDescription(key="home", translation_key="home"), _home),
    (ViscaButtonEntityDescription(key="ptz_stop", translation_key="ptz_stop"), _ptz_stop),
    (ViscaButtonEntityDescription(key="zoom_stop", translation_key="zoom_stop"), _zoom_stop),
    (ViscaButtonEntityDescription(key="preset_recall", translation_key="preset_recall"), _preset_recall),
    (ViscaButtonEntityDescription(key="preset_save", translation_key="preset_save"), _preset_save),
    (ViscaButtonEntityDescription(key="focus_near", translation_key="focus_near"), _focus_near),
    (ViscaButtonEntityDescription(key="focus_far", translation_key="focus_far"), _focus_far),
    (ViscaButtonEntityDescription(key="focus_stop", translation_key="focus_stop"), _focus_stop),
    (ViscaButtonEntityDescription(key="focus_one_push", translation_key="focus_one_push"), _focus_one_push),
    (ViscaButtonEntityDescription(key="focus_infinity", translation_key="focus_infinity"), _focus_infinity),
    (ViscaButtonEntityDescription(key="wb_one_push", translation_key="wb_one_push"), _wb_one_push),
    (ViscaButtonEntityDescription(key="pt_reset", translation_key="pt_reset"), _pt_reset),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyViscaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VISCA button entities."""
    runtime = entry.runtime_data
    async_add_entities(
        SonyViscaButton(runtime, description, handler)
        for description, handler in BUTTONS
        if runtime.supported(description.capability)
    )


class SonyViscaButton(SonyViscaEntity, ButtonEntity):
    """Button that sends a VISCA command."""

    def __init__(
        self,
        runtime: SonyViscaRuntimeData,
        description: ViscaButtonEntityDescription,
        handler: Callable[[ViscaClient, SonyViscaRuntimeData], Awaitable[None]],
    ) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description
        self._handler = handler

    async def async_press(self) -> None:
        """Send the button command."""
        try:
            await self._handler(self.runtime.client, self.runtime)
        except ViscaError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
