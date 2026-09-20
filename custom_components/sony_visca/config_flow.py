"""Config flow for the Sony VISCA integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig

from .const import (
    CONF_CAMERA_ID,
    CONF_FRAME_RATE,
    CONF_MODEL,
    CONF_VISCA_MODEL_ID,
    DEFAULT_CAMERA_ID,
    DEFAULT_FRAME_RATE,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DOMAIN,
)
from .models import CameraModel, GENERIC_MODEL_KEY, model_display_name, selectable_models
from .visca import CameraProbe, ViscaError, async_probe_camera, config_unique_id

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_CAMERA_ID, default=DEFAULT_CAMERA_ID): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=7)
        ),
    }
)


def _model_schema(models: list[CameraModel], default: str) -> vol.Schema:
    """Build a dropdown of real camera names."""
    options = [SelectOptionDict(value=model.key, label=model.name) for model in models]
    return vol.Schema(
        {
            vol.Required(CONF_MODEL, default=default): SelectSelector(
                SelectSelectorConfig(options=options, mode="dropdown")
            )
        }
    )


class SonyViscaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Sony VISCA config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._probe: CameraProbe | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for network settings, then detect the camera model."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            camera_id = user_input[CONF_CAMERA_ID]
            user_input[CONF_HOST] = host
            self._user_input = user_input

            await self.async_set_unique_id(config_unique_id(host, port, camera_id))
            self._abort_if_unique_id_configured()

            try:
                self._probe = await async_probe_camera(host, port, camera_id)
            except ViscaError:
                _LOGGER.exception("Could not connect to VISCA camera at %s:%s", host, port)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface unexpected failures in the UI
                _LOGGER.exception("Unexpected error while connecting to %s:%s", host, port)
                errors["base"] = "unknown"
            else:
                if self._probe.model_key:
                    return self._async_create_camera_entry(self._probe.model_key)
                return await self.async_step_model()

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_model(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Let the user pick a real model name when autodetect is ambiguous."""
        candidates = list(self._probe.candidates) if self._probe else []
        models = selectable_models(candidates or None)
        default = models[0].key if candidates else DEFAULT_MODEL

        if user_input is not None:
            return self._async_create_camera_entry(user_input[CONF_MODEL])

        return self.async_show_form(step_id="model", data_schema=_model_schema(models, default))

    def _async_create_camera_entry(self, model_key: str) -> FlowResult:
        """Create the config entry with a human-readable title."""
        host = self._user_input[CONF_HOST]
        camera_id = self._user_input[CONF_CAMERA_ID]
        visca_model_id = self._probe.visca_model_id if self._probe else None
        data = {
            **self._user_input,
            CONF_MODEL: model_key or GENERIC_MODEL_KEY,
        }
        if visca_model_id:
            data[CONF_VISCA_MODEL_ID] = visca_model_id

        title = f"{model_display_name(model_key)} ({host})"
        if camera_id != DEFAULT_CAMERA_ID:
            title = f"{title} #{camera_id}"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow for frame-rate settings."""
        return SonyViscaOptionsFlow()


class SonyViscaOptionsFlow(OptionsFlow):
    """Options flow for shutter-table frame rate."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit the camera frame rate used for shutter/iris labels."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(CONF_FRAME_RATE, DEFAULT_FRAME_RATE)
        options = [
            SelectOptionDict(value="60", label="59.94 / 29.97 (60 Hz)"),
            SelectOptionDict(value="50", label="50 / 25 fps (50 Hz)"),
            SelectOptionDict(value="24", label="23.98 fps"),
        ]
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FRAME_RATE, default=current): SelectSelector(
                        SelectSelectorConfig(options=options, mode="dropdown")
                    )
                }
            ),
        )
