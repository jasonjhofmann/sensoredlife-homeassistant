"""Constants for the SensoredLife integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "sensoredlife"
MANUFACTURER: Final = "SensoredLife"

# Cloud endpoints (reverse-engineered from the SensoredLife web app).
BASE_URL: Final = "https://www.sensoredlife.com"
LOGIN_PATH: Final = "/LoginGateway.php"
DEVICES_PATH: Final = "/api/users/{user_id}/devices"
# On-demand "request a fresh reading" — tells the gateway to call in now. This
# spends one of the account's paid instant-update credits.
FORCE_UPDATE_PATH: Final = "/api/devices/{imei}/sendtext/RPT"

# The MarCELL units only call in to the cloud every ~1-2 hours; polling the
# cloud cache more often than that just keeps HA in sync. It never triggers a
# paid on-demand cellular "instant update".
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)

# The auth token is valid for ~30 days; re-login proactively when it has less
# than this remaining (or on any 401 from the API).
TOKEN_REFRESH_BUFFER: Final = timedelta(days=1)

# A gateway whose most recent cloud read is older than this is treated as
# offline (connectivity binary_sensor off). Generous, because some units only
# report a few times per day.
STALE_AFTER: Final = timedelta(hours=8)

# SPuck "no current reading" sentinels (sensor offline, out of RF range, or a
# puck with no temp/humidity element — e.g. a leak-only puck). The cloud reports
# 999.9 for a TH puck that lost its reading and 99.9 for a puck that has no such
# element at all; the vendor UI shows both as N/A, so both map to unavailable.
SPUCK_TEMP_SENTINELS: Final = (999.9, 99.9)
SPUCK_HUMID_SENTINELS: Final = (99.9,)
SENTINEL_TOLERANCE: Final = 0.5

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
