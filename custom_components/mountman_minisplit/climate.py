"""Climate entity for Mountman Mini-Split IR."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_DEFAULT_FAN,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_PACKET_FAMILY,
    CONF_TRANSMITTER_ACTION,
    DEFAULT_FAN_MODE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_PACKET_FAMILY,
    DEFAULT_TARGET_TEMP,
    DEFAULT_TRANSMITTER_ACTION,
    DOMAIN,
    ENTITY_DOMAINS_THAT_NEED_TARGETS,
    MOUNTMAN_FAMILIES,
    MOUNTMAN_FANS,
    MOUNTMAN_MODES,
    SERVICE_SEND_STATE,
    SUPPORTED_MAX_TEMP,
    SUPPORTED_MIN_TEMP,
)
from .packet import MountmanCommand, build_command

_LOGGER = logging.getLogger(__name__)

HA_TO_MOUNTMAN_MODE = {
    HVACMode.OFF: "off",
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
}

HA_TO_MOUNTMAN_FAN = {
    FAN_AUTO: "auto",
    FAN_LOW: "low",
    FAN_MEDIUM: "medium",
    FAN_HIGH: "high",
    "offish": "offish",
}

MOUNTMAN_TO_HA_FAN = {value: key for key, value in HA_TO_MOUNTMAN_FAN.items()}

SEND_STATE_SCHEMA = {
    vol.Optional("mode"): vol.In(MOUNTMAN_MODES),
    vol.Optional("temp_f"): vol.All(vol.Coerce(int), vol.Range(min=SUPPORTED_MIN_TEMP, max=SUPPORTED_MAX_TEMP)),
    vol.Optional("fan"): vol.In(MOUNTMAN_FANS),
    vol.Optional("family"): vol.In(MOUNTMAN_FAMILIES),
    vol.Optional("b8_override"): vol.Coerce(int),
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Mountman climate entities from a config entry."""

    platform = entity_platform.async_get_current_platform()
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("entity_services_registered"):
        platform.async_register_entity_service(
            SERVICE_SEND_STATE,
            SEND_STATE_SCHEMA,
            "async_send_state_service",
        )
        domain_data["entity_services_registered"] = True

    async_add_entities([MountmanMiniSplitClimate(hass, entry)])


