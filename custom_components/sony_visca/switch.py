"""Switch platform for Sony VISCA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonyViscaConfigEntry
from .const import TALLY_KEEPALIVE_S
from .entity import SonyViscaEntity, SonyViscaRuntimeData, filter_supported
from .model_caps import (
    CAP_ADVANCED,
    CAP_ADVANCED_LEGACY,
    CAP_AUTO_FRAMING,
    CAP_HIGH_RESOLUTION,
    CAP_ICR,
    CAP_PT_SLOW,
    CAP_SLOW_SHUTTER,
    CAP_SPOTLIGHT,
    CAP_TALLY,
    CAP_TELECONVERT,
    CAP_WIDE_DYNAMIC,
    CAP_X400_CORE_X40UH,
    CAP_X400_ONLY,
    CAP_X400_X1000,
    CAP_X400_X40UH,
    CAP_X400_X40UH_SE,
)
from .visca import ViscaError


@dataclass(kw_only=True)
class ViscaSwitchEntityDescription(SwitchEntityDescription):
    """Switch description with optional model gating."""

    capability: frozenset[str] | None = None
    data_key: str = ""
    setter: str = ""
    tally: bool = False


SWITCHES: tuple[ViscaSwitchEntityDescription, ...] = (
    ViscaSwitchEntityDescription(key="power", translation_key="power", data_key="power", setter="set_power"),
    ViscaSwitchEntityDescription(
        key="exposure_comp",
        translation_key="exposure_comp",
        data_key="exposure_comp",
        setter="set_exposure_comp",
    ),
    ViscaSwitchEntityDescription(
        key="backlight_comp",
        translation_key="backlight_comp",
        data_key="backlight_comp",
        setter="set_backlight",
    ),
    ViscaSwitchEntityDescription(
        key="spotlight_comp",
        translation_key="spotlight_comp",
        data_key="spotlight_comp",
        setter="set_spotlight",
        capability=CAP_SPOTLIGHT,
    ),
    ViscaSwitchEntityDescription(
        key="slow_shutter",
        translation_key="slow_shutter",
        data_key="slow_shutter",
        setter="set_slow_shutter",
        capability=CAP_SLOW_SHUTTER,
    ),
    ViscaSwitchEntityDescription(
        key="tele_convert",
        translation_key="tele_convert",
        data_key="tele_convert",
        setter="set_tele_convert",
        capability=CAP_TELECONVERT,
    ),
    ViscaSwitchEntityDescription(
        key="visibility_enhancer",
        translation_key="visibility_enhancer",
        data_key="visibility_enhancer",
        setter="set_visibility_enhancer",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="high_sensitivity",
        translation_key="high_sensitivity",
        data_key="high_sensitivity",
        setter="set_high_sensitivity",
        capability=CAP_ADVANCED_LEGACY,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="defog",
        translation_key="defog",
        data_key="defog",
        setter="set_defog",
        capability=CAP_X400_ONLY,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="wide_dynamic",
        translation_key="wide_dynamic",
        data_key="wide_dynamic",
        setter="set_wdr_on",
        capability=CAP_WIDE_DYNAMIC,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="knee",
        translation_key="knee",
        data_key="knee_setting",
        setter="set_knee",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="pt_slow",
        translation_key="pt_slow",
        data_key="pt_slow",
        setter="set_pt_slow",
        capability=CAP_PT_SLOW,
    ),
    ViscaSwitchEntityDescription(
        key="tally_red",
        translation_key="tally_red",
        data_key="tally_red",
        setter="set_tally",
        capability=CAP_TALLY,
        tally=True,
    ),
    ViscaSwitchEntityDescription(
        key="auto_framing",
        translation_key="auto_framing",
        data_key="auto_framing",
        setter="set_auto_framing",
        capability=CAP_AUTO_FRAMING,
    ),
    ViscaSwitchEntityDescription(
        key="icr",
        translation_key="icr",
        data_key="icr",
        setter="set_icr",
        capability=CAP_ICR,
    ),
    ViscaSwitchEntityDescription(
        key="auto_icr",
        translation_key="auto_icr",
        data_key="auto_icr",
        setter="set_auto_icr",
        capability=CAP_X400_X40UH_SE,
    ),
    ViscaSwitchEntityDescription(
        key="image_flip",
        translation_key="image_flip",
        data_key="image_flip",
        setter="set_image_flip",
        capability=CAP_X400_CORE_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="image_stabilizer",
        translation_key="image_stabilizer",
        data_key="image_stabilizer",
        setter="set_image_stabilizer",
        capability=CAP_X400_X40UH_SE,
    ),
    ViscaSwitchEntityDescription(
        key="flicker_cancel",
        translation_key="flicker_cancel",
        data_key="flicker_cancel",
        setter="set_flicker_cancel",
        capability=CAP_X400_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="high_resolution",
        translation_key="high_resolution",
        data_key="high_resolution",
        setter="set_high_resolution",
        capability=CAP_HIGH_RESOLUTION,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="ir_receive",
        translation_key="ir_receive",
        data_key="ir_receive",
        setter="set_ir_receive",
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="color_bar",
        translation_key="color_bar",
        data_key="color_bar",
        setter="set_color_bar",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="pan_reverse",
        translation_key="pan_reverse",
        data_key="pan_reverse",
        setter="set_pan_reverse",
        capability=frozenset({"0519", "051A", "051B"}),
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="tilt_reverse",
        translation_key="tilt_reverse",
        data_key="tilt_reverse",
        setter="set_tilt_reverse",
        capability=frozenset({"0519", "051A", "051B"}),
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="standby_mode",
        translation_key="standby_mode",
        data_key="standby_mode",
        setter="set_standby_mode",
        capability=CAP_X400_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSwitchEntityDescription(
        key="osd",
        translation_key="osd",
        data_key="osd",
        setter="set_osd",
        capability=CAP_X400_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyViscaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VISCA switch entities."""
    runtime = entry.runtime_data
    async_add_entities(
        SonyViscaSwitch(runtime, description) for description in filter_supported(runtime, SWITCHES)
    )


