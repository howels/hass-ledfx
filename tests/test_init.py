"""Tests for the ledfx entry lifecycle and the updater error handling."""

# pylint: disable=protected-access

from __future__ import annotations

import copy
import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.dt import utcnow
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    load_fixture,
)

from custom_components.ledfx import async_remove_config_entry_device
from custom_components.ledfx.const import ATTR_STATE, DEFAULT_SCAN_INTERVAL, DOMAIN
from custom_components.ledfx.enums import Version
from custom_components.ledfx.exceptions import LedFxConnectionError
from custom_components.ledfx.updater import LedFxUpdater
from tests.setup import async_mock_client, async_mock_client_2, async_setup


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations"""

    yield


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """The entry loads with its platforms and unloads without leftovers."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client(mock_client)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED
        assert isinstance(config_entry.runtime_data, LedFxUpdater)
        assert hass.states.async_entity_ids("light")

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.NOT_LOADED
        assert all(
            state.state == STATE_UNAVAILABLE
            for state in hass.states.async_all()
            if state.entity_id.startswith("light.")
        )

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED


async def test_setup_while_ledfx_is_offline(hass: HomeAssistant) -> None:
    """The entry loads while LedFx is unreachable and reports `off` for the state."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client(mock_client)
        mock_client.return_value.config = AsyncMock(side_effect=LedFxConnectionError)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED

        updater: LedFxUpdater = config_entry.runtime_data

        assert updater.data[ATTR_STATE] is False
        assert (
            hass.states.get("binary_sensor.ledfx_192_168_31_1_state").state == STATE_OFF
        )


@pytest.mark.parametrize("failing_method", ["config", "virtuals", "devices", "scenes"])
async def test_updater_survives_connection_loss(
    hass: HomeAssistant, failing_method: str
) -> None:
    """A failing request marks LedFx as unreachable and polling continues."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        updater: LedFxUpdater = config_entry.runtime_data
        state_id: str = "binary_sensor.ledfx_192_168_31_1_state"

        assert updater.version == Version.V2
        assert hass.states.get(state_id).state == STATE_ON

        working = getattr(mock_client.return_value, failing_method)
        setattr(
            mock_client.return_value,
            failing_method,
            AsyncMock(side_effect=LedFxConnectionError),
        )

        async_fire_time_changed(
            hass, utcnow() + timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1)
        )
        await hass.async_block_till_done()

        assert hass.states.get(state_id).state == STATE_OFF

        setattr(mock_client.return_value, failing_method, working)

        async_fire_time_changed(
            hass, utcnow() + timedelta(seconds=2 * DEFAULT_SCAN_INTERVAL + 2)
        )
        await hass.async_block_till_done()

        assert hass.states.get(state_id).state == STATE_ON


async def test_sw_version_uses_ledfx_version(hass: HomeAssistant) -> None:
    """The service device reports the LedFx version, not the config version."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        info: dict = json.loads(load_fixture("info_data.json")) | {"version": "2.2.1"}
        mock_client.return_value.info = AsyncMock(return_value=info)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        service = _device(
            dr.async_get(hass),
            config_entry.entry_id,
            (DOMAIN, config_entry.runtime_data.address),
        )

        assert service is not None
        assert service.sw_version == "2.2.1"


async def test_virtual_with_effect_but_inactive_is_off(hass: HomeAssistant) -> None:
    """LedFx 2.x keeps the effect on a virtual that was switched off."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        virtuals: dict = copy.deepcopy(json.loads(load_fixture("virtuals_data.json")))
        virtuals["virtuals"]["wled"]["active"] = False
        mock_client.return_value.virtuals = AsyncMock(return_value=virtuals)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("light.ledfx_192_168_31_1_wled").state == STATE_OFF


async def test_virtuals_without_physical_devices(hass: HomeAssistant) -> None:
    """Virtuals are exposed even when LedFx lists no physical devices."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)
        mock_client.return_value.devices = AsyncMock(
            return_value={"status": "success", "devices": {}}
        )

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("light.ledfx_192_168_31_1_wled") is not None
        assert DOMAIN in hass.config.components


def _device(
    registry: dr.DeviceRegistry, entry_id: str, identifier: tuple[str, str]
) -> dr.DeviceEntry | None:
    """Return the device of a config entry by identifier.

    Home Assistant 2026.11 deprecates `async_get_device` because identifiers are
    unique per config entry only. Filtering the entry's devices works on every
    supported release.
    """

    return next(
        (
            device
            for device in dr.async_entries_for_config_entry(registry, entry_id)
            if identifier in device.identifiers
        ),
        None,
    )


async def test_entities_follow_the_entity_naming_standard(hass: HomeAssistant) -> None:
    """Every entity names itself relative to its device."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)

        assert entries
        assert all(entry.has_entity_name for entry in entries)
        assert all(entry.device_id for entry in entries)

        lights = [entry for entry in entries if entry.domain == "light"]

        assert lights
        # A light is the main feature of its device and carries no name of its own.
        assert all(entry.original_name is None for entry in lights)


async def test_virtuals_are_separate_devices(hass: HomeAssistant) -> None:
    """Each virtual has its own device next to the service device."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        updater: LedFxUpdater = config_entry.runtime_data
        registry = dr.async_get(hass)

        service = _device(registry, config_entry.entry_id, (DOMAIN, updater.address))

        assert service is not None
        assert service.entry_type is dr.DeviceEntryType.SERVICE
        assert updater.devices

        for code in updater.devices:
            device = _device(
                registry, config_entry.entry_id, updater.device_identifier(code)
            )

            assert device is not None
            assert device.id != service.id


async def test_remove_config_entry_device(hass: HomeAssistant) -> None:
    """A device LedFx still reports stays. A stale device can be removed."""

    with patch("custom_components.ledfx.updater.LedFxClient") as mock_client:
        await async_mock_client_2(mock_client)

        _, config_entry = await async_setup(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        updater: LedFxUpdater = config_entry.runtime_data
        registry = dr.async_get(hass)

        service = _device(registry, config_entry.entry_id, (DOMAIN, updater.address))
        code = next(iter(updater.devices))
        current = _device(
            registry, config_entry.entry_id, (DOMAIN, f"{updater.address}-{code}")
        )
        stale = registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, f"{updater.address}-gone")},
        )

        assert not await async_remove_config_entry_device(hass, config_entry, service)
        assert not await async_remove_config_entry_device(hass, config_entry, current)
        assert await async_remove_config_entry_device(hass, config_entry, stale)
