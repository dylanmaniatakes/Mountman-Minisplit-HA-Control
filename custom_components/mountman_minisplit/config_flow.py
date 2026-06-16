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
    CONF_REPEAT_COUNT,
    CONF_REPEAT_DELAY_MS,
    CONF_TRANSMITTER_ACTION,
    DEFAULT_FAN_MODE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_NAME,
    DEFAULT_PACKET_FAMILY,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_REPEAT_DELAY_MS,
    DEFAULT_TRANSMITTER_ACTION,
    DOMAIN,
    ENTITY_DOMAINS_THAT_NEED_TARGETS,
    MOUNTMAN_FAMILIES,
    MOUNTMAN_FANS,
    SUPPORTED_MAX_TEMP,
    SUPPORTED_MIN_TEMP,
)


class MountmanMiniSplitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mountman Mini-Split IR."""

    VERSION = 2

    @staticmethod
    def async_get_options_flow(config_entry):
        """Create an options flow for changing test-time settings later."""

        return MountmanMiniSplitOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict | None = None):
        """Create the integration from the Home Assistant UI."""

        if user_input is not None:
            user_input = _normalize_user_input(user_input)
            action_error = _transmitter_action_error(user_input[CONF_TRANSMITTER_ACTION])
            if action_error:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_user_schema(user_input),
                    errors={CONF_TRANSMITTER_ACTION: action_error},
                )

            await self.async_set_unique_id(user_input[CONF_TRANSMITTER_ACTION])
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
            action_error = _transmitter_action_error(user_input[CONF_TRANSMITTER_ACTION])
            if action_error:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema({**defaults, **user_input}),
                    errors={CONF_TRANSMITTER_ACTION: action_error},
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
            vol.Required(CONF_MIN_TEMP, default=defaults.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)): vol.All(
                vol.Coerce(int), vol.Range(min=SUPPORTED_MIN_TEMP, max=SUPPORTED_MAX_TEMP)
            ),
            vol.Required(CONF_MAX_TEMP, default=defaults.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)): vol.All(
                vol.Coerce(int), vol.Range(min=SUPPORTED_MIN_TEMP, max=SUPPORTED_MAX_TEMP)
            ),
            vol.Required(CONF_REPEAT_COUNT, default=defaults.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=5)
            ),
            vol.Required(
                CONF_REPEAT_DELAY_MS,
                default=defaults.get(CONF_REPEAT_DELAY_MS, DEFAULT_REPEAT_DELAY_MS),
            ): vol.All(vol.Coerce(int), vol.Range(min=40, max=500)),
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
            vol.Required(CONF_MIN_TEMP, default=defaults.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)): vol.All(
                vol.Coerce(int), vol.Range(min=SUPPORTED_MIN_TEMP, max=SUPPORTED_MAX_TEMP)
            ),
            vol.Required(CONF_MAX_TEMP, default=defaults.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)): vol.All(
                vol.Coerce(int), vol.Range(min=SUPPORTED_MIN_TEMP, max=SUPPORTED_MAX_TEMP)
            ),
            vol.Required(CONF_REPEAT_COUNT, default=defaults.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=5)
            ),
            vol.Required(
                CONF_REPEAT_DELAY_MS,
                default=defaults.get(CONF_REPEAT_DELAY_MS, DEFAULT_REPEAT_DELAY_MS),
            ): vol.All(vol.Coerce(int), vol.Range(min=40, max=500)),
        }
    )


def _transmitter_action_error(action: str) -> str | None:
    """Return a config-flow error key when the transmitter action is unsafe."""

    domain, separator, service = action.strip().partition(".")
    if not (domain and separator and service):
        return "invalid_action"

    if domain in ENTITY_DOMAINS_THAT_NEED_TARGETS:
        return "entity_id_not_action"

    return None


def _normalize_user_input(user_input: dict) -> dict:
    """Trim fields where invisible spaces would create hard-to-find mistakes."""

    normalized = dict(user_input)
    normalized[CONF_TRANSMITTER_ACTION] = normalized[CONF_TRANSMITTER_ACTION].strip()
    return normalized
