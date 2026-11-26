"""Tests for the ledfx API client."""

# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import load_fixture
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ledfx.client import LedFxClient
from custom_components.ledfx.enums import Method
from custom_components.ledfx.exceptions import LedFxConnectionError, LedFxRequestError
from custom_components.ledfx.helper import build_authorization
from tests.setup import MOCK_DEVICE, MOCK_IP_ADDRESS, MOCK_PORT, get_url

EFFECT_CONFIG: dict[str, Any] = {
    "blur": 8.587469069357562,
    "brightness": 1,
    "flip": True,
    "gradient_name": "Sunset",
    "gradient_roll": 4,
    "mirror": False,
    "gradient_repeat": 1,
    "background_color": "white",
}


def _client(hass: HomeAssistant, authorization: str | None = None) -> LedFxClient:
    """Build a client for the mock address."""

    return LedFxClient(
        async_get_clientsession(hass), f"{MOCK_IP_ADDRESS}/", MOCK_PORT, authorization
    )


def _last_call(aioclient_mock: AiohttpClientMocker) -> tuple[str, str, Any]:
    """Return method, url and body of the last request."""

    method, url, body, _ = aioclient_mock.mock_calls[-1]

    return method, str(url), body


@pytest.mark.parametrize(
    ("call", "path", "fixture"),
    [
        ("info", "info", "info_data.json"),
        ("devices", "devices", "devices_data.json"),
        ("virtuals", "virtuals", "virtuals_data.json"),
        ("scenes", "scenes", "scenes_data.json"),
        ("audio_devices", "audio/devices", "audio_devices_data.json"),
        ("schema", "schema", "schema_data.json"),
        ("config", "config", "config_data.json"),
        ("config", "config", "config_v2_data.json"),
        ("colors", "colors", "colors_data.json"),
    ],
)
async def test_get(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    call: str,
    path: str,
    fixture: str,
) -> None:
    """GET endpoints return the decoded body."""

    aioclient_mock.get(get_url(path), text=load_fixture(fixture))

    assert await getattr(_client(hass), call)() == json.loads(load_fixture(fixture))

    assert _last_call(aioclient_mock)[:2] == (Method.GET.value, get_url(path))


@pytest.mark.parametrize("is_virtual", [False, True])
async def test_device_on(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, is_virtual: bool
) -> None:
    """Device on posts the effect."""

    prefix: str = "virtuals" if is_virtual else "devices"
    url: str = get_url(f"{prefix}/{MOCK_DEVICE}/effects")
    aioclient_mock.post(url, text=load_fixture("device_on_data.json"))

    assert await _client(hass).device_on(
        MOCK_DEVICE, "wavelength(Reactive)", is_virtual
    ) == json.loads(load_fixture("device_on_data.json"))

    method, _url, body = _last_call(aioclient_mock)
    assert (method, _url) == (Method.POST.value, url)
    assert body == {"config": {"active": True}, "type": "wavelength(Reactive)"}


@pytest.mark.parametrize("is_virtual", [False, True])
async def test_device_off(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, is_virtual: bool
) -> None:
    """Device off deletes the effect."""

    prefix: str = "virtuals" if is_virtual else "devices"
    url: str = get_url(f"{prefix}/{MOCK_DEVICE}/effects")
    aioclient_mock.delete(url, text=load_fixture("device_off_data.json"))

    assert await _client(hass).device_off(MOCK_DEVICE, is_virtual) == json.loads(
        load_fixture("device_off_data.json")
    )

    assert _last_call(aioclient_mock)[:2] == (Method.DELETE.value, url)


