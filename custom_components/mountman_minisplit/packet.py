"""Mountman packet and raw timing generation.

This module is intentionally small and dependency-free because it is the part of
the HACS integration most likely to change as real hardware testing improves.

Protocol summary:

- A Mountman command is a 14-byte packet.
- The first 13 bytes contain state fields.
- The last byte is `sum(first_13_bytes) & 0xFF`.
- Bits are transmitted LSB-first inside each byte.
- Raw IR uses pulse-distance timing at 38 kHz:
  - header: 3100 mark, 1500 space
  - bit mark: 560
  - zero space: 1040
  - one space: 2060
  - trailer mark: 560
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.exceptions import HomeAssistantError

TEMP_MAP_F: dict[int, tuple[int, int]] = {
    61: (0x0F, 0x80),
    62: (0x0F, 0x84),
    63: (0x0E, 0x80),
    64: (0x0D, 0x80),
    65: (0x0D, 0x84),
    66: (0x0C, 0x80),
    67: (0x0C, 0x84),
    68: (0x0B, 0x80),
    69: (0x0B, 0x84),
    70: (0x0A, 0x80),
    71: (0x0A, 0x84),
    72: (0x09, 0x80),
}

B8_FAN: dict[str, int] = {
    "auto": 0x38,
    "low": 0x3A,
    "medium": 0x3B,
    "high": 0x3D,
    "offish": 0x05,
}

PACKET_HEX_POWER_OFF = "23 CB 26 01 00 20 03 0D 3D 00 00 00 84 06"


@dataclass(frozen=True)
class MountmanCommand:
    """A generated Mountman command ready for transmission."""

    packet: list[int]
    timings: list[int]

    @property
    def packet_hex(self) -> str:
        """Return the packet in documentation-friendly hex form."""

        return " ".join(f"{byte:02X}" for byte in self.packet)


def build_command(
    *,
    mode: str,
    temp_f: int,
    fan: str,
    family: str,
    b8_override: int | None = None,
) -> MountmanCommand:
    """Build a Mountman packet and raw IR timing list.

    The `mode`, `fan`, and `family` names are intentionally plain strings
    because they map directly to Home Assistant services and ESPHome action
    data. Validation happens here so bad service calls fail before anything is
    transmitted.
    """

    packet = build_packet(
        mode=mode,
        temp_f=temp_f,
        fan=fan,
        family=family,
        b8_override=b8_override,
    )
    return MountmanCommand(packet=packet, timings=packet_to_raw_timings(packet))


def build_packet(
    *,
    mode: str,
    temp_f: int,
    fan: str,
    family: str,
    b8_override: int | None = None,
) -> list[int]:
    """Build one 14-byte Mountman packet."""

    mode = mode.lower()
    fan = fan.lower()
    family = family.lower()

    if mode == "off":
        return parse_hex_packet(PACKET_HEX_POWER_OFF)

    if temp_f not in TEMP_MAP_F:
        raise HomeAssistantError(f"Unsupported Mountman temperature: {temp_f}F")

    temp_a, temp_b = TEMP_MAP_F[temp_f]

    if mode == "cool":
        b5 = _cool_family_to_b5(family)
        b6 = 0x03
        b8 = _fan_to_b8(fan)
    elif mode == "heat":
        b5 = 0x24
        b6 = 0x01
        b8 = 0x05
    elif mode == "dry":
        b5 = 0x24
        b6 = 0x02
        temp_a = 0x08
        b8 = 0x00
        temp_b = 0x80
    elif mode == "fan_only":
        b5 = 0x24
        b6 = 0x07
        temp_a = 0x08
        b8 = 0x05
        temp_b = 0x80
    else:
        raise HomeAssistantError(f"Unsupported Mountman mode: {mode}")

    if b8_override is not None and b8_override >= 0:
        b8 = b8_override & 0xFF

    payload = [0x23, 0xCB, 0x26, 0x01, 0x00, b5, b6, temp_a, b8, 0x00, 0x00, 0x00, temp_b]
    return payload + [sum(payload) & 0xFF]


def packet_to_raw_timings(packet: list[int]) -> list[int]:
    """Convert packet bytes to ESPHome/Flipper raw IR timings."""

    raw = [3100, 1500]
    for byte in packet:
        for bit_index in range(8):
            bit = (byte >> bit_index) & 1
            raw.append(560)
            raw.append(2060 if bit else 1040)
    raw.append(560)
    return raw


def parse_hex_packet(packet_hex: str) -> list[int]:
    """Parse a documentation-style hex packet string."""

    return [int(part, 16) for part in packet_hex.split()]


def _cool_family_to_b5(family: str) -> int:
    """Convert the cool packet family name to byte 5."""

    if family == "normal":
        return 0x24
    if family == "alternate":
        return 0x64
    raise HomeAssistantError(f"Unsupported Mountman packet family: {family}")


def _fan_to_b8(fan: str) -> int:
    """Convert the fan name to the observed byte-8 value."""

    try:
        return B8_FAN[fan]
    except KeyError as exc:
        raise HomeAssistantError(f"Unsupported Mountman fan mode: {fan}") from exc
