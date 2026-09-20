# Sony VISCA for Home Assistant

Custom Home Assistant integration for Sony PTZ cameras that speak **VISCA over IP**.

This integration covers connection setup, power, pan/tilt/zoom, focus, exposure, white balance, presets 1–64, tally, and system features. Entities are filtered by camera model.

## Requirements

- Home Assistant 2024.1 or newer
- A Sony (or compatible) PTZ camera with **VISCA over IP** enabled
- UDP port **52381** reachable from Home Assistant (default)

Several Sony models disable VISCA over IP by default. Enable it in the on-screen menu or with the dip switches on the back of the camera. See the camera technical manual for the exact steps.

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install **Sony VISCA**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for **Sony VISCA**.

### Manual

1. Copy `custom_components/sony_visca` into `<config>/custom_components/sony_visca`.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Configuration

The integration is configured in the UI (config flow). YAML setup is not supported.

| Field | Default | Description |
| --- | --- | --- |
| Host | — | Camera IP address or hostname |
| Port | `52381` | VISCA over IP UDP port |
| Camera ID | `1` | VISCA address (`1` becomes `0x81`) |

Setup sends `CAM_PowerInq` and `CAM_VersionInq`. Known Sony models are selected automatically. If several cameras share the same VISCA identity (for example SRG-201SE / 300SE / 301SE), a dropdown of those product names is shown. Unknown cameras can be set to **Other / generic** (universal features only) or **Other / all features**.

After setup, open the integration options to set the **frame rate** (`60` / `50` / `24`). This selects the shutter-speed labels used by the camera.

## Entities and services

Each camera becomes one device. Only entities supported by the selected model are created.

- Power, exposure compensation, backlight/spotlight, ICR, tally, stabilizer, and other feature switches
- Selects for focus/zoom/exposure/white-balance modes plus iris, gain, and shutter
- Numbers for speeds, zoom/focus position, gains, and other levels
- Buttons for home, stop, preset recall/save, one-push AF, and PT reset
- Sensors for power, pan/tilt/zoom/focus position, and pan/tilt degrees

Domain services for automations and dashboards:

- `sony_visca.ptz` — continuous pan/tilt (`left`, `right`, `up`, `down`, diagonals, `stop`)
- `sony_visca.zoom` — `in` / `out` / `stop`, optional variable speed 0–7
- `sony_visca.focus` — `near` / `far` / `stop`, optional variable speed 0–7
- `sony_visca.recall_preset` / `sony_visca.save_preset` — presets 1–64
- `sony_visca.ptz_absolute` / `sony_visca.ptz_relative` — raw or degree positions
- `sony_visca.send_command` — raw hexadecimal VISCA payload

If more than one camera is configured, target the device in the service call.

Tally uses a 10-second keepalive while the switch stays on, matching Sony camera behaviour.
