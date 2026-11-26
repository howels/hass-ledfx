"""Tests for free-text effect fields."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.text import ATTR_VALUE
from homeassistant.components.text import DOMAIN as TEXT_DOMAIN
from homeassistant.components.text import ENTITY_ID_FORMAT as TEXT_ENTITY_ID_FORMAT
from homeassistant.components.text import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util.dt import utcnow
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    load_fixture,
)

from custom_components.ledfx.const import ATTRIBUTION, DEFAULT_SCAN_INTERVAL, DOMAIN
from custom_components.ledfx.exceptions import LedFxRequestError
from custom_components.ledfx.helper import generate_entity_id
from custom_components.ledfx.updater import text_length_bounds, text_pattern
from tests.setup import MOCK_IP_ADDRESS, async_mock_client_2, async_setup

TEXT_PATTERN = "^[A-Za-z0-9 ]*$"

TEXTER_SCHEMA: dict[str, Any] = {
    "effects": {
        "texter2d": {
            "name": "Texter",
            "schema": {
                "properties": {
                    "brightness": {"type": "number", "title": "Brightness"},
                    "text": {
                        "type": "string",
                        "title": "Text",
                        "minLength": 1,
                        "maxLength": 32,
                        "pattern": TEXT_PATTERN,
                    },
                    "font": {
                        "type": "string",
                        "title": "Font",
                        "enum": ["Press Start 2P", "Roboto"],
                    },
                    "note": {
                        "type": "string",
                        "title": "Note",
                        "minLength": -4,
                        "maxLength": "nope",
                        "pattern": "(",
                    },
                }
            },
        }
    }
}


def _virtuals(text: str = "Hello") -> dict[str, Any]:
    """Return one active Texter virtual and one inactive virtual."""

    return {
        "paused": False,
        "virtuals": {
            "wled": {
                "config": {"name": "WLED", "icon_name": "mdi:led-strip-variant"},
                "id": "wled",
                "is_device": "garland-1",
                "active": True,
                "effect": {
                    "name": "Texter",
                    "type": "texter2d",
                    "config": {
                        "brightness": 1.0,
                        "background_color": "#ffffff",
                        "text": text,
                        "font": "Roboto",
                        "note": "Side",
                    },
                },
            },
            "wled-1": {
                "config": {"name": "Spare", "icon_name": "mdi:led-strip-variant"},
                "id": "wled-1",
                "is_device": "ambient-lighting",
                "active": False,
                "effect": {},
            },
        },
    }


def _text_id(key: str, device: str = "wled") -> str:
    return generate_entity_id(TEXT_ENTITY_ID_FORMAT, MOCK_IP_ADDRESS, f"{device}_{key}")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations"""

    yield


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ({}, (0, 255)),
        ({"minLength": 1, "maxLength": 32}, (1, 32)),
        ({"minLength": -4, "maxLength": "nope"}, (0, 255)),
        ({"minLength": 300, "maxLength": 400}, (255, 255)),
        ({"minLength": 10, "maxLength": 4}, (10, 10)),
    ],
)
def test_text_length_bounds(reported: dict, expected: tuple[int, int]) -> None:
    """Limits stay inside the Home Assistant state length."""

    assert text_length_bounds(reported) == expected


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        (None, None),
        ("", None),
        (12, None),
        ("(", None),
        (TEXT_PATTERN, TEXT_PATTERN),
    ],
)
def test_text_pattern(reported: Any, expected: str | None) -> None:
    """Only a compilable pattern is kept."""

    assert text_pattern(reported) is expected


