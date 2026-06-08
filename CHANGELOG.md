# Changelog

## 0.3.0 — 2026-06-07

- Bundle brand artwork in `custom_components/sensoredlife/brand/` (icon + MarCELL
  logo, with dark-theme variants). Home Assistant 2026.3+ serves these locally
  via the brands proxy, so the integration shows its icon/logo without waiting
  on a home-assistant/brands submission.

## 0.2.0 — 2026-06-07

- Fix: the **Last read** timestamp was several hours off (it appeared in the
  future). The cloud reports `ReportTimestamp` in UTC; the device `Timezone`
  field is only a display preference and is no longer applied to it.
- Add a **Request reading** button on each gateway — triggers an on-demand
  cellular reading (the website's "Update" button), then refreshes. Note: this
  spends one of the account's paid instant-update credits.

## 0.1.0 — 2026-06-07

Initial release. First-class Home Assistant integration for SensoredLife
MarCELL cellular monitors, targeting the Silver quality scale.

- Config flow with credential validation (test-before-configure) and a
  reauthentication flow.
- `DataUpdateCoordinator` polling the SensoredLife cloud cache every 15 minutes
  (no paid instant-update credits consumed).
- One Home Assistant device per MarCELL gateway: Temperature, Humidity, Power
  (mains vs. backup battery), Online, Signal strength, Backup battery voltage,
  and Last read entities — temperature/humidity carry their configured safe
  ranges as attributes.
- Wireless SPuck sub-probes as child devices (Temperature, Humidity, Battery),
  reporting Unavailable when the cloud returns its offline sentinels.
- Diagnostics with credential redaction.
