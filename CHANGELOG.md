# Changelog

## 0.5.4 — 2026-06-10

Adjacent-sweep fixes — two small robustness gaps found auditing the 0.5.3
string-coercion and login-flow changes.

- **Fix (SPuck battery)**: `BatteryLevel` is now coerced like every other
  reading (the API sends numbers as strings) — a string `"18"` previously
  failed the `isinstance(int | float)` check and the battery silently
  became None. Garbage (non-numeric or non-finite) still degrades to
  None.
- **Fix (API client)**: the devices fetch now logs in first if no user id
  is cached yet, instead of relying on callers to have logged in — a cold
  call can no longer build a devices URL containing a literal `None`.

## 0.5.3 — 2026-06-10

Audit fixes — robustness against cloud glitches, plus privacy cleanups.

- **Fix (stale devices)**: a device is now pruned from the registry only
  after it has been missing from **3 consecutive polls** — a transient
  partial `/devices` response no longer permanently deletes a device. And
  when a pruned device later reappears in the account, its entities are
  recreated immediately instead of requiring a restart.
- **Fix (diagnostics)**: the parsed lowercase `location` field
  (street-address-class data) is now redacted — previously only the raw
  PascalCase `Location` key was listed, and redaction is case-sensitive.
- **Fix (config flow)**: stop closing the validation session —
  `async_create_clientsession` sessions are lifecycle-owned by Home
  Assistant, and HA 2026.5+ blocks the close with a "Please create a bug
  report" warning (same fix the coordinator got in 0.5.1).
- **Fix (API client)**: a 200 response with a non-JSON body (e.g. an HTML
  maintenance page) on login or the devices fetch now maps to the normal
  connection error instead of escaping as a raw `JSONDecodeError`. A
  missing or unparseable `TokenExpiration` no longer forces a re-login on
  every poll (or crashes) — the token is assumed valid for 24 h, with a
  debug log.
- **Fix (reauth damping)**: a single auth failure after a working poll —
  e.g. a transient CSRF rejection — now retries as a normal failed update;
  only a **second consecutive** auth failure starts the reauthentication
  flow. Initial setup still reauths immediately on bad credentials.
- **Fix (safe ranges)**: `RangeMin`/`RangeMax` alarm bounds are coerced to
  floats like every other reading (the API sends numbers as strings), so
  the `in_safe_range` attribute no longer raises `TypeError` on string
  bounds.
- **Fix (sentinels)**: the offline sentinels (999.9 / 99.9) are matched
  exactly (after rounding to one decimal) instead of with a ±0.5 tolerance
  window, so real readings in 99.4–100.4 °F / %RH are no longer masked as
  unavailable.
- Gateway device model is now the generic **"MarCELL"** — the API exposes
  no model/tier indicator, so the previous hardcoded "MarCELL PRO" was a
  guess (and inconsistent with the 9 h offline threshold, which is sized
  for the non-Pro 8 h upload cadence).
- Test fixtures now use clearly synthetic serial numbers.
- Tooling/CI (previously unreleased) — pin ruff's `target-version` to the
  Python support floor (py312, per the declared HA 2024.12 minimum)
  instead of py314. Under py314, `ruff format` rewrites `except (A, B):`
  into the 3.14-only unparenthesized form (PEP 758), which would ship a
  SyntaxError to every HA on Python ≤3.13 (the regression that hit
  visiblair 0.6.2). Mypy stays on 3.14 (it parses installed HA source,
  which uses 3.14-only syntax). CI now runs pytest on a 3.13/3.14
  matrix, adds `ruff format --check`, and adds a Python 3.12
  `compileall` syntax-floor job.

## 0.5.2 — 2026-06-10

- Diagnostics redact set now pre-lists the sensitive keys of the RAW
  API payloads (PascalCase /devices roster + login response) that the
  dump never includes today — so if a future revision attaches a raw
  payload, identifiers/tokens scrub automatically instead of leaking.
  Includes a regression test.

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
