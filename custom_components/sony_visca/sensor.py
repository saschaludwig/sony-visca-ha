"""Sensor platform for Sony VISCA."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SonyViscaConfigEntry
from .entity import SonyViscaEntity, SonyViscaRuntimeData
from .visca import raw_to_degrees

SENSORS = (
    SensorEntityDescription(
        key="power",
        translation_key="power",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="pan_position",
        translation_key="pan_position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tilt_position",
        translation_key="tilt_position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="zoom_position",
        translation_key="zoom_position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="focus_position",
        translation_key="focus_position",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pan_degrees",
        translation_key="pan_degrees",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°",
    ),
    SensorEntityDescription(
        key="tilt_degrees",
        translation_key="tilt_degrees",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyViscaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VISCA sensor entities."""
    async_add_entities([SonyViscaSensor(entry.runtime_data, description) for description in SENSORS])


class SonyViscaSensor(SonyViscaEntity, SensorEntity):
    """Sensor backed by coordinator inquiry data."""

    def __init__(self, runtime: SonyViscaRuntimeData, description: SensorEntityDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Keep the power diagnostic visible while the camera is in standby."""
        if self.entity_description.key == "power":
            return self.runtime.client.connected
        return super().available

    @property
    def native_value(self) -> bool | int | float | str | None:
        """Return the latest inquired value."""
        if not self.coordinator.data:
            return None
        key = self.entity_description.key
        if key == "power":
            value = self.coordinator.data.get("power")
            if value is None:
                return None
            return "on" if value else "off"
        if key == "pan_degrees":
            raw = self.coordinator.data.get("pan_position")
            if raw is None:
                return None
            return raw_to_degrees(self.runtime.visca_id, int(raw), "pan", bool(self.coordinator.data.get("image_flip")))
        if key == "tilt_degrees":
            raw = self.coordinator.data.get("tilt_position")
            if raw is None:
                return None
            return raw_to_degrees(self.runtime.visca_id, int(raw), "tilt", bool(self.coordinator.data.get("image_flip")))
        return self.coordinator.data.get(key)
