"""Shared entity helpers for Sony VISCA."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .choices import CameraChoices
from .const import DOMAIN, MANUFACTURER
from .coordinator import SonyViscaCoordinator
from .model_caps import has_capability, visca_id_for_model
from .models import model_display_name
from .visca import ViscaClient, config_unique_id


class SonyViscaRuntimeData:
    """Runtime objects attached to a config entry."""

    def __init__(
        self,
        client: ViscaClient,
        coordinator: SonyViscaCoordinator,
        host: str,
        port: int,
        camera_id: int,
        model: str,
        frame_rate: str,
        choices: CameraChoices,
    ) -> None:
        self.client = client
        self.coordinator = coordinator
        self.host = host
        self.port = port
        self.camera_id = camera_id
        self.model = model
        self.frame_rate = frame_rate
        self.choices = choices
        self.unique_id = config_unique_id(host, port, camera_id)
        self.visca_id = visca_id_for_model(model)
        self.tally_unsub: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the Home Assistant device for this camera."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=MANUFACTURER,
            model=model_display_name(self.model),
            name=f"{model_display_name(self.model)} {self.host}",
        )

    def supported(self, capability: frozenset[str] | None) -> bool:
        """Return True if this camera should expose a gated entity."""
        return has_capability(self.model, capability)


class SonyViscaEntity(CoordinatorEntity[SonyViscaCoordinator]):
    """Base entity bound to a VISCA camera device."""

    _attr_has_entity_name = True

    def __init__(self, runtime: SonyViscaRuntimeData, key: str) -> None:
        super().__init__(runtime.coordinator)
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.unique_id}_{key}"
        self._attr_device_info = runtime.device_info

    def _data(self, key: str, default: Any = None) -> Any:
        if not self.coordinator.data:
            return default
        return self.coordinator.data.get(key, default)


def filter_supported(
    runtime: SonyViscaRuntimeData,
    items: Iterable[Any],
    capability_attr: str = "capability",
) -> list[Any]:
    """Keep descriptions that the current camera model supports."""
    return [item for item in items if runtime.supported(getattr(item, capability_attr, None))]
