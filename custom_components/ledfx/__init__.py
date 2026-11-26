"""LedFx custom integration."""

from __future__ import annotations

import logging

from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, PLATFORMS
from .helper import build_auth, get_config_value
from .updater import LedFxConfigEntry, LedFxUpdater

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: LedFxConfigEntry) -> bool:
    """Set up entry configured via user interface.

    :param hass: HomeAssistant: Home Assistant object
    :param entry: LedFxConfigEntry: Config Entry object
    :return bool: Is success
    """

    updater: LedFxUpdater = LedFxUpdater(
        hass,
        get_config_value(entry, CONF_IP_ADDRESS),
        get_config_value(entry, CONF_PORT),
        build_auth(
            get_config_value(entry, CONF_USERNAME),
            get_config_value(entry, CONF_PASSWORD),
        ),
        get_config_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        get_config_value(entry, CONF_TIMEOUT, DEFAULT_TIMEOUT),
        config_entry=entry,
    )

    # The updater records an unreachable LedFx in the `state` binary sensor
    # instead of raising, so the entry loads while LedFx is offline and
    # discovers devices as soon as LedFx becomes reachable.
    await updater.async_config_entry_first_refresh()

    entry.runtime_data = updater

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: LedFxConfigEntry) -> None:
    """Reload the entry after its options changed.

    :param hass: HomeAssistant: Home Assistant object
    :param entry: LedFxConfigEntry: Config Entry object
    """

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LedFxConfigEntry) -> bool:
    """Unload an entry configured via user interface.

    :param hass: HomeAssistant: Home Assistant object
    :param entry: LedFxConfigEntry: Config Entry object
    :return bool: Is success
    """

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

