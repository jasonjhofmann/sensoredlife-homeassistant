# SensoredLife (MarCELL) for Home Assistant

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jasonjhofmann/sensoredlife-homeassistant/main/custom_components/sensoredlife/brand/dark_logo@2x.png">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/sensoredlife-homeassistant/main/custom_components/sensoredlife/brand/logo@2x.png" alt="MarCELL" width="200">
</picture>

[![release](https://img.shields.io/github/v/release/jasonjhofmann/sensoredlife-homeassistant?label=release&color=blue)](https://github.com/jasonjhofmann/sensoredlife-homeassistant/releases)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![validate](https://github.com/jasonjhofmann/sensoredlife-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/jasonjhofmann/sensoredlife-homeassistant/actions/workflows/validate.yml)

Read [SensoredLife](https://www.sensoredlife.com) **MarCELL** cellular
temperature, humidity, and power monitors into Home Assistant, along with the
wireless **SPuck** sub-probes paired to them.

MarCELL units report over the cellular network to the SensoredLife cloud, and
there's no local API. This integration polls the cloud cache, which holds the
same data the website shows. It never presses the paid on-demand **Update**
button on its own, so routine polling doesn't spend your account's
instant-update credits.

> Unofficial. Not affiliated with or endorsed by SensoredLife, LLC.

## Before you begin

You need the following:

- Home Assistant 2024.12.0 or later.
- A SensoredLife account with at least one MarCELL gateway on it.
- The email address and password you use to sign in at sensoredlife.com. The
  integration authenticates with the website login. There's no separate API
  key.

## Supported devices

The integration reads every gateway and probe on the account. It doesn't need a
model list, and it picks up devices you add or remove later without you
re-adding the integration.

- **MarCELL cellular gateways**, one Home Assistant device each. The cloud API
  exposes no model or tier field, so every gateway reports its model as
  "MarCELL" whether or not it's a PRO.
- **SPuck wireless sub-probes**, as child devices of the gateway they're paired
  to. Temperature and humidity SPucks report both readings. A SPuck with no
  climate element, such as a leak puck, still gets a battery sensor, and its
  temperature and humidity entities report `unavailable`.

## Entities

Each MarCELL gateway gets:

| Entity | Domain | Notes |
| --- | --- | --- |
| Temperature | `sensor` | Has `safe_minimum`, `safe_maximum`, and `in_safe_range` attributes taken from the account's alarm bounds |
| Humidity | `sensor` | Same three attributes |
| Power | `binary_sensor` | `plug` class. `on` means mains power, `off` means the gateway is running on its backup battery |
| Online | `binary_sensor` | `connectivity` class. Goes `off` when the gateway hasn't reported for more than 9 hours |
| Signal strength | `sensor` | Diagnostic, disabled by default |
| Backup battery | `sensor` | Internal cell voltage. Diagnostic |
| Last read | `sensor` | Timestamp of the most recent cloud read. Diagnostic |
| Request reading | `button` | Forces an immediate call-in. Spends a credit |

Each SPuck gets:

| Entity | Domain | Notes |
| --- | --- | --- |
| Temperature | `sensor` | Reports `unavailable` on a puck with no climate element |
| Humidity | `sensor` | Reports `unavailable` on a puck with no climate element |
| Battery | `sensor` | Percentage. Diagnostic |
| Last call-in | `sensor` | When the probe last reported to its gateway. Diagnostic |

The 9-hour offline threshold sits just above the slowest normal upload cadence,
so a healthy non-PRO gateway on schedule never trips it.

A SPuck that has dropped offline or gone out of RF range reports `unavailable`
rather than a bogus value. The cloud signals this with `999.9 °F` and `99.9 %`
sentinels, which the integration matches exactly, so a genuine reading near
those values still comes through.

**Last call-in** is the entity that tells you a probe has gone quiet. Without
it, a silent SPuck keeps echoing whatever it last reported.

## Add the integration

1. Go to **Settings > Devices & services > Add integration** and select
   **SensoredLife (MarCELL)**.
2. Enter the email address and password you use at sensoredlife.com.
3. Click **Submit**.

Home Assistant validates the credentials against the cloud before it creates
the entry.

If the password stops working later, Home Assistant starts a reauthentication
flow on its own, so you don't need to delete and re-add the integration. One
failed auth after a working poll is treated as an ordinary failed update; it
takes two consecutive failures to trigger the prompt, which keeps a transient
CSRF rejection from nagging you.

To change the credentials yourself, select **⋮ > Reconfigure** on the config
entry.

## Install

### Install with HACS

SensoredLife is in the HACS default repository, so you don't need to add a
custom repository.

1. In HACS, search for **SensoredLife (MarCELL)** and download it.
2. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonjhofmann&repository=sensoredlife-homeassistant&category=integration)

### Install manually

1. Copy `custom_components/sensoredlife/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## How data is updated

The integration makes one authenticated request every 15 minutes that returns
every gateway and SPuck at once. That request reads the cloud cache.

### How fresh the data actually is

A MarCELL stores a reading hourly, or every 30 minutes on a PRO. It only
uploads to the cloud every 8 hours, or every 4 hours on a PRO, unless somebody
is actively viewing the account in the SensoredLife web app. This integration
doesn't pretend to be an active viewer.

So a value in Home Assistant can be several hours old. The 15-minute poll keeps
Home Assistant in step with whatever the device last uploaded, and nothing
more. Use the **Last read** timestamp and the **Online** sensor to judge how
current a value is.

### Force a fresh reading

The **Request reading** button tells a gateway to call in immediately, the same
as the **Update** button on the website. The integration re-polls about 20
seconds later, once the cloud has caught up.

Each press spends one of your account's paid instant-update credits. Routine
polling never does.

### Devices that come and go

A device has to be missing from three consecutive polls before the integration
removes it from the registry, so one partial cloud response can't wipe out your
devices. If a removed device reappears on the account, its entities come back
on the next poll without a restart.

## Automation examples

Notify when a SPuck leaves its safe temperature range, using the
`in_safe_range` attribute:

```yaml
automation:
  - alias: "Wine cellar out of range"
    triggers:
      - trigger: state
        entity_id: sensor.chest_freezer_temperature
        attribute: in_safe_range
        to: false
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Cold-chain alert"
          message: >-
            {{ state_attr(trigger.entity_id, 'friendly_name') }} is
            {{ states(trigger.entity_id) }}, outside its safe range.
```

Notify on a power outage at a monitored building:

```yaml
automation:
  - alias: "Warehouse lost power"
    triggers:
      - trigger: state
        entity_id: binary_sensor.warehouse_power
        to: "off"
        for: "00:02:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Warehouse is running on backup battery. Mains power is out."
```

Notify when a gateway stops reporting:

```yaml
automation:
  - alias: "MarCELL gateway offline"
    triggers:
      - trigger: state
        entity_id: binary_sensor.wine_cellar_online
        to: "off"
        for: "00:30:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Wine Cellar hasn't reported to the cloud in a while."
```

## Limitations

- **Cloud-only.** There's no local API, so the integration depends on the
  SensoredLife cloud and your internet connection.
- **Not real-time.** Values come from the cloud cache, and a device uploads
  only every 8 hours, or 4 on a PRO, when nobody is viewing the account. A
  reading can be hours old. Use **Request reading** for an immediate value.
- **Credits.** Each **Request reading** press costs one paid instant-update
  credit.
- **Fahrenheit at the source.** The cloud reports temperature in °F. Home
  Assistant converts it to your configured unit for display.
- **No humidity element on some gateways.** Those report `0 %`.

## Remove the integration

Go to **Settings > Devices & services > SensoredLife (MarCELL)** and select
**⋮ > Delete**. No credentials or files are left behind.

## Troubleshoot

### "Invalid username or password" when adding the integration

Confirm the same credentials work at
[sensoredlife.com](https://www.sensoredlife.com). The integration uses the
website login, so if the website rejects them, so will Home Assistant.

### Entities show `unavailable`

Either a coordinator poll failed because the cloud was unreachable, or a SPuck
is offline or out of RF range of its gateway. Check the gateway's **Online**
binary sensor and its **Last read** timestamp to tell the two apart.

### A reauthentication prompt appears

Your SensoredLife password changed. Enter the new one when prompted.

### Download diagnostics

Go to the integration page and select **⋮ > Download diagnostics**. The
snapshot shows the parsed gateway and SPuck data, update health, and the last
error. Credentials, device identifiers, and location fields are redacted.

### Turn on debug logging

Add the following to `configuration.yaml` and restart. To change the level
without restarting, call the `logger.set_level` action instead.

```yaml
logger:
  logs:
    custom_components.sensoredlife: debug
```

## Quality scale

The integration targets the Platinum tier of the Home Assistant Integration
Quality Scale. See
[`custom_components/sensoredlife/quality_scale.yaml`](custom_components/sensoredlife/quality_scale.yaml)
for per-rule status. Coverage is enforced at 95% in CI, and `mypy --strict` is
clean.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for the architecture tour, the project
invariants (XSRF session isolation, sentinel handling, identifier redaction),
the quality gates, and the release process.

## License

MIT. See [LICENSE](LICENSE).

The MarCELL logo is bundled at `custom_components/sensoredlife/brand/` and
served through Home Assistant's Brands Proxy API. "MarCELL" and "SensoredLife"
are trademarks of SensoredLife, LLC.

## Related projects

- [aranet-cloud-homeassistant](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
  reads Aranet Cloud sensors into Home Assistant.
- [visiblair-homeassistant](https://github.com/jasonjhofmann/visiblair-homeassistant)
  reads VisiblAir air-quality sensors into Home Assistant.
