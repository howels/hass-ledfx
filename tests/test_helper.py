"""Tests for the ledfx helpers."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant

from custom_components.ledfx.exceptions import LedFxConnectionError, LedFxRequestError
from custom_components.ledfx.helper import async_verify_access, normalise_user_input


@pytest.mark.parametrize(
    ("address", "ssl", "expected_address", "expected_ssl"),
    [
        ("192.0.2.1", None, "192.0.2.1", None),
        ("192.0.2.1", True, "192.0.2.1", True),
        (" ledfx.example ", None, "ledfx.example", None),
        ("https://ledfx.example", False, "ledfx.example", True),
        ("HTTPS://ledfx.example/", None, "ledfx.example", True),
        ("http://ledfx.example/", True, "ledfx.example", False),
        ("ledfx.example/", None, "ledfx.example", None),
    ],
)
def test_normalise_user_input(
    address: str, ssl: bool | None, expected_address: str, expected_ssl: bool | None
) -> None:
    """A URL scheme in the address overrides the HTTPS setting."""

    user_input = {CONF_IP_ADDRESS: address, CONF_PORT: "443"}
    if ssl is not None:
        user_input[CONF_SSL] = ssl

    result = normalise_user_input(user_input)

    assert result[CONF_IP_ADDRESS] == expected_address
    assert result.get(CONF_SSL) is expected_ssl
    assert result[CONF_PORT] == "443"
    assert user_input[CONF_IP_ADDRESS] == address


def test_normalise_user_input_without_address() -> None:
    """Input without an address passes through unchanged."""

    assert normalise_user_input({}) == {}


async def test_verify_access_passes_https_settings(hass: HomeAssistant) -> None:
    """The check builds the client with HTTPS and the matching session."""

    session = MagicMock()

    with patch("custom_components.ledfx.helper.LedFxClient") as mock_client, patch(
        "custom_components.ledfx.helper.async_get_clientsession", return_value=session
    ) as mock_session:
        mock_client.return_value.config = AsyncMock(return_value={})

        assert (
            await async_verify_access(
                hass, "ledfx.example", "443", None, None, 10, True, False
            )
            == HTTPStatus.OK
        )

    mock_session.assert_called_once_with(hass, verify_ssl=False)
    assert mock_client.call_args.args[0] is session
    assert mock_client.call_args.args[5] is True


async def test_verify_access_defaults_to_http(hass: HomeAssistant) -> None:
    """The check keeps plain HTTP and certificate verification by default."""

    with patch("custom_components.ledfx.helper.LedFxClient") as mock_client, patch(
        "custom_components.ledfx.helper.async_get_clientsession"
    ) as mock_session:
        mock_client.return_value.config = AsyncMock(return_value={})

        await async_verify_access(hass, "192.0.2.1", "8888", None, None)

    mock_session.assert_called_once_with(hass, verify_ssl=True)
    assert mock_client.call_args.args[5] is False


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (LedFxConnectionError, HTTPStatus.NOT_FOUND),
        (LedFxRequestError, HTTPStatus.FORBIDDEN),
    ],
)
async def test_verify_access_errors(
    hass: HomeAssistant, error: type[Exception], status: HTTPStatus
) -> None:
    """Connection and rejected requests map to distinct statuses."""

    with patch("custom_components.ledfx.helper.LedFxClient") as mock_client:
        mock_client.return_value.config = AsyncMock(side_effect=error)

        assert (
            await async_verify_access(hass, "192.0.2.1", "8888", None, None) == status
        )
