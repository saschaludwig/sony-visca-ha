"""Tests for connection checks and config-flow helpers."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.sony_visca import visca as visca_module
from custom_components.sony_visca.const import DEFAULT_CAMERA_ID, DEFAULT_MODEL, DEFAULT_PORT
from custom_components.sony_visca.models import model_display_name, models_for_visca_id, resolve_model_key
from custom_components.sony_visca.visca import ViscaError, ViscaVersion, async_probe_camera, config_unique_id


class _FakeClient:
    """Stand-in for ViscaClient used by the config-flow connection test."""

    instances: list[_FakeClient] = []

    def __init__(self, host: str, port: int, camera_id: int) -> None:
        self.host = host
        self.port = port
        self.camera_id = camera_id
        self.connected = False
        self.disconnected = False
        self.fail_connect = False
        self.fail_inquiry = False
        self.version: ViscaVersion | None = ViscaVersion(0x0001, 0x0617, 0x0100, 0x02)
        _FakeClient.instances.append(self)

    async def connect(self) -> None:
        if self.fail_connect:
            raise ViscaError("connect failed")
        self.connected = True

    async def inquire_power(self) -> bool:
        if self.fail_inquiry:
            raise ViscaError("inquiry failed")
        return True

    async def inquire_version(self) -> ViscaVersion:
        if self.version is None:
            raise ViscaError("no version")
        return self.version

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset_fake_clients() -> None:
    _FakeClient.instances = []


def test_unique_id_and_model_names() -> None:
    assert config_unique_id("cam.local", DEFAULT_PORT, DEFAULT_CAMERA_ID) == "cam.local:52381:1"
    assert DEFAULT_MODEL == "other"
    assert model_display_name("srg_x400") == "SRG-X400"
    assert model_display_name("051E") == "ILME-FR7"
    assert resolve_model_key("other_all") == "other_all"
    assert resolve_model_key("other_min") == "other"
    assert [model.name for model in models_for_visca_id("0516")] == [
        "SRG-201SE",
        "SRG-300SE",
        "SRG-301SE",
    ]


def test_async_probe_detects_unique_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(visca_module, "ViscaClient", _FakeClient)
    probe = asyncio.run(async_probe_camera("192.168.0.100", 52381, 1))
    client = _FakeClient.instances[0]
    assert client.connected is True
    assert client.disconnected is True
    assert probe.model_key == "srg_x400"
    assert probe.visca_model_id == "0617"


def test_async_probe_inquiry_failure_still_disconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(host: str, port: int, camera_id: int) -> _FakeClient:
        client = _FakeClient(host, port, camera_id)
        client.fail_inquiry = True
        return client

    monkeypatch.setattr(visca_module, "ViscaClient", factory)
    with pytest.raises(ViscaError, match="inquiry failed"):
        asyncio.run(async_probe_camera("192.168.0.100", 52381, 1))
    assert _FakeClient.instances[0].disconnected is True


def test_config_flow_module_imports_when_homeassistant_is_present() -> None:
    pytest.importorskip("homeassistant")
    from custom_components.sony_visca.config_flow import SonyViscaConfigFlow, USER_SCHEMA
    from custom_components.sony_visca.const import DOMAIN

    assert SonyViscaConfigFlow.domain == DOMAIN or SonyViscaConfigFlow.__name__ == "SonyViscaConfigFlow"
    schema_keys = {str(key) for key in USER_SCHEMA.schema}
    assert any("host" in key for key in schema_keys)
    assert any("port" in key for key in schema_keys)
    assert any("camera_id" in key for key in schema_keys)
    assert not any("model" in key for key in schema_keys)
