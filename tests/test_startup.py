"""Tests for the startup scene and playlist selects."""

# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.select import ENTITY_ID_FORMAT as SELECT_ENTITY_ID_FORMAT
from homeassistant.components.select import SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import load_fixture

from custom_components.ledfx.exceptions import LedFxRequestError
from custom_components.ledfx.helper import generate_entity_id
from custom_components.ledfx.updater import LedFxUpdater, startup_options
from tests.setup import MOCK_IP_ADDRESS, async_mock_client_2, async_setup


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations"""

    yield


async def _setup(
    hass: HomeAssistant, mock_client: Any, config: dict | None = None
) -> tuple[LedFxUpdater, Any]:
    """Set up an entry whose LedFx reports the startup settings."""

    await async_mock_client_2(mock_client)

    mock_client.return_value.config = AsyncMock(
        return_value=json.loads(load_fixture("config_v2_data.json"))
        | (
            {"startup_scene_id": "test", "startup_playlist_id": ""}
            if config is None
            else config
        )
    )
    mock_client.return_value.playlists = AsyncMock(
        return_value={
            "playlists": {
                "evening": {"name": "Evening"},
                "morning": {"name": "Morning"},
            }
        }
    )
    mock_client.return_value.set_config = AsyncMock(return_value={})

    _, config_entry = await async_setup(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry.runtime_data, config_entry


def _select_id(code: str) -> str:
    return generate_entity_id(SELECT_ENTITY_ID_FORMAT, MOCK_IP_ADDRESS, code)


def test_startup_options() -> None:
    """Options lead with None, sort by name and keep duplicates apart."""

    assert startup_options({}) == {"": "None"}
    assert startup_options(
        {"b": "Beta", "a": "alpha", "c": "Beta", "n": "None"}
    ) == {
        "": "None",
        "a": "alpha",
        "b": "Beta",
        "c": "Beta (c)",
        "n": "None (n)",
    }


async def test_startup_selects(hass: HomeAssistant) -> None:
    """LedFx reports the startup scene and playlist as selects."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        updater, _ = await _setup(hass, mock_client)

        scene = hass.states.get(_select_id("startup_scene"))
        assert scene is not None
        assert scene.name == "LedFx Startup scene"
        assert scene.state == "test"
        assert scene.attributes["options"] == ["None", "test"]
        assert scene.attributes["icon"] == "mdi:image-play"

        playlist = hass.states.get(_select_id("startup_playlist"))
        assert playlist is not None
        assert playlist.name == "LedFx Startup playlist"
        assert playlist.state == "None"
        assert playlist.attributes["options"] == ["None", "Evening", "Morning"]

        assert (
            updater.selects["startup_scene"].description.entity_category
            == EntityCategory.CONFIG
        )


async def test_select_startup_scene(hass: HomeAssistant) -> None:
    """Selecting an option writes the matching id to the LedFx configuration."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup(hass, mock_client)

        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: _select_id("startup_playlist"), ATTR_OPTION: "Morning"},
            blocking=True,
        )

        mock_client.return_value.set_config.assert_awaited_once_with(
            {"startup_playlist_id": "morning"}
        )
        assert hass.states.get(_select_id("startup_playlist")).state == "Morning"

        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: _select_id("startup_scene"), ATTR_OPTION: "None"},
            blocking=True,
        )

        mock_client.return_value.set_config.assert_awaited_with(
            {"startup_scene_id": ""}
        )
        assert hass.states.get(_select_id("startup_scene")).state == "None"


async def test_select_startup_scene_error(hass: HomeAssistant) -> None:
    """A rejected write reaches the caller and leaves the state unchanged."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup(hass, mock_client)

        mock_client.return_value.set_config = AsyncMock(
            side_effect=LedFxRequestError("Scene not found")
        )

        with pytest.raises(HomeAssistantError, match="Scene not found"):
            await hass.services.async_call(
                SELECT_DOMAIN,
                SERVICE_SELECT_OPTION,
                {ATTR_ENTITY_ID: _select_id("startup_scene"), ATTR_OPTION: "None"},
                blocking=True,
            )

        assert hass.states.get(_select_id("startup_scene")).state == "test"



async def test_no_entity_for_unreported_settings(hass: HomeAssistant) -> None:
    """No select exists when LedFx reports no startup setting."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup(hass, mock_client, config={})

        assert hass.states.get(_select_id("startup_scene")) is None
        assert hass.states.get(_select_id("startup_playlist")) is None
