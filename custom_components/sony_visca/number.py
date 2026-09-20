"""Number platform for Sony VISCA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SonyViscaConfigEntry
from .const import (
    DEFAULT_FOCUS_SPEED,
    DEFAULT_PAN_SPEED,
    DEFAULT_PRESET,
    DEFAULT_TILT_SPEED,
    DEFAULT_ZOOM_SPEED,
)
from .entity import SonyViscaEntity, SonyViscaRuntimeData
from .model_caps import (
    CAP_ADVANCED,
    CAP_PRESET_DRIVE_SPEED,
    CAP_RAMP_CURVE,
    CAP_X400_CORE_X40UH,
    CAP_X400_X1000,
)
from .visca import CameraSpeeds, ViscaError


def _get_pan(speeds: CameraSpeeds) -> int:
    return speeds.pan


def _set_pan(speeds: CameraSpeeds, value: int) -> None:
    speeds.pan = value


def _get_tilt(speeds: CameraSpeeds) -> int:
    return speeds.tilt


def _set_tilt(speeds: CameraSpeeds, value: int) -> None:
    speeds.tilt = value


def _get_zoom(speeds: CameraSpeeds) -> int:
    return speeds.zoom


def _set_zoom(speeds: CameraSpeeds, value: int) -> None:
    speeds.zoom = value


def _get_focus(speeds: CameraSpeeds) -> int:
    return speeds.focus


def _set_focus(speeds: CameraSpeeds, value: int) -> None:
    speeds.focus = value


def _get_preset(speeds: CameraSpeeds) -> int:
    return speeds.preset


def _set_preset(speeds: CameraSpeeds, value: int) -> None:
    speeds.preset = value


def _get_preset_speed(speeds: CameraSpeeds) -> int:
    return speeds.preset_speed


def _set_preset_speed(speeds: CameraSpeeds, value: int) -> None:
    speeds.preset_speed = value


LOCAL_NUMBERS: tuple[
    tuple[NumberEntityDescription, Callable[[CameraSpeeds], int], Callable[[CameraSpeeds, int], None], int],
    ...,
] = (
    (
        NumberEntityDescription(
            key="pan_speed",
            translation_key="pan_speed",
            native_min_value=1,
            native_max_value=24,
            native_step=1,
            mode=NumberMode.SLIDER,
        ),
        _get_pan,
        _set_pan,
        DEFAULT_PAN_SPEED,
    ),
    (
        NumberEntityDescription(
            key="tilt_speed",
            translation_key="tilt_speed",
            native_min_value=1,
            native_max_value=24,
            native_step=1,
            mode=NumberMode.SLIDER,
        ),
        _get_tilt,
        _set_tilt,
        DEFAULT_TILT_SPEED,
    ),
    (
        NumberEntityDescription(
            key="zoom_speed",
            translation_key="zoom_speed",
            native_min_value=0,
            native_max_value=7,
            native_step=1,
            mode=NumberMode.SLIDER,
        ),
        _get_zoom,
        _set_zoom,
        DEFAULT_ZOOM_SPEED,
    ),
    (
        NumberEntityDescription(
            key="focus_speed",
            translation_key="focus_speed",
            native_min_value=0,
            native_max_value=7,
            native_step=1,
            mode=NumberMode.SLIDER,
        ),
        _get_focus,
        _set_focus,
        DEFAULT_FOCUS_SPEED,
    ),
    (
        NumberEntityDescription(
            key="preset_selector",
            translation_key="preset_selector",
            native_min_value=1,
            native_max_value=64,
            native_step=1,
            mode=NumberMode.BOX,
        ),
        _get_preset,
        _set_preset,
        DEFAULT_PRESET,
    ),
    (
        NumberEntityDescription(
            key="preset_speed",
            translation_key="preset_speed",
            native_min_value=1,
            native_max_value=24,
            native_step=1,
            mode=NumberMode.SLIDER,
        ),
        _get_preset_speed,
        _set_preset_speed,
        DEFAULT_PAN_SPEED,
    ),
)


@dataclass(kw_only=True)
class ViscaCameraNumberDescription(NumberEntityDescription):
    """Number written to the camera and refreshed from inquiries."""

    capability: frozenset[str] | None = None
    data_key: str = ""
    setter: str = ""
    offset: int = 0


CAMERA_NUMBERS: tuple[ViscaCameraNumberDescription, ...] = (
    ViscaCameraNumberDescription(
        key="zoom_direct",
        translation_key="zoom_direct",
        native_min_value=0,
        native_max_value=65535,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="zoom_position",
        setter="set_zoom_direct",
    ),
    ViscaCameraNumberDescription(
        key="focus_direct",
        translation_key="focus_direct",
        native_min_value=0,
        native_max_value=65535,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="focus_position",
        setter="set_focus_direct",
    ),
    ViscaCameraNumberDescription(
        key="focus_near_limit",
        translation_key="focus_near_limit",
        native_min_value=0,
        native_max_value=65535,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="focus_near_limit",
        setter="set_focus_near_limit",
        capability=CAP_ADVANCED,
    ),
    ViscaCameraNumberDescription(
        key="af_op_time",
        translation_key="af_op_time",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="af_op_time",
        setter="set_af_op_time",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="af_stay_time",
        translation_key="af_stay_time",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="af_stay_time",
        setter="set_af_stay_time",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="exposure_comp_level",
        translation_key="exposure_comp_level",
        native_min_value=-7,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="exposure_comp_level",
        setter="set_exposure_comp_direct",
        offset=7,
    ),
    ViscaCameraNumberDescription(
        key="red_gain",
        translation_key="red_gain",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="red_gain",
        setter="set_red_gain_direct",
    ),
    ViscaCameraNumberDescription(
        key="blue_gain",
        translation_key="blue_gain",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="blue_gain",
        setter="set_blue_gain_direct",
    ),
    ViscaCameraNumberDescription(
        key="wb_offset",
        translation_key="wb_offset",
        native_min_value=-7,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="wb_offset",
        setter="set_wb_offset",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="wb_speed",
        translation_key="wb_speed",
        native_min_value=0,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="wb_speed",
        setter="set_wb_speed",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="nr_level",
        translation_key="nr_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="nr_level",
        setter="set_noise_reduction",
    ),
    ViscaCameraNumberDescription(
        key="detail_level",
        translation_key="detail_level",
        native_min_value=-7,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="detail_level",
        setter="set_detail_level",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="color_gain",
        translation_key="color_gain",
        native_min_value=0,
        native_max_value=14,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="color_gain",
        setter="set_color_gain",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="color_hue",
        translation_key="color_hue",
        native_min_value=-7,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="color_hue",
        setter="set_color_hue",
        capability=CAP_X400_X1000,
        offset=7,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="chroma_suppress",
        translation_key="chroma_suppress",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="chroma_suppress",
        setter="set_chroma_suppress",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="ae_speed",
        translation_key="ae_speed",
        native_min_value=0,
        native_max_value=63,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="ae_speed",
        setter="set_ae_speed",
        capability=CAP_ADVANCED,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="black_level",
        translation_key="black_level",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        data_key="black_level",
        setter="set_black_level",
        capability=CAP_X400_X1000,
        entity_category=EntityCategory.CONFIG,
    ),
    ViscaCameraNumberDescription(
        key="ramp_curve",
        translation_key="ramp_curve",
        native_min_value=1,
        native_max_value=9,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="ramp_curve",
        setter="set_ramp_curve",
        capability=CAP_RAMP_CURVE,
    ),
    ViscaCameraNumberDescription(
        key="preset_common_speed",
        translation_key="preset_common_speed",
        native_min_value=1,
        native_max_value=24,
        native_step=1,
        mode=NumberMode.SLIDER,
        data_key="preset_common_speed",
        setter="set_preset_speed_common",
        capability=CAP_X400_CORE_X40UH,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyViscaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VISCA number entities."""
    runtime = entry.runtime_data
    entities: list[NumberEntity] = [
        SonyViscaLocalNumber(runtime, description, getter, setter, default)
        for description, getter, setter, default in LOCAL_NUMBERS
        if description.key != "preset_speed" or runtime.supported(CAP_PRESET_DRIVE_SPEED)
    ]
    entities.extend(
        SonyViscaCameraNumber(runtime, description)
        for description in CAMERA_NUMBERS
        if runtime.supported(description.capability)
    )
    async_add_entities(entities)


