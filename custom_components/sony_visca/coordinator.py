"""Data update coordinator for Sony VISCA cameras."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .choices import CameraChoices
from .const import DOMAIN, INQUIRY_POLL_INTERVAL_S
from .inquiries import (
    LOW_PRIORITY_INQUIRIES,
    inquiry_blocks_for_group,
    parse_inquiry_block,
)
from .model_caps import (
    CAP_ADVANCED,
    CAP_AUTO_FRAMING,
    CAP_PT_SLOW,
    CAP_RAMP_CURVE,
    CAP_TALLY,
    has_capability,
)
from .models import inquiry_group_for_model
from .visca import ViscaClient, ViscaError, parse_pan_tilt_response

_LOGGER = logging.getLogger(__name__)

_LOW_PRIORITY_CAPS = {
    "090644": CAP_PT_SLOW,
    "090631": CAP_RAMP_CURVE,
    "097e010a": CAP_TALLY,
    "090428": CAP_ADVANCED,
    "097e043a": CAP_AUTO_FRAMING,
}


class SonyViscaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll block inquiries, pan/tilt position, and one low-priority inquiry."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViscaClient,
        model: str,
        choices: CameraChoices,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=INQUIRY_POLL_INTERVAL_S),
        )
        self.client = client
        self.model = model
        self.choices = choices
        self.group = inquiry_group_for_model(model)
        self.blocks = inquiry_blocks_for_group(self.group)
        self._low_priority = [
            inquiry
            for inquiry in LOW_PRIORITY_INQUIRIES
            if has_capability(model, _LOW_PRIORITY_CAPS.get(inquiry.key))
        ]
        self._low_index = 0

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = dict(self.data) if self.data else {}
        errors: list[str] = []
        successes = 0

        for block in self.blocks:
            try:
                payload = await self.client.inquire(*block.command)
                parsed = parse_inquiry_block(block, payload, self.choices)
                if parsed:
                    data.update(parsed)
                    successes += 1
            except ViscaError as err:
                errors.append(f"{block.key}: {err}")

        try:
            pan, tilt = await self.client.inquire_pan_tilt()
            data["pan_position"] = pan
            data["tilt_position"] = tilt
            successes += 1
        except ViscaError as err:
            errors.append(f"pan_tilt: {err}")

        if self._low_priority:
            inquiry = self._low_priority[self._low_index % len(self._low_priority)]
            self._low_index += 1
            try:
                payload = await self.client.inquire(*inquiry.command)
                inquiry.apply(payload, data)
                successes += 1
            except ViscaError as err:
                errors.append(f"{inquiry.key}: {err}")

        if "power" not in data:
            try:
                data["power"] = await self.client.inquire_power()
                successes += 1
            except ViscaError as err:
                errors.append(f"power: {err}")

        if successes == 0:
            raise UpdateFailed("; ".join(errors) or "All VISCA inquiries failed")
        if errors:
            _LOGGER.debug("Some VISCA inquiries failed: %s", "; ".join(errors))
        return data
