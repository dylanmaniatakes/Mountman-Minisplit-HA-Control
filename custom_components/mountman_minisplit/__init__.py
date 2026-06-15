"""Mountman Mini-Split IR integration.

The integration creates an assumed-state Home Assistant climate entity for a
Mountman mini-split controlled over infrared. The HA side builds the Mountman
packet and raw timing list, then calls an ESPHome action to transmit it.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Mountman Mini-Split IR config entry."""

    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Mountman Mini-Split IR config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entity when options such as the ESPHome action name change."""

    await hass.config_entries.async_reload(entry.entry_id)
