#!/usr/bin/env python3
"""Decode and generate Mountman mini-split IR packets.

This module is both a small command-line tool and a readable protocol reference.
Mini-split IR protocols are a little different from simple TV-style remotes:
each button press normally sends a complete "current state" packet. That means
"set temperature to 72F in heat mode" is its own full packet containing mode,
temperature, fan/swing-ish fields, and a checksum.

The main jobs in this file are:

1. Decode Flipper Zero raw IR captures into 14-byte Mountman packets.
2. Build new packets from the field map in README.md.
3. Convert packets back into raw IR timings that Flipper, ESPHome, or Home
   Assistant can transmit.

When a constant or bit operation looks oddly specific, it probably came from the
captured raw files in this folder. Comments explain those assumptions so future
protocol changes are easier to reason about.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


# The Flipper captures identify this as a normal 38 kHz IR remote. The duty
# cycle controls how much of each carrier wave is "on" while transmitting. The
# original captures say 0.330000, so generated Flipper files keep that value.
FREQUENCY_HZ = 38_000
DUTY_CYCLE = 0.33

# Timing values are in microseconds. This protocol uses pulse-distance encoding:
# every bit starts with about the same length mark, then the following space is
# short for 0 and long for 1.
HEADER_MARK_US = 3100
HEADER_SPACE_US = 1500
BIT_MARK_US = 560
ZERO_SPACE_US = 1040
ONE_SPACE_US = 2060
TRAILER_MARK_US = 560

# Every decoded Mountman packet has 112 bits, which is 14 bytes. The last byte is
# the checksum, so most packet-building code works with 13 data bytes and then
# appends byte 14.
BITS_PER_PACKET = 112
BYTES_PER_PACKET = 14

# Real IR captures are never perfectly exact. Batteries, sensor distance, room
# lighting, and Flipper sampling jitter all move the timings around. These
# ranges are deliberately wide enough to find valid frames in messy captures,
# but narrow enough to ignore unrelated long gaps and noise.
HEADER_MARK_RANGE = (2500, 3600)
HEADER_SPACE_RANGE = (1200, 1900)
BIT_MARK_RANGE = (350, 800)
BIT_SPACE_RANGE = (750, 2400)

# A 0 space is roughly 1040 microseconds and a 1 space is roughly 2060
# microseconds. Anything at or above this midpoint is decoded as a 1.
BIT_ONE_THRESHOLD_US = 1500

# Temperature is split across byte 7 and byte 12. It is not a simple "temp =
# byte + offset" field. This table begins with values recovered from captures.
KNOWN_TEMP_MAP_F: dict[int, tuple[int, int]] = {
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

INFERRED_TEMP_MAP_F: dict[int, tuple[int, int]] = {
    # The known table shows byte 7 stepping down every two Fahrenheit degrees
    # while byte 12 alternates between 0x80 and 0x84. The 73-88F values below
    # continue that pattern so they can be tested from Home Assistant, but they
    # should be treated as predicted until captures confirm them.
    temp_f: (0x09 - ((temp_f - 72) // 2), 0x84 if temp_f % 2 else 0x80)
    for temp_f in range(73, 89)
}

TEMP_MAP_F: dict[int, tuple[int, int]] = {
    **KNOWN_TEMP_MAP_F,
    **INFERRED_TEMP_MAP_F,
}

# Byte 8 appears to pack fan and/or swing/louver state. The names here describe
# what was observed on the remote, not a guaranteed final protocol truth.
B8_FAN: dict[str, int] = {
    "auto": 0x38,
    "low": 0x3A,
    "medium": 0x3B,
    "high": 0x3D,
    "offish": 0x05,
}

# These are real packets decoded from captures. Keeping a few captured packets in
# code gives the generator a trustworthy baseline and makes the tests easier to
# understand.
CAPTURED_PACKET_HEX: dict[str, str] = {
    "pow_off": "23 CB 26 01 00 20 03 0D 3D 00 00 00 84 06",
    "power_on": "23 CB 26 01 00 24 03 0D 3D 00 00 00 84 0A",
    "heat_72": "23 CB 26 01 00 24 01 09 05 00 00 00 80 C8",
}

# This bundle is the recommended first hardware test because it mixes one known
# working captured command with the two unconfirmed cool-72 candidates. That
# makes it useful before investing in a full Home Assistant climate entity.
FIRST_TEST_PACKETS: tuple[tuple[str, str], ...] = (
    (
        "MOUNTMAN_HEAT_72_CAPTURED",
        CAPTURED_PACKET_HEX["heat_72"],
    ),
    (
        "MOUNTMAN_COOL_72_NORMAL_B8_05_PREDICTED",
        "23 CB 26 01 00 24 03 09 05 00 00 00 80 CA",
    ),
    (
        "MOUNTMAN_COOL_72_ALT_HIGH_PREDICTED",
        "23 CB 26 01 00 64 03 09 3D 00 00 00 80 42",
    ),
    (
        "MOUNTMAN_POWER_OFF_CAPTURED",
        CAPTURED_PACKET_HEX["pow_off"],
    ),
)


@dataclass(frozen=True)
class DecodeResult:
    """One packet found inside a Flipper raw IR signal block.

    A single Flipper "name:" block can contain junk before the useful frame, or
    even multiple Mountman-sized frames. `start_index` records where this packet
    started inside the raw timing list so weird captures can be investigated
    later instead of silently flattened.
    """

    name: str
    packet: list[int]
    checksum_ok: bool
    start_index: int
    frequency: int | None = None
    duty_cycle: float | None = None

    @property
    def packet_hex(self) -> str:
        """Return the decoded packet in the same human-readable form as README."""
        return packet_to_hex(self.packet)


def checksum(payload_13_bytes: Sequence[int]) -> int:
    """Calculate the Mountman checksum byte.

    The checksum is intentionally simple: add the first 13 bytes, then keep only
    the lowest 8 bits. `& 0xFF` is a common way to say "wrap around at 256".

    Example: if the sum is 0x10A, the checksum byte is 0x0A.
    """

    if len(payload_13_bytes) != BYTES_PER_PACKET - 1:
        raise ValueError(f"checksum expects 13 bytes, got {len(payload_13_bytes)}")
    return sum(payload_13_bytes) & 0xFF


def append_checksum(payload_13_bytes: Sequence[int]) -> list[int]:
    """Return a new 14-byte packet by appending the checksum byte."""

    payload = list(payload_13_bytes)
    return payload + [checksum(payload)]


def parse_hex_packet(value: str) -> list[int]:
    """Parse a packet written as hex text into integer byte values.

    This accepts strings like "23 CB 26 ..." and also tolerates punctuation
    between bytes. It is useful because the README, tests, and capture notes all
    use hex text for readability.
    """

    parts = re.findall(r"[0-9A-Fa-f]{2}", value)
    packet = [int(part, 16) for part in parts]
    if len(packet) != BYTES_PER_PACKET:
        raise ValueError(f"expected {BYTES_PER_PACKET} bytes, got {len(packet)} from {value!r}")
    return packet


def packet_to_hex(packet: Sequence[int]) -> str:
    """Format packet bytes as uppercase hex separated by spaces."""

    return " ".join(f"{byte:02X}" for byte in packet)


def packet_to_raw_timings(packet: Sequence[int]) -> list[int]:
    """Convert a 14-byte packet into Flipper-style raw IR timings.

    Flipper `.ir` files store raw IR as a list like:

        header mark, header space, bit mark, bit space, bit mark, bit space...

    All values are positive because the Flipper file format knows the numbers
    alternate mark/space/mark/space. ESPHome's `transmit_raw` action is
    different: ESPHome wants marks as positive values and spaces as negative
    values. Use `packet_to_esphome_raw_timings` for that format.

    The Mountman packet is encoded LSB-first inside each byte. LSB-first means
    "least significant bit first": bit 0 is transmitted before bit 1, bit 1
    before bit 2, and so on. This is why the loop below counts `bit_index` from
    0 to 7 instead of reading the byte from left to right.
    """

    if len(packet) != BYTES_PER_PACKET:
        raise ValueError(f"expected {BYTES_PER_PACKET} packet bytes, got {len(packet)}")

    raw = [HEADER_MARK_US, HEADER_SPACE_US]
    for byte in packet:
        for bit_index in range(8):
            # Shift the requested bit down to the ones place, then mask with 1.
            # For example, if bit_index is 3, `(byte >> 3) & 1` extracts bit 3.
            bit = (byte >> bit_index) & 1
            raw.append(BIT_MARK_US)
            raw.append(ONE_SPACE_US if bit else ZERO_SPACE_US)
    raw.append(TRAILER_MARK_US)
    return raw


def packet_to_esphome_raw_timings(packet: Sequence[int]) -> list[int]:
    """Convert a 14-byte packet into ESPHome signed raw IR timings.

    ESPHome uses the sign of each number to distinguish marks from spaces:

    - positive values mean carrier-on marks
    - negative values mean carrier-off spaces

    Sending Flipper-style all-positive timings to ESPHome produces visible IR
    LED activity, but the receiver sees one long carrier burst instead of a
    readable mark/space packet.
    """

    flipper_raw = packet_to_raw_timings(packet)
    return [value if index % 2 == 0 else -value for index, value in enumerate(flipper_raw)]


def raw_timings_to_packet(timings: Sequence[int], start_index: int = 0) -> list[int] | None:
    """Decode one Mountman packet from raw timings.

    `start_index` should point at the header mark. The function returns `None`
    instead of raising when the timings do not look like a complete packet. That
    makes it safe for `find_packets_in_timings` to scan through noisy captures
    looking for the real frame.
    """

    body_start = start_index + 2
    body_end = body_start + BITS_PER_PACKET * 2
    if body_end > len(timings):
        return None

    bits: list[int] = []
    for index in range(body_start, body_end, 2):
        mark = abs(timings[index])
        space = abs(timings[index + 1])
        if not _in_range(mark, BIT_MARK_RANGE) or not _in_range(space, BIT_SPACE_RANGE):
            return None
        # Pulse-distance decoding: the mark is mostly constant, and the space
        # length carries the bit value.
        bits.append(1 if space >= BIT_ONE_THRESHOLD_US else 0)

    packet: list[int] = []
    for byte_start in range(0, BITS_PER_PACKET, 8):
        byte = 0
        for bit_index, bit in enumerate(bits[byte_start:byte_start + 8]):
            # Rebuild each byte in the same LSB-first order used by the remote.
            byte |= bit << bit_index
        packet.append(byte)
    return packet


def find_packets_in_timings(timings: Sequence[int]) -> list[tuple[int, list[int]]]:
    """Find all Mountman-sized frames inside a raw timing list.

    Some captured buttons contain a clean packet starting at timing index 0.
    Others include odd leading timing bursts before the real packet. Instead of
    assuming the first number is always the header, this scans for anything that
    looks like the Mountman header and then tries to decode a full 112-bit frame
    from that point.
    """

    frames: list[tuple[int, list[int]]] = []
    last_packet_end = -1

    for index in range(0, max(0, len(timings) - 2)):
        if index < last_packet_end:
            continue
        mark = abs(timings[index])
        space = abs(timings[index + 1])
        if not (_in_range(mark, HEADER_MARK_RANGE) and _in_range(space, HEADER_SPACE_RANGE)):
            continue
        packet = raw_timings_to_packet(timings, index)
        if packet is None:
            continue
        frames.append((index, packet))
        # Once a packet has been accepted, skip over its body so overlapping
        # false positives inside the packet are not reported as extra frames.
        last_packet_end = index + 2 + BITS_PER_PACKET * 2

    return frames


def decode_flipper_file(path: str | Path) -> list[DecodeResult]:
    """Decode every Mountman-looking frame in a Flipper `.ir` file."""

    text = Path(path).read_text(errors="ignore")
    results: list[DecodeResult] = []

    for block in _iter_flipper_blocks(text):
        name = block.get("name")
        data = block.get("data")
        if not name or data is None:
            continue

        for start_index, packet in find_packets_in_timings(data):
            checksum_ok = (sum(packet[:-1]) & 0xFF) == packet[-1]
            results.append(
                DecodeResult(
                    name=name,
                    packet=packet,
                    checksum_ok=checksum_ok,
                    start_index=start_index,
                    frequency=block.get("frequency"),
                    duty_cycle=block.get("duty_cycle"),
                )
            )

    return results


def build_mountman_packet(
    *,
    mode: str,
    temp_f: int = 72,
    fan: str = "high",
    family: str = "normal",
    b8_override: int | None = None,
) -> list[int]:
    """Build a full 14-byte command packet from high-level settings.

    Mini-split remotes usually do not send "temp up" as a tiny command. They
    send the whole desired state. For example, changing to heat 72F sends a
    packet that includes power/mode family, mode, temp fields, fan/swing-ish
    field, and checksum.

    `family` is only used for cool mode right now:

    - normal -> byte 5 is 0x24
    - alternate -> byte 5 is 0x64

    `b8_override` exists for experiments. It forces byte 8 directly when
    testing swing/fan theories without adding a permanent named option.
    """

    mode = mode.lower()
    fan = fan.lower()
    family = family.lower()

    if mode == "off":
        # Off is currently returned as the exact captured off command. Once more
        # off captures exist, this may become state-dependent like the other
        # modes.
        return parse_hex_packet(CAPTURED_PACKET_HEX["pow_off"])

    if temp_f not in TEMP_MAP_F:
        valid = f"{min(TEMP_MAP_F)}-{max(TEMP_MAP_F)}"
        raise ValueError(f"temp_f must be in the known/predicted range {valid}, got {temp_f}")

    temp_a, temp_b = TEMP_MAP_F[temp_f]
    b8: int

    if mode == "cool":
        if family not in {"normal", "alternate"}:
            raise ValueError("family must be normal or alternate")
        # Byte 5 is still being learned. Captures show 0x24 for normal/on-state
        # cool commands and 0x64 for the alternate/display/turbo-ish family.
        b5 = 0x24 if family == "normal" else 0x64
        b6 = 0x03
        b8 = _fan_to_b8(fan)
    elif mode == "heat":
        b5 = 0x24
        b6 = 0x01
        b8 = 0x05
    elif mode == "dry":
        # The dry and fan-only captures use a fixed temp-looking byte 7 value
        # rather than the requested setpoint. That is why these modes override
        # temp_a/temp_b after the normal temperature lookup.
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
        raise ValueError(f"unsupported mode: {mode}")

    if b8_override is not None:
        # This is intentionally late so experiments can override the normal
        # fan/swing byte for any supported mode.
        b8 = b8_override

    payload = [0x23, 0xCB, 0x26, 0x01, 0x00, b5, b6, temp_a, b8, 0x00, 0x00, 0x00, temp_b]
    return append_checksum(payload)


def flipper_entry(name: str, packet: Sequence[int]) -> str:
    """Create one named raw IR entry in Flipper Zero `.ir` file format."""

    return "\n".join(
        [
            "#",
            f"name: {name}",
            "type: raw",
            f"frequency: {FREQUENCY_HZ}",
            f"duty_cycle: {DUTY_CYCLE:.6f}",
            "data: " + " ".join(str(value) for value in packet_to_raw_timings(packet)),
        ]
    )


def flipper_file(entries: Iterable[tuple[str, Sequence[int]]]) -> str:
    """Create a complete Flipper Zero `.ir` file from named packets."""

    body = "\n".join(flipper_entry(name, packet) for name, packet in entries)
    return f"Filetype: IR signals file\nVersion: 1\n{body}\n"


def first_test_flipper_file() -> str:
    """Build the recommended first hardware-test Flipper file."""

    entries = [(name, parse_hex_packet(packet_hex)) for name, packet_hex in FIRST_TEST_PACKETS]
    return flipper_file(entries)


def _fan_to_b8(fan: str) -> int:
    """Translate a readable fan name into the observed byte-8 value."""

    try:
        return B8_FAN[fan]
    except KeyError as exc:
        raise ValueError(f"fan must be one of {', '.join(B8_FAN)}, got {fan!r}") from exc


def _in_range(value: int | float, value_range: tuple[int, int]) -> bool:
    """Return True when a measured timing is inside an accepted range."""

    return value_range[0] <= value <= value_range[1]


def _iter_flipper_blocks(text: str) -> Iterable[dict[str, object]]:
    """Yield the useful fields from each Flipper `# ... data:` block.

    Flipper `.ir` files are simple text files. Each signal starts after a line
    containing `#`, then has fields such as `name:`, `frequency:`, `duty_cycle:`,
    and `data:`. This parser keeps only the fields this tool needs.
    """

    current: dict[str, object] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            if current:
                yield current
                current = {}
            continue
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "name":
            current["name"] = value
        elif key == "frequency":
            current["frequency"] = int(value)
        elif key == "duty_cycle":
            current["duty_cycle"] = float(value)
        elif key == "data":
            # Raw data is an alternating mark/space timing list measured in
            # microseconds.
            current["data"] = [int(part) for part in value.split()]

    if current:
        yield current


def _print_decode(args: argparse.Namespace) -> int:
    """CLI handler for `decode`."""

    results = decode_flipper_file(args.path)
    if args.json:
        payload = [asdict(result) | {"packet_hex": result.packet_hex} for result in results]
        print(json.dumps(payload, indent=2))
        return 0

    if not results:
        print(f"No decodable Mountman-sized frames found in {args.path}")
        return 1

    for result in results:
        status = "ok" if result.checksum_ok else "bad-checksum"
        print(f"{result.name}: {result.packet_hex} checksum={status} start={result.start_index}")
    return 0


def _print_generate(args: argparse.Namespace) -> int:
    """CLI handler for `generate`."""

    packet = build_mountman_packet(
        mode=args.mode,
        temp_f=args.temp,
        fan=args.fan,
        family=args.family,
        b8_override=args.b8,
    )

    if args.output_format == "packet":
        content = packet_to_hex(packet) + "\n"
    elif args.output_format == "raw":
        content = " ".join(str(value) for value in packet_to_raw_timings(packet)) + "\n"
    elif args.output_format == "esphome-raw":
        content = " ".join(str(value) for value in packet_to_esphome_raw_timings(packet)) + "\n"
    elif args.output_format == "flipper":
        content = flipper_file([(args.name, packet)])
    elif args.output_format == "ha-yaml":
        content = _ha_yaml(packet)
    else:
        raise AssertionError(args.output_format)

    if args.out:
        Path(args.out).write_text(content)
        print(f"Wrote {args.out}")
    else:
        print(content, end="")
    return 0


def _write_first_tests(args: argparse.Namespace) -> int:
    """CLI handler for `first-tests`."""

    Path(args.out).write_text(first_test_flipper_file())
    print(f"Wrote {args.out}")
    return 0


def _ha_yaml(packet: Sequence[int]) -> str:
    """Render a Home Assistant-style raw IR action payload.

    The action name is the repo's default ESPHome node/action pairing. If a user
    changes the ESPHome node name, the action name changes too. The timing
    values are the important piece: they are ESPHome signed timings where spaces
    are negative.
    """

    timings = packet_to_esphome_raw_timings(packet)
    timing_lines = "\n".join(f"    - {value}" for value in timings)
    return (
        "action: esphome.gym_send_raw\n"
        "data:\n"
        "  command:\n"
        f"{timing_lines}\n"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for this script."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    decode = subparsers.add_parser("decode", help="Decode Flipper raw IR captures")
    decode.add_argument("path")
    decode.add_argument("--json", action="store_true")
    decode.set_defaults(func=_print_decode)

    generate = subparsers.add_parser("generate", help="Generate a packet or raw timing payload")
    generate.add_argument("--mode", choices=["cool", "heat", "dry", "fan_only", "off"], default="cool")
    generate.add_argument("--temp", type=int, default=72)
    generate.add_argument("--fan", choices=sorted(B8_FAN), default="high")
    generate.add_argument("--family", choices=["normal", "alternate"], default="normal")
    generate.add_argument("--b8", type=lambda value: int(value, 0), help="Override byte 8, e.g. 0x05")
    generate.add_argument("--name", default="MOUNTMAN_GENERATED")
    generate.add_argument(
        "--format",
        dest="output_format",
        choices=["packet", "raw", "esphome-raw", "flipper", "ha-yaml"],
        default="packet",
    )
    generate.add_argument("--out")
    generate.set_defaults(func=_print_generate)

    first_tests = subparsers.add_parser("first-tests", help="Write the first Flipper test bundle")
    first_tests.add_argument("--out", default="flipper-tests/MOUNTMAN_FIRST_TESTS.ir")
    first_tests.set_defaults(func=_write_first_tests)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line tool and return a shell-friendly exit code."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
