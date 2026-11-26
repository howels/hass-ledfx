"""LedFx API client exceptions."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class LedFxError(HomeAssistantError):
    """LedFx error"""


class LedFxConnectionError(LedFxError):
    """LedFx connection error"""


class LedFxRequestError(LedFxError):
    """LedFx request error"""