@pytest.mark.parametrize(
    ("is_virtual", "category", "expected_category"),
    [
        (False, "default_presets", "default_presets"),
        (False, "custom_presets", "custom_presets"),
        (True, "default_presets", "ledfx_presets"),
        (True, "custom_presets", "user_presets"),
    ],
)
async def test_preset(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    is_virtual: bool,
    category: str,
    expected_category: str,
) -> None:
    """Presets use the category names of the configuration version in use."""

    prefix: str = "virtuals" if is_virtual else "devices"
    url: str = get_url(f"{prefix}/{MOCK_DEVICE}/presets")
    aioclient_mock.put(url, text=load_fixture("preset_data.json"))

    assert await _client(hass).preset(
        MOCK_DEVICE, category, "wavelength(Reactive)", "sunset-sweep", is_virtual
    ) == json.loads(load_fixture("preset_data.json"))

    method, _url, body = _last_call(aioclient_mock)
    assert (method, _url) == (Method.PUT.value, url)
    assert body == {
        "category": expected_category,
        "effect_id": "wavelength(Reactive)",
        "preset_id": "sunset-sweep",
    }


@pytest.mark.parametrize("is_virtual", [False, True])
async def test_effect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, is_virtual: bool
) -> None:
    """Effect updates put the new config."""

    prefix: str = "virtuals" if is_virtual else "devices"
    url: str = get_url(f"{prefix}/{MOCK_DEVICE}/effects")
    aioclient_mock.put(url, text=load_fixture("effect_data.json"))

    assert await _client(hass).effect(
        MOCK_DEVICE, "wavelength(Reactive)", EFFECT_CONFIG, is_virtual
    ) == json.loads(load_fixture("effect_data.json"))

    method, _url, body = _last_call(aioclient_mock)
    assert (method, _url) == (Method.PUT.value, url)
    assert body == {"config": EFFECT_CONFIG, "type": "wavelength(Reactive)"}


async def test_set_audio_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Audio device selection uses the endpoint of the API version."""

    aioclient_mock.put(
        get_url("audio/devices"), text=load_fixture("set_audio_device_data.json")
    )
    aioclient_mock.put(get_url("config"), text=load_fixture("set_audio_device_data.json"))

    client: LedFxClient = _client(hass)

    await client.set_audio_device(0)
    assert _last_call(aioclient_mock) == (
        Method.PUT.value,
        get_url("audio/devices"),
        {"index": 0},
    )

    await client.set_audio_device(2, True)
    assert _last_call(aioclient_mock) == (
        Method.PUT.value,
        get_url("config"),
        {"audio": {"audio_device": 2}},
    )


async def test_run_scene(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Scenes are activated by id."""

    aioclient_mock.put(get_url("scenes"), text=load_fixture("run_scene_data.json"))

    assert await _client(hass).run_scene("test") == json.loads(
        load_fixture("run_scene_data.json")
    )

    assert _last_call(aioclient_mock) == (
        Method.PUT.value,
        get_url("scenes"),
        {"action": "activate", "id": "test"},
    )


