# LedFX for Home Assistant
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![CodeQL](https://img.shields.io/badge/CODEQL-Passing-30C854.svg?style=for-the-badge)](https://github.com/dmamontov/hass-miwifi/actions?query=CodeQL)
[![Telegram](https://img.shields.io/badge/Telegram-channel-34ABDF.svg?style=for-the-badge)](https://t.me/hass_mamontov_tech)

Component for deep integration [LedFx](https://github.com/LedFx/LedFx) from [Home Assistant](https://www.home-assistant.io/).

## Requirements
* Home Assistant 2025.1.0 or later. Tested against 2025.1, 2026.2, 2026.11 and the 2026.12 beta.
* LedFx version >= [0.10.7](https://github.com/LedFx/LedFx/releases/tag/v0.10.7). The integration reads the configuration version from `/api/config` and uses the 0.10.x API or the 2.x API accordingly. Verified against the LedFx 2.2.1 source.

## Important information
* ❗ Effect controls (number, switch, select) are disabled by default. They must be enabled manually.
* ❗ Controls (number, switch, select) if enabled, have the status `UNAVAILABLE` by default. After enabling the effect on the device, the status will be changed by those that are supported by this effect.

## More info

- [Install](https://github.com/dmamontov/hass-ledfx/wiki/Install)
- [Config](https://github.com/dmamontov/hass-ledfx/wiki/Config)
- [Entities](https://github.com/dmamontov/hass-ledfx/wiki/Entities)
- [Performance](https://github.com/dmamontov/hass-ledfx/wiki/Performance)
- [Diagnostics](https://github.com/dmamontov/hass-ledfx/wiki/Diagnostics)
- [FAQ](https://github.com/dmamontov/hass-ledfx/wiki/FAQ)

## Install
The easiest way to install the LedFx integration is with [HACS](https://hacs.xyz/). First install [HACS](https://hacs.xyz/) if you don’t have it yet. After installation you can find this integration in the [HACS](https://hacs.xyz/) store under integrations.

Alternatively, you can install it manually. Just copy and paste the content of the hass-ledfx/custom_components folder in your config/custom_components directory. As example, you will get the sensor.py file in the following path: /config/custom_components/ledfx/sensor.py. The disadvantage of a manual installation is that you won’t be notified about updates.

## Config
**Via GUI**

`Settings` > `Integrations` > `Plus` > `LedFx`

To connect, enter the ip address and port. And also if you use basic auth, enter the user and password.

**HTTPS:** Enable `Use HTTPS` when LedFx sits behind a TLS reverse proxy. Entering `https://` before the address enables it as well, and `http://` disables it. Existing entries keep using HTTP.

`Verify the HTTPS certificate` is enabled by default. Disable it only for a self-signed certificate.

**Host names:** LedFx answers a request only when its `Host` header is an IP address, a local name, or an entry in `allowed_hosts` in the LedFx `config.yaml`. LedFx returns 403 for any other name, and the integration reports that as a rejected request. Add the DNS name of a reverse proxy to `allowed_hosts`.

❗ Via YAML (legacy way) not supported

## LedFx settings

LedFx configuration version 2 reports further settings. The integration creates an entity only for a setting that LedFx reports.

| Entity | Type | Effect |
|---|---|---|
| Startup scene | select | Sets `startup_scene_id`. LedFx activates that scene when it starts. `None` activates no scene. |
| Startup playlist | select | Sets `startup_playlist_id`. LedFx starts that playlist when it starts. `None` starts no playlist. |

Neither startup setting restarts LedFx.

## Performance
![](/images/performance.gif)

1. Install [lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities) from HACS
2. Install [light-entity-card](https://github.com/ljmerza/light-entity-card) from HACS
3. Add new Lovelace card before that replacing `device`: [example](https://gist.github.com/dmamontov/34d252351d9eda98f53b2d6180771f12)

## Attribution
The integration originates from [dmamontov/hass-ledfx](https://github.com/dmamontov/hass-ledfx). The direct line of descent runs from the upstream to DeKaN/hass-ledfx and then to Anto79-ops/hass-ledfx. The bacwolf and Gurutasker forks branch from the upstream, and no commits from them appear in this repository's history. The forks listed are those created before Anto79-ops/hass-ledfx. Their dates are GitHub fork creation dates. The `LICENSE` file, Apache License 2.0, is unchanged.

| Date | Repository | Maintainer | Event |
|---|---|---|---|
| 2021-12-14 | [dmamontov/hass-ledfx](https://github.com/dmamontov/hass-ledfx) | Dmitry Mamontov | Upstream repository created. |
| 2022-08-23 | [bacwolf/hass-ledfx](https://github.com/bacwolf/hass-ledfx) | bacwolf | Fork created. |
| 2023-03-14 | dmamontov/hass-ledfx | Dmitry Mamontov | Version 3.0.0 merged ([PR #20](https://github.com/dmamontov/hass-ledfx/pull/20)). |
| 2023-07-15 | dmamontov/hass-ledfx | Guillaume Duveau (guix77) | Global play/pause proposed ([PR #24](https://github.com/dmamontov/hass-ledfx/pull/24)). Not merged upstream. |
| 2023-10-07 | [Gurutasker/hass-ledfx](https://github.com/Gurutasker/hass-ledfx) | Gurutasker | Fork created. |
| 2023-11-18 | [DeKaN/hass-ledfx](https://github.com/DeKaN/hass-ledfx) | Dmitriy (DeKaN) | Fork created. The same day adds Home Assistant 2023.11 compatibility and the play/pause code. |
| 2024-02-28 | DeKaN/hass-ledfx | Dmitriy (DeKaN) | Deprecation warning fixed. |
| 2025-01-04 | DeKaN/hass-ledfx | Dmitriy (DeKaN) | Deprecations fixed. |
| 2025-10-13 | [Anto79-ops/hass-ledfx](https://github.com/Anto79-ops/hass-ledfx) | Anto79-ops | Fork of DeKaN/hass-ledfx created. Carries an `__init__.py` update proposed as [PR #1](https://github.com/DeKaN/hass-ledfx/pull/1), not merged upstream. |
| 2026-11-26 | This fork | Current maintainer | Adapted for Home Assistant 2026.11 and 2026.12 and for LedFx 2.x. The commit history records each change. |

The play/pause code is attributed to PR #24 because the commit that added it, `7c65830`, reads "Add play/pause from PR to origin". PR #24 is the only play/pause pull request on the upstream.
