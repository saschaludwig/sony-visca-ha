"""Async tests for the VISCA UDP client against a fake camera."""

from __future__ import annotations

import asyncio

from custom_components.sony_visca.const import TYPE_COMMAND
from custom_components.sony_visca.visca import ViscaClient, build_packet, build_payload


class FakeCameraProtocol(asyncio.DatagramProtocol):
    """Minimal VISCA-over-IP responder for tests."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.received: list[bytes] = []

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.received.append(data)
        if self.transport is None or data[:2] == bytes((0x02, 0x00)):
            return

        sequence = int.from_bytes(data[4:8], "big")
        payload = data[8:]
        reply_payload: bytes | None = None

        if len(payload) >= 4 and payload[1:4] == bytes((0x09, 0x00, 0x02)):
            reply_payload = bytes.fromhex("90 50 00 01 06 17 01 00 02 FF")
        elif len(payload) >= 4 and payload[1:4] == bytes((0x09, 0x04, 0x00)):
            reply_payload = bytes.fromhex("90 50 02 FF")
        elif len(payload) >= 4 and payload[1:4] == bytes((0x09, 0x06, 0x12)):
            reply_payload = bytes.fromhex("90 50 00 01 02 03 00 04 05 06 FF")
        elif len(payload) >= 4 and payload[1:4] == bytes((0x09, 0x04, 0x47)):
            reply_payload = bytes.fromhex("90 50 00 04 00 00 FF")
        elif len(payload) >= 2 and payload[1] == 0x01:
            ack = build_packet(bytes((0x01, 0x11)), sequence, bytes.fromhex("90 41 FF"))
            done = build_packet(bytes((0x01, 0x11)), sequence, bytes.fromhex("90 51 FF"))
            self.transport.sendto(ack, addr)
            self.transport.sendto(done, addr)
            return

        if reply_payload is not None:
            self.transport.sendto(build_packet(bytes((0x01, 0x11)), sequence, reply_payload), addr)


async def _start_fake_camera() -> tuple[asyncio.DatagramTransport, FakeCameraProtocol, int]:
    loop = asyncio.get_running_loop()
    protocol = FakeCameraProtocol()
    transport, _ = await loop.create_datagram_endpoint(lambda: protocol, local_addr=("127.0.0.1", 0))
    port = transport.get_extra_info("sockname")[1]
    return transport, protocol, port


def test_client_inquiries_and_commands() -> None:
    asyncio.run(_client_inquiries_and_commands())


async def _client_inquiries_and_commands() -> None:
    transport, camera, port = await _start_fake_camera()
    client = ViscaClient("127.0.0.1", port, 1)
    try:
        await client.connect()
        assert await client.inquire_power() is True
        version = await client.inquire_version()
        assert version.model_id_hex == "0617"
        pan, tilt = await client.inquire_pan_tilt()
        assert pan == 0x0123
        assert tilt == 0x0456
        assert await client.inquire_zoom() == 0x0400

        await client.set_power(True)
        await client.pan_tilt("left")
        await client.zoom("in")
        await client.recall_preset(3)
        await client.save_preset(3)
    finally:
        await client.disconnect()
        transport.close()

    command_payloads = [packet[8:] for packet in camera.received if packet[:2] == TYPE_COMMAND]
    assert build_payload(1, 0x01, 0x04, 0x00, 0x02) in command_payloads
    assert build_payload(1, 0x01, 0x06, 0x01, 0x0C, 0x0C, 0x01, 0x03) in command_payloads
    assert build_payload(1, 0x01, 0x04, 0x07, 0x21) in command_payloads
    assert build_payload(1, 0x01, 0x04, 0x3F, 0x02, 2) in command_payloads
    assert build_payload(1, 0x01, 0x04, 0x3F, 0x01, 2) in command_payloads


def test_variable_zoom_speed_payload() -> None:
    asyncio.run(_variable_zoom_speed_payload())


async def _variable_zoom_speed_payload() -> None:
    transport, camera, port = await _start_fake_camera()
    client = ViscaClient("127.0.0.1", port, 2)
    try:
        await client.connect()
        await client.zoom("out", speed=5)
    finally:
        await client.disconnect()
        transport.close()

    assert build_payload(2, 0x01, 0x04, 0x07, 0x35) in [packet[8:] for packet in camera.received]
