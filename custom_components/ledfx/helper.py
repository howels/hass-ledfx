"""Integration helper."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from aiohttp import BasicAuth
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration
from homeassistant.util import slugify

from .client import LedFxClient
from .const import DEFAULT_TIMEOUT, DOMAIN
from .enums import EffectCategory
from .exceptions import LedFxConnectionError, LedFxRequestError

_LOGGER = logging.getLogger(__name__)


def get_config_value(
    config_entry: config_entries.ConfigEntry | None, param: str, default=None
) -> Any:
    """Get current value for configuration parameter.

    :param config_entry: config_entries.ConfigEntry|None: config entry from Flow
    :param param: str: parameter name for getting value
    :param default: default value for parameter, defaults to None
    :return Any: parameter value, or default value or None
    """

    return (
        config_entry.options.get(param, config_entry.data.get(param, default))
        if config_entry is not None
        else default
    )


async def async_verify_access(  # pylint: disable=too-many-arguments
    hass: HomeAssistant,
    ip: str,  # pylint: disable=invalid-name
    port: str,
    username: str | None,
    password: str | None,
    timeout: int = DEFAULT_TIMEOUT,
) -> HTTPStatus:
    """Verify authentication data.

    :param hass: HomeAssistant: Home Assistant object
    :param ip: str: Ip address
    :param port: str: Port
    :param username: str | None: Basic auth username
    :param password: str | None: Basic auth password
    :param timeout: int: Timeout
    :return HTTPStatus: OK, FORBIDDEN (rejected request) or NOT_FOUND (unreachable)
    """

    client: LedFxClient = LedFxClient(
        async_get_clientsession(hass),
        ip,
        port,
        build_auth(username, password),
        timeout,
    )

    try:
        await client.config()
    except LedFxConnectionError:
        return HTTPStatus.NOT_FOUND
    except LedFxRequestError:
        return HTTPStatus.FORBIDDEN

    return HTTPStatus.OK


async def async_get_version(hass: HomeAssistant) -> str:
    """Get the documentation url for creating a local user.

    :param hass: HomeAssistant: Home Assistant object
    :return str: Documentation URL
    """

    integration = await async_get_integration(hass, DOMAIN)

    return f"{integration.version}"


def build_auth(username: str | None, password: str | None) -> BasicAuth | None:
    """Build basic auth data

    :param username: Username
    :param password: Password
    :return BasicAuth | None
    """

    if username is None or password is None:
        return None

    return BasicAuth(username, password)


def clean_flow_user_input(user_input: dict, supports_basic_auth: bool = False) -> dict:
    """Clean user input

    :param user_input: dict: User input
    :param supports_basic_auth: bool: Is supports basic auth
    :return dict: User input
    """

    return {
        key: value
        for key, value in user_input.items()
        if supports_basic_auth
        or (not supports_basic_auth and key not in [CONF_USERNAME, CONF_PASSWORD])
    }


def generate_entity_id(
    entity_id_format: str, ip_address: str, name: str | None = None
) -> str:
    """Generate Entity ID

    :param entity_id_format: str: Format
    :param ip_address: str: Ip address
    :param name: str | None: Name
    :return str: Entity ID
    """

    _name: str = f"_{name}" if name is not None else ""

    return entity_id_format.format(slugify(f"ledfx_{ip_address}{_name}".lower()))


def build_effects(
    effects: list, default_presets: dict[str, list], custom_presets: dict[str, list]
) -> list:
    """Build effects

    :param effects: list: Effects list
    :param default_presets: dict[str, list]: Default presets list
    :param custom_presets: dict[str, list]: Custom presets list
    :return list
    """

    full_effects: list = []

    for effect in effects:
        full_effects.append(effect)
        full_effects += [
            f"{effect} - {preset}" for preset in default_presets.get(effect, [])
        ]
        full_effects += [
            f"{effect} - {preset}"
            for preset in custom_presets.get(effect, [])
            if effect in custom_presets
        ]

    return full_effects


def find_effect(
    effect: str, default_presets: dict[str, list], custom_presets: dict[str, list]
) -> tuple[str | None, str | None, EffectCategory]:
    """Find effect

    :param effect: str: Effect
    :param default_presets: dict[str, list]: Default presets list
    :param custom_presets: dict[str, list]: Custom presets list
    :return tuple[str | None, str | None, EffectCategory]
    """

    preset: str | None = None
    category: EffectCategory = EffectCategory.NONE

    if " - " in effect:
        chunk: list = effect.split(" - ")
        effect = chunk[0]
        preset = " - ".join(chunk[1:])

        if effect in custom_presets and preset in custom_presets[effect]:
            category = EffectCategory.CUSTOM
        elif effect in default_presets and preset in default_presets[effect]:
            category = EffectCategory.DEFAULT

    return effect, preset, category


def hex_to_rgbw(
    color: str | None,
) -> tuple[int, int, int, int] | None:
    """Convert hex color to rgbw

    :param color: str | None
    :return tuple[int, int, int, int] | None: None for a missing or unparsable value
    """

    if not color or not isinstance(color, str):
        return None

    color = color.lstrip("#").lower()

    if len(color) == 3:
        color = "".join(char * 2 for char in color)

    if len(color) != 6:
        return None

    if color == "ffffff":
        return 0, 0, 0, 255

    if color == "000000":
        return 0, 0, 0, 0

    try:
        return (
            int(color[0:2], 16),
            int(color[2:4], 16),
            int(color[4:6], 16),
            0,
        )
    except ValueError:
        return None


def rgbw_to_hex(color: tuple[int, int, int, int] | None) -> str | None:
    """Convert hex color to rgbw

    :param color: tuple[int, int, int, int] | None
    :return str
    """

    if not color:  # pragma: no cover
        return None

    if color[0] == 0 and color[1] == 0 and color[2] == 0:
        return "#ffffff" if color[3] > 0 else "#000000"

    return "#%02x%02x%02x" % color[:3]  # pylint: disable=consider-using-f-string
