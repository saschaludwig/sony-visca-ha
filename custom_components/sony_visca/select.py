"""Select platform for Sony VISCA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonyViscaConfigEntry
from .const import (
    AF_MODES,
    AF_SENSITIVITIES,
    EXPOSURE_MODES,
    FOCUS_MODES,
    PICTURE_EFFECTS,
    PRESET_MODES,
    PRESET_SPEED_MODES,
    TALLY_LEVELS,
    WDR_MODES,
    ZOOM_SPEED_TYPES,
)
from .entity import SonyViscaEntity, SonyViscaRuntimeData, filter_supported
from .model_caps import (
    CAP_ADVANCED,
    CAP_ADVANCED_LEGACY,
    CAP_CLEAR_IMAGE_ZOOM,
    CAP_PICTURE_EFFECT,
    CAP_TALLY,
    CAP_WB_ATW,
    CAP_WIDE_DYNAMIC,
    CAP_X1000,
    CAP_X400_X1000,
    CAP_X400_X1000_NO_H780,
    CAP_X400_X40UH,
)
from .visca import ViscaError

PICTURE_EFFECT_FROM_RAW = {0: "off", 2: "neg_art", 4: "black_white"}


@dataclass(kw_only=True)
class ViscaSelectEntityDescription(SelectEntityDescription):
    """Select description with optional model gating and a client setter."""

    capability: frozenset[str] | None = None
    data_key: str = ""
    options_fn: Callable[[SonyViscaRuntimeData], list[str]] | None = None
    setter: str = ""
    parse_value: Callable[[object], str | None] | None = None
    to_command: Callable[[str], object] | None = None


def _choice_values(kind: str) -> Callable[[SonyViscaRuntimeData], list[str]]:
    def _values(runtime: SonyViscaRuntimeData) -> list[str]:
        return [choice.value for choice in getattr(runtime.choices, kind)]

    return _values


def _zoom_mode_options(runtime: SonyViscaRuntimeData) -> list[str]:
    options = ["optical", "digital"]
    if runtime.supported(CAP_CLEAR_IMAGE_ZOOM):
        options.append("clear_image")
    return options


def _wb_mode_options(runtime: SonyViscaRuntimeData) -> list[str]:
    options = ["auto1", "indoor", "outdoor", "one_push"]
    if runtime.supported(CAP_WB_ATW):
        options.append("auto2")
    options.append("manual")
    return options


def _hex_int(value: str) -> int:
    return int(value, 16)


SELECTS: tuple[ViscaSelectEntityDescription, ...] = (
    ViscaSelectEntityDescription(
        key="focus_mode",
        translation_key="focus_mode",
        options=list(FOCUS_MODES),
        data_key="focus_mode",
        setter="set_focus_mode",
    ),
    ViscaSelectEntityDescription(
        key="zoom_mode",
        translation_key="zoom_mode",
        options_fn=_zoom_mode_options,
        data_key="zoom_mode",
        setter="set_zoom_mode",
    ),
    ViscaSelectEntityDescription(
        key="af_mode",
        translation_key="af_mode",
        options=list(AF_MODES),
        data_key="af_mode",
        setter="set_af_mode",
        capability=CAP_ADVANCED,
    ),
    ViscaSelectEntityDescription(
        key="af_sensitivity",
        translation_key="af_sensitivity",
        options=list(AF_SENSITIVITIES),
        data_key="af_sensitivity",
        setter="set_af_sensitivity",
        capability=CAP_ADVANCED,
    ),
    ViscaSelectEntityDescription(
        key="exposure_mode",
        translation_key="exposure_mode",
        options=list(EXPOSURE_MODES),
        data_key="exposure_mode",
        setter="set_exposure_mode",
    ),
    ViscaSelectEntityDescription(
        key="iris",
        translation_key="iris",
        options_fn=_choice_values("iris"),
        data_key="iris",
        setter="set_iris_direct",
        to_command=_hex_int,
    ),
    ViscaSelectEntityDescription(
        key="gain",
        translation_key="gain",
        options_fn=_choice_values("gain"),
        data_key="gain",
        setter="set_gain_direct",
        to_command=_hex_int,
    ),
    ViscaSelectEntityDescription(
        key="shutter",
        translation_key="shutter",
        options_fn=_choice_values("shutter"),
        data_key="shutter",
        setter="set_shutter_direct",
        to_command=_hex_int,
    ),
    ViscaSelectEntityDescription(
        key="brightness",
        translation_key="brightness",
        options_fn=_choice_values("brightness"),
        data_key="brightness",
        setter="set_brightness_direct",
        to_command=_hex_int,
        capability=frozenset({"0511", "0513", "0516", "0604", "0605"}),
    ),
    ViscaSelectEntityDescription(
        key="wb_mode",
        translation_key="wb_mode",
        options_fn=_wb_mode_options,
        data_key="wb_mode",
        setter="set_wb_mode",
    ),
    ViscaSelectEntityDescription(
        key="wdr",
        translation_key="wdr",
        options=list(WDR_MODES),
        data_key="wdr",
        setter="set_wdr",
        capability=CAP_WIDE_DYNAMIC,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="picture_effect",
        translation_key="picture_effect",
        options=list(PICTURE_EFFECTS),
        data_key="picture_effect",
        setter="set_picture_effect",
        capability=CAP_PICTURE_EFFECT,
        parse_value=lambda raw: PICTURE_EFFECT_FROM_RAW.get(int(raw)) if raw is not None else None,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="zoom_speed_type",
        translation_key="zoom_speed_type",
        options=list(ZOOM_SPEED_TYPES),
        data_key="zoom_speed_type",
        setter="set_zoom_speed_type",
        capability=CAP_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="preset_speed_mode",
        translation_key="preset_speed_mode",
        options=list(PRESET_SPEED_MODES),
        data_key="preset_speed_mode",
        setter="set_preset_speed_select",
        capability=CAP_X400_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="preset_mode",
        translation_key="preset_mode",
        options=list(PRESET_MODES),
        data_key="preset_mode",
        setter="set_preset_mode",
        capability=CAP_X400_X1000_NO_H780,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="tally_level",
        translation_key="tally_level",
        options=list(TALLY_LEVELS),
        data_key="tally_level",
        setter="set_tally_level",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaSelectEntityDescription(
        key="gain_limit",
        translation_key="gain_limit",
        options_fn=_choice_values("gain_limit"),
        data_key="gain_limit",
        setter="set_gain_limit",
        to_command=_hex_int,
        capability=CAP_ADVANCED_LEGACY,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyViscaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VISCA select entities."""
    runtime = entry.runtime_data
    entities = []
    for description in filter_supported(runtime, SELECTS):
        if description.options_fn and not description.options_fn(runtime):
            continue
        entities.append(SonyViscaSelect(runtime, description))
    async_add_entities(entities)


class SonyViscaSelect(SonyViscaEntity, SelectEntity):
    """Select backed by a VISCA mode or choice table."""

    entity_description: ViscaSelectEntityDescription

    def __init__(self, runtime: SonyViscaRuntimeData, description: ViscaSelectEntityDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description
        if description.options_fn:
            self._attr_options = description.options_fn(runtime)
        else:
            self._attr_options = list(description.options or [])

    @property
    def current_option(self) -> str | None:
        """Return the current inquired option."""
        value = self._data(self.entity_description.data_key or self.entity_description.key)
        if self.entity_description.parse_value:
            value = self.entity_description.parse_value(value)
        if value is None:
            return None
        option = str(value)
        if option in self._attr_options:
            return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Send the selected option to the camera."""
        value: object = option
        if self.entity_description.to_command:
            value = self.entity_description.to_command(option)
        try:
            await getattr(self.runtime.client, self.entity_description.setter)(value)
        except ViscaError as err:
            raise HomeAssistantError(str(err)) from err
        if self.coordinator.data is not None:
            self.coordinator.data[self.entity_description.data_key or self.entity_description.key] = option
        await self.coordinator.async_request_refresh()
