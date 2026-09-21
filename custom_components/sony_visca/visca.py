"""VISCA over IP client."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import logging
import socket
from typing import Any, Literal

from .const import (
    AF_MODE_BYTES,
    COMMAND_COMPLETION_TIMEOUT_MS,
    DEFAULT_FOCUS_SPEED,
    DEFAULT_PAN_SPEED,
    DEFAULT_PRESET,
    DEFAULT_TILT_SPEED,
    DEFAULT_ZOOM_SPEED,
    EXPOSURE_MODE_BYTES,
    FOCUS_ACTIONS,
    MAX_CONSECUTIVE_TIMEOUTS,
    PICTURE_EFFECT_BYTES,
    PRESET_MODE_BYTES,
    PRESET_SPEED_MODE_BYTES,
    PTZ_DIRECTIONS,
    SEQUENCE_RESET,
    TALLY_LEVEL_BYTES,
    TIMEOUT_MS,
    TYPE_COMMAND,
    TYPE_INQUIRY,
    WB_MODE_BYTES,
    WDR_MODE_BYTES,
    ZOOM_MODE_BYTES,
    ZOOM_SPEED_TYPE_BYTES,
    VISCA_ERRORS,
)
from .models import CameraModel, models_for_visca_id

LOGGER = logging.getLogger(__name__)

WaitMode = Literal["ack", "completion", "inquiry"]


class ViscaError(Exception):
    """VISCA protocol or transport error."""


def camera_address(camera_id: int) -> int:
    """Return the VISCA address byte for camera IDs 1-7."""
    if not 1 <= camera_id <= 7:
        raise ValueError("Camera ID must be between 1 and 7")
    return 0x80 + camera_id


def build_payload(camera_id: int, *command_bytes: int) -> bytes:
    """Build a VISCA payload: address + command + terminator."""
    return bytes((camera_address(camera_id), *command_bytes, 0xFF))


def build_packet(payload_type: bytes, sequence: int, payload: bytes) -> bytes:
    """Build an 8-byte VISCA-over-IP header plus payload."""
    if len(payload_type) != 2:
        raise ValueError("Payload type must be 2 bytes")
    header = bytearray(8)
    header[0:2] = payload_type
    header[2:4] = len(payload).to_bytes(2, "big")
    header[4:8] = sequence.to_bytes(4, "big")
    return bytes(header) + payload


def parse_ip_packet(data: bytes) -> tuple[int, bytes] | None:
    """Parse a VISCA-over-IP datagram into (sequence, visca_payload)."""
    if len(data) < 11:
        return None
    payload_length = int.from_bytes(data[2:4], "big")
    if payload_length < 2 or 8 + payload_length > len(data):
        return None
    sequence = int.from_bytes(data[4:8], "big")
    payload = data[8 : 8 + payload_length]
    if payload[0] != 0x90:
        return None
    return sequence, payload


def nibble_concat(payload: bytes, indices: list[int]) -> int:
    """Concatenate lower nibbles of the given payload bytes."""
    value = 0
    for index in indices:
        value = (value << 4) | (payload[index] & 0x0F)
    return value


def nibble_bytes(value: int, count: int = 4) -> tuple[int, ...]:
    """Split an integer into ``count`` low nibbles, most significant first."""
    return tuple((value >> (4 * (count - 1 - index))) & 0x0F for index in range(count))


# 5+5 nibble models: FR7, AM7, 360SHE, 280SHE. 5+4: X1000 family.
_PT_5_5 = frozenset({"051E", "051F", "0604", "0605"})
_PT_5_4 = frozenset({"0519", "051A", "051B"})

# Raw VISCA ranges and matching degree ranges.
_PT_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "0511": {"pan": (-0x1400, 0x1400), "tilt_off": (-0x0500, 0x0500), "tilt_on": (-0x0500, 0x0500)},
    "0519": {"pan": (-0x9CA7, 0x9CA7), "tilt_off": (-0x1BA5, 0x52EF), "tilt_on": (-0x52EF, 0x1BA5)},
    "051A": {"pan": (-0x9CA7, 0x9CA7), "tilt_off": (-0x1BA5, 0x52EF), "tilt_on": (-0x52EF, 0x1BA5)},
    "051B": {"pan": (-0x9CA7, 0x9CA7), "tilt_off": (-0x1BA5, 0x52EF), "tilt_on": (-0x52EF, 0x1BA5)},
    "0604": {"pan": (-0x15400, 0x15400), "tilt_off": (-0x3C00, 0x0B400), "tilt_on": (-0x0B400, 0x03C00)},
    "0605": {"pan": (-0x15400, 0x15400), "tilt_off": (-0x3C00, 0x0B400), "tilt_on": (-0x0B400, 0x03C00)},
}
_PT_RANGE_DEFAULT = {"pan": (-0x2200, 0x2200), "tilt_off": (-0x0400, 0x1200), "tilt_on": (-0x1200, 0x0400)}
_PT_DEGREES: dict[str, dict[str, tuple[float, float]]] = {
    "0511": {"pan": (-100, 100), "tilt_off": (-25, 25), "tilt_on": (-25, 25)},
    "0519": {"pan": (-170, 170), "tilt_off": (-30, 90), "tilt_on": (-90, 30)},
    "051A": {"pan": (-170, 170), "tilt_off": (-30, 90), "tilt_on": (-90, 30)},
    "051B": {"pan": (-170, 170), "tilt_off": (-30, 90), "tilt_on": (-90, 30)},
    "0604": {"pan": (-170, 170), "tilt_off": (-30, 90), "tilt_on": (-90, 30)},
    "0605": {"pan": (-170, 170), "tilt_off": (-30, 90), "tilt_on": (-90, 30)},
}
_PT_DEGREE_DEFAULT = {"pan": (-170.0, 170.0), "tilt_off": (-20.0, 90.0), "tilt_on": (-90.0, 20.0)}


def _pt_range(visca_id: str | None) -> dict[str, tuple[int, int]]:
    if visca_id and visca_id in _PT_RANGES:
        return _PT_RANGES[visca_id]
    return _PT_RANGE_DEFAULT


def _pt_degrees(visca_id: str | None) -> dict[str, tuple[float, float]]:
    if visca_id and visca_id in _PT_DEGREES:
        return _PT_DEGREES[visca_id]
    return _PT_DEGREE_DEFAULT


def degrees_to_raw(visca_id: str | None, degrees: float, axis: str, image_flip: bool = False) -> int:
    """Convert pan/tilt degrees to a raw VISCA position."""
    raw_range = _pt_range(visca_id)
    deg_range = _pt_degrees(visca_id)
    key = "pan" if axis == "pan" else ("tilt_on" if image_flip else "tilt_off")
    raw_min, raw_max = raw_range[key]
    deg_min, deg_max = deg_range[key]
    clamped = max(deg_min, min(deg_max, degrees))
    raw = int(round((clamped / deg_max) * raw_max)) if deg_max else 0
    return max(raw_min, min(raw_max, raw))


def raw_to_degrees(visca_id: str | None, raw: int, axis: str, image_flip: bool = False) -> float:
    """Convert a raw VISCA position to degrees."""
    raw_range = _pt_range(visca_id)
    deg_range = _pt_degrees(visca_id)
    key = "pan" if axis == "pan" else ("tilt_on" if image_flip else "tilt_off")
    raw_max = raw_range[key][1]
    deg_max = deg_range[key][1]
    if not raw_max:
        return 0.0
    return round((raw / raw_max) * deg_max, 1)


def build_pt_position_payload(
    camera_id: int,
    command: int,
    speed: int,
    pan: int,
    tilt: int,
    visca_id: str | None,
) -> bytes:
    """Build CAM_PanTiltAbs/Rel with 4+4, 5+4, or 5+5 nibble layouts."""
    pan_nibbles, tilt_nibbles = 4, 4
    if visca_id in _PT_5_5:
        pan_nibbles, tilt_nibbles = 5, 5
    elif visca_id in _PT_5_4:
        pan_nibbles, tilt_nibbles = 5, 4
    pan_mask = (1 << (pan_nibbles * 4)) - 1
    tilt_mask = (1 << (tilt_nibbles * 4)) - 1
    return build_payload(
        camera_id,
        0x01,
        0x06,
        command,
        speed & 0xFF,
        0x00,
        *nibble_bytes(pan & pan_mask, pan_nibbles),
        *nibble_bytes(tilt & tilt_mask, tilt_nibbles),
    )


def to_signed(value: int, bits: int) -> int:
    """Convert an unsigned n-bit value to a signed integer."""
    sign_bit = 1 << (bits - 1)
    if value >= sign_bit:
        return value - (sign_bit << 1)
    return value


def parse_power_response(payload: bytes) -> bool:
    """Parse CAM_PowerInq: y0 50 0p FF (02=On, 03=Standby)."""
    if len(payload) < 4 or payload[1] != 0x50:
        raise ViscaError("Invalid power inquiry response")
    return (payload[2] & 0x0F) == 0x02


@dataclass(frozen=True)
class ViscaVersion:
    """Parsed CAM_VersionInq reply (Sony format)."""

    vendor_id: int
    model_id: int
    rom_version: int
    sockets: int

    @property
    def model_id_hex(self) -> str:
        """Return the 4-digit VISCA model code."""
        return f"{self.model_id:04X}"


@dataclass(frozen=True)
class CameraProbe:
    """Result of a config-flow connection check."""

    power_on: bool
    version: ViscaVersion | None
    candidates: tuple[CameraModel, ...]
    model_key: str | None

    @property
    def visca_model_id(self) -> str | None:
        """Return the detected VISCA model code, if any."""
        if self.version is None:
            return None
        return self.version.model_id_hex


def parse_version_response(payload: bytes) -> ViscaVersion:
    """Parse CAM_VersionInq: y0 50 GG GG HH HH JJ JJ KK FF."""
    if len(payload) < 10 or payload[1] != 0x50:
        raise ViscaError("Invalid version inquiry response")
    return ViscaVersion(
        vendor_id=(payload[2] << 8) | payload[3],
        model_id=(payload[4] << 8) | payload[5],
        rom_version=(payload[6] << 8) | payload[7],
        sockets=payload[8],
    )


def resolve_probe_models(version: ViscaVersion | None) -> tuple[tuple[CameraModel, ...], str | None]:
    """Map a version inquiry to known cameras and a unique model key."""
    if version is None:
        return (), None
    matches = tuple(models_for_visca_id(version.model_id_hex))
    if len(matches) == 1:
        return matches, matches[0].key
    return matches, None


def parse_zoom_response(payload: bytes) -> int:
    """Parse CAM_ZoomPosInq: y0 50 0z 0z 0z 0z FF."""
    if len(payload) < 7 or payload[1] != 0x50:
        raise ViscaError("Invalid zoom inquiry response")
    return nibble_concat(payload, [2, 3, 4, 5])


def parse_pan_tilt_response(payload: bytes) -> tuple[int, int]:
    """Parse CAM_PanTiltPosInq for 4+4, 5+4, or 5+5 nibble layouts."""
    if len(payload) < 10 or payload[1] != 0x50:
        raise ViscaError("Invalid pan/tilt inquiry response")

    if len(payload) >= 13:
        pan_raw = nibble_concat(payload, [2, 3, 4, 5, 6])
        tilt_raw = nibble_concat(payload, [7, 8, 9, 10, 11])
        return to_signed(pan_raw, 20), to_signed(tilt_raw, 20)

    if len(payload) >= 12:
        pan_raw = nibble_concat(payload, [2, 3, 4, 5, 6])
        tilt_raw = nibble_concat(payload, [7, 8, 9, 10])
        return to_signed(pan_raw, 20), to_signed(tilt_raw, 16)

    pan_raw = nibble_concat(payload, [2, 3, 4, 5])
    tilt_raw = nibble_concat(payload, [6, 7, 8, 9])
    return to_signed(pan_raw, 16), to_signed(tilt_raw, 16)


def resolve_ipv4(host: str) -> str:
    """Resolve a hostname to an IPv4 address."""
    infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    if not infos:
        raise ViscaError(f"Could not resolve {host}")
    return infos[0][4][0]


def config_unique_id(host: str, port: int, camera_id: int) -> str:
    """Build the config-entry unique ID."""
    return f"{host}:{port}:{camera_id}"


@dataclass
class CameraSpeeds:
    """Controller-side PTZ speeds and preset selector."""

    pan: int = DEFAULT_PAN_SPEED
    tilt: int = DEFAULT_TILT_SPEED
    zoom: int = DEFAULT_ZOOM_SPEED
    focus: int = DEFAULT_FOCUS_SPEED
    preset: int = DEFAULT_PRESET
    preset_speed: int = DEFAULT_PAN_SPEED


@dataclass
class _Queued:
    payload: bytes
    packet_type: bytes
    wait: WaitMode
    future: asyncio.Future[bytes]


@dataclass
class _Pending:
    future: asyncio.Future[bytes]
    wait: WaitMode
    is_command: bool
    timer: asyncio.TimerHandle | None = field(default=None)


class _ViscaDatagramProtocol(asyncio.DatagramProtocol):
    """Receive VISCA UDP replies and hand them to the client."""

    def __init__(self, client: ViscaClient) -> None:
        self._client = client
        self.ready = asyncio.Event()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.ready.set()

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._client.handle_response(data)

    def error_received(self, exc: Exception) -> None:
        LOGGER.warning("VISCA UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            LOGGER.warning("VISCA UDP connection lost: %s", exc)


class ViscaClient:
    """Async VISCA-over-IP client with sequence numbers, ACK queue, and timeouts."""

    def __init__(self, host: str, port: int, camera_id: int) -> None:
        self.host = host
        self.port = port
        self.camera_id = camera_id
        self.resolved_host: str | None = None
        self.speeds = CameraSpeeds()
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _ViscaDatagramProtocol | None = None
        self._sequence = 0
        self._cts = True
        self._queue: deque[_Queued] = deque()
        self._active: dict[int, _Pending] = {}
        self._pending_seq: int | None = None
        self._consecutive_timeouts = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def connected(self) -> bool:
        """Return True if the UDP transport is open."""
        return self._transport is not None and not self._transport.is_closing()

    async def connect(self) -> None:
        """Open the UDP socket and reset the camera sequence counter."""
        loop = asyncio.get_running_loop()
        self._loop = loop
        self.resolved_host = await loop.run_in_executor(None, resolve_ipv4, self.host)
        protocol = _ViscaDatagramProtocol(self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        bind_error: str | None = None
        try:
            sock.setblocking(False)
            try:
                # Sony replies to the VISCA UDP port, often from a different source port.
                sock.bind(("", self.port))
            except OSError as err:
                bind_error = repr(err)
                sock.bind(("", 0))
            transport, _ = await loop.create_datagram_endpoint(lambda: protocol, sock=sock)
        except OSError as err:
            sock.close()
            raise ViscaError(f"Could not open VISCA UDP socket: {err}") from err
        self._transport = transport
        self._protocol = protocol
        await protocol.ready.wait()
        if bind_error:
            LOGGER.warning(
                "Could not bind VISCA UDP port %s (%s), using %s",
                self.port,
                bind_error,
                transport.get_extra_info("sockname"),
            )
        self.reset_sequence()

    def _destination(self) -> tuple[str, int] | None:
        if self.resolved_host is None:
            return None
        return (self.resolved_host, self.port)

    def _send_datagram(self, data: bytes) -> None:
        if self._transport is None:
            return
        destination = self._destination()
        if destination is None:
            self._transport.sendto(data)
        else:
            self._transport.sendto(data, destination)

    async def disconnect(self) -> None:
        """Close the socket and cancel in-flight packets."""
        self._cancel_all(ViscaError("VISCA client disconnected"))
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._protocol = None

    def reset_sequence(self) -> None:
        """Send the VISCA-over-IP sequence reset control packet."""
        self._cancel_all(ViscaError("VISCA sequence reset"))
        self._sequence = 0
        self._cts = True
        self._consecutive_timeouts = 0
        if self._transport is not None:
            self._send_datagram(SEQUENCE_RESET)

    async def inquire_power(self) -> bool:
        """Query camera power state."""
        payload = await self.send(build_payload(self.camera_id, 0x09, 0x04, 0x00), TYPE_INQUIRY, "inquiry")
        return parse_power_response(payload)

    async def inquire_zoom(self) -> int:
        """Query zoom position."""
        payload = await self.send(build_payload(self.camera_id, 0x09, 0x04, 0x47), TYPE_INQUIRY, "inquiry")
        return parse_zoom_response(payload)

    async def inquire_pan_tilt(self) -> tuple[int, int]:
        """Query pan and tilt positions."""
        payload = await self.send(build_payload(self.camera_id, 0x09, 0x06, 0x12), TYPE_INQUIRY, "inquiry")
        return parse_pan_tilt_response(payload)

    async def inquire_version(self) -> ViscaVersion:
        """Query vendor and model IDs via CAM_VersionInq."""
        payload = await self.send(build_payload(self.camera_id, 0x09, 0x00, 0x02), TYPE_INQUIRY, "inquiry")
        return parse_version_response(payload)

    async def set_power(self, on: bool) -> None:
        """Turn the camera on or off."""
        value = 0x02 if on else 0x03
        await self.send(build_payload(self.camera_id, 0x01, 0x04, 0x00, value), TYPE_COMMAND, "completion")

    async def pan_tilt(self, direction: str, pan_speed: int | None = None, tilt_speed: int | None = None) -> None:
        """Start or stop a continuous pan/tilt move."""
        if direction not in PTZ_DIRECTIONS:
            raise ViscaError(f"Unknown PTZ direction: {direction}")
        pan_dir, tilt_dir = PTZ_DIRECTIONS[direction]
        pan = pan_speed if pan_speed is not None else self.speeds.pan
        tilt = tilt_speed if tilt_speed is not None else self.speeds.tilt
        wait: WaitMode = "ack" if direction != "stop" else "completion"
        await self.send(
            build_payload(self.camera_id, 0x01, 0x06, 0x01, pan, tilt, pan_dir, tilt_dir),
            TYPE_COMMAND,
            wait,
        )

    async def pan_tilt_home(self) -> None:
        """Move to the home position."""
        await self.send(build_payload(self.camera_id, 0x01, 0x06, 0x04), TYPE_COMMAND, "completion")

    async def pan_tilt_stop(self) -> None:
        """Stop pan/tilt movement."""
        await self.pan_tilt("stop")

    async def zoom(self, action: str, speed: int | None = None) -> None:
        """Start or stop a zoom move."""
        use_speed = self.speeds.zoom if speed is None else speed
        if action == "stop":
            command = 0x00
            wait: WaitMode = "completion"
        elif action == "in":
            command = 0x20 + use_speed
            wait = "ack"
        elif action == "out":
            command = 0x30 + use_speed
            wait = "ack"
        else:
            raise ViscaError(f"Unknown zoom action: {action}")
        await self.send(build_payload(self.camera_id, 0x01, 0x04, 0x07, command), TYPE_COMMAND, wait)

    async def zoom_stop(self) -> None:
        """Stop zoom movement."""
        await self.zoom("stop")

    async def recall_preset(self, preset: int) -> None:
        """Recall a camera preset (1-64)."""
        await self.send(
            build_payload(self.camera_id, 0x01, 0x04, 0x3F, 0x02, _preset_index(preset)),
            TYPE_COMMAND,
            "completion",
        )

    async def save_preset(self, preset: int) -> None:
        """Save the current position as a camera preset (1-64)."""
        await self.send(
            build_payload(self.camera_id, 0x01, 0x04, 0x3F, 0x01, _preset_index(preset)),
            TYPE_COMMAND,
            "completion",
        )

    async def inquire(self, *command_bytes: int) -> bytes:
        """Send a VISCA inquiry and return the payload."""
        return await self.send(build_payload(self.camera_id, *command_bytes), TYPE_INQUIRY, "inquiry")

    async def command(self, *command_bytes: int, wait: WaitMode = "completion") -> bytes:
        """Send a VISCA command."""
        return await self.send(build_payload(self.camera_id, *command_bytes), TYPE_COMMAND, wait)

    async def set_on_off(self, *prefix: int, on: bool, wait: WaitMode = "completion") -> None:
        """Send a standard 02/03 on/off VISCA command."""
        await self.command(*prefix, 0x02 if on else 0x03, wait=wait)

    async def send_hex_command(self, hex_command: str) -> None:
        """Send a raw VISCA payload from a hex string (address optional)."""
        cleaned = hex_command.replace(" ", "").replace(":", "")
        try:
            payload = bytes.fromhex(cleaned)
        except ValueError as err:
            raise ViscaError("Command must be hexadecimal") from err
        if not payload:
            raise ViscaError("Command is empty")
        if payload[0] & 0xF0 != 0x80:
            payload = bytes((camera_address(self.camera_id), *payload))
        if payload[-1] != 0xFF:
            payload = payload + bytes((0xFF,))
        await self.send(payload, TYPE_COMMAND, "completion")

    async def set_focus_mode(self, mode: str) -> None:
        """Set auto or manual focus."""
        if mode not in ("auto", "manual"):
            raise ViscaError(f"Unknown focus mode: {mode}")
        await self.set_on_off(0x01, 0x04, 0x38, on=mode == "auto")

    async def focus(self, action: str, speed: int | None = None) -> None:
        """Start or stop a focus move."""
        if action not in FOCUS_ACTIONS:
            raise ViscaError(f"Unknown focus action: {action}")
        use_speed = self.speeds.focus if speed is None else speed
        if action == "stop":
            command, wait = 0x00, "completion"
        elif action == "far":
            command, wait = 0x20 + use_speed, "ack"
        else:
            command, wait = 0x30 + use_speed, "ack"
        await self.command(0x01, 0x04, 0x08, command, wait=wait)

    async def focus_one_push(self) -> None:
        """Trigger one-push autofocus."""
        await self.command(0x01, 0x04, 0x18, 0x01)

    async def focus_infinity(self) -> None:
        """Set focus to infinity."""
        await self.command(0x01, 0x04, 0x18, 0x02)

    async def set_focus_direct(self, position: int) -> None:
        """Set the focus position."""
        await self.command(0x01, 0x04, 0x48, *nibble_bytes(position, 4))

    async def set_zoom_direct(self, position: int) -> None:
        """Set the zoom position."""
        await self.command(0x01, 0x04, 0x47, *nibble_bytes(position, 4))

    async def set_zoom_mode(self, mode: str) -> None:
        """Set optical, digital, or clear-image zoom."""
        if mode not in ZOOM_MODE_BYTES:
            raise ViscaError(f"Unknown zoom mode: {mode}")
        await self.command(0x01, 0x04, 0x06, ZOOM_MODE_BYTES[mode])

    async def set_tele_convert(self, on: bool) -> None:
        """Enable or disable tele convert."""
        await self.set_on_off(0x01, 0x7E, 0x04, 0x36, on=on)

    async def set_af_mode(self, mode: str) -> None:
        """Set AF mode (normal / interval / zoom trigger)."""
        if mode not in AF_MODE_BYTES:
            raise ViscaError(f"Unknown AF mode: {mode}")
        await self.command(0x01, 0x04, 0x57, AF_MODE_BYTES[mode])

    async def set_af_sensitivity(self, mode: str) -> None:
        """Set AF sensitivity."""
        if mode not in ("normal", "low"):
            raise ViscaError(f"Unknown AF sensitivity: {mode}")
        await self.command(0x01, 0x04, 0x58, 0x02 if mode == "normal" else 0x03)

    async def set_af_interval(self, op_time: int, stay_time: int) -> None:
        """Set AF interval operating and stay times."""
        await self.command(
            0x01,
            0x04,
            0x27,
            *nibble_bytes(op_time & 0xFF, 2),
            *nibble_bytes(stay_time & 0xFF, 2),
        )

    async def set_focus_near_limit(self, position: int) -> None:
        """Set the focus near limit."""
        await self.command(0x01, 0x04, 0x28, *nibble_bytes(position, 4))

    async def set_zoom_speed_type(self, mode: str) -> None:
        """Set zoom speed type on X1000-family cameras."""
        if mode not in ZOOM_SPEED_TYPE_BYTES:
            raise ViscaError(f"Unknown zoom speed type: {mode}")
        await self.command(0x01, 0x7E, 0x04, 0x57, ZOOM_SPEED_TYPE_BYTES[mode])

    async def set_exposure_mode(self, mode: str) -> None:
        """Set the exposure mode."""
        if mode not in EXPOSURE_MODE_BYTES:
            raise ViscaError(f"Unknown exposure mode: {mode}")
        await self.command(0x01, 0x04, 0x39, EXPOSURE_MODE_BYTES[mode])

    async def set_iris_direct(self, value: int) -> None:
        """Set iris from a raw VISCA byte."""
        await self.command(0x01, 0x04, 0x4B, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_gain_direct(self, value: int) -> None:
        """Set gain from a raw VISCA byte."""
        await self.command(0x01, 0x04, 0x4C, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_shutter_direct(self, value: int) -> None:
        """Set shutter from a raw VISCA byte."""
        await self.command(0x01, 0x04, 0x4A, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_brightness_direct(self, value: int) -> None:
        """Set brightness position on legacy cameras."""
        await self.command(0x01, 0x04, 0x4D, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_exposure_comp(self, on: bool) -> None:
        """Enable or disable exposure compensation."""
        await self.set_on_off(0x01, 0x04, 0x3E, on=on)

    async def set_exposure_comp_direct(self, value: int) -> None:
        """Set exposure compensation from a raw VISCA byte."""
        await self.command(0x01, 0x04, 0x4E, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_backlight(self, on: bool) -> None:
        """Enable or disable backlight compensation."""
        await self.set_on_off(0x01, 0x04, 0x33, on=on)

    async def set_spotlight(self, on: bool) -> None:
        """Enable or disable spotlight compensation."""
        await self.set_on_off(0x01, 0x04, 0x3A, on=on)

    async def set_slow_shutter(self, on: bool) -> None:
        """Enable or disable auto slow shutter."""
        await self.set_on_off(0x01, 0x04, 0x5A, on=on)

    async def set_noise_reduction(self, level: int) -> None:
        """Set noise reduction level 0-5."""
        await self.command(0x01, 0x04, 0x53, level & 0x0F)

    async def set_wdr(self, mode: str) -> None:
        """Set wide dynamic range."""
        if mode not in WDR_MODE_BYTES:
            raise ViscaError(f"Unknown WDR mode: {mode}")
        await self.command(0x01, 0x7E, 0x04, 0x00, WDR_MODE_BYTES[mode])

    async def set_high_sensitivity(self, on: bool) -> None:
        """Enable or disable high sensitivity."""
        await self.set_on_off(0x01, 0x04, 0x5E, on=on)

    async def set_visibility_enhancer(self, on: bool) -> None:
        """Enable or disable visibility enhancer."""
        await self.set_on_off(0x01, 0x04, 0x3D, on=on)

    async def set_defog(self, on: bool) -> None:
        """Enable or disable defog."""
        await self.set_on_off(0x01, 0x04, 0x37, on=on)

    async def set_ae_speed(self, value: int) -> None:
        """Set AE speed."""
        await self.command(0x01, 0x04, 0x5D, value & 0x3F)

    async def set_gain_limit(self, value: int) -> None:
        """Set gain limit."""
        await self.command(0x01, 0x04, 0x2C, value & 0x0F)

    async def set_wb_mode(self, mode: str) -> None:
        """Set white balance mode."""
        if mode not in WB_MODE_BYTES:
            raise ViscaError(f"Unknown white-balance mode: {mode}")
        await self.command(0x01, 0x04, 0x35, WB_MODE_BYTES[mode])

    async def wb_one_push(self) -> None:
        """Trigger one-push white balance."""
        await self.command(0x01, 0x04, 0x10, 0x05)

    async def set_red_gain_direct(self, value: int) -> None:
        """Set red gain."""
        await self.command(0x01, 0x04, 0x43, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_blue_gain_direct(self, value: int) -> None:
        """Set blue gain."""
        await self.command(0x01, 0x04, 0x44, 0x00, 0x00, *nibble_bytes(value & 0xFF, 2))

    async def set_wb_offset(self, value: int) -> None:
        """Set white-balance offset (-7 to +7 stored as 0-14)."""
        await self.command(0x01, 0x7E, 0x01, 0x2E, 0x00, 0x00, *nibble_bytes((value + 7) & 0xFF, 2))

    async def set_wb_speed(self, value: int) -> None:
        """Set white-balance speed."""
        await self.command(0x01, 0x04, 0x56, value & 0x07)

    async def set_color_gain(self, value: int) -> None:
        """Set color gain / level."""
        await self.command(0x01, 0x04, 0x49, 0x00, 0x00, 0x00, value & 0x0F)

    async def set_color_hue(self, value: int) -> None:
        """Set color hue / phase (0-14, 7 is center)."""
        await self.command(0x01, 0x04, 0x4F, 0x00, 0x00, 0x00, value & 0x0F)

    async def set_chroma_suppress(self, value: int) -> None:
        """Set chroma suppress level."""
        await self.command(0x01, 0x04, 0x5F, value & 0x07)

    async def set_gamma(self, value: int) -> None:
        """Set gamma table."""
        await self.command(0x01, 0x04, 0x5B, value & 0x0F)

    async def set_detail_level(self, value: int) -> None:
        """Set detail level (-7 to +7 stored as 0-14)."""
        await self.command(0x01, 0x05, 0x42, (value + 7) & 0x0F)

    async def set_black_level(self, value: int) -> None:
        """Set black level."""
        await self.command(0x01, 0x7E, 0x04, 0x15, *nibble_bytes(value & 0xFF, 2))

    async def set_picture_profile(self, value: int) -> None:
        """Set picture profile index."""
        await self.command(0x01, 0x7E, 0x04, 0x5F, value & 0x0F)

    async def set_color_matrix(self, value: int) -> None:
        """Set color matrix index."""
        await self.command(0x01, 0x04, 0x7A, value & 0x0F)

    async def set_knee(self, on: bool) -> None:
        """Enable or disable knee."""
        await self.set_on_off(0x01, 0x7E, 0x01, 0x6D, on=on)

    async def pan_tilt_reset(self) -> None:
        """Reset pan/tilt."""
        await self.command(0x01, 0x06, 0x05)

    async def set_pt_slow(self, on: bool) -> None:
        """Enable or disable pan/tilt slow mode."""
        await self.set_on_off(0x01, 0x06, 0x44, on=on)

    async def set_ramp_curve(self, value: int) -> None:
        """Set ramp curve 1-9."""
        await self.command(0x01, 0x06, 0x31, value & 0x0F)

    async def set_pan_reverse(self, on: bool) -> None:
        """Reverse pan direction."""
        await self.command(0x01, 0x7E, 0x01, 0x06, 0x00, 0x01 if on else 0x00)

    async def set_tilt_reverse(self, on: bool) -> None:
        """Reverse tilt direction."""
        await self.command(0x01, 0x7E, 0x01, 0x09, 0x00, 0x01 if on else 0x00)

    async def pan_tilt_absolute(
        self,
        pan: int,
        tilt: int,
        speed: int | None = None,
        visca_id: str | None = None,
        relative: bool = False,
    ) -> None:
        """Move to an absolute or relative pan/tilt position."""
        use_speed = speed if speed is not None else self.speeds.pan
        payload = build_pt_position_payload(self.camera_id, 0x03 if relative else 0x02, use_speed, pan, tilt, visca_id)
        await self.send(payload, TYPE_COMMAND, "completion")

    async def set_preset_speed(self, preset: int, speed: int) -> None:
        """Set the recall drive speed for one preset."""
        await self.command(0x01, 0x7E, 0x01, 0x0B, _preset_index(preset), speed & 0xFF)

    async def set_preset_speed_select(self, mode: str) -> None:
        """Set preset speed compatible/separate/common."""
        if mode not in PRESET_SPEED_MODE_BYTES:
            raise ViscaError(f"Unknown preset speed mode: {mode}")
        await self.command(0x01, 0x7E, 0x04, 0x1B, PRESET_SPEED_MODE_BYTES[mode])

    async def set_preset_speed_common(self, speed: int) -> None:
        """Set the common preset drive speed."""
        await self.command(0x01, 0x7E, 0x04, 0x1C, *nibble_bytes(speed & 0xFF, 2))

    async def set_preset_mode(self, mode: str) -> None:
        """Set preset mode 1/2/trace."""
        if mode not in PRESET_MODE_BYTES:
            raise ViscaError(f"Unknown preset mode: {mode}")
        await self.command(0x01, 0x7E, 0x04, 0x3D, PRESET_MODE_BYTES[mode])

    async def set_tally(self, on: bool, color: str = "red") -> None:
        """Set tally lamp state."""
        color_cmd = {"green": (0x04, 0x1A), "yellow": (0x04, 0x11)}.get(color, (0x01, 0x0A))
        await self.command(0x01, 0x7E, *color_cmd, 0x00, 0x02 if on else 0x03)

    async def set_tally_level(self, level: str) -> None:
        """Set tally brightness."""
        if level not in TALLY_LEVEL_BYTES:
            raise ViscaError(f"Unknown tally level: {level}")
        await self.command(0x01, 0x7E, 0x01, 0x0A, 0x01, TALLY_LEVEL_BYTES[level])

    async def set_auto_framing(self, on: bool) -> None:
        """Enable or disable PTZ auto framing."""
        await self.command(0x01, 0x7E, 0x04, 0x3A, 0x01 if on else 0x00)

    async def menu_back(self) -> None:
        """Toggle or go back in the camera menu."""
        await self.command(0x01, 0x06, 0x06, 0x10)

    async def menu_enter(self) -> None:
        """Press menu enter."""
        await self.command(0x01, 0x7E, 0x01, 0x02, 0x00, 0x01)

    async def set_icr(self, on: bool) -> None:
        """Enable or disable ICR / night mode."""
        await self.set_on_off(0x01, 0x04, 0x01, on=on)

    async def set_auto_icr(self, on: bool) -> None:
        """Enable or disable auto ICR."""
        await self.set_on_off(0x01, 0x04, 0x51, on=on)

    async def set_image_flip(self, on: bool) -> None:
        """Enable or disable image flip."""
        await self.set_on_off(0x01, 0x04, 0x66, on=on)

    async def set_image_stabilizer(self, on: bool) -> None:
        """Enable or disable image stabilizer."""
        await self.set_on_off(0x01, 0x04, 0x34, on=on)

    async def set_flicker_cancel(self, on: bool) -> None:
        """Enable or disable flicker cancel."""
        await self.set_on_off(0x01, 0x04, 0x32, on=on)

    async def set_high_resolution(self, on: bool) -> None:
        """Enable or disable high resolution."""
        await self.set_on_off(0x01, 0x04, 0x52, on=on)

    async def set_picture_effect(self, mode: str) -> None:
        """Set picture effect."""
        if mode not in PICTURE_EFFECT_BYTES:
            raise ViscaError(f"Unknown picture effect: {mode}")
        await self.command(0x01, 0x04, 0x63, PICTURE_EFFECT_BYTES[mode])

    async def set_ir_receive(self, on: bool) -> None:
        """Enable or disable IR receive."""
        await self.set_on_off(0x01, 0x06, 0x08, on=on)

    async def set_color_bar(self, on: bool) -> None:
        """Enable or disable the color bar."""
        await self.set_on_off(0x01, 0x04, 0x7D, on=on)

    async def set_standby_mode(self, on: bool) -> None:
        """Enable or disable standby mode."""
        await self.set_on_off(0x01, 0x7E, 0x04, 0x50, on=on)

    async def set_osd(self, on: bool) -> None:
        """Show or hide the on-screen display."""
        await self.set_on_off(0x01, 0x7E, 0x04, 0x76, on=on)

    async def send(
        self,
        payload: bytes,
        packet_type: bytes = TYPE_COMMAND,
        wait: WaitMode = "ack",
    ) -> bytes:
        """Queue a VISCA packet and wait for the selected response."""
        if self._transport is None or self._loop is None:
            raise ViscaError("VISCA client is not connected")

        future: asyncio.Future[bytes] = self._loop.create_future()
        queued = _Queued(payload=payload, packet_type=packet_type, wait=wait, future=future)
        if self._cts:
            self._send_packet(queued)
        else:
            self._queue.append(queued)
        return await future

    def handle_response(self, data: bytes) -> None:
        """Handle a VISCA-over-IP datagram from the camera."""
        parsed = parse_ip_packet(data)
        if parsed is None:
            return
        sequence, payload = parsed

        if (payload[1] & 0xF0) == 0x60 and len(payload) >= 3:
            error_code = payload[2]
            error_text = VISCA_ERRORS.get(error_code, "Unknown VISCA error")
            LOGGER.warning("VISCA error 0x%02x: %s", error_code, error_text)

        pending = self._active.get(sequence)
        if pending is None:
            return

        is_initial = sequence == self._pending_seq
        response_type = payload[1] >> 4

        if response_type == 4:
            self._on_successful_response()
            if pending.wait == "ack":
                if not pending.future.done():
                    pending.future.set_result(payload)
                self._clear_pending(sequence)
            else:
                self._reschedule(pending, COMMAND_COMPLETION_TIMEOUT_MS / 1000)
            if is_initial:
                self._pending_seq = None
                self._drain_or_idle()
            return

        if payload[1] == 0x50 and len(payload) > 3:
            self._finish(sequence, payload, None)
            self._on_successful_response()
            if is_initial:
                self._pending_seq = None
                self._drain_or_idle()
            return

        if response_type == 5:
            if pending.wait != "ack" and not pending.future.done():
                pending.future.set_result(payload)
            elif pending.wait == "ack" and not pending.future.done():
                pending.future.set_result(payload)
            self._clear_pending(sequence)
            self._on_successful_response()
            if is_initial:
                self._pending_seq = None
                self._drain_or_idle()
            return

        if response_type == 6:
            error_code = payload[2] if len(payload) >= 3 else 0
            error_text = VISCA_ERRORS.get(error_code, "Unknown VISCA error")
            self._finish(sequence, None, ViscaError(f"{error_text} (0x{error_code:02x})"))
            self._on_successful_response()
            if is_initial:
                self._pending_seq = None
                self._drain_or_idle()

    def _send_packet(self, queued: _Queued) -> None:
        if self._transport is None or self._loop is None:
            if not queued.future.done():
                queued.future.set_exception(ViscaError("VISCA client is not connected"))
            self._cts = True
            return

        self._cts = False
        self._sequence += 1
        if self._sequence >= 0xFFFFFFFF:
            self.reset_sequence()
            self._queue.appendleft(queued)
            return

        packet = build_packet(queued.packet_type, self._sequence, queued.payload)
        pending = _Pending(
            future=queued.future,
            wait=queued.wait,
            is_command=queued.packet_type == TYPE_COMMAND,
        )
        # Occupying commands (power, preset) may get Completion as the first
        # forwarded reply. The 2s ACK timeout is too short for power-on (~7s).
        first_timeout_ms = COMMAND_COMPLETION_TIMEOUT_MS if queued.wait == "completion" else TIMEOUT_MS
        pending.timer = self._loop.call_later(first_timeout_ms / 1000, self._handle_timeout, self._sequence)
        self._active[self._sequence] = pending
        self._pending_seq = self._sequence
        LOGGER.debug("VISCA send seq=%s %s", self._sequence, packet.hex(" "))
        self._send_datagram(packet)

    def _drain_or_idle(self) -> None:
        if self._queue:
            self._send_packet(self._queue.popleft())
        else:
            self._cts = True

    def _on_successful_response(self) -> None:
        self._consecutive_timeouts = 0

    def _handle_timeout(self, sequence: int) -> None:
        pending = self._active.pop(sequence, None)
        if pending is None:
            return
        LOGGER.warning("VISCA timeout for packet seq=%s", sequence)
        self._consecutive_timeouts += 1
        if not pending.future.done():
            pending.future.set_exception(ViscaError(f"VISCA timeout for sequence {sequence}"))

        if self._consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
            LOGGER.warning("Too many VISCA timeouts, resetting connection")
            self.reset_sequence()
            return

        if sequence == self._pending_seq:
            self._pending_seq = None
            self._cts = True
            if self._queue:
                self._send_packet(self._queue.popleft())

    def _reschedule(self, pending: _Pending, delay: float) -> None:
        if pending.timer is not None:
            pending.timer.cancel()
        if self._loop is not None:
            # Keep the sequence in _active so completion can still arrive.
            sequence = next((seq for seq, item in self._active.items() if item is pending), None)
            if sequence is not None:
                pending.timer = self._loop.call_later(delay, self._handle_timeout, sequence)

    def _finish(self, sequence: int, payload: bytes | None, error: Exception | None) -> None:
        pending = self._active.pop(sequence, None)
        if pending is None:
            return
        if pending.timer is not None:
            pending.timer.cancel()
        if pending.future.done():
            return
        if error is not None:
            pending.future.set_exception(error)
        elif payload is not None:
            pending.future.set_result(payload)

    def _clear_pending(self, sequence: int) -> None:
        pending = self._active.pop(sequence, None)
        if pending is not None and pending.timer is not None:
            pending.timer.cancel()

    def _cancel_all(self, error: Exception) -> None:
        for pending in self._active.values():
            if pending.timer is not None:
                pending.timer.cancel()
            if not pending.future.done():
                pending.future.set_exception(error)
        self._active.clear()
        while self._queue:
            queued = self._queue.popleft()
            if not queued.future.done():
                queued.future.set_exception(error)
        self._pending_seq = None
        self._cts = True


def _preset_index(preset: int) -> int:
    if not 1 <= preset <= 64:
        raise ViscaError("Preset must be between 1 and 64")
    return (preset - 1) & 0xFF


async def async_probe_camera(host: str, port: int, camera_id: int) -> CameraProbe:
    """Open a short-lived client, confirm power, and try CAM_VersionInq."""
    client = ViscaClient(host, port, camera_id)
    try:
        await client.connect()
        power_on = await client.inquire_power()
        version = None
        try:
            version = await client.inquire_version()
        except ViscaError:
            LOGGER.debug("CAM_VersionInq failed for %s:%s", host, port)
        candidates, model_key = resolve_probe_models(version)
        return CameraProbe(
            power_on=power_on,
            version=version,
            candidates=candidates,
            model_key=model_key,
        )
    finally:
        await client.disconnect()


async def async_test_connection(host: str, port: int, camera_id: int) -> bool:
    """Open a short-lived client and run CAM_PowerInq."""
    await async_probe_camera(host, port, camera_id)
    return True
