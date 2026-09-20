"""Sony VISCA Home Assistant integration."""

from __future__ import annotations

from typing import TypeAlias

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .choices import CameraChoices
from .const import (
    ATTR_ACTION,
    ATTR_COMMAND,
    ATTR_DIRECTION,
    ATTR_PAN,
    ATTR_PAN_SPEED,
    ATTR_PRESET,
    ATTR_SPEED,
    ATTR_TILT,
    ATTR_TILT_SPEED,
    ATTR_UNITS,
    CONF_CAMERA_ID,
    CONF_FRAME_RATE,
    CONF_MODEL,
    DEFAULT_FRAME_RATE,
    DEFAULT_MODEL,
    DOMAIN,
    FOCUS_ACTIONS,
    PTZ_DIRECTIONS,
    PTZ_UNITS,
    SERVICE_FOCUS,
    SERVICE_PTZ,
    SERVICE_PTZ_ABSOLUTE,
    SERVICE_PTZ_RELATIVE,
    SERVICE_RECALL_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_SEND_COMMAND,
    SERVICE_ZOOM,
    ZOOM_ACTIONS,
)
from .coordinator import SonyViscaCoordinator
from .entity import SonyViscaRuntimeData
from .model_caps import visca_id_for_model
from .models import inquiry_group_for_model, resolve_model_key
from .visca import ViscaClient, ViscaError, degrees_to_raw

PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
SERVICES = (
    SERVICE_PTZ,
    SERVICE_ZOOM,
    SERVICE_FOCUS,
    SERVICE_RECALL_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_PTZ_ABSOLUTE,
    SERVICE_PTZ_RELATIVE,
    SERVICE_SEND_COMMAND,
)

SonyViscaConfigEntry: TypeAlias = ConfigEntry

PTZ_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DIRECTION): vol.In(list(PTZ_DIRECTIONS)),
        vol.Optional(ATTR_PAN_SPEED): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
        vol.Optional(ATTR_TILT_SPEED): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
    },
    extra=vol.ALLOW_EXTRA,
)

ZOOM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ACTION): vol.In(ZOOM_ACTIONS),
        vol.Optional(ATTR_SPEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
    },
    extra=vol.ALLOW_EXTRA,
)

FOCUS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ACTION): vol.In(FOCUS_ACTIONS),
        vol.Optional(ATTR_SPEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
    },
    extra=vol.ALLOW_EXTRA,
)

PRESET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1, max=64)),
    },
    extra=vol.ALLOW_EXTRA,
)

