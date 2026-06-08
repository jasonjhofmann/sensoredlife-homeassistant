"""
SensoredLife / MarCELL cellular temperature·humidity·power monitors → Home Assistant.

WHY: the MarCELL PRO units (and their wireless "SPuck" sub-sensors) report over
cellular to the SensoredLife cloud — there is no local API. But the web app is a
thin AngularJS front-end over a clean JSON REST API, and a SINGLE authenticated
GET returns everything the dashboard shows:

    GET /api/users/{userId}/devices?access_token=…
        → [ per gateway: Name, Location, SerialNumber, IMEI, Timezone,
              LastRead{Temperature, Humidity, Power, SignalStrength, ReportTimestamp},
              BatteryVoltage (gateway backup cell), SignalStrength,
              AlarmPoints[]  (device-level safe ranges: TEMP / HUMIDITY / POWER),
              Peripherals[]  (SPucks: Name, BatteryLevel %, SignalStrength,
                              CallinTime, AlarmPoints[] SP_TEMP / SP_HUMID) ]

So we log in once, cache the token (30-day life), and poll that one endpoint.
We read the cloud CACHE only — we never hit the "Update (NNNN)" instant-update
button, which spends the account's paid on-demand cellular credits.

SENTINELS / QUIRKS
  - SPuck temp 999.9 and humidity 99.9 mean "no current reading" (sensor offline
    / out of range of the gateway) → published as unavailable.
  - Gateway LastRead.Power "1.00" = mains ON, "0.00" = on backup battery.
  - device["Timezone"] is an INTEGER UTC-offset in hours; ReportTimestamp /
    CallinTime are wall-clock in that offset (convert to aware UTC for HA).
  - Warehouse-type units report Humidity 0 (no RH element) but still expose a
    humidity safe-range; we publish what the dashboard shows.

ENTITIES (state.set — informational, no unique_id). One set per gateway:
    sensor.marcell_<dev>_temperature        °F   (attrs: safe_min/max, in_safe_range,
                                                  signal, serial, imei, report_time)
    sensor.marcell_<dev>_humidity           %    (attrs: safe_min/max, in_safe_range)
    binary_sensor.marcell_<dev>_power       on=mains / off=backup battery
    binary_sensor.marcell_<dev>_online      connectivity (report age < STALE_HOURS)
    sensor.marcell_<dev>_battery_voltage    V    (gateway backup cell)
    sensor.marcell_<dev>_signal             cellular signal strength
    sensor.marcell_<dev>_last_read          timestamp
  Per SPuck (wireless sub-probe), entity_ids are device-prefixed for uniqueness:
    sensor.marcell_<dev>_<spuck>_temperature   °F  (attrs: safe_min/max, in_safe_range)
    sensor.marcell_<dev>_<spuck>_humidity      %
    sensor.marcell_<dev>_<spuck>_battery       %   (device_class battery)

SERVICE
    pyscript.sensoredlife_refresh   — immediate poll.

POLLING: startup (after HA settles) + every POLL_MINUTES. state.set entities do
not survive a restart, so the startup poll repopulates them all. The MarCELL
units only call in every ~1–2 h, so a frequent cloud poll is cheap and just
keeps HA in sync with the cache; it does NOT cost instant-update credits.

CREDENTIALS — /config/secrets.yaml (gitignored):
    sensoredlife_username / sensoredlife_password

PYSCRIPT NOTES
  - Blocking HTTP + file IO run in task.executor; every function on that path is
    @pyscript_compile (pyscript-interpreted functions can't run in the executor).
  - state.set / log / task.* must run in INTERPRETED functions (not compiled).
  - Use list comprehensions, not generator expressions (pyscript interp lacks
    ast_generatorexp).
"""

import datetime
import json

import requests
import yaml

from homeassistant.util import dt as dt_util

# Bumped on substantive changes; logged once per poll so a redeploy is visible.
VERSION = "sensoredlife v0.1 (marcell)"

BASE = "https://www.sensoredlife.com"
LOGIN_URL = BASE + "/LoginGateway.php"
SECRETS_PATH = "/config/secrets.yaml"
TOKEN_PATH = "/config/.sensoredlife_token.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)

HTTP_TIMEOUT = 30        # seconds per request
POLL_MINUTES = 15        # cloud-cache poll cadence
POLL_RETRIES = 2         # attempts per poll
RETRY_DELAY = 20         # seconds between attempts
STARTUP_DELAY = 45       # let HA settle before the first poll
TOKEN_BUFFER = 86400     # re-login if the token expires within 1 day
STALE_HOURS = 8          # report older than this → gateway "offline"
SPUCK_TEMP_SENTINEL = 999.9
SPUCK_HUMID_SENTINEL = 99.9