class SonyViscaLocalNumber(NumberEntity, RestoreEntity):
    """Number entity that stores a controller-side VISCA setting."""

    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: SonyViscaRuntimeData,
        description: NumberEntityDescription,
        getter: Callable[[CameraSpeeds], int],
        setter: Callable[[CameraSpeeds, int], None],
        default: int,
    ) -> None:
        self.runtime = runtime
        self.entity_description = description
        self._getter = getter
        self._setter = setter
        self._default = default
        self._attr_unique_id = f"{runtime.unique_id}_{description.key}"
        self._attr_device_info = runtime.device_info
        self._attr_native_value = float(default)

    async def async_added_to_hass(self) -> None:
        """Restore the last value and apply it to the client."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = float(last_state.state)
            except ValueError:
                self._attr_native_value = float(self._default)
        self._setter(self.runtime.client.speeds, int(self._attr_native_value))

    async def async_set_native_value(self, value: float) -> None:
        """Update the controller-side setting."""
        self._attr_native_value = value
        self._setter(self.runtime.client.speeds, int(value))
        if self.entity_description.key == "preset_speed":
            try:
                await self.runtime.client.set_preset_speed(
                    self.runtime.client.speeds.preset, int(value)
                )
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()


class SonyViscaCameraNumber(SonyViscaEntity, NumberEntity):
    """Number written to the camera."""

    entity_description: ViscaCameraNumberDescription

    def __init__(self, runtime: SonyViscaRuntimeData, description: ViscaCameraNumberDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the latest inquired value."""
        value = self._data(self.entity_description.data_key or self.entity_description.key)
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Send the value to the camera."""
        command_value = int(value) + self.entity_description.offset
        setter = getattr(self.runtime.client, self.entity_description.setter)
        try:
            if self.entity_description.setter in {"set_af_op_time", "set_af_stay_time"}:
                data = self.coordinator.data or {}
                op_time = int(value) if self.entity_description.key == "af_op_time" else int(data.get("af_op_time") or 5)
                stay_time = (
                    int(value) if self.entity_description.key == "af_stay_time" else int(data.get("af_stay_time") or 5)
                )
                await self.runtime.client.set_af_interval(op_time, stay_time)
            else:
                await setter(command_value)
        except ViscaError as err:
            raise HomeAssistantError(str(err)) from err
        if self.coordinator.data is not None:
            self.coordinator.data[self.entity_description.data_key or self.entity_description.key] = int(value)
        await self.coordinator.async_request_refresh()
