# SensoredLife (MarCELL) for Home Assistant

[![release](https://img.shields.io/github/v/release/jasonjhofmann/sensoredlife-homeassistant?label=release&color=blue)](https://github.com/jasonjhofmann/sensoredlife-homeassistant/releases)
[![hacs](https://img.shields.io/badge/HACS-custom-orange.svg)](https://hacs.xyz)
[![validate](https://github.com/jasonjhofmann/sensoredlife-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/jasonjhofmann/sensoredlife-homeassistant/actions/workflows/validate.yml)

A custom integration that brings [SensoredLife](https://www.sensoredlife.com)
**MarCELL** cellular temperature / humidity / power monitors — and their wireless
**SPuck** sub-probes — into Home Assistant.

These units report over the cellular network to the SensoredLife cloud; there is
no local API. This integration polls the SensoredLife cloud **cache** (the same
data the website shows). It **never** triggers the paid on-demand "Update"
button on its own, so routine polling does not consume your account's
instant-update credits.

> Unofficial. Not affiliated with or endorsed by SensoredLife, LLC.

## Supported devices

- **MarCELL PRO** cellular gateway (temperature / humidity / mains-power monitor
  with a backup battery). Each gateway is one Home Assistant device.
- **SPuck** wireless sub-probes paired to a gateway, as child devices:
  - Temperature/humidity SPucks (e.g. fridge/freezer/cellar probes).
  - Leak/other SPucks with no climate element (e.g. "Leak Puck") still appear
    with a Battery sensor; their temperature/humidity report *Unavailable*.

Any number of gateways and SPucks on the account are supported, and devices
added to (or removed from) the account later are picked up automatically without
re-adding the integration.

## Supported functionality

Each MarCELL gateway becomes a Home Assistant **device** with:

| Entity | Notes |
| --- | --- |
| `sensor` Temperature | °F, with `safe_minimum` / `safe_maximum` / `in_safe_range` attributes |
| `sensor` Humidity | %, with the same safe-range attributes |
| `binary_sensor` Power | `plug` — on = mains, off = running on backup battery |
| `binary_sensor` Online | `connectivity` — off when the device hasn't reported in >9 h |
| `sensor` Signal strength | diagnostic (disabled by default) |
| `sensor` Backup battery | gateway internal cell voltage, diagnostic |
| `sensor` Last read | timestamp of the most recent cloud read, diagnostic |
| `button` Request reading | on-demand "call in now" (the website's **Update** button) |

Each wireless **SPuck** becomes a child device (linked to its gateway) with
**Temperature**, **Humidity**, **Battery (%)**, and a **Last call-in** timestamp
(when the probe last actually reported to its gateway — so a SPuck that has gone
silent is obvious instead of echoing a stale value). A SPuck that has dropped
offline (the cloud returns its `999.9 °F` / `99.9 %` sentinels) reports as
**Unavailable** rather than a bogus reading.

## Data updates

The integration makes a single authenticated request that returns every gateway
and SPuck at once, polled **every 15 minutes**. This reads the cloud **cache**.

> **How fresh is the data?** A MarCELL stores readings hourly (every 30 min on
> Pro) but only **uploads to the cloud every 8 hours (every 4 hours on Pro)**
> unless someone is *actively viewing* the account in the SensoredLife web app —
> which this integration does not do. So a value in Home Assistant can be several
> hours old; the 15-minute poll just keeps HA in step with whatever the device
> last uploaded. Use the **Last read** timestamp and the **Online** sensor to
> judge freshness.

The **Request reading** button forces a gateway to call in immediately (the same
as the website's *Update* button), then refreshes once the cloud catches up.
Each press spends one of your account's paid **instant-update credits** —
routine 15-minute polling never does.

## Use cases

- **Wine cellar / cold storage** — alert when a cellar SPuck leaves its safe
  temperature/humidity band.
- **Fridge & freezer cold-chain** — catch a freezer warming up, or a probe that
  has gone offline (a silent dead sensor is the real danger).
- **Power-outage detection** — the Power binary sensor flips to *off* when a
  monitored building loses mains and the gateway runs on its backup battery.
- **Freeze / overheat protection** — notify when a remote building's temperature
  approaches a damaging range.

## Examples

Notify when a SPuck leaves its safe temperature range (using the built-in
`in_safe_range` attribute):

```yaml
automation:
  - alias: "Wine cellar out of range"
    trigger:
      - trigger: state
        entity_id: sensor.chest_freezer_temperature
        attribute: in_safe_range
        to: false
    action:
      - action: notify.mobile_app_phone
        data:
          title: "Cold-chain alert"
          message: >-
            {{ state_attr(trigger.entity_id, 'friendly_name') }} is
            {{ states(trigger.entity_id) }}°, outside its safe range.
```

Alert on a power outage at a monitored building:

```yaml
automation:
  - alias: "Warehouse lost power"
    trigger:
      - trigger: state
        entity_id: binary_sensor.warehouse_power
        to: "off"
        for: "00:02:00"
    action:
      - action: notify.mobile_app_phone
        data:
          message: "Warehouse is running on backup battery (mains power lost)."
```

Warn when a gateway stops reporting (stale / offline):

```yaml
automation:
  - alias: "MarCELL gateway offline"
    trigger:
      - trigger: state
        entity_id: binary_sensor.wine_cellar_online
        to: "off"
        for: "00:30:00"
    action:
      - action: notify.mobile_app_phone
        data:
          message: "Wine Cellar hasn't reported to the cloud in a while."
```

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

Credentials are validated against the cloud before the entry is created.

- If the password is rejected later, Home Assistant starts a
  **re-authentication** flow automatically — no need to delete and re-add.
- To change the account credentials yourself, use **Reconfigure** on the
  integration's ⋮ menu.

## Removal

Settings → **Devices & Services** → **SensoredLife (MarCELL)** → ⋮ → **Delete**.
No credentials or files are left behind.

## Known limitations

- **Cloud-only.** There is no local API; the integration depends on the
  SensoredLife cloud and your internet connection.
- **Not real-time.** Values come from the cloud cache, and a device only uploads
  every **8 h (4 h on Pro)** when no one is actively viewing the account — so a
  reading can be several hours old. Use **Request reading** for an immediate
  value (costs a credit).
- **Instant-update credits.** The Request-reading button consumes one of the
  account's paid credits per press.
- **Temperature is reported in °F** by the cloud; Home Assistant converts it to
  your configured unit for display.
- Some gateways have no humidity element and report `0 %`.

## Troubleshooting

- **"Invalid username or password"** when adding — confirm the same credentials
  work at [sensoredlife.com](https://www.sensoredlife.com). The integration uses
  the website login, not a separate API key.
- **Entities show *Unavailable*** — a coordinator poll failed (cloud
  unreachable) or, for a SPuck, the probe is offline / out of RF range of its
  gateway. Check the gateway's **Online** binary sensor and **Last read** time.
- **Re-authentication prompt** — your SensoredLife password changed; enter the
  new one when prompted.
- **Download diagnostics** (integration page → ⋮ → Download diagnostics) to
  see parsed gateway/SPuck data, update health, and the last error —
  credentials and device identifiers are redacted.

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.sensoredlife: debug
```

## Quality scale

Targets the **Platinum** tier of the Home Assistant Integration Quality Scale.
See [`custom_components/sensoredlife/quality_scale.yaml`](custom_components/sensoredlife/quality_scale.yaml)
for the per-rule status (module test coverage is ≥95%, `mypy --strict` clean).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) — architecture tour, project
invariants (XSRF session isolation, sentinel handling, identifier redaction),
quality gates, and the release process.

## License

[MIT](LICENSE)