# Module cache of the auth token so we don't log in every poll. Mirrors TOKEN_PATH.
_token = {}


# ===========================================================================
# I/O helpers (compiled — run in task.executor)
# ===========================================================================
@pyscript_compile
def _load_credentials():
    """Read SensoredLife creds from /config/secrets.yaml."""
    with open(SECRETS_PATH, "r", encoding="utf-8") as fh:
        secrets = yaml.safe_load(fh) or {}
    user = secrets.get("sensoredlife_username")
    pw = secrets.get("sensoredlife_password")
    if not user or not pw:
        raise RuntimeError(
            "sensoredlife_username / sensoredlife_password missing from secrets.yaml")
    return user, pw


@pyscript_compile
def _load_token_file():
    """Restore the cached token across restarts; {} if absent/unreadable."""
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


@pyscript_compile
def _save_token_file(tok):
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        json.dump(tok, fh)


@pyscript_compile
def _login(username, password):
    """POST /LoginGateway.php → {access_token, user_id, expires}."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    resp = sess.post(
        LOGIN_URL,
        json={"username": username, "password": password},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body.get("AccessToken")
    user_id = body.get("Id")
    if not token or user_id is None:
        raise RuntimeError("login response missing AccessToken / Id")
    return {
        "access_token": token,
        "user_id": user_id,
        "expires": int(body.get("TokenExpiration") or 0),
    }


@pyscript_compile
def _fetch_devices(access_token, user_id):
    """GET the one endpoint that carries the whole dashboard. 401 → caller re-logs in."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    url = "%s/api/users/%s/devices" % (BASE, user_id)
    resp = sess.get(url, params={"access_token": access_token}, timeout=HTTP_TIMEOUT)
    if resp.status_code in (401, 403):
        raise PermissionError("token rejected (%d)" % resp.status_code)
    resp.raise_for_status()
    return resp.json()


# ===========================================================================
# Parsing helpers (interpreted)
# ===========================================================================
def _to_float(value):
    """Coerce to a rounded float, or None if not numeric."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _slug(text):
    """entity_id-safe slug: lowercase, non-alphanumerics → single underscores."""
    out = []
    prev_us = False
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append("_")
            prev_us = True
    return "".join(out).strip("_") or "device"


def _parse_ts(raw, tz_offset_hours):
    """'YYYY-MM-DD HH:MM:SS' in the device's integer UTC offset → aware UTC dt."""
    if not raw:
        return None
    try:
        naive = datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    try:
        offset = datetime.timezone(datetime.timedelta(hours=int(tz_offset_hours)))
    except (TypeError, ValueError):
        offset = datetime.timezone.utc
    return naive.replace(tzinfo=offset).astimezone(datetime.timezone.utc)


def _device_range(device, sensor_type):
    """(min, max) for a device-level AlarmPoint (PeripheralId is None), else (None, None)."""
    for ap in device.get("AlarmPoints") or []:
        if ap.get("PeripheralId"):
            continue
        ds = ap.get("DeviceSensor") or {}
        if ds.get("SensorType") == sensor_type:
            return ap.get("RangeMin"), ap.get("RangeMax")
    return None, None


def _spuck_reading(spuck, sensor_type):
    """(value, min, max) from a SPuck AlarmPoint of the given SensorType."""
    for ap in spuck.get("AlarmPoints") or []:
        ds = ap.get("DeviceSensor") or {}
        if ds.get("SensorType") == sensor_type:
            return _to_float(ap.get("LastRead")), ap.get("RangeMin"), ap.get("RangeMax")
    return None, None, None


def _in_range(value, lo, hi):
    """True/False if value within [lo, hi]; None if undetermined."""
    if value is None or lo is None or hi is None:
        return None
    return bool(lo <= value <= hi)


