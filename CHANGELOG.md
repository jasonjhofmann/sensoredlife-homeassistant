# Changelog

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