class SonyViscaSwitch(SonyViscaEntity, SwitchEntity):
    """Switch backed by a VISCA on/off command."""

    entity_description: ViscaSwitchEntityDescription

    def __init__(self, runtime: SonyViscaRuntimeData, description: ViscaSwitchEntityDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the latest inquired or assumed state."""
        value = self._data(self.entity_description.data_key or self.entity_description.key)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        description = self.entity_description
        try:
            if description.tally:
                await self._async_set_tally(on)
            elif description.setter == "set_wdr_on":
                await self.runtime.client.set_wdr("high" if on else "off")
            else:
                await getattr(self.runtime.client, description.setter)(on)
        except ViscaError as err:
            raise HomeAssistantError(str(err)) from err
        if self.coordinator.data is not None:
            self.coordinator.data[description.data_key or description.key] = on
        await self.coordinator.async_request_refresh()

    async def _async_set_tally(self, on: bool) -> None:
        if self.runtime.tally_unsub is not None:
            self.runtime.tally_unsub()
            self.runtime.tally_unsub = None
        await self.runtime.client.set_tally(on)
        if on:
            self.runtime.tally_unsub = self.hass.loop.call_later(
                TALLY_KEEPALIVE_S, self._schedule_tally_keepalive
            )

    def _schedule_tally_keepalive(self) -> None:
        self.hass.async_create_task(self._async_tally_keepalive())

    async def _async_tally_keepalive(self) -> None:
        try:
            await self.runtime.client.set_tally(True)
        except ViscaError:
            return
        self.runtime.tally_unsub = self.hass.loop.call_later(
            TALLY_KEEPALIVE_S, self._schedule_tally_keepalive
        )
