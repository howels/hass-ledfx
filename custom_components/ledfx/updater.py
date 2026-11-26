"""LedFx data updater."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import cached_property
from http import HTTPStatus
from typing import Any, Final

from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.light import LightEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory, EntityDescription
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import LedFxClient
from .const import (
    ATTR_DEVICE_SW_VERSION,
    ATTR_FIELD,
    ATTR_FIELD_EFFECTS,
    ATTR_FIELD_OPTIONS,
    ATTR_FIELD_TYPE,
    ATTR_LIGHT_BRIGHTNESS,
    ATTR_LIGHT_COLOR,
    ATTR_LIGHT_CONFIG,
    ATTR_LIGHT_CUSTOM_PRESETS,
    ATTR_LIGHT_DEFAULT_PRESETS,
    ATTR_LIGHT_EFFECT,
    ATTR_LIGHT_EFFECT_CONFIG,
    ATTR_LIGHT_EFFECTS,
    ATTR_LIGHT_STATE,
    ATTR_PAUSED,
    ATTR_SELECT_AUDIO_INPUT,
    ATTR_SELECT_AUDIO_INPUT_OPTIONS,
    ATTR_STATE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL,
    DEFAULT_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAINTAINER,
    NAME,
    SIGNAL_NEW_BUTTON,
    SIGNAL_NEW_DEVICE,
    SIGNAL_NEW_NUMBER,
    SIGNAL_NEW_SELECT,
    SIGNAL_NEW_SENSOR,
    SIGNAL_NEW_SWITCH,
)
from .enums import ActionType, Version
from .exceptions import LedFxConnectionError, LedFxError, LedFxRequestError

PREPARE_METHODS: Final = (
    "config",
    "info",
    "colors",
    "schema",
    "virtuals",
    "devices",
    "audio_devices",
    "scenes",
)

_LOGGER = logging.getLogger(__name__)


# pylint: disable=too-many-branches,too-many-lines,too-many-arguments
class LedFxUpdater(DataUpdateCoordinator[dict[str, Any]]):
    """LedFx data updater for interaction with LedFX API."""

    version: Version = Version.V1

    client: LedFxClient
    code: HTTPStatus = HTTPStatus.BAD_GATEWAY
    ip: str
    port: str

    new_button_callback: CALLBACK_TYPE | None = None
    new_device_callback: CALLBACK_TYPE | None = None
    new_number_callback: CALLBACK_TYPE | None = None
    new_select_callback: CALLBACK_TYPE | None = None
    new_sensor_callback: CALLBACK_TYPE | None = None
    new_switch_callback: CALLBACK_TYPE | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        ip: str,
        port: str,
        authorization: str | None = None,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
        config_entry: ConfigEntry | None = None,
        ssl: bool = DEFAULT_SSL,
        verify_ssl: bool = DEFAULT_VERIFY_SSL,
    ) -> None:
        """Initialize updater.

        :param hass: HomeAssistant: Home Assistant object
        :param ip: str: ip address
        :param port: str: port
        :param authorization: str | None: Value of the Authorization header
        :param scan_interval: int: Update interval
        :param timeout: int: Query execution timeout
        :param config_entry: ConfigEntry | None: Config entry that owns the updater
        :param ssl: bool: Use HTTPS instead of HTTP
        :param verify_ssl: bool: Verify the HTTPS certificate
        """

        self.client = LedFxClient(
            async_get_clientsession(hass, verify_ssl=verify_ssl),
            ip,
            port,
            authorization,
            timeout,
            ssl,
        )

        self.ip = ip  # pylint: disable=invalid-name
        self.port = port
        self.scheme: str = "https" if ssl else "http"

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{NAME} updater",
            update_interval=timedelta(seconds=scan_interval),
        )

        self.data: dict[str, Any] = {}

        self.buttons: dict[str, LedFxEntityDescription] = {}
        self.devices: dict[str, LedFxEntityDescription] = {}
        self.numbers: dict[str, LedFxEntityDescription] = {}
        self.selects: dict[str, LedFxEntityDescription] = {}
        self.sensors: dict[str, LedFxEntityDescription] = {}
        self.switches: dict[str, LedFxEntityDescription] = {}

        self.effect_properties: dict = {}
        self.colors: dict = {}
        self.gradients: dict = {}

        self._virtuals: dict = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Update LedFx information.

        :return dict: dict with LedFx data.
        """

        self.code = HTTPStatus.OK

        try:
            for method in PREPARE_METHODS:
                await self._async_prepare(method, self.data)
        except LedFxConnectionError:
            self.code = HTTPStatus.NOT_FOUND
        except LedFxRequestError:
            self.code = HTTPStatus.FORBIDDEN

        self.data[ATTR_STATE] = self.code == HTTPStatus.OK

        return self.data

    @cached_property
    def address(self) -> str:
        """Full address

        :return str
        """

        return f"{self.ip}:{self.port}"

    @property
    def device_info(self) -> DeviceInfo:
        """Device info.

        :return DeviceInfo: Service DeviceInfo.
        """

        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.address)},
            name=NAME,
            manufacturer=MAINTAINER,
            sw_version=self.data.get(ATTR_DEVICE_SW_VERSION, None),
            configuration_url=f"{self.scheme}://{self.address}/",
        )

    def device_identifier(self, code: str) -> tuple[str, str]:
        """Return the device registry identifier of a virtual.

        The identifier is unique per LedFx address and virtual, so virtuals that
        share one physical device remain separate devices with their own names.

        :param code: str: Virtual id
        :return tuple[str, str]: Device registry identifier
        """

        return (DOMAIN, f"{self.address}-{code}")

    async def _async_prepare(self, method: str, data: dict) -> None:
        """Prepare data.

        :param method: str
        :param data: dict
        """

        action = getattr(self, f"_async_prepare_{method}")

        if action is not None:
            await action(data)

    async def _async_prepare_info(self, data: dict) -> None:
        """Prepare info.

        :param data: dict
        """

        response: dict = await self.client.info()

        if response.get("version"):
            data[ATTR_DEVICE_SW_VERSION] = str(response["version"])

    async def _async_prepare_colors(self, data: dict) -> None:
        """Prepare colors.

        :param data: dict
        """

        if self.version != Version.V2:
            return

        response: dict = await self.client.colors()

        colors: dict = {}
        gradients: dict = {}
        if "colors" in response:
            if "builtin" in response["colors"]:
                colors |= response["colors"]["builtin"]
            if "user" in response["colors"]:
                colors |= response["colors"]["user"]

        if "gradients" in response:
            if "builtin" in response["gradients"]:
                gradients |= response["gradients"]["builtin"]
            if "user" in response["gradients"]:
                gradients |= response["gradients"]["user"]

        self.colors = colors
        self.gradients = gradients

    async def _async_prepare_schema(self, data: dict) -> None:
        """Prepare schema.

        :param data: dict
        """

        response: dict = await self.client.schema()

        if "effects" in response and response["effects"]:
            data[ATTR_LIGHT_EFFECTS] = sorted(list(response["effects"].keys()))

            for effect, fields in response["effects"].items():
                for code, parameter in (
                    fields.get("schema", {}).get("properties", {}).items()
                ):
                    if code == "brightness" or (
                        self.version == Version.V2 and code == "background_color"
                    ):
                        continue

                    if code in self.effect_properties:
                        if (
                            effect
                            not in self.effect_properties[code][ATTR_FIELD_EFFECTS]
                        ):
                            self.effect_properties[code][ATTR_FIELD_EFFECTS].append(
                                effect
                            )

                        continue

                    field, field_type, options = self._build_entity(code, parameter)

                    if field:
                        self.effect_properties[code] = {
                            ATTR_FIELD: field,
                            ATTR_FIELD_TYPE: field_type,
                            ATTR_FIELD_OPTIONS: options,
                            ATTR_FIELD_EFFECTS: [effect],
                        }

        if (
            "audio" in response
            and "schema" in response["audio"]
            and "properties" in response["audio"]["schema"]
            and "audio_device" in response["audio"]["schema"]["properties"]
            and "enum" in response["audio"]["schema"]["properties"]["audio_device"]
        ):
            data[ATTR_SELECT_AUDIO_INPUT_OPTIONS] = dict(
                response["audio"]["schema"]["properties"]["audio_device"]["enum"]
            )

            if (
                isinstance(data.get(ATTR_SELECT_AUDIO_INPUT), int)
                and str(data[ATTR_SELECT_AUDIO_INPUT])
                in data[ATTR_SELECT_AUDIO_INPUT_OPTIONS]
            ):
                data[ATTR_SELECT_AUDIO_INPUT] = data[ATTR_SELECT_AUDIO_INPUT_OPTIONS][
                    str(data[ATTR_SELECT_AUDIO_INPUT])
                ]

    def _build_entity(
        self, code: str, entity_data: dict
    ) -> tuple[EntityDescription | None, str | None, list | None]:
        """Build entity

        :param code: str: Code
        :param entity_data: dict: Entity data
        :return tuple[EntityDescription | None, str | None, list | None]
        """

        if entity_data.get("type") == "boolean":
            return (
                SwitchEntityDescription(
                    key=code,
                    name=entity_data.get("title", code.title()),
                    device_class=SwitchDeviceClass.SWITCH,
                    entity_category=EntityCategory.CONFIG,
                    entity_registry_enabled_default=False,
                ),
                "switch",
                None,
            )

        if entity_data.get("type") in ("integer", "number", "int"):
            minimum: float = float(entity_data.get("minimum", 0.0))
            maximum: float = float(entity_data.get("maximum", minimum + 100.0))
            is_integer: bool = entity_data.get("type") in ("integer", "int")

            return (
                NumberEntityDescription(
                    key=code,
                    name=entity_data.get("title", code.title()),
                    native_max_value=maximum,
                    native_min_value=minimum,
                    native_step=1.0
                    if is_integer
                    else (0.01 if maximum - minimum <= 1 else 0.1),
                    entity_category=EntityCategory.CONFIG,
                    entity_registry_enabled_default=False,
                ),
                "number",
                None,
            )

        if entity_data.get("type") in ("string", "color"):
            enum: list = entity_data.get("enum", [])
            field_type: str = "select"

            if entity_data.get("type") == "color":
                enum = list(
                    self.gradients.keys()
                    if entity_data.get("gradient", False)
                    else self.colors.keys()
                )
                field_type = "color"

            return (
                SelectEntityDescription(
                    key=code,
                    name=entity_data.get("title", code.title()),
                    entity_category=EntityCategory.CONFIG,
                    entity_registry_enabled_default=False,
                ),
                field_type,
                enum,
            )

        return None, None, None

    async def _async_prepare_config(self, data: dict) -> None:
        """Prepare config.

        :param data: dict
        """

        response: dict = await self.client.config()

        if "configuration_version" in response:
            self.version = Version.V2

            data.setdefault(
                ATTR_DEVICE_SW_VERSION, str(response["configuration_version"])
            )

            await self._async_prepare_config_v2(data, response)

            return

        if "config" in response:
            self.version = Version.V1

            await self._async_prepare_config_v1(data, response)

    async def _async_prepare_config_v1(self, data: dict, response: dict) -> None:
        """Prepare config V1.

        :param data: dict
        :param response: dict
        """

        config: dict = response["config"]

        if "audio" in config:
            for code, value in config["audio"].items():
                if code == "device_name":
                    data[ATTR_SELECT_AUDIO_INPUT] = value
                elif code != "device_index":
                    self._prepare_audio_sensor(data, code, value)

        if config.get("default_presets"):
            data[ATTR_LIGHT_DEFAULT_PRESETS] = {
                effect: sorted(list(presets.keys()))
                for effect, presets in config["default_presets"].items()
            }

        if config.get("custom_presets"):
            data[ATTR_LIGHT_CUSTOM_PRESETS] = {
                effect: sorted(list(presets.keys()))
                for effect, presets in config["custom_presets"].items()
            }

    async def _async_prepare_config_v2(self, data: dict, response: dict) -> None:
        """Prepare config V2.

        :param data: dict
        :param response: dict
        """

        if "audio" in response:
            for code, value in response["audio"].items():
                if code == "audio_device":
                    try:
                        data[ATTR_SELECT_AUDIO_INPUT] = int(value)
                    except (TypeError, ValueError):
                        data.pop(ATTR_SELECT_AUDIO_INPUT, None)
                elif code not in ("device_index", "audio_device_name"):
                    self._prepare_audio_sensor(data, code, value)

        if response.get("ledfx_presets"):
            data[ATTR_LIGHT_DEFAULT_PRESETS] = {
                effect: sorted(list(presets.keys()))
                for effect, presets in response["ledfx_presets"].items()
            }

        if response.get("user_presets"):
            data[ATTR_LIGHT_CUSTOM_PRESETS] = {
                effect: sorted(list(presets.keys()))
                for effect, presets in response["user_presets"].items()
            }

    def _prepare_audio_sensor(self, data: dict, code: str, value: Any) -> None:
        """Store an audio setting and create a diagnostic sensor for it.

        :param data: dict
        :param code: str: Setting code
        :param value: Any: Setting value
        """

        data[code] = value

        if code in self.sensors:
            return

        is_numeric: bool = isinstance(value, (int, float)) and not isinstance(
            value, bool
        )

        self.sensors[code] = LedFxEntityDescription(
            description=SensorEntityDescription(
                key=code,
                name=code.replace("_", " ").title(),
                state_class=SensorStateClass.MEASUREMENT if is_numeric else None,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
            device_info=self.device_info,
        )

        if self.new_sensor_callback:
            async_dispatcher_send(self.hass, SIGNAL_NEW_SENSOR, self.sensors[code])

    async def _async_prepare_virtuals(self, data: dict) -> None:
        """Prepare virtuals and the global pause state.

        :param data: dict
        """

        if self.version == Version.V1:
            try:
                response: dict = await self.client.virtuals()
            except LedFxError:
                self._virtuals = {}
                data[ATTR_PAUSED] = False

                return
        else:
            response = await self.client.virtuals()

        self._virtuals = response.get("virtuals") or {}
        data[ATTR_PAUSED] = bool(response.get("paused", False))

    async def _async_prepare_devices(self, data: dict) -> None:
        """Prepare devices.

        :param data: dict
        """

        response: dict = await self.client.devices()
        physical: dict = response.get("devices") or {}

        if self.version == Version.V1:
            if physical:
                self._build_device(data, physical)

            return

        devices: dict = {}
        for key, virtual in self._virtuals.items():
            devices[key] = virtual

            if (
                virtual.get("is_device")
                and virtual.get("is_device", "") in physical
            ):
                physical_device: dict = physical[virtual["is_device"]]

                devices[key]["config"] = dict(virtual.get("config", {})) | {
                    code: value
                    for code, value in physical_device.get("config", {}).items()
                    if code == "ip_address"
                }
                devices[key]["type"] = physical_device.get("type")

        if devices:
            self._build_device(data, devices)

    def _build_device(self, data: dict, devices: dict) -> None:
        """Build device

        :param data: dict
        :param devices: dict
        """

        for code, device in devices.items():
            # LedFx 2.x keeps the last effect on a virtual that was switched off,
            # and reports that through the `active` flag.
            data[f"{code}_{ATTR_LIGHT_STATE}"] = bool(
                device.get("effect") and device.get("active", True)
            )

            if data[f"{code}_{ATTR_LIGHT_STATE}"]:
                data |= {
                    f"{code}_{ATTR_LIGHT_BRIGHTNESS}": convert_brightness(
                        float(device["effect"].get("config", {}).get("brightness", 1)),
                        True,
                    ),
                    f"{code}_{ATTR_LIGHT_EFFECT}": device["effect"].get("type"),
                    f"{code}_{ATTR_LIGHT_EFFECT_CONFIG}": self._convert_effect_config(
                        dict(device["effect"].get("config", {}))
                    ),
                }
            else:
                data |= {
                    f"{code}_{ATTR_LIGHT_BRIGHTNESS}": 0,
                    f"{code}_{ATTR_LIGHT_EFFECT}": data.get(ATTR_LIGHT_EFFECTS, ["-"])[
                        0
                    ],
                    f"{code}_{ATTR_LIGHT_EFFECT_CONFIG}": {},
                }

            if self.version == Version.V2:
                data |= {
                    f"{code}_{ATTR_LIGHT_COLOR}": device["effect"]
                    .get("config", {})
                    .get("background_color")
                    if data[f"{code}_{ATTR_LIGHT_STATE}"]
                    else None
                }

            data[f"{code}_{ATTR_LIGHT_CONFIG}"] = {
                config: value
                for config, value in device.get("config", {}).items()
                if config not in ["icon_name", "name"]
            }

            device_config: dict = device.get("config", {})
            device_info: DeviceInfo = DeviceInfo(
                identifiers={self.device_identifier(code)},
                name=device_config.get("name", code),
                model=device_config.get("type") or device.get("type"),
                configuration_url=f"{self.scheme}://{self.address}/devices/{code}",
            )

            self._prepare_device_fields(code, device_info)

            if code in self.devices:
                continue

            icon: str = device_config.get("icon_name", "")

            self.devices[code] = LedFxEntityDescription(
                description=LightEntityDescription(
                    key=code,
                    name=None,
                    icon=icon if icon.startswith("mdi:") else "mdi:led-strip-variant",
                    entity_registry_enabled_default=True,
                ),
                type=ActionType.DEVICE,
                device_info=device_info,
            )

            if self.new_device_callback:
                async_dispatcher_send(self.hass, SIGNAL_NEW_DEVICE, self.devices[code])

    def _convert_effect_config(self, config: dict) -> dict:
        """Convert effect config

        :param config: dict
        :return dict
        """

        for code, value in config.items():
            if (
                code in self.effect_properties
                and self.effect_properties[code][ATTR_FIELD_TYPE] == "color"
            ):
                colors = self.colors if value in self.colors else self.gradients
                for name, color in colors.items():
                    if color == value:
                        config[code] = name

                        break

        return config

    def _prepare_device_fields(self, code: str, device_info: DeviceInfo) -> None:
        """Prepare device fields

        :param code: str: Device code
        :param device_info: DeviceInfo: Device Info object
        """

        for prop, info in self.effect_properties.items():
            field: LedFxEntityDescription | None = None
            signal: str | None = None

            # Dispatch on the recorded field type. `isinstance` against an entity
            # description class is unreliable: Home Assistant's frozen dataclass
            # compatibility layer returns instances of an internal subclass.
            field_type: str | None = info.get(ATTR_FIELD_TYPE)

            if field_type == "number":
                if f"{code}_{prop}" in self.numbers:
                    continue

                field = self.numbers[f"{code}_{prop}"] = LedFxEntityDescription(
                    description=info[ATTR_FIELD],
                    type=ActionType.DEVICE,
                    device_info=device_info,
                    device_code=code,
                    extra={
                        ATTR_FIELD_EFFECTS: sorted(info.get(ATTR_FIELD_EFFECTS, {})),
                        ATTR_FIELD_TYPE: info.get(ATTR_FIELD_TYPE),
                    },
                )

                if self.new_number_callback:
                    signal = SIGNAL_NEW_NUMBER
            elif field_type == "switch":
                if f"{code}_{prop}" in self.switches:
                    continue

                field = self.switches[f"{code}_{prop}"] = LedFxEntityDescription(
                    description=info[ATTR_FIELD],
                    type=ActionType.DEVICE,
                    device_info=device_info,
                    device_code=code,
                    extra={
                        ATTR_FIELD_EFFECTS: sorted(info.get(ATTR_FIELD_EFFECTS, {})),
                        ATTR_FIELD_TYPE: info.get(ATTR_FIELD_TYPE),
                    },
                )

                if self.new_switch_callback:
                    signal = SIGNAL_NEW_SWITCH
            elif field_type in ("select", "color"):
                if f"{code}_{prop}" in self.selects:
                    continue

                field = self.selects[f"{code}_{prop}"] = LedFxEntityDescription(
                    description=info[ATTR_FIELD],
                    type=ActionType.DEVICE,
                    device_info=device_info,
                    device_code=code,
                    extra={
                        ATTR_FIELD_EFFECTS: sorted(info.get(ATTR_FIELD_EFFECTS, [])),
                        ATTR_FIELD_OPTIONS: sorted(info.get(ATTR_FIELD_OPTIONS, [])),
                        ATTR_FIELD_TYPE: info.get(ATTR_FIELD_TYPE),
                    },
                )

                if self.new_select_callback:
                    signal = SIGNAL_NEW_SELECT

            if field is not None and signal is not None:
                async_dispatcher_send(
                    self.hass,
                    signal,
                    field,
                )

    async def _async_prepare_audio_devices(self, data: dict) -> None:
        """Prepare audio_devices.

        :param data: dict
        """

        if self.version != Version.V1:
            return

        response: dict = await self.client.audio_devices()

        if "devices" in response:
            data[ATTR_SELECT_AUDIO_INPUT_OPTIONS] = dict(response["devices"])

    async def _async_prepare_scenes(self, data: dict) -> None:
        """Prepare scenes.

        :param data: dict
        """

        response: dict = await self.client.scenes()

        if "scenes" in response and response["scenes"]:
            for code, scene in response["scenes"].items():
                if code in self.buttons:
                    continue

                self.buttons[code] = LedFxEntityDescription(
                    description=ButtonEntityDescription(
                        key=code,
                        name=scene["name"].title() if "name" in scene else code,
                        icon="mdi:image",
                        entity_registry_enabled_default=True,
                    ),
                    type=ActionType.SCENE,
                    device_info=self.device_info,
                )

                if self.new_button_callback:
                    async_dispatcher_send(
                        self.hass, SIGNAL_NEW_BUTTON, self.buttons[code]
                    )


@dataclass
class LedFxEntityDescription:
    """LedFx entity description."""

    description: EntityDescription
    device_info: DeviceInfo
    device_code: str | None = None
    type: ActionType = ActionType.DEFAULT
    extra: dict | None = None


def convert_brightness(brightness: float, is_reverse: bool = False) -> float:
    """Convert brightness

    LedFx uses a 0.0-1.0 range, Home Assistant uses 0-255.

    :param brightness: float
    :param is_reverse: bool: Convert from the LedFx range to the Home Assistant range
    :return: float
    """

    if is_reverse:
        return float(min(max(round(brightness * 255), 0), 255))

    return round(min(max(float(brightness) / 255, 0.0), 1.0), 2)


LedFxConfigEntry = ConfigEntry[LedFxUpdater]


@callback
def async_get_updater(hass: HomeAssistant, identifier: str) -> LedFxUpdater:
    """Return LedFxUpdater for a config entry id.

    :param hass: HomeAssistant
    :param identifier: str: Config entry id
    :return LedFxUpdater
    """

    entry: ConfigEntry | None = hass.config_entries.async_get_entry(identifier)

    if (
        entry is None
        or entry.domain != DOMAIN
        or not isinstance(getattr(entry, "runtime_data", None), LedFxUpdater)
    ):
        raise ValueError(f"Integration with identifier: {identifier} not found.")

    return entry.runtime_data
