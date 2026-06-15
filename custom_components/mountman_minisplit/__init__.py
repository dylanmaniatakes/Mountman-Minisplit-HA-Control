"""Mountman Mini-Split IR integration.

The integration creates an assumed-state Home Assistant climate entity for a
Mountman mini-split controlled over infrared. The HA side builds the Mountman
packet and raw timing list, then calls an ESPHome action to transmit it.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MAX_TEMP, DEFAULT_MAX_TEMP, DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Mountman Mini-Split IR config entry."""

    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Mountman Mini-Split IR config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries when protocol support expands.

    Version 1 used 72F as the default maximum because captures only reached 72F.
    Version 2 keeps the captured values but also allows the inferred 73-88F
    temperature map. Existing users who accepted the old default should get the
    expanded test range automatically after updating.
    """

    if entry.version != 1:
        return True

    data = dict(entry.data)
    options = dict(entry.options)

    if data.get(CONF_MAX_TEMP) == 72:
        data[CONF_MAX_TEMP] = DEFAULT_MAX_TEMP

    if options.get(CONF_MAX_TEMP) == 72:
        options[CONF_MAX_TEMP] = DEFAULT_MAX_TEMP

    hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entity when options such as the ESPHome action name change."""

    await hass.config_entries.async_reload(entry.entry_id)