async def _setup_texter(hass: HomeAssistant, mock_client: Any) -> Any:
    """Set up an entry whose schema contains the Texter text field."""

    await async_mock_client_2(mock_client)
    mock_client.return_value.schema = AsyncMock(return_value=TEXTER_SCHEMA)
    mock_client.return_value.virtuals = AsyncMock(return_value=_virtuals())
    mock_client.return_value.effect = AsyncMock(
        return_value=json.loads(load_fixture("effect_data.json"))
    )

    _, config_entry = await async_setup(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry


async def _enable(hass: HomeAssistant, entity_id: str) -> None:
    """Enable an entity and let the coordinator publish its state."""

    er.async_get(hass).async_update_entity(entity_id=entity_id, disabled_by=None)
    await hass.async_block_till_done()

    # Enabling an entity reloads the config entry after a short delay.
    for _ in range(2):
        async_fire_time_changed(
            hass, utcnow() + timedelta(seconds=DEFAULT_SCAN_INTERVAL + 30)
        )
        await hass.async_block_till_done()


async def test_texter_text_entity(hass: HomeAssistant) -> None:
    """The Texter text field is a disabled text entity until it is enabled."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        config_entry = await _setup_texter(hass, mock_client)
        registry = er.async_get(hass)
        entity_id = _text_id("text")

        assert hass.states.get(entity_id) is None

        entry = registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert entry.entity_category == EntityCategory.CONFIG
        assert entry.unique_id == f"{config_entry.entry_id}-wled-text"

        assert (
            registry.async_get_entity_id(
                "select", DOMAIN, f"{config_entry.entry_id}-wled-font"
            )
            is not None
        )
        assert (
            registry.async_get_entity_id(
                "text", DOMAIN, f"{config_entry.entry_id}-wled-font"
            )
            is None
        )

        await _enable(hass, entity_id)
        await _enable(hass, _text_id("note"))
        await _enable(hass, _text_id("text", "wled-1"))

        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "Hello"
        assert state.name == "WLED Text"
        assert state.attributes["icon"] == "mdi:format-text"
        assert state.attributes["min"] == 1
        assert state.attributes["max"] == 32
        assert state.attributes["pattern"] == TEXT_PATTERN
        assert state.attributes["mode"] == "text"
        assert state.attributes["attribution"] == ATTRIBUTION

        note = hass.states.get(_text_id("note"))
        assert note is not None
        assert note.state == "Side"
        assert note.attributes["min"] == 0
        assert note.attributes["max"] == 255
        assert note.attributes.get("pattern") is None

        spare = hass.states.get(_text_id("text", "wled-1"))
        assert spare is not None
        assert spare.state == STATE_UNAVAILABLE


async def test_set_text_value(hass: HomeAssistant) -> None:
    """A valid value is written to the effect, and invalid values are refused."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup_texter(hass, mock_client)
        entity_id = _text_id("text")
        await _enable(hass, entity_id)

        await hass.services.async_call(
            TEXT_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "Hi there"},
            blocking=True,
        )

        mock_client.return_value.effect.assert_awaited_once_with(
            "wled",
            "texter2d",
            {
                "brightness": 1.0,
                "background_color": "#ffffff",
                "text": "Hi there",
                "font": "Roboto",
                "note": "Side",
            },
            True,
        )
        assert hass.states.get(entity_id).state == "Hi there"

        # Home Assistant 2026.2 raises ValueError. Later releases raise
        # ServiceValidationError. Both reject the value before LedFx sees it.
        with pytest.raises((ServiceValidationError, ValueError)):
            await hass.services.async_call(
                TEXT_DOMAIN,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "Hi!"},
                blocking=True,
            )

        with pytest.raises((ServiceValidationError, ValueError)):
            await hass.services.async_call(
                TEXT_DOMAIN,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "x" * 33},
                blocking=True,
            )

        assert mock_client.return_value.effect.await_count == 1
        assert hass.states.get(entity_id).state == "Hi there"

        mock_client.return_value.effect = AsyncMock(side_effect=LedFxRequestError)

        with pytest.raises(LedFxRequestError):
            await hass.services.async_call(
                TEXT_DOMAIN,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "Next"},
                blocking=True,
            )


async def test_text_follows_ledfx(hass: HomeAssistant) -> None:
    """A later read replaces the value shown by the text entity."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await _setup_texter(hass, mock_client)
        entity_id = _text_id("text")
        await _enable(hass, entity_id)

        mock_client.return_value.virtuals = AsyncMock(
            return_value=_virtuals("Next line")
        )

        async_fire_time_changed(
            hass, utcnow() + timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1)
        )
        await hass.async_block_till_done()

        assert hass.states.get(entity_id).state == "Next line"
