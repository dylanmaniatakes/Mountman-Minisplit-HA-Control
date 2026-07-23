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
- ESPHome raw transmit lists use signed timing values:
  - positive values are marks, where the IR carrier is on
  - negative values are spaces, where the IR carrier is off
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeassistant.exceptions import HomeAssistantError

BYTES_PER_PACKET = 14

CAPTURED_TEMP_MAP_F: dict[int, tuple[int, int]] = {
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

HEAT_INFERRED_TEMP_MAP_F: dict[int, tuple[int, int]] = {
    # The captured table reaches 72F. Above that, the observed pattern continues
    # cleanly: byte 7 steps down every two Fahrenheit degrees, and byte 12
    # alternates between 0x80 and 0x84. These higher values are intentionally
    # marked as inferred in the docs until hardware captures confirm them.
    temp_f: (0x09 - ((temp_f - 72) // 2), 0x84 if temp_f % 2 else 0x80)
    for temp_f in range(73, 89)
}

HEAT_TEMP_MAP_F: dict[int, tuple[int, int]] = {
    **CAPTURED_TEMP_MAP_F,
    **HEAT_INFERRED_TEMP_MAP_F,
}

COOL_TEMP_MAP_F: dict[int, tuple[int, int]] = {
    # Cool captures are known through 71F. Live Home Assistant testing showed
    # that using the heat-style 72F/73F inferred fields made the mini-split show
    # one degree lower in cool mode. From 72F upward, cool mode therefore uses
    # the next step in the same observed field sequence.
    **{temp_f: CAPTURED_TEMP_MAP_F[temp_f] for temp_f in range(61, 72)},
    **{
        temp_f: (0x09 - ((temp_f + 1 - 72) // 2), 0x84 if (temp_f + 1) % 2 else 0x80)
        for temp_f in range(72, 89)
    },
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
    # ESPHome signed raw timings. Positive values are carrier-on marks and
    # negative values are carrier-off spaces.
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


def build_command_from_packet_hex(packet_hex: str) -> MountmanCommand:
    """Build a command from an exact 14-byte packet written as hex.

    This is a diagnostic path. It bypasses the high-level mode/temp/fan mapper
    so a captured packet from the research notes can be retransmitted exactly.
    The checksum is still validated because a typo in one byte can produce a
    packet that is difficult to reason about during hardware testing.
    """

    packet = parse_hex_packet(packet_hex)
    expected_checksum = sum(packet[:-1]) & 0xFF
    actual_checksum = packet[-1]

    if actual_checksum != expected_checksum:
        raise HomeAssistantError(
            "Mountman packet checksum mismatch: "
            f"expected 0x{expected_checksum:02X}, got 0x{actual_checksum:02X}."
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

    if temp_f < min(HEAT_TEMP_MAP_F) or temp_f > max(HEAT_TEMP_MAP_F):
        valid_range = f"{min(HEAT_TEMP_MAP_F)}-{max(HEAT_TEMP_MAP_F)}F"
        raise HomeAssistantError(
            f"Unsupported Mountman temperature: {temp_f}F. "
            f"Supported range is {valid_range}; some mode-specific values are inferred and still need captures."
        )

    if mode == "cool":
        temp_a, temp_b = _temperature_fields_for_mode(mode, temp_f)
        b5 = _cool_family_to_b5(family)
        b6 = 0x03
        b8 = _fan_to_b8(fan)
    elif mode == "heat":
        temp_a, temp_b = _temperature_fields_for_mode(mode, temp_f)
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
    """Convert packet bytes to ESPHome signed raw IR timings.

    ESPHome's `remote_transmitter.transmit_raw` action treats positive numbers
    as carrier-on marks and negative numbers as carrier-off spaces. A Flipper
    `.ir` file stores the same durations as positive numbers because the file
    format already knows the entries alternate mark/space/mark/space.
    """

    raw = [3100, -1500]
    for byte in packet:
        for bit_index in range(8):
            bit = (byte >> bit_index) & 1
            raw.append(560)
            raw.append(-(2060 if bit else 1040))
    raw.append(560)
    return raw


def parse_hex_packet(packet_hex: str) -> list[int]:
    """Parse a documentation-style hex packet string."""

    parts = re.findall(r"[0-9A-Fa-f]{2}", packet_hex)
    packet = [int(part, 16) for part in parts]
    if len(packet) != BYTES_PER_PACKET:
        raise HomeAssistantError(
            f"Mountman packets must be {BYTES_PER_PACKET} bytes; parsed {len(packet)} bytes from {packet_hex!r}."
        )
    return packet


def _cool_family_to_b5(family: str) -> int:
    """Convert the cool packet family name to byte 5."""

    if family == "normal":
        return 0x24
    if family == "alternate":
        return 0x64
    raise HomeAssistantError(f"Unsupported Mountman packet family: {family}")


def _temperature_fields_for_mode(mode: str, temp_f: int) -> tuple[int, int]:
    """Return the mode-specific temperature fields.

    Cool mode now has its own table because hardware testing showed that the
    heat/general inferred table is one degree low at 72F and above. Heat keeps
    the original table because heat-mode values above 72F have not been tested
    during summer.
    """

    if mode == "cool":
        return COOL_TEMP_MAP_F[temp_f]
    return HEAT_TEMP_MAP_F[temp_f]


def _fan_to_b8(fan: str) -> int:
    """Convert the fan name to the observed byte-8 value."""

    try:
        return B8_FAN[fan]
    except KeyError as exc:
        raise HomeAssistantError(f"Unsupported Mountman fan mode: {fan}") from exc
