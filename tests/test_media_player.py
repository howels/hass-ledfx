"""Tests for the ledfx media player."""

# pylint: disable=protected-access

from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.components.media_player import (
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    MediaPlayerState,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import load_fixture

from tests.setup import async_mock_client, async_mock_client_2, async_setup

ENTITY_ID = "media_player.ledfx_192_168_31_1_media_player"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations"""

    yield


@pytest.mark.parametrize("mock", [async_mock_client, async_mock_client_2])
async def test_pause_and_play(hass: HomeAssistant, mock) -> None:
    """Pause and play send a toggle only when the state has to change."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await mock(mock_client)

        virtuals: dict = copy.deepcopy(json.loads(load_fixture("virtuals_data.json")))
        mock_client.return_value.virtuals = AsyncMock(return_value=virtuals)

        toggle = AsyncMock(
            side_effect=[
                {"status": "success", "paused": True},
                {"status": "success", "paused": False},
            ]
        )
        mock_client.return_value.toggle_play_pause = toggle

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get(ENTITY_ID).state == MediaPlayerState.PLAYING

        # Already playing: no request.
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PLAY,
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )
        assert toggle.await_count == 0

        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PAUSE,
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )
        assert toggle.await_count == 1
        assert hass.states.get(ENTITY_ID).state == MediaPlayerState.PAUSED

        # Already paused: no request.
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PAUSE,
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )
        assert toggle.await_count == 1

        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PLAY,
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )
        assert toggle.await_count == 2
        assert hass.states.get(ENTITY_ID).state == MediaPlayerState.PLAYING


async def test_paused_state_from_ledfx(hass: HomeAssistant) -> None:
    """The entity reports the global pause state from LedFx."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        virtuals: dict = copy.deepcopy(json.loads(load_fixture("virtuals_data.json")))
        virtuals["paused"] = True
        mock_client.return_value.virtuals = AsyncMock(return_value=virtuals)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get(ENTITY_ID).state == MediaPlayerState.PAUSED