# ===========================================================================
# Publishing (interpreted — state.set)
# ===========================================================================
def _publish_device(device, now_utc):
    name = device.get("Name") or device.get("SerialNumber") or "MarCELL"
    dev = _slug(name)
    last = device.get("LastRead") or {}
    tz = device.get("Timezone", 0)

    report_dt = _parse_ts(last.get("ReportTimestamp"), tz)
    age_h = None
    online = None
    if report_dt is not None:
        age_h = round((now_utc - report_dt).total_seconds() / 3600.0, 2)
        online = age_h <= STALE_HOURS

    serial = device.get("SerialNumber")
    imei = device.get("IMEI") or device.get("DeviceId")
    signal = _to_float(last.get("SignalStrength")) or _to_float(device.get("SignalStrength"))
    power_on = _to_float(last.get("Power"))

    # Temperature (always present on these units).
    temp = _to_float(last.get("Temperature"))
    t_lo, t_hi = _device_range(device, "TEMP")
    if temp is not None:
        state.set(
            "sensor.marcell_%s_temperature" % dev, temp,
            friendly_name="MarCELL %s Temperature" % name,
            unit_of_measurement="°F", device_class="temperature",
            state_class="measurement", icon="mdi:thermometer",
            safe_min=t_lo, safe_max=t_hi, in_safe_range=_in_range(temp, t_lo, t_hi),
            location=device.get("Location"), serial=serial, imei=imei,
            signal_strength=signal, report_time=last.get("FormattedLastMessage"),
            online=online, source="sensoredlife",
        )

    # Humidity.
    hum = _to_float(last.get("Humidity"))
    h_lo, h_hi = _device_range(device, "HUMIDITY")
    if hum is not None:
        state.set(
            "sensor.marcell_%s_humidity" % dev, hum,
            friendly_name="MarCELL %s Humidity" % name,
            unit_of_measurement="%", device_class="humidity",
            state_class="measurement", icon="mdi:water-percent",
            safe_min=h_lo, safe_max=h_hi, in_safe_range=_in_range(hum, h_lo, h_hi),
            source="sensoredlife",
        )

    # Power (mains present) as a binary_sensor.
    if power_on is not None:
        state.set(
            "binary_sensor.marcell_%s_power" % dev, "on" if power_on >= 0.5 else "off",
            friendly_name="MarCELL %s Power" % name,
            device_class="power", icon="mdi:power-plug", source="sensoredlife",
        )

    # Online / connectivity.
    if online is not None:
        state.set(
            "binary_sensor.marcell_%s_online" % dev, "on" if online else "off",
            friendly_name="MarCELL %s Online" % name,
            device_class="connectivity", icon="mdi:access-point-network",
            report_age_hours=age_h, last_report=report_dt.isoformat() if report_dt else None,
            source="sensoredlife",
        )

    # Gateway backup-battery voltage.
    batt_v = _to_float(device.get("BatteryVoltage"))
    if batt_v is not None:
        state.set(
            "sensor.marcell_%s_battery_voltage" % dev, batt_v,
            friendly_name="MarCELL %s Backup Battery" % name,
            unit_of_measurement="V", device_class="voltage",
            state_class="measurement", icon="mdi:battery", source="sensoredlife",
        )

    # Cellular signal strength.
    if signal is not None:
        state.set(
            "sensor.marcell_%s_signal" % dev, signal,
            friendly_name="MarCELL %s Signal" % name,
            state_class="measurement", icon="mdi:signal", source="sensoredlife",
        )

    # Last cloud read time.
    if report_dt is not None:
        state.set(
            "sensor.marcell_%s_last_read" % dev, report_dt.isoformat(),
            friendly_name="MarCELL %s Last Read" % name,
            device_class="timestamp", icon="mdi:clock-outline", source="sensoredlife",
        )

    n_spucks = 0
    for spuck in device.get("Peripherals") or []:
        _publish_spuck(dev, name, spuck, now_utc)
        n_spucks += 1
    return n_spucks


