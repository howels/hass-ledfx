"""LedFx API client."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    CLIENT_URL,
    DEFAULT_POST_TIMEOUT,
    DEFAULT_TIMEOUT,
    DIAGNOSTIC_CONTENT,
    DIAGNOSTIC_DATE_TIME,
    DIAGNOSTIC_MESSAGE,
)
from .enums import EffectCategory, Method
from .exceptions import LedFxConnectionError, LedFxRequestError

_LOGGER = logging.getLogger(__name__)

# Preset category names used by the LedFx configuration version 2 API.
PRESET_CATEGORIES_V2: dict[str, str] = {
    EffectCategory.DEFAULT.value: "ledfx_presets",
    EffectCategory.CUSTOM.value: "user_presets",
}


# pylint: disable=too-many-public-methods,too-many-arguments
class LedFxClient:
    """LedFx API Client."""

    ip: str  # pylint: disable=invalid-name
    port: str

    _session: ClientSession
    _authorization: str | None = None
    _timeout: int = DEFAULT_TIMEOUT

    _url: str

    def __init__(
        self,
        session: ClientSession,
        ip: str,  # pylint: disable=invalid-name
        port: str,
        authorization: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        use_ssl: bool = False,
    ) -> None:
        """Initialize API client.

        :param session: ClientSession: aiohttp session
        :param ip: str: ip address or host name
        :param port: str: port
        :param authorization: str | None: Value of the Authorization header
        :param timeout: int: Query execution timeout
        :param use_ssl: bool: Use HTTPS instead of HTTP
        """

        ip = ip.removesuffix("/")
        self._session = session
        self.ip = ip  # pylint: disable=invalid-name
        self.port = port
        self._authorization = authorization
        self._timeout = timeout

        host: str = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
        self._url = CLIENT_URL.format(
            scheme="https" if use_ssl else "http", ip=host, port=port
        )

        self.diagnostics: dict[str, Any] = {}

    async def request(
        self,
        path: str,
        method: Method = Method.GET,
        body: dict | None = None,
        validate_field: str | tuple = "status",
    ) -> dict:
        """Request method.

        :param path: str: api path
        :param method: Method: api method
        :param body: dict | None: api body
        :param validate_field: str | tuple: validate field
        :return dict: dict with api data.
        """

        _timeout: int = (
            self._timeout
            if method == Method.GET
            else max(self._timeout, DEFAULT_POST_TIMEOUT)
        )
        _url: str = f"{self._url}/{path}"

        status: int = 0

        try:
            async with self._session.request(
                method.value,
                _url,
                json=body,
                headers=(
                    {"Authorization": self._authorization}
                    if self._authorization
                    else None
                ),
                timeout=ClientTimeout(total=_timeout),
            ) as response:
                content: bytes = await response.read()
                status = response.status

            self._debug("Successful request", _url, content, path)

            _data: Any = json.loads(content)
        except (ClientError, TimeoutError, ValueError, TypeError) as _e:
            if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                self._debug("Authentication failed", _url, _e, path)

                raise LedFxRequestError("Authentication failed") from _e

            self._debug("Connection error", _url, _e, path)

            raise LedFxConnectionError("Connection error") from _e

        if not isinstance(_data, dict):
            self._debug("Invalid response received", _url, _data, path)

            raise LedFxRequestError("Request error")

        if validate_field == "status" and (
            validate_field not in _data or _data[validate_field] != "success"
        ):
            self._debug("Invalid status received", _url, _data, path)

            raise LedFxRequestError("Request error")

        if (isinstance(validate_field, str) and validate_field not in _data) or (
            isinstance(validate_field, tuple)
            and not any(key in _data for key in validate_field)
        ):
            self._debug("Invalid response received", _url, _data, path)

            raise LedFxRequestError("Request error")

        return _data

    async def info(self) -> dict:
        """info method.

        :return dict: dict with api data.
        """

        return await self.request("info", validate_field="url")

    async def devices(self) -> dict:
        """devices method.

        :return dict: dict with api data.
        """

        return await self.request("devices")

    async def virtuals(self) -> dict:
        """virtuals method.

        :return dict: dict with api data.
        """

        return await self.request("virtuals")

    async def scenes(self) -> dict:
        """scenes method.

        :return dict: dict with api data.
        """

        return await self.request("scenes")

    async def audio_devices(self) -> dict:
        """audio/devices method.

        :return dict: dict with api data.
        """

        return await self.request("audio/devices", validate_field="devices")

    async def schema(self) -> dict:
        """schema method.

        :return dict: dict with api data.
        """

        return await self.request("schema", validate_field="devices")

    async def config(self) -> dict:
        """config method.

        :return dict: dict with api data.
        """

        return await self.request(
            "config", validate_field=("config", "configuration_version")
        )

    async def colors(self) -> dict:
        """colors method.

        :return dict: dict with api data.
        """

        return await self.request("colors", validate_field="colors")

    async def device_on(
        self, device_code: str, effect: str, is_virtual: bool = False
    ) -> dict:
        """devices/effects on method.

        :param device_code: str: device code
        :param effect: str: effect code
        :param is_virtual: bool: Is virtual device
        :return dict: dict with api data.
        """

        prefix: str = "virtuals" if is_virtual else "devices"

        return await self.request(
            f"{prefix}/{device_code}/effects",
            Method.POST,
            {"config": {"active": True}, "type": effect},
        )

    async def device_off(self, device_code: str, is_virtual: bool = False) -> dict:
        """devices/effects off method.

        :param device_code: str: device code
        :param is_virtual: bool: Is virtual device
        :return dict: dict with api data.
        """

        prefix: str = "virtuals" if is_virtual else "devices"

        return await self.request(f"{prefix}/{device_code}/effects", Method.DELETE)

    async def preset(
        self,
        device_code: str,
        category: str,
        effect: str,
        preset: str,
        is_virtual: bool = False,
    ) -> dict:
        """devices/presets on method.

        :param device_code: str: device code
        :param category: str: preset category
        :param effect: str: effect code
        :param preset: str: preset code
        :param is_virtual: bool: Is virtual device
        :return dict: dict with api data.
        """

        prefix: str = "virtuals" if is_virtual else "devices"

        if is_virtual:
            category = PRESET_CATEGORIES_V2.get(category, category)

        return await self.request(
            f"{prefix}/{device_code}/presets",
            Method.PUT,
            {"category": category, "effect_id": effect, "preset_id": preset},
        )

    async def effect(
        self, device_code: str, effect: str, config: dict, is_virtual: bool = False
    ) -> dict:
        """devices/effects update method.

        :param device_code: str: device code
        :param effect: str: effect code
        :param config: dict: effect config
        :param is_virtual: bool: Is virtual device
        :return dict: dict with api data.
        """

        prefix: str = "virtuals" if is_virtual else "devices"

        return await self.request(
            f"{prefix}/{device_code}/effects",
            Method.PUT,
            {"config": config, "type": effect},
        )

    async def set_audio_device(self, index: int, is_new: bool = False) -> dict:
        """audio/devices set method.

        :param index: int: device index
        :param is_new: bool: Is new api
        :return dict: dict with api data.
        """

        if is_new:
            return await self.request(
                "config", Method.PUT, {"audio": {"audio_device": index}}
            )

        return await self.request("audio/devices", Method.PUT, {"index": index})

    async def toggle_play_pause(self) -> dict:
        """virtuals pause toggle method.

        :return dict: dict with api data, including the new `paused` state.
        """

        return await self.request("virtuals", Method.PUT)

    async def run_scene(self, scene_id: str) -> dict:
        """scenes run method.

        :param scene_id: str: scene id
        :return dict: dict with api data.
        """

        return await self.request(
            "scenes", Method.PUT, {"action": "activate", "id": scene_id}
        )

    def _debug(self, message: str, url: str, content: Any, path: str) -> None:
        """Debug log

        :param message: str: Message
        :param url: str: URL
        :param content: Any: Content
        :param path: str: Path
        """

        _LOGGER.debug("%s (%s): %s", message, url, str(content))

        _content: dict | str = {}

        try:
            _content = json.loads(content)
        except (ValueError, TypeError):  # pragma: no cover
            _content = str(content)

        self.diagnostics[path] = {
            DIAGNOSTIC_DATE_TIME: datetime.now().replace(microsecond=0).isoformat(),
            DIAGNOSTIC_MESSAGE: message,
            DIAGNOSTIC_CONTENT: _content,
        }
