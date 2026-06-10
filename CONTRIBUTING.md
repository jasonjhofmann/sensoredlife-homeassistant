# Contributing

## Architecture (5-minute tour)

```
custom_components/sensoredlife/
  api.py           SensoredLife cloud client (aiohttp). Browser-shaped login:
                   seeds an XSRF cookie, echoes it on POSTs, caches the access
                   token, and retries exactly once on a stale token.
  models.py        Response parsing into frozen dataclasses (Gateway, SPuck).
                   The cloud's offline sentinels (999.9 / 99.9) are normalized
                   to None HERE, not in entities.
  coordinator.py   One coordinator per account. Polls /devices (the full
                   account roster), prunes registry devices only after 3
                   consecutive polls missing (never on an empty response),
                   logs removals; one auth failure is damped to a retry,
                   reauth starts on the second consecutive failure.
  entity.py        Gateway/SPuck base entities and device wiring.
  sensor.py / binary_sensor.py / button.py   Entities; button = force call-in.
  diagnostics.py   Redacts credentials AND identifiers (serials, IMEIs,
                   SPuck ids) — gateways are a list, not an IMEI-keyed dict,
                   because async_redact_data only redacts values, not keys.
  quality_scale.yaml  Per-rule self-assessment; keep in sync with changes.
```

Invariants:

- **The login session is dedicated** (own cookie jar via
  `async_create_clientsession`) so the XSRF cookie never touches HA's shared
  session. Do NOT close it manually — HA owns created-session lifecycles and
  core blocks `session.close()` (warn_use, hard error under test since
  HA 2026.5).
- **Stale-token policy is retry-once** — a second 401/403 surfaces as
  reauth, never a login loop.
- **Sentinels die in models.py.** Entities must never see 999.9/99.9.
- **Identifiers (IMEI/serial/SPuck id) are treated as sensitive**: redacted in
  diagnostics, never logged in full (log names or truncated ids).
- `strings.json` and `translations/en.json` stay identical.

## Development setup

```sh
uv venv .venv && uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest tests -q --cov=custom_components.sensoredlife   # ≥95% enforced
.venv/bin/python -m mypy custom_components/sensoredlife/                   # strict via pyproject
.venv/bin/python -m ruff check custom_components tests
```

CI runs all three plus hassfest and HACS validation on every PR.
`docs/reference_pyscript_scraper.py` is the pre-integration pyscript this
integration replaced — kept as API reference, not loaded by anything.

## Making a release

1. Update `CHANGELOG.md`; bump `version` in `manifest.json` (keys stay sorted:
   `domain`, `name`, then alphabetical — hassfest enforces).
2. Land changes via branch + PR; wait for the Validate workflow to go green.
3. Tag and create the GitHub release **after** the green run on `main`.

## Debugging

Integration page → ⋮ → **Enable debug logging**, or:

```yaml
logger:
  logs:
    custom_components.sensoredlife: debug
```

Debug logs cover login outcomes (token expiry, never the token), per-poll
gateway/SPuck counts, and force-update requests; stale-device removals log at
INFO. Diagnostics downloads include update health and the last error with
credentials and identifiers redacted.