class MountmanMiniSplitClimate(ClimateEntity, RestoreEntity):
    """Assumed-state Mountman mini-split climate entity.

    Infrared is one-way. The entity reports the last state Home Assistant asked
    the mini-split to use; it cannot confirm the physical unit accepted the
    command unless a receiver/decoder is added later.
    """

    _attr_assumed_state = True
    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH, "offish"]

    def __init__(self, hass: HomeAssistant, entry) -> None:
        """Initialize the climate entity."""

        self.hass = hass
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="Mountman protocol research",
            model="Infrared mini-split bridge",
        )

        config = {**entry.data, **entry.options}
        self._transmitter_action = config.get(CONF_TRANSMITTER_ACTION, DEFAULT_TRANSMITTER_ACTION)
        self._packet_family = config.get(CONF_PACKET_FAMILY, DEFAULT_PACKET_FAMILY)
        self._default_fan = config.get(CONF_DEFAULT_FAN, DEFAULT_FAN_MODE)
        self._attr_min_temp = config.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        self._attr_max_temp = config.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = DEFAULT_TARGET_TEMP
        self._attr_fan_mode = MOUNTMAN_TO_HA_FAN.get(self._default_fan, FAN_HIGH)
        self._last_packet_hex: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return debugging attributes useful during protocol testing."""

        attrs: dict[str, Any] = {
            "transmitter_action": self._transmitter_action,
            "packet_family": self._packet_family,
        }
        if self._last_packet_hex:
            attrs["last_packet"] = self._last_packet_hex
        return attrs

    async def async_added_to_hass(self) -> None:
        """Restore the last assumed state after Home Assistant restarts."""

        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        if last_state.state in self._attr_hvac_modes:
            self._attr_hvac_mode = HVACMode(last_state.state)

        if (temperature := last_state.attributes.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = int(round(float(temperature)))

        if (fan_mode := last_state.attributes.get(ATTR_FAN_MODE)) in self._attr_fan_modes:
            self._attr_fan_mode = fan_mode

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature, optionally with a new HVAC mode."""

        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = int(round(float(temperature)))

        if (hvac_mode := kwargs.get("hvac_mode")) is not None:
            self._attr_hvac_mode = HVACMode(hvac_mode)

        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode and transmit the corresponding full-state packet."""

        self._attr_hvac_mode = hvac_mode
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode and retransmit the current full-state packet."""

        self._attr_fan_mode = fan_mode
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the climate entity on using cool mode as a conservative default."""

        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.COOL
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Transmit the captured Mountman power-off packet."""

        self._attr_hvac_mode = HVACMode.OFF
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_send_state_service(
        self,
        mode: str | None = None,
        temp_f: int | None = None,
        fan: str | None = None,
        family: str | None = None,
        b8_override: int | None = None,
    ) -> None:
        """Entity service for sending explicit test states.

        This is useful while validating candidates such as cool 72F with a
        byte-8 override.
        """

        await self._async_send_mountman_state(
            mode=mode or HA_TO_MOUNTMAN_MODE[self._attr_hvac_mode],
            temp_f=temp_f or int(self._attr_target_temperature),
            fan=fan or HA_TO_MOUNTMAN_FAN.get(self._attr_fan_mode, self._default_fan),
            family=family or self._packet_family,
            b8_override=b8_override,
        )
        self.async_write_ha_state()

    async def _async_send_current_state(self) -> None:
        """Transmit the entity's current assumed state."""

        await self._async_send_mountman_state(
            mode=HA_TO_MOUNTMAN_MODE[self._attr_hvac_mode],
            temp_f=int(self._attr_target_temperature),
            fan=HA_TO_MOUNTMAN_FAN.get(self._attr_fan_mode, self._default_fan),
            family=self._packet_family,
            b8_override=None,
        )

    async def _async_send_mountman_state(
        self,
        *,
        mode: str,
        temp_f: int,
        fan: str,
        family: str,
        b8_override: int | None,
    ) -> None:
        """Build the command and call the configured ESPHome action."""

        command = build_command(
            mode=mode,
            temp_f=temp_f,
            fan=fan,
            family=family,
            b8_override=b8_override,
        )
        self._last_packet_hex = command.packet_hex

        await self._async_call_action({"command": command.timings}, command)

    async def _async_call_action(self, service_data: dict[str, Any], command: MountmanCommand) -> None:
        """Call the configured Home Assistant action/service."""

        domain, service = _split_action(self._transmitter_action)
        _LOGGER.debug(
            "Sending Mountman packet %s through %s.%s",
            command.packet_hex,
            domain,
            service,
        )

        try:
            await self.hass.services.async_call(domain, service, service_data, blocking=True)
        except ServiceNotFound as exc:
            raise HomeAssistantError(
                f"Mountman transmitter action {self._transmitter_action!r} was not found. "
                "Confirm the ESPHome device is online and the action name is correct."
            ) from exc


def _split_action(action: str) -> tuple[str, str]:
    """Split a Home Assistant action string like `esphome.gym_send_raw`."""

    action = action.strip()
    if "." not in action:
        raise HomeAssistantError(f"Invalid Mountman transmitter action: {action}")
    domain, service = action.split(".", 1)
    if not domain or not service:
        raise HomeAssistantError(f"Invalid Mountman transmitter action: {action}")
    if domain in ENTITY_DOMAINS_THAT_NEED_TARGETS:
        raise HomeAssistantError(
            f"Mountman transmitter action {action!r} looks like an entity id or entity service. "
            "Use an ESPHome user-defined action such as 'esphome.gym_send_raw'. "
            "The factory firmware button entity, such as 'button.gym_gym_ir_send', cannot accept "
            "the raw timing array generated by this integration."
        )
    return domain, service
