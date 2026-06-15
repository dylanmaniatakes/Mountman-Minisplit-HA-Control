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

    async def async_step_user(self, user_input: dict | None = None):
        """Create the integration from the Home Assistant UI."""

        if user_input is not None:
            action = user_input[CONF_TRANSMITTER_ACTION].strip()
            if "." not in action:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_user_schema(user_input),
                    errors={CONF_TRANSMITTER_ACTION: "invalid_action"},
                )

            await self.async_set_unique_id(action)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(step_id="user", data_schema=_user_schema())


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
