"""Test helpers.

When Home Assistant is not installed, register the integration package without
executing its Home Assistant ``__init__.py`` so protocol tests can import
``visca`` and ``const`` directly.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "custom_components" / "sony_visca"


def pytest_configure() -> None:
    """Allow importing protocol modules without Home Assistant."""
    try:
        import homeassistant  # noqa: F401
    except ImportError:
        parent = types.ModuleType("custom_components")
        parent.__path__ = [str(ROOT / "custom_components")]
        package = types.ModuleType("custom_components.sony_visca")
        package.__path__ = [str(PACKAGE_DIR)]
        parent.sony_visca = package
        sys.modules.setdefault("custom_components", parent)
        sys.modules["custom_components.sony_visca"] = package
