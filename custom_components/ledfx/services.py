"""LedFx service actions."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CLIENT_NAME,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_SERVER_ID,
    ATTR_SERVER_URL,
    DOMAIN,
    SERVICE_ADD_SENDSPIN_SERVER,
    SERVICE_REMOVE_SENDSPIN_SERVER,
    SERVICE_UPDATE_SENDSPIN_SERVER,
)
from .updater import LedFxUpdater

_LOGGER = logging.getLogger(__name__)

ADD_SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SERVER_ID): cv.string,
        vol.Required(ATTR_SERVER_URL): cv.string,
        vol.Optional(ATTR_CLIENT_NAME): cv.string,
    }
)

UPDATE_SERVER_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Required(ATTR_SERVER_ID): cv.string,
            vol.Optional(ATTR_SERVER_URL): cv.string,
            vol.Optional(ATTR_CLIENT_NAME): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_SERVER_URL, ATTR_CLIENT_NAME),
)

REMOVE_SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SERVER_ID): cv.string,
    }
)


def _get_updater(call: ServiceCall) -> LedFxUpdater:
    """Return the updater of the config entry that a service call names.

    :param call: ServiceCall
    :return LedFxUpdater
    """

    entry = call.hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])

    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": call.data[ATTR_CONFIG_ENTRY_ID]},
        )

    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )

    return entry.runtime_data


async def _async_add_server(call: ServiceCall) -> None:
    """Add a Sendspin server.

    :param call: ServiceCall
    """

    updater: LedFxUpdater = _get_updater(call)

    await updater.client.add_sendspin_server(
        call.data[ATTR_SERVER_ID],
        call.data[ATTR_SERVER_URL],
        call.data.get(ATTR_CLIENT_NAME),
    )
    await updater.async_request_refresh()


async def _async_update_server(call: ServiceCall) -> None:
    """Update a Sendspin server.

    :param call: ServiceCall
    """

    updater: LedFxUpdater = _get_updater(call)

    await updater.client.update_sendspin_server(
        call.data[ATTR_SERVER_ID],
        call.data.get(ATTR_SERVER_URL),
        call.data.get(ATTR_CLIENT_NAME),
    )
    await updater.async_request_refresh()


async def _async_remove_server(call: ServiceCall) -> None:
    """Remove a Sendspin server.

    :param call: ServiceCall
    """

    updater: LedFxUpdater = _get_updater(call)

    await updater.client.remove_sendspin_server(call.data[ATTR_SERVER_ID])
    await updater.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the LedFx service actions.

    :param hass: HomeAssistant
    """

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_SENDSPIN_SERVER,
        _async_add_server,
        schema=ADD_SERVER_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SENDSPIN_SERVER,
        _async_update_server,
        schema=UPDATE_SERVER_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_SENDSPIN_SERVER,
        _async_remove_server,
        schema=REMOVE_SERVER_SCHEMA,
    )
