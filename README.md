# SensoredLife (MarCELL) for Home Assistant

A custom integration that brings [SensoredLife](https://www.sensoredlife.com)
**MarCELL** cellular temperature / humidity / power monitors — and their wireless
**SPuck** sub-probes — into Home Assistant.

These units report over the cellular network to the SensoredLife cloud; there is
no local API. This integration polls the SensoredLife cloud **cache** (the same
data the website shows). It **never** triggers the paid on-demand "Update"
button, so it does not consume your account's instant-update credits.

> Unofficial. Not affiliated with or endorsed by SensoredLife, LLC.

## Features

Each MarCELL gateway becomes a Home Assistant **device** with:

| Entity | Notes |
| --- | --- |
| `sensor` Temperature | °F, with `safe_minimum` / `safe_maximum` / `in_safe_range` attributes |
| `sensor` Humidity | %, with the same safe-range attributes |
| `binary_sensor` Power | `plug` — on = mains, off = running on backup battery |
| `binary_sensor` Online | `connectivity` — off when the last cloud read is stale |
| `sensor` Signal strength | diagnostic |
| `sensor` Backup battery | gateway internal cell voltage, diagnostic |
| `sensor` Last read | timestamp of the most recent cloud read, diagnostic |

Each wireless **SPuck** becomes a child device (linked to its gateway) with
Temperature, Humidity, and Battery (%) sensors. A SPuck that has dropped offline
(the cloud returns its `999.9 °F` / `99.9 %` sentinels) reports as
**unavailable** rather than a bogus reading.

## Installation

### HACS (custom repository)

1. HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Add `https://github.com/jasonjhofmann/sensoredlife-homeassistant`, category
   **Integration**.
3. Install **SensoredLife (MarCELL)** and restart Home Assistant.

### Manual

Copy `custom_components/sensoredlife/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Settings → **Devices & Services** → **Add Integration** → **SensoredLife
(MarCELL)**, then enter:

| Parameter | Description |
| --- | --- |
| **Username** | The email address you use to sign in at sensoredlife.com. |
| **Password** | Your SensoredLife account password. |

Credentials are validated against the cloud before the entry is created. If the
password later changes (or is rejected), Home Assistant starts a
**re-authentication** flow automatically — no need to delete and re-add.

The integration polls every 15 minutes. The MarCELL units themselves only call
in every 1–2 hours, so this simply keeps Home Assistant in step with the cloud
cache.

## Removal

Settings → **Devices & Services** → **SensoredLife (MarCELL)** → ⋮ → **Delete**.
No credentials or files are left behind.

## Troubleshooting

- **"Invalid username or password"** when adding — confirm the same credentials
  work at [sensoredlife.com](https://www.sensoredlife.com). The integration uses
  the website login, not a separate API key.
- **Entities show *Unavailable*** — a coordinator poll failed (cloud
  unreachable) or, for a SPuck, the probe is offline / out of RF range of its
  gateway. Check the gateway's **Online** binary sensor and **Last read** time.
- **Re-authentication prompt** — your SensoredLife password changed; enter the
  new one when prompted.

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.sensoredlife: debug
```

## Quality scale

Targets the **Silver** tier of the Home Assistant Integration Quality Scale. See
[`custom_components/sensoredlife/quality_scale.yaml`](custom_components/sensoredlife/quality_scale.yaml)
for the per-rule status. Every code rule is satisfied and module test coverage
is ≥95%. The one remaining item is brand assets — a separate
home-assistant/brands submission, which cannot live in this repo.

## License

[MIT](LICENSE)
