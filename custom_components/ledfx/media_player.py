"""Media player component."""

from __future__ import annotations

from homeassistant.components.media_player import (
    ENTITY_ID_FORMAT,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityDescription,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_PAUSED, ATTR_STATE
from .entity import LedFxEntity
from .updater import LedFxConfigEntry, LedFxUpdater

PARALLEL_UPDATES = 0

MEDIA_PLAYERS: tuple[MediaPlayerEntityDescription, ...] = (
    MediaPlayerEntityDescription(
        key="media_player",
        name="LedFx media player",
        device_class=MediaPlayerDeviceClass.TV,
        entity_registry_enabled_default=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LedFxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LedFx media player entry.

    :param hass: HomeAssistant: Home Assistant object
    :param config_entry: LedFxConfigEntry: Config Entry object
    :param async_add_entities: AddEntitiesCallback: Async add callback
    """

    updater: LedFxUpdater = config_entry.runtime_data

    entities: list[LedFxMediaPlayer] = [
        LedFxMediaPlayer(
            f"{config_entry.entry_id}-{description.key}",
            description,
            updater,
        )
        for description in MEDIA_PLAYERS
    ]
    async_add_entities(entities)


class LedFxMediaPlayer(LedFxEntity, MediaPlayerEntity):
    """LedFx media player entry.

    LedFx exposes one global pause switch for all virtuals. The entity maps
    `PLAYING` to unpaused and `PAUSED` to paused.
    """

    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
    )

    def __init__(
        self,
        unique_id: str,
        description: MediaPlayerEntityDescription,
        updater: LedFxUpdater,
    ) -> None:
        """Initialize media player.

        :param unique_id: str: Unique ID
        :param description: MediaPlayerEntityDescription: MediaPlayerEntityDescription object
        :param updater: LedFxUpdater: LedFx updater object
        """

        LedFxEntity.__init__(self, unique_id, description, updater, ENTITY_ID_FORMAT)

        self._attr_state = self._state_from_data()

    def _state_from_data(self) -> MediaPlayerState:
        """Return the media player state for the current updater data."""

        if self._updater.data.get(ATTR_PAUSED):
            return MediaPlayerState.PAUSED

        return MediaPlayerState.PLAYING

    def _handle_coordinator_update(self) -> None:
        """Update state."""

        self._attr_available = self._updater.data.get(ATTR_STATE, False)
        self._attr_state = self._state_from_data()

        self.async_write_ha_state()

    async def _async_set_paused(self, paused: bool) -> None:
        """Set the global pause state.

        LedFx only offers a toggle, so a request is sent when the state differs.

        :param paused: bool: Requested pause state
        """

        if bool(self._updater.data.get(ATTR_PAUSED)) == paused:
            return

        response: dict = await self._updater.client.toggle_play_pause()

        self._updater.data[ATTR_PAUSED] = bool(response.get(ATTR_PAUSED, paused))
        self._attr_state = self._state_from_data()

        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        """Resume the virtuals."""

        await self._async_set_paused(False)

    async def async_media_pause(self) -> None:
        """Pause the virtuals."""

        await self._async_set_paused(True)