async def test_toggle_play_pause(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The global pause toggle is a bodyless PUT on the virtuals endpoint."""

    aioclient_mock.put(
        get_url("virtuals"), json={"status": "success", "paused": True}
    )

    assert await _client(hass).toggle_play_pause() == {
        "status": "success",
        "paused": True,
    }

    assert _last_call(aioclient_mock) == (Method.PUT.value, get_url("virtuals"), None)


async def test_ipv6_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """IPv6 literals are bracketed in the request URL."""

    url: str = f"http://[fd00::1]:{MOCK_PORT}/api/scenes"
    aioclient_mock.get(url, text=load_fixture("scenes_data.json"))

    client: LedFxClient = LedFxClient(
        async_get_clientsession(hass), "fd00::1", MOCK_PORT
    )

    await client.scenes()

    assert _last_call(aioclient_mock)[1] == url


async def test_basic_auth(hass: HomeAssistant) -> None:
    """Basic auth credentials are sent in the Authorization header."""

    session = MagicMock()
    session.request.return_value.__aenter__.return_value = AsyncMock(
        status=200,
        read=AsyncMock(return_value=load_fixture("scenes_data.json").encode()),
    )

    authorization: str | None = build_authorization("user", "pass")

    assert authorization == "Basic dXNlcjpwYXNz"

    await LedFxClient(session, MOCK_IP_ADDRESS, MOCK_PORT, authorization).scenes()

    assert session.request.call_args.kwargs["headers"] == {
        "Authorization": "Basic dXNlcjpwYXNz"
    }
    assert "auth" not in session.request.call_args.kwargs


async def test_no_credentials_sends_no_header(hass: HomeAssistant) -> None:
    """A client without credentials sends no Authorization header."""

    session = MagicMock()
    session.request.return_value.__aenter__.return_value = AsyncMock(
        status=200,
        read=AsyncMock(return_value=load_fixture("scenes_data.json").encode()),
    )

    await LedFxClient(session, MOCK_IP_ADDRESS, MOCK_PORT).scenes()

    assert session.request.call_args.kwargs["headers"] is None


async def test_playlists(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The playlists endpoint returns a bare payload."""

    aioclient_mock.get(get_url("playlists"), json={"playlists": {"a": {"name": "A"}}})

    assert await _client(hass).playlists() == {"playlists": {"a": {"name": "A"}}}


async def test_set_config(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Config keys go to the config endpoint as the request body."""

    aioclient_mock.put(get_url("config"), json={"status": "success"})

    await _client(hass).set_config({"startup_scene_id": "test"})

    assert _last_call(aioclient_mock) == (
        Method.PUT.value,
        get_url("config"),
        {"startup_scene_id": "test"},
    )


async def test_failure_reason(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The error carries the reason that LedFx gives."""

    aioclient_mock.put(
        get_url("scenes"),
        json={
            "status": "failed",
            "payload": {"type": "error", "reason": "Scene 'x' not found."},
        },
    )

    with pytest.raises(LedFxRequestError, match="Scene 'x' not found."):
        await _client(hass).run_scene("x")

    aioclient_mock.clear_requests()
    aioclient_mock.put(get_url("scenes"), json={"status": "failed"})

    with pytest.raises(LedFxRequestError, match="Request error"):
        await _client(hass).run_scene("x")


async def test_https_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client built with use_ssl requests the HTTPS URL."""

    url: str = get_url("scenes").replace("http://", "https://", 1)
    aioclient_mock.get(url, text=load_fixture("scenes_data.json"))

    client = LedFxClient(
        async_get_clientsession(hass), MOCK_IP_ADDRESS, MOCK_PORT, use_ssl=True
    )

    assert await client.scenes() == json.loads(load_fixture("scenes_data.json"))
    assert _last_call(aioclient_mock)[:2] == (Method.GET.value, url)


async def test_https_url_with_ipv6(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An IPv6 host is bracketed under HTTPS as well."""

    url: str = "https://[fd00::1]:8443/api/scenes"
    aioclient_mock.get(url, text=load_fixture("scenes_data.json"))

    await LedFxClient(
        async_get_clientsession(hass), "fd00::1", "8443", use_ssl=True
    ).scenes()

    assert _last_call(aioclient_mock)[1] == url


async def test_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Transport failures raise a connection error and are recorded."""

    aioclient_mock.get(get_url("scenes"), exc=TimeoutError)

    client: LedFxClient = _client(hass)

    with pytest.raises(LedFxConnectionError):
        await client.scenes()

    assert client.diagnostics["scenes"]["message"] == "Connection error"


@pytest.mark.parametrize(
    "response",
    [
        {"text": "not json"},
        {"text": "[]"},
        {"json": {"status": "failed", "payload": {"type": "error"}}},
        {"json": {"scenes": {}}},
    ],
)
async def test_request_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, response: dict
) -> None:
    """Responses that are not a success payload are rejected."""

    aioclient_mock.get(get_url("scenes"), **response)

    with pytest.raises((LedFxRequestError, LedFxConnectionError)):
        await _client(hass).scenes()


@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """An authentication failure is a request error, not a connection error."""

    aioclient_mock.get(get_url("scenes"), status=status, text="denied")

    with pytest.raises(LedFxRequestError):
        await _client(hass).scenes()
