"""DataUpdateCoordinator for the SensoredLife integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SensoredLifeAuthError,
    SensoredLifeClient,
    SensoredLifeConnectionError,
)
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .models import Gateway

_LOGGER = logging.getLogger(__name__)

# A device must be missing from this many CONSECUTIVE polls before it is
# pruned from the registry — a transient partial /devices response must not
# permanently delete a device (and detach its history).
PRUNE_AFTER_MISSED_POLLS: Final = 3

type SensoredLifeConfigEntry = ConfigEntry[SensoredLifeCoordinator]


class SensoredLifeCoordinator(DataUpdateCoordinator[dict[str, Gateway]]):
    """Polls the SensoredLife cloud cache and exposes parsed gateways."""

    config_entry: SensoredLifeConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: SensoredLifeConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        # A dedicated session (own cookie jar) keeps the login XSRF cookie out
        # of Home Assistant's shared session. HA owns its lifecycle (closed at
        # shutdown) — calling session.close() ourselves is blocked by core's
        # warn_use wrapper as of HA 2026.5+.
        session = async_create_clientsession(hass)
        self.client = SensoredLifeClient(
            session,
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )
        # identifier -> consecutive polls it has been missing from the roster.
        self._missed_polls: dict[str, int] = {}
        # Notified with each pruned identifier so platforms can forget its
        # unique_ids (and recreate entities if the device later reappears).
        self._device_removed_listeners: list[Callable[[str], None]] = []
        # Consecutive auth failures; see _async_update_data.
        self._auth_failures = 0

    @callback
    def async_add_device_removed_listener(
        self, listener: Callable[[str], None]
    ) -> CALLBACK_TYPE:
        """Subscribe to pruned-device identifiers; returns an unsubscribe."""
        self._device_removed_listeners.append(listener)

        @callback
        def _unsubscribe() -> None:
            self._device_removed_listeners.remove(listener)

        return _unsubscribe

    async def _async_update_data(self) -> dict[str, Gateway]:
        """Fetch the latest readings for every gateway."""
        try:
            data = await self.client.async_get_gateways()
        except SensoredLifeAuthError as err:
            # A single auth failure can be a transient cloud glitch (a CSRF
            # rejection or a 200-with-no-token), not bad credentials — only a
            # SECOND consecutive failure starts the reauthentication flow.
            # During initial setup (no successful poll yet, self.data is None)
            # reauth starts immediately: damping there would just loop
            # setup-retry forever on genuinely bad credentials.
            self._auth_failures += 1
            if self.data is None or self._auth_failures >= 2:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(
                f"Authentication failed (may be transient; reauth on repeat): {err}"
            ) from err
        except SensoredLifeConnectionError as err:
            raise UpdateFailed(str(err)) from err
        self._auth_failures = 0
        _LOGGER.debug(
            "Poll OK: %d gateways (%s)",
            len(data),
            ", ".join(gateway.name for gateway in data.values()) or "none",
        )
        self._async_remove_stale_devices(data)
        return data

    @callback
    def _async_remove_stale_devices(self, data: dict[str, Gateway]) -> None:
        """Drop devices (gateways/SPucks) no longer present in the account.

        The /devices feed is the full account roster (offline devices still
        appear), so a missing identifier means the device was removed — but a
        device is only pruned after PRUNE_AFTER_MISSED_POLLS consecutive
        missing polls, so a transient partial response never deletes one.
        """
        # Never prune (or count a miss) on an empty roster — a spurious empty
        # response would otherwise wipe every device (and detach its history).
        if not data:
            return

        current: set[str] = set()
        for imei, gateway in data.items():
            current.add(imei)
            current.update(spuck.spuck_id for spuck in gateway.spucks)

        device_registry = dr.async_get(self.hass)
        missed: dict[str, int] = {}
        for device in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            ids = {ident for domain, ident in device.identifiers if domain == DOMAIN}
            if not ids or not ids.isdisjoint(current):
                # Present this poll — any earlier miss streak resets (its
                # counter simply isn't carried over into ``missed``).
                continue
            streak = max(self._missed_polls.get(ident, 0) for ident in ids) + 1
            if streak < PRUNE_AFTER_MISSED_POLLS:
                _LOGGER.debug(
                    "Device %s missing from poll (%d/%d before removal)",
                    device.name,
                    streak,
                    PRUNE_AFTER_MISSED_POLLS,
                )
                for ident in ids:
                    missed[ident] = streak
                continue
            _LOGGER.info(
                "Removing stale device %s — missing from %d consecutive polls",
                device.name,
                streak,
            )
            device_registry.async_update_device(
                device.id, remove_config_entry_id=self.config_entry.entry_id
            )
            for ident in ids:
                for listener in self._device_removed_listeners:
                    listener(ident)
        self._missed_polls = missed
