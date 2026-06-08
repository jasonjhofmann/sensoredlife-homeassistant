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
# After a force-update, the gateway takes a few seconds to call in (~7 s
# observed). Re-poll once after this delay so the new reading shows up without
# waiting for the next scheduled refresh.
FORCE_UPDATE_SETTLE: Final = timedelta(seconds=20)

# We poll the cloud cache every 15 minutes. A MarCELL only uploads to the cloud
# every 8 h (4 h on Pro) unless a viewer is "active" in the web app — which this
# integration does not simulate — so a cached value can be several hours old.
# Polling more often just keeps HA in step with the last upload; it never
# triggers a paid on-demand cellular "instant update".
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)

# The auth token is valid for ~30 days; re-login proactively when it has less
# than this remaining (or on any 401 from the API).
TOKEN_REFRESH_BUFFER: Final = timedelta(days=1)

# A gateway whose most recent cloud read is older than this is treated as
# offline (connectivity binary_sensor off). Kept just above the slowest normal
# upload cadence (8 h on non-Pro models) so a healthy device on schedule never
# false-flags as offline; a genuinely silent device still trips within ~9 h.
STALE_AFTER: Final = timedelta(hours=9)

# SPuck "no current reading" sentinels (sensor offline, out of RF range, or a
# puck with no temp/humidity element — e.g. a leak-only puck). The cloud reports
# 999.9 for a TH puck that lost its reading and 99.9 for a puck that has no such
# element at all; the vendor UI shows both as N/A, so both map to unavailable.
SPUCK_TEMP_SENTINELS: Final = (999.9, 99.9)
SPUCK_HUMID_SENTINELS: Final = (99.9,)
SENTINEL_TOLERANCE: Final = 0.5

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
