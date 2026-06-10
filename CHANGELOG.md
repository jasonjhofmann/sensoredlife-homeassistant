# Changelog

## 0.5.1 — 2026-06-10

Observability & maintainability pass, plus one forward-compat fix the
new CI gate caught immediately.

- **Fix**: stop closing the dedicated login session on unload — sessions
  from `async_create_clientsession` are lifecycle-owned by Home Assistant,
  and core makes manual `close()` a hard error under HA 2026.5+.

- **CI now enforces the quality gates**: pytest with `--cov-fail-under=95`,
  `mypy` (strict), and `ruff` run on every PR alongside hassfest/HACS —
  previously they existed only locally.
- **Debug logging**: login outcomes (token expiry — never the token),
  per-poll gateway/SPuck counts, force-update requests; stale-device
  removals now log at INFO instead of mutating the registry silently.
- **Diagnostics** add update interval and the last error.
- **CONTRIBUTING.md**: architecture tour and the project's invariants
  (XSRF session isolation, retry-once token policy, sentinel handling,
  identifier redaction).
- README: diagnostics-download troubleshooting bullet, Development section.

## 0.5.0 — 2026-06-08

- Add a **Last call-in** timestamp sensor to each SPuck, exposing when the probe
  last actually reported to its gateway. This makes a silent/dead SPuck obvious
  (and alertable) instead of it echoing a stale-but-plausible reading.

## 0.4.1 — 2026-06-07

Review pass — correctness, privacy, and docs.

- Docs: corrected the cloud upload cadence — devices upload every **8 h (4 h on
  Pro)** when no one is actively viewing, not "every 1–2 hours."
- The **Online** sensor threshold is raised to 9 h so a healthy non-Pro gateway
  (8 h uploads) no longer false-flags as offline.
- The **Request reading** button now re-polls ~20 s after the press (the gateway
  needs a few seconds to call in), so the fresh reading appears without waiting
  for the next scheduled poll.
- Diagnostics: device IMEIs are now redacted (they previously leaked as map keys
  and on SPucks).
- Robustness: never prune all devices on a spurious empty cloud response.

## 0.4.0 — 2026-06-07

Reach the **Platinum** quality scale.

- **Dynamic devices** — gateways and SPucks added to the account after setup now
  appear automatically, no reload needed.
- **Stale devices** — gateways/SPucks removed from the account are dropped from
  the device registry.
- **Reconfigure flow** — change the account credentials in place via the
  integration's ⋮ → Reconfigure (in addition to the existing reauth flow).
- **Translated exceptions** — the Request-reading button failure is now a
  translatable message.
- Signal-strength diagnostic sensor is disabled by default.
- Expanded documentation (supported devices, data updates, use cases, automation
  examples, known limitations).

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