PTZ_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PAN): vol.Coerce(float),
        vol.Required(ATTR_TILT): vol.Coerce(float),
        vol.Optional(ATTR_SPEED): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
        vol.Optional(ATTR_UNITS, default="raw"): vol.In(PTZ_UNITS),
    },
    extra=vol.ALLOW_EXTRA,
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): str,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: SonyViscaConfigEntry) -> bool:
    """Set up a Sony VISCA camera from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    camera_id = entry.data[CONF_CAMERA_ID]
    model = resolve_model_key(entry.data.get(CONF_MODEL, DEFAULT_MODEL))
    frame_rate = entry.options.get(CONF_FRAME_RATE, DEFAULT_FRAME_RATE)
    choices = CameraChoices(inquiry_group_for_model(model), frame_rate)

    client = ViscaClient(host, port, camera_id)
    try:
        await client.connect()
        await client.inquire_power()
    except ViscaError as err:
        await client.disconnect()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SonyViscaCoordinator(hass, client, model, choices)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SonyViscaRuntimeData(
        client=client,
        coordinator=coordinator,
        host=host,
        port=port,
        camera_id=camera_id,
        model=model,
        frame_rate=frame_rate,
        choices=choices,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: SonyViscaConfigEntry) -> None:
    """Reload the config entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SonyViscaConfigEntry) -> bool:
    """Unload a config entry and close the UDP client."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = entry.runtime_data
        if runtime.tally_unsub is not None:
            runtime.tally_unsub()
            runtime.tally_unsub = None
        await runtime.client.disconnect()
        remaining = [
            item
            for item in hass.config_entries.async_entries(DOMAIN)
            if item.entry_id != entry.entry_id and item.state is ConfigEntryState.LOADED
        ]
        if not remaining:
            for service in SERVICES:
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_PTZ):
        return

    async def handle_ptz(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.pan_tilt(
                    call.data[ATTR_DIRECTION],
                    call.data.get(ATTR_PAN_SPEED),
                    call.data.get(ATTR_TILT_SPEED),
                )
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
            await runtime.coordinator.async_request_refresh()

    async def handle_zoom(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.zoom(call.data[ATTR_ACTION], call.data.get(ATTR_SPEED))
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
            await runtime.coordinator.async_request_refresh()

    async def handle_focus(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.focus(call.data[ATTR_ACTION], call.data.get(ATTR_SPEED))
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
            await runtime.coordinator.async_request_refresh()

    async def handle_recall(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.recall_preset(call.data[ATTR_PRESET])
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
            await runtime.coordinator.async_request_refresh()

    async def handle_save(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.save_preset(call.data[ATTR_PRESET])
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err

    async def handle_ptz_position(call: ServiceCall, relative: bool) -> None:
        for runtime in _runtimes_from_call(hass, call):
            pan = call.data[ATTR_PAN]
            tilt = call.data[ATTR_TILT]
            if call.data.get(ATTR_UNITS, "raw") == "degrees":
                flip = bool((runtime.coordinator.data or {}).get("image_flip"))
                visca_id = visca_id_for_model(runtime.model)
                pan = degrees_to_raw(visca_id, pan, "pan", flip)
                tilt = degrees_to_raw(visca_id, tilt, "tilt", flip)
            try:
                await runtime.client.pan_tilt_absolute(
                    int(pan),
                    int(tilt),
                    call.data.get(ATTR_SPEED),
                    runtime.visca_id,
                    relative=relative,
                )
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err
            await runtime.coordinator.async_request_refresh()

    async def handle_absolute(call: ServiceCall) -> None:
        await handle_ptz_position(call, False)

    async def handle_relative(call: ServiceCall) -> None:
        await handle_ptz_position(call, True)

    async def handle_send(call: ServiceCall) -> None:
        for runtime in _runtimes_from_call(hass, call):
            try:
                await runtime.client.send_hex_command(call.data[ATTR_COMMAND])
            except ViscaError as err:
                raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_PTZ, handle_ptz, schema=PTZ_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ZOOM, handle_zoom, schema=ZOOM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FOCUS, handle_focus, schema=FOCUS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RECALL_PRESET, handle_recall, schema=PRESET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SAVE_PRESET, handle_save, schema=PRESET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PTZ_ABSOLUTE, handle_absolute, schema=PTZ_POSITION_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PTZ_RELATIVE, handle_relative, schema=PTZ_POSITION_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, handle_send, schema=SEND_COMMAND_SCHEMA)


def _runtimes_from_call(hass: HomeAssistant, call: ServiceCall) -> list[SonyViscaRuntimeData]:
    """Resolve targeted Sony VISCA devices from a service call."""
    device_ids = call.data.get("device_id") or []
    if isinstance(device_ids, str):
        device_ids = [device_ids]
    entity_ids = call.data.get("entity_id") or []
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    entry_ids: set[str] = set()

    device_reg = dr.async_get(hass)
    for device_id in device_ids:
        device = device_reg.async_get(device_id)
        if device is None:
            continue
        for config_entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(config_entry_id)
            if entry is not None and entry.domain == DOMAIN:
                entry_ids.add(entry.entry_id)

    if entity_ids:
        from homeassistant.helpers import entity_registry as er

        entity_reg = er.async_get(hass)
        for entity_id in entity_ids:
            entity = entity_reg.async_get(entity_id)
            if entity is None or entity.config_entry_id is None:
                continue
            entry = hass.config_entries.async_get_entry(entity.config_entry_id)
            if entry is not None and entry.domain == DOMAIN:
                entry_ids.add(entry.entry_id)

    if not entry_ids:
        loaded = [
            item
            for item in hass.config_entries.async_entries(DOMAIN)
            if item.state is ConfigEntryState.LOADED
        ]
        if len(loaded) == 1:
            entry_ids.add(loaded[0].entry_id)
        else:
            raise HomeAssistantError("Specify a Sony VISCA device for this service call")

    runtimes: list[SonyViscaRuntimeData] = []
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or not hasattr(entry, "runtime_data"):
            continue
        runtimes.append(entry.runtime_data)
    if not runtimes:
        raise HomeAssistantError("No Sony VISCA device is available")
    return runtimes
