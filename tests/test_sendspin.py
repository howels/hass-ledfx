"""Tests for the Sendspin servers sensor and services."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.components.sensor import ENTITY_ID_FORMAT as SENSOR_ENTITY_ID_FORMAT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import load_fixture

from custom_components.ledfx.const import DOMAIN
from custom_components.ledfx.exceptions import LedFxRequestError
from custom_components.ledfx.helper import generate_entity_id
from tests.setup import MOCK_IP_ADDRESS, async_mock_client_2, async_setup

SERVER = {"server_url": "ws://192.0.2.10:8927/sendspin", "client_name": "LedFx"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations"""

    yield


async def _setup(
    hass: HomeAssistant, mock_client: Any, sendspin: bool = True
) -> Any:
    """Set up an entry whose LedFx reports a Sendspin server."""

    await async_mock_client_2(mock_client)

    mock_client.return_value.config = AsyncMock(
        return_value=json.loads(load_fixture("config_v2_data.json"))
        | {"sendspin_servers": {"living_room": SERVER}}
    )
    mock_client.return_value.info = AsyncMock(
        return_value=json.loads(load_fixture("info_data.json"))
        | {"features": {"sendspin": sendspin}}
    )
    for method in (
        "add_sendspin_server",
        "update_sendspin_server",
        "remove_sendspin_server",
    ):
        setattr(mock_client.return_value, method, AsyncMock(return_value={}))

    _, config_entry = await async_setup(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry


def _sensor_id(code: str) -> str:
    return generate_entity_id(SENSOR_ENTITY_ID_FORMAT, MOCK_IP_ADDRESS, code)


async def test_sendspin_sensor(hass: HomeAssistant) -> None:
    """The sensor counts the servers and lists them in its attributes."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup(hass, mock_client)

        state = hass.states.get(_sensor_id("sendspin_servers"))

        assert state is not None
        assert state.name == "LedFx Sendspin servers"
        assert state.state == "1"
        assert state.attributes["servers"] == {"living_room": SERVER}


async def test_sensor_needs_the_feature(hass: HomeAssistant) -> None:
    """The sensor stays absent when LedFx reports no Sendspin feature."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup(hass, mock_client, sendspin=False)

        assert hass.states.get(_sensor_id("sendspin_servers")) is None


async def test_sendspin_services(hass: HomeAssistant) -> None:
    """The services pass their fields to LedFx and refresh the data."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        config_entry = await _setup(hass, mock_client)
        client = mock_client.return_value
        base = {"config_entry_id": config_entry.entry_id}

        await hass.services.async_call(
            DOMAIN,
            "add_sendspin_server",
            base
            | {
                "server_id": "kitchen",
                "server_url": "ws://192.0.2.11:8927/sendspin",
                "client_name": "Kitchen",
            },
            blocking=True,
        )
        client.add_sendspin_server.assert_awaited_once_with(
            "kitchen", "ws://192.0.2.11:8927/sendspin", "Kitchen"
        )

        await hass.services.async_call(
            DOMAIN,
            "update_sendspin_server",
            base | {"server_id": "living_room", "client_name": "Lounge"},
            blocking=True,
        )
        client.update_sendspin_server.assert_awaited_once_with(
            "living_room", None, "Lounge"
        )

        await hass.services.async_call(
            DOMAIN,
            "remove_sendspin_server",
            base | {"server_id": "living_room"},
            blocking=True,
        )
        client.remove_sendspin_server.assert_awaited_once_with("living_room")


async def test_sendspin_service_errors(hass: HomeAssistant) -> None:
    """The services report a missing entry, an empty update and a LedFx failure."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        config_entry = await _setup(hass, mock_client)

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "remove_sendspin_server",
                {"config_entry_id": "missing", "server_id": "x"},
                blocking=True,
            )

        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN,
                "update_sendspin_server",
                {"config_entry_id": config_entry.entry_id, "server_id": "x"},
                blocking=True,
            )

        mock_client.return_value.remove_sendspin_server = AsyncMock(
            side_effect=LedFxRequestError("Server 'x' not found.")
        )

        with pytest.raises(HomeAssistantError, match="not found"):
            await hass.services.async_call(
                DOMAIN,
                "remove_sendspin_server",
                {"config_entry_id": config_entry.entry_id, "server_id": "x"},
                blocking=True,
            )

        assert await hass.config_entries.async_unload(config_entry.entry_id)

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "remove_sendspin_server",
                {"config_entry_id": config_entry.entry_id, "server_id": "x"},
                blocking=True,
            )