def _publish_spuck(dev, dev_name, spuck, now_utc):
    sp_name = spuck.get("Name") or spuck.get("Id") or "SPuck"
    sp = _slug(sp_name)
    base = "marcell_%s_%s" % (dev, sp)

    callin = _parse_ts(spuck.get("CallinTime"), 0)  # CallinTime is already UTC-ish; offset 0
    sig = _to_float(spuck.get("SignalStrength"))

    temp, t_lo, t_hi = _spuck_reading(spuck, "SP_TEMP")
    if temp is not None and abs(temp - SPUCK_TEMP_SENTINEL) > 0.5:
        state.set(
            "sensor.%s_temperature" % base, temp,
            friendly_name="%s Temperature" % sp_name,
            unit_of_measurement="°F", device_class="temperature",
            state_class="measurement", icon="mdi:thermometer",
            safe_min=t_lo, safe_max=t_hi, in_safe_range=_in_range(temp, t_lo, t_hi),
            gateway=dev_name, signal_strength=sig, source="sensoredlife",
        )
    else:
        # Offline / no reading → mark unavailable so it doesn't read as a real temp.
        state.set(
            "sensor.%s_temperature" % base, "unavailable",
            friendly_name="%s Temperature" % sp_name,
            unit_of_measurement="°F", device_class="temperature",
            gateway=dev_name, source="sensoredlife",
        )

    hum, h_lo, h_hi = _spuck_reading(spuck, "SP_HUMID")
    if hum is not None and abs(hum - SPUCK_HUMID_SENTINEL) > 0.5:
        state.set(
            "sensor.%s_humidity" % base, hum,
            friendly_name="%s Humidity" % sp_name,
            unit_of_measurement="%", device_class="humidity",
            state_class="measurement", icon="mdi:water-percent",
            safe_min=h_lo, safe_max=h_hi, in_safe_range=_in_range(hum, h_lo, h_hi),
            gateway=dev_name, source="sensoredlife",
        )
    else:
        state.set(
            "sensor.%s_humidity" % base, "unavailable",
            friendly_name="%s Humidity" % sp_name,
            unit_of_measurement="%", device_class="humidity",
            gateway=dev_name, source="sensoredlife",
        )

    batt = spuck.get("BatteryLevel")
    if batt is not None:
        state.set(
            "sensor.%s_battery" % base, batt,
            friendly_name="%s Battery" % sp_name,
            unit_of_measurement="%", device_class="battery",
            state_class="measurement", icon="mdi:battery",
            gateway=dev_name, last_callin=callin.isoformat() if callin else None,
            source="sensoredlife",
        )


# ===========================================================================
# Poll orchestration
# ===========================================================================
def _get_token(username, password, force=False):
    """Return a valid token dict, logging in (and caching) as needed."""
    global _token
    if not _token:
        _token = task.executor(_load_token_file) or {}
    now_epoch = int(dt_util.utcnow().timestamp())
    fresh = (
        not force
        and _token.get("access_token")
        and (_token.get("expires", 0) - now_epoch) > TOKEN_BUFFER
    )
    if fresh:
        return _token
    log.info("SensoredLife: logging in (token %s)" % ("forced" if force else "missing/expiring"))
    _token = task.executor(_login, username, password)
    task.executor(_save_token_file, _token)
    return _token


def _run_poll(reason):
    log.info("SensoredLife: poll start (%s), %s" % (reason, VERSION))
    try:
        username, password = task.executor(_load_credentials)
    except Exception as err:
        log.error("SensoredLife: credentials unavailable: %s" % err)
        return

    devices = None
    last_err = None
    for attempt in range(1, POLL_RETRIES + 1):
        try:
            tok = _get_token(username, password)
            devices = task.executor(_fetch_devices, tok["access_token"], tok["user_id"])
            break
        except PermissionError as err:
            # Token rejected — force a re-login on the next attempt.
            last_err = err
            log.warning("SensoredLife: %s — re-authenticating" % err)
            try:
                _get_token(username, password, force=True)
            except Exception as e2:
                last_err = e2
        except Exception as err:
            last_err = err
            log.warning("SensoredLife: attempt %d/%d failed: %s"
                        % (attempt, POLL_RETRIES, err))
            if attempt < POLL_RETRIES:
                task.sleep(RETRY_DELAY)

    if devices is None:
        log.error("SensoredLife: poll failed after %d attempts: %s" % (POLL_RETRIES, last_err))
        return
    if not isinstance(devices, list):
        log.error("SensoredLife: unexpected response shape: %s" % type(devices))
        return

    now_utc = dt_util.utcnow()
    n_dev = 0
    n_spuck = 0
    for device in devices:
        try:
            n_spuck += _publish_device(device, now_utc)
            n_dev += 1
        except Exception as err:
            log.error("SensoredLife: failed publishing %s: %s"
                      % (device.get("Name"), err))

    log.info("SensoredLife: poll ok — %d gateways, %d SPucks" % (n_dev, n_spuck))


# ===========================================================================
# Triggers + service
# ===========================================================================
@time_trigger("startup")
def sensoredlife_startup():
    """First poll after HA settles (repopulates all state.set entities)."""
    task.unique("sensoredlife_poll")
    task.sleep(STARTUP_DELAY)
    _run_poll("startup")


@time_trigger("period(now, %dmin)" % POLL_MINUTES)
def sensoredlife_periodic():
    task.unique("sensoredlife_poll")
    _run_poll("periodic")


@service
def sensoredlife_refresh():
    """HA service `pyscript.sensoredlife_refresh`: immediate cloud-cache poll."""
    task.unique("sensoredlife_poll")
    _run_poll("manual")
