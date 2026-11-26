"""LedFx diagnostic."""

from __future__ import annotations

from typing import Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .updater import LedFxConfigEntry

TO_REDACT: Final = {
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_USERNAME,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: LedFxConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""

    _data: dict = {"config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT)}

    _updater = config_entry.runtime_data

    _data["data"] = async_redact_data(_updater.data, TO_REDACT)

    if len(_updater.client.diagnostics) > 0:
        _data["requests"] = async_redact_data(_updater.client.diagnostics, TO_REDACT)

    for key in ("buttons", "devices", "numbers", "selects", "sensors", "switches"):
        if values := getattr(_updater, key, None):
            _data[key] = list(values.keys())

    return _data
