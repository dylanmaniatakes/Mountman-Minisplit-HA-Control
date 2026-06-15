"""Config flow for Mountman Mini-Split IR."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import (
    CONF_DEFAULT_FAN,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_PACKET_FAMILY,
    CONF_TRANSMITTER_ACTION,
    DEFAULT_FAN_MODE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_NAME,
    DEFAULT_PACKET_FAMILY,
    DEFAULT_TRANSMITTER_ACTION,
    DOMAIN,
    MOUNTMAN_FAMILIES,
    MOUNTMAN_FANS,
)


class MountmanMiniSplitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mountman Mini-Split IR."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Create an options flow for changing test-time settings later."""

        return MountmanMiniSplitOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict | None = None):
        """Create the integration from the Home Assistant UI."""

        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            if not _action_looks_valid(user_input[CONF_TRANSMITTER_ACTION]):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_user_schema(user_input),
                    errors={CONF_TRANSMITTER_ACTION: "invalid_action"},
                )

            await self.async_set_unique_id(action)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(step_id="user", data_schema=_user_schema())


class MountmanMiniSplitOptionsFlow(config_entries.OptionsFlow):
    """Let users tune transmitter and protocol defaults after setup.

    This is especially useful while testing ESPHome firmware. The ESPHome action
    name is based on the node name, so changing the node from `gym` to
    `gymircontroller` also changes the action Home Assistant must call.
    """

    def __init__(self, config_entry) -> None:
        """Store the config entry being edited."""

        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Show and save editable integration options."""

        defaults = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            if not _action_looks_valid(user_input[CONF_TRANSMITTER_ACTION]):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema({**defaults, **user_input}),
                    errors={CONF_TRANSMITTER_ACTION: "invalid_action"},
                )

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=_options_schema(defaults))


def _user_schema(defaults: dict | None = None) -> vol.Schema:
    """Return the config-flow form schema."""

    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_TRANSMITTER_ACTION,
                default=defaults.get(CONF_TRANSMITTER_ACTION, DEFAULT_TRANSMITTER_ACTION),
            ): str,
            vol.Required(
                CONF_PACKET_FAMILY,
                default=defaults.get(CONF_PACKET_FAMILY, DEFAULT_PACKET_FAMILY),
            ): vol.In(MOUNTMAN_FAMILIES),
            vol.Required(
                CONF_DEFAULT_FAN,
                default=defaults.get(CONF_DEFAULT_FAN, DEFAULT_FAN_MODE),
            ): vol.In(MOUNTMAN_FANS),
            vol.Required(CONF_MIN_TEMP, default=defaults.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)): int,
            vol.Required(CONF_MAX_TEMP, default=defaults.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)): int,
        }
    )


def _options_schema(defaults: dict) -> vol.Schema:
    """Return the options form schema.

    The display name stays in the original config entry because changing entity
    names safely is better handled by Home Assistant's entity registry UI. The
    settings below are operational defaults that can be changed as testing
    reveals the correct ESPHome action name and packet family.
    """

    return vol.Schema(
        {
            vol.Required(
                CONF_TRANSMITTER_ACTION,
                default=defaults.get(CONF_TRANSMITTER_ACTION, DEFAULT_TRANSMITTER_ACTION),
            ): str,
            vol.Required(
                CONF_PACKET_FAMILY,
                default=defaults.get(CONF_PACKET_FAMILY, DEFAULT_PACKET_FAMILY),
            ): vol.In(MOUNTMAN_FAMILIES),
            vol.Required(
                CONF_DEFAULT_FAN,
                default=defaults.get(CONF_DEFAULT_FAN, DEFAULT_FAN_MODE),
            ): vol.In(MOUNTMAN_FANS),
            vol.Required(CONF_MIN_TEMP, default=defaults.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)): int,
            vol.Required(CONF_MAX_TEMP, default=defaults.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)): int,
        }
    )


def _action_looks_valid(action: str) -> bool:
    """Return whether a Home Assistant action name has `domain.service` shape."""

    domain, separator, service = action.strip().partition(".")
    return bool(domain and separator and service)


def _normalize_user_input(user_input: dict) -> dict:
    """Trim fields where invisible spaces would create hard-to-find mistakes."""

    normalized = dict(user_input)
    normalized[CONF_TRANSMITTER_ACTION] = normalized[CONF_TRANSMITTER_ACTION].strip()
    return normalized
