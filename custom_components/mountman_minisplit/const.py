"""Constants for the Mountman Mini-Split IR integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "mountman_minisplit"
PLATFORMS = [Platform.CLIMATE]

DEFAULT_NAME = "Mountman Mini-Split"
DEFAULT_TRANSMITTER_ACTION = "esphome.gym_send_raw"
DEFAULT_PACKET_FAMILY = "normal"
DEFAULT_FAN_MODE = "high"
DEFAULT_TARGET_TEMP = 72
DEFAULT_MIN_TEMP = 61
DEFAULT_MAX_TEMP = 72

CONF_TRANSMITTER_ACTION = "transmitter_action"
CONF_PACKET_FAMILY = "packet_family"
CONF_DEFAULT_FAN = "default_fan"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"

MOUNTMAN_MODES = ["off", "cool", "heat", "dry", "fan_only"]
MOUNTMAN_FANS = ["auto", "low", "medium", "high", "offish"]
MOUNTMAN_FAMILIES = ["normal", "alternate"]

ENTITY_DOMAINS_THAT_NEED_TARGETS = {
    "binary_sensor",
    "button",
    "climate",
    "fan",
    "input_boolean",
    "input_button",
    "input_number",
    "input_select",
    "light",
    "number",
    "remote",
    "select",
    "sensor",
    "switch",
    "text",
}

SERVICE_SEND_STATE = "send_state"
