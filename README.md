# Mountman Mini-Split IR Protocol Notes

Reverse-engineering notes, decoded packets, Flipper Zero raw IR files, and Home Assistant / ESPHome control guidance for a Mountman mini-split remote.

This repository is a public engineering notebook for one captured Mountman remote/unit pair. It is meant to help three groups of people:

- Home Assistant users trying to control a Mountman mini-split with an ESPHome IR transmitter.
- Flipper Zero users who only need a usable raw IR test file.
- Protocol researchers who want decoded packets, field notes, and small readable tools for continuing the reverse-engineering work.

The protocol map is early but usable. The captures indicate this is a mini-split/AC-style IR protocol: most useful commands are not simple "button only" commands. They are full-state packets that include mode, temperature, fan/swing-related bits, feature flags, and a checksum.

The Home Assistant Stuff is mostly vibe coded, I worked closely with the AI and I am slowly going through the code. The Protocol capture was all my work. 

## Current Verification Status

The Home Assistant climate entity path has been hardware-tested with a Seeed Studio XIAO IR Mate running the manual ESPHome raw-sender firmware. The verified path is:

```text
Home Assistant climate entity
  -> mountman_minisplit HACS integration
  -> ESPHome Native API raw send action
  -> XIAO IR Mate IR LEDs
  -> Mountman mini-split
```

This confirms the integration can generate and transmit working Mountman full-state packets through ESPHome. Some packet details still need more captures, especially heat-mode values above 72F, exact cool-family behavior, swing/fan packing, and special feature buttons.

Treat these findings as evidence for this captured remote/unit family, not as a universal Mountman specification. Mini-splits sold under the same brand can sometimes use different OEM remotes or protocol variants.

## Quick Start Paths

### Home Assistant / ESPHome

1. For a Seeed Studio XIAO IR Mate, read `home-assistant/SETUP.md`.
2. Provide a Home Assistant action that can transmit raw IR timing arrays at 38 kHz. The repo includes `esphome/xiao-ir-mate-raw-api.yaml` as a manual ESPHome firmware example, but HACS does not install or manage that file.
3. Install this repository in HACS as a custom integration.
4. Add the `Mountman Mini-Split IR` integration in Home Assistant and point it at the raw IR transmitter action.
5. Test a known captured command before building dashboards or automations.
6. Keep in mind that IR is one-way: Home Assistant will only know the state it last sent unless an IR receiver is also used.

ESPHome note: the raw sender is a Native API action, not a normal device entity. It is expected to appear under Home Assistant **Developer Tools > Actions** as something like `esphome.gym_send_raw`. The example firmware also includes a visible `Send Mountman Off Test` button so the IR LEDs can be smoke-tested from the ESPHome device page.

Do not configure the Mountman integration with an ESPHome device id or a button entity such as `button.gym_gym_ir_send`. The integration must call a raw-send action that accepts a `command` timing array. The Seeed factory firmware's Send button can replay a learned slot, but it cannot accept the generated Mountman packet.

ESPHome timing note: ESPHome raw transmit actions use signed timings. Marks are positive and spaces are negative, for example `3100, -1500, 560, -2060`. Flipper `.ir` files store the same mark/space durations as all-positive numbers because the file format already knows they alternate.

Hardware debugging note: if a Flipper can see ESPHome packets but the mini-split does not respond, use the `mountman_minisplit.send_packet` service to send the exact captured `Heat_72` packet:

```yaml
action: mountman_minisplit.send_packet
target:
  entity_id: climate.mountman_mini_split
data:
  packet_hex: "23 CB 26 01 00 24 01 09 05 00 00 00 80 C8"
```

That test bypasses the high-level climate mapping. If the exact packet works from Flipper but not from ESPHome, investigate emitter strength, aim, duty cycle, carrier accuracy, and ESPHome timing quality.

### Flipper Zero

1. Copy `flipper-tests/MOUNTMAN_FIRST_TESTS.ir` to the Flipper.
2. Test `MOUNTMAN_HEAT_72_CAPTURED` first because it came from a real capture.
3. Test both cool 72°F candidates and record which one the unit accepts.

### Protocol Research

1. Use `python3 tools/mountman_ir.py decode Remote2-updated.ir` to inspect decoded packets.
2. Compare decoded packets against the field map below.
3. Add new captures with names that describe the full remote screen state, such as `COOL_72_FANHIGH_SWINGON_ECOOFF`.

## Source captures

Captured with a Flipper Zero as raw IR:

- `Remote.ir` — first small capture set
- `Remote2.ir` — expanded capture set
- `Remote2-updated.ir` — expanded capture set with additional re-captures

## Current usable artifacts

This repo includes a small toolchain so the protocol notes are reproducible and testable:

- `tools/mountman_ir.py` decodes Flipper raw captures, builds Mountman packets, converts packets to raw timings, and writes Flipper `.ir` files.
- `flipper-tests/MOUNTMAN_FIRST_TESTS.ir` contains the first real-world test bundle: captured heat 72°F, both predicted cool 72°F candidates, and captured power off.
- `custom_components/mountman_minisplit/` is the HACS-installable Home Assistant custom integration. The climate entity path has been verified on the test mini-split.
- `esphome/xiao-ir-mate-raw-api.yaml` is a manual ESPHome firmware example for exposing a raw IR send action and a fixed OFF test button.
- `esphome/README.md` explains that firmware files are manual-use only and are not installed by HACS.
- `home-assistant/SETUP.md` explains the Seeed factory firmware path, HACS install path, and raw transmitter action requirement.
- `RELEASING.md` explains how to tag test releases so HACS can manage versions during protocol testing.
- `tests/test_mountman_ir.py` checks checksum math, packet generation, and capture decoding against known packets.

Code comments are intentionally explicit. Protocol assumptions, bit-order decisions, and test reasons should be explained in the codebase so the project remains approachable for readers with different experience levels.

Useful commands:

```bash
# Decode the expanded capture file into 14-byte packets.
python3 tools/mountman_ir.py decode Remote2-updated.ir

# Generate one packet as hex.
python3 tools/mountman_ir.py generate --mode heat --temp 72 --format packet

# Generate the normal-family predicted cool 72°F candidate as a Flipper file.
python3 tools/mountman_ir.py generate \
  --mode cool \
  --temp 72 \
  --family normal \
  --b8 0x05 \
  --format flipper \
  --name MOUNTMAN_COOL_72_NORMAL_B8_05 \
  --out flipper-tests/MOUNTMAN_COOL_72_NORMAL_B8_05.ir

# Recreate the first test bundle.
python3 tools/mountman_ir.py first-tests

# Run the local safety checks.
python3 -m unittest discover -v
```

Generator output formats:

- `packet` - 14-byte packet as hex.
- `raw` - Flipper-style all-positive raw timing list.
- `esphome-raw` - ESPHome `transmit_raw` timing list with negative space values.
- `flipper` - complete Flipper `.ir` file.
- `ha-yaml` - Home Assistant action payload for the ESPHome user-defined raw sender.

## Signal format

| Property | Value |
|---|---:|
| Carrier | 38 kHz |
| Duty cycle | ~33% in Flipper file |
| Encoding | Pulse-distance raw IR |
| Header | ~3100 µs mark, ~1500 µs space |
| Bit mark | ~560 µs |
| 0 bit space | ~1040 µs |
| 1 bit space | ~2060 µs |
| Payload | 112 bits / 14 bytes |
| Bit order | LSB-first per byte |
| Checksum | Byte 13 = `sum(bytes[0:13]) & 0xFF` |

The packet is 14 bytes:

```text
[0] [1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11] [12] [13]
23  CB  26  01  00  XX  XX  XX  XX  00  00   00   XX   checksum
```

Bytes 0-4 appear fixed for this remote/unit family:

```text
23 CB 26 01 00
```

## Checksum

The checksum is simple modulo-256 addition of the first 13 bytes.

```python
def mountman_checksum(packet_13_bytes: list[int]) -> int:
    return sum(packet_13_bytes) & 0xFF
```

Example:

```text
23 CB 26 01 00 24 03 0D 3D 00 00 00 84 = 0A
```

## Known decoded packets

### Basic power / eco / swing / fan captures

| Capture name | Packet |
|---|---|
| `Pow_off` | `23 CB 26 01 00 20 03 0D 3D 00 00 00 84 06` |
| `Power_on` | `23 CB 26 01 00 24 03 0D 3D 00 00 00 84 0A` |
| `Eco_on` | `23 CB 26 01 00 A4 03 0D 3D 00 00 00 84 8A` |
| `Swing_on` | `23 CB 26 01 00 24 03 0D 3D 00 00 00 84 0A` |
| `Swing_off_new` | `23 CB 26 01 00 24 03 0D 05 00 00 00 80 CE` |
| `Eco_off_new` | `23 CB 26 01 00 24 03 0D 05 00 00 00 80 CE` |
| `Fan_auto` | `23 CB 26 01 00 24 03 0D 38 00 00 00 84 05` |
| `Fan_low` | `23 CB 26 01 00 24 03 0D 3A 00 00 00 84 07` |
| `Fan_med` | `23 CB 26 01 00 24 03 0D 3B 00 00 00 84 08` |
| `Fan_high` | `23 CB 26 01 00 24 03 0D 3D 00 00 00 84 0A` |
| `Display` | `23 CB 26 01 00 64 03 0D 3D 00 00 00 84 4A` |
| `Turbo_on` | `23 CB 26 01 00 64 43 0F 3D 00 00 00 88 90` |
| `Turbo_off` | `23 CB 26 01 00 64 03 0D 3D 00 00 00 84 4A` |
| `Sleep_on` | `23 CB 26 01 00 64 03 0D 39 00 00 00 84 46` |
| `Anti_mildew_on` | `23 CB 26 01 00 64 23 0D 3D 00 00 00 84 6A` |
| `Anti_mildew_off` | `23 CB 26 01 00 64 03 0D 3D 00 00 00 84 4A` |

### Mode captures

| Capture name | Packet |
|---|---|
| `Mode_dehumid` | `23 CB 26 01 00 24 02 08 00 00 00 00 80 C3` |
| `Mode_fan_only` | `23 CB 26 01 00 24 07 08 05 00 00 00 80 CD` |
| `Mode_heat` | `23 CB 26 01 00 24 01 09 00 00 00 00 80 C3` |

### Cool temperature captures

The cool captures below were captured in the same high-fan/swing-on-ish family using byte 5 = `64`, byte 6 = `03`, byte 8 = `3D`.

| Temp | Packet |
|---:|---|
| 61°F | `23 CB 26 01 00 64 03 0F 3D 00 00 00 80 48` |
| 62°F | `23 CB 26 01 00 64 03 0F 3D 00 00 00 84 4C` |
| 63°F | `23 CB 26 01 00 64 03 0E 3D 00 00 00 80 47` |
| 64°F | `23 CB 26 01 00 64 03 0D 3D 00 00 00 80 46` |
| 65°F | `23 CB 26 01 00 64 03 0D 3D 00 00 00 84 4A` |
| 66°F | `23 CB 26 01 00 64 03 0C 3D 00 00 00 80 45` |
| 67°F | `23 CB 26 01 00 64 03 0C 3D 00 00 00 84 49` |
| 68°F | `23 CB 26 01 00 64 03 0B 3D 00 00 00 80 44` |
| 69°F | `23 CB 26 01 00 64 03 0B 3D 00 00 00 84 48` |
| 70°F | `23 CB 26 01 00 64 03 0A 3D 00 00 00 80 43` |
| 71°F | `23 CB 26 01 00 64 03 0A 3D 00 00 00 84 47` |

Additional re-captures using byte 5 = `24` confirm the same temperature fields:

| Capture | Packet |
|---|---|
| `Cool_63_new` | `23 CB 26 01 00 24 03 0E 3D 00 00 00 80 07` |
| `Cool_64_new` | `23 CB 26 01 00 24 03 0D 3D 00 00 00 80 06` |

Cool 72°F adjusted candidates:

Live Home Assistant testing showed the first 72F cool guess displayed as 71F on the mini-split. The current cool-mode generator therefore shifts the temperature field up one step at 72F and above.

| Candidate | Packet |
|---|---|
| Normal powered family, swing off-ish | `23 CB 26 01 00 24 03 09 05 00 00 00 84 CE` |
| Alternate cool/display family, high fan/swing on-ish | `23 CB 26 01 00 64 03 09 3D 00 00 00 84 46` |

### Heat temperature captures

| Temp | Packet |
|---:|---|
| 67°F | `23 CB 26 01 00 24 01 0C 05 00 00 00 84 CF` |
| 68°F | `23 CB 26 01 00 24 01 0B 05 00 00 00 80 CA` |
| 69°F | `23 CB 26 01 00 24 01 0B 05 00 00 00 84 CE` |
| 70°F | `23 CB 26 01 00 24 01 0A 05 00 00 00 80 C9` |
| 71°F | `23 CB 26 01 00 24 01 0A 05 00 00 00 84 CD` |
| 72°F | `23 CB 26 01 00 24 01 09 05 00 00 00 80 C8` |

## Field map, current best understanding

| Byte | Meaning / theory | Evidence |
|---:|---|---|
| 0 | Fixed device/protocol byte | Always `23` |
| 1 | Fixed device/protocol byte | Always `CB` |
| 2 | Fixed device/protocol byte | Always `26` |
| 3 | Frame/type byte | Usually `01`; `Mute_on_new` used `02` and may be special/invalid capture |
| 4 | Fixed/unused | Always `00` in valid captures |
| 5 | Power / feature family | `20` off, `24` normal on, `64` alternate cool/display/turbo/sleep family, `A4` eco on |
| 6 | Mode / feature | `03` cool/normal, `01` heat, `02` dry/dehumidify, `07` fan only, `43` turbo variant, `23` anti-mildew variant |
| 7 | Temperature high/coarse field | See temp table |
| 8 | Fan / swing / louver packed field | `38` auto, `3A` low, `3B` med, `3D` high; `05` appears swing-off-ish/default in heat/fan-only |
| 9 | Unknown | `00` in valid captures |
| 10 | Unknown | `00` in valid captures |
| 11 | Unknown | `00` in valid captures |
| 12 | Temperature low/fine field | Mostly `80` or `84`; paired with byte 7 |
| 13 | Checksum | Sum of bytes 0-12 modulo 256 |

## Temperature map

Temperature is split across byte 7 and byte 12. It is not a simple linear single-byte temperature field.

Base field sequence:

| Temp | Byte 7 | Byte 12 |
|---:|---:|---:|
| 61°F | `0F` | `80` |
| 62°F | `0F` | `84` |
| 63°F | `0E` | `80` |
| 64°F | `0D` | `80` |
| 65°F | `0D` | `84` |
| 66°F | `0C` | `80` |
| 67°F | `0C` | `84` |
| 68°F | `0B` | `80` |
| 69°F | `0B` | `84` |
| 70°F | `0A` | `80` |
| 71°F | `0A` | `84` |
| 72°F | `09` | `80` |
| 73°F | `09` | `84` inferred |
| 74°F | `08` | `80` inferred |
| ... | ... | ... |
| 88°F | `01` | `80` inferred |

Heat uses this sequence directly. Cool uses this sequence through 71F, then uses the next sequence entry at 72F and above because live testing showed the original 72F guess displayed as 71F on the unit.

```text
Cool 72F -> base 73F fields: 09 84
Cool 73F -> base 74F fields: 08 80
```

For the upper edge, cool 88F continues the same base sequence one more step.

A first-pass mapping for the base sequence:

```python
TEMP_MAP_F = {
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
    73: (0x09, 0x84), # inferred
    74: (0x08, 0x80), # inferred
    # Continue the same pattern through 88F.
}
```

## Python helpers

### Decode a Flipper `.ir` raw file into bytes

```python
from pathlib import Path
import re


def decode_flipper_ir(path: str):
    text = Path(path).read_text(errors="ignore")
    results = []

    for block in text.split("#"):
        name_match = re.search(r"^name:\\s*(.+)$", block, re.M)
        data_match = re.search(r"^data:\\s*(.+)$", block, re.M)
        if not name_match or not data_match:
            continue

        name = name_match.group(1).strip()
        timings = [int(x) for x in data_match.group(1).split()]

        # Header is roughly: 3100 mark, 1500 space.
        body = timings[2:]
        bits = []
        for i in range(0, min(len(body) - 1, 112 * 2), 2):
            mark = abs(body[i])
            space = abs(body[i + 1])
            bits.append(1 if space > 1500 else 0)

        if len(bits) < 112:
            results.append((name, None, False))
            continue

        packet = []
        for i in range(0, 112, 8):
            b = 0
            for bit_index, bit in enumerate(bits[i:i + 8]):
                b |= bit << bit_index
            packet.append(b)

        checksum_ok = (sum(packet[:-1]) & 0xFF) == packet[-1]
        results.append((name, packet, checksum_ok))

    return results


for name, packet, checksum_ok in decode_flipper_ir("Remote2.ir"):
    if packet:
        print(f"{name}: {' '.join(f'{b:02X}' for b in packet)} checksum={checksum_ok}")
    else:
        print(f"{name}: no decode")
```

### Build Flipper-style raw timings from a 14-byte packet

```python
def packet_to_raw_timings(packet: list[int]) -> list[int]:
    raw = [3100, 1500]
    for byte in packet:
        for bit_index in range(8):
            bit = (byte >> bit_index) & 1  # LSB-first
            raw.append(560)
            raw.append(2060 if bit else 1040)
    raw.append(560)
    return raw
```

### Build ESPHome signed raw timings from a 14-byte packet

```python
def packet_to_esphome_raw_timings(packet: list[int]) -> list[int]:
    """Return timings for ESPHome remote_transmitter.transmit_raw.

    ESPHome uses positive values for carrier-on marks and negative values for
    carrier-off spaces. Flipper files use all-positive values because their raw
    file format already knows the values alternate mark/space.
    """

    flipper_raw = packet_to_raw_timings(packet)
    return [value if index % 2 == 0 else -value for index, value in enumerate(flipper_raw)]
```

### Create a Flipper `.ir` file from a 13-byte payload

```python
from pathlib import Path


def checksum(packet_13_bytes: list[int]) -> int:
    return sum(packet_13_bytes) & 0xFF


def packet_to_raw_timings(packet: list[int]) -> list[int]:
    raw = [3100, 1500]
    for byte in packet:
        for bit_index in range(8):
            bit = (byte >> bit_index) & 1
            raw.append(560)
            raw.append(2060 if bit else 1040)
    raw.append(560)
    return raw


def write_flipper_ir(name: str, payload_13: list[int], out_path: str):
    packet = payload_13 + [checksum(payload_13)]
    raw = packet_to_raw_timings(packet)

    content = "\n".join([
        "Filetype: IR signals file",
        "Version: 1",
        "#",
        f"name: {name}",
        "type: raw",
        "frequency: 38000",
        "duty_cycle: 0.330000",
        "data: " + " ".join(map(str, raw)),
        "",
    ])
    Path(out_path).write_text(content)


# Example: predicted cool 72°F, normal powered family
write_flipper_ir(
    "MOUNTMAN_COOL_72_SWINGOFF_HIGH_V2",
    [0x23, 0xCB, 0x26, 0x01, 0x00, 0x24, 0x03, 0x09, 0x05, 0x00, 0x00, 0x00, 0x84],
    "MOUNTMAN_COOL_72_SWINGOFF_HIGH_V2.ir",
)
```

## Suggested capture naming convention

Use names that describe the **remote screen state**, not just the physical button pressed.

Good:

```text
COOL_68_FANAUTO_SWINGOFF_ECOOFF
COOL_72_FANHIGH_SWINGON_ECOOFF
HEAT_70_FANAUTO_SWINGOFF_ECOOFF
OFF_FROM_COOL_72
```

Bad:

```text
button1
tempup
mode2
capture_new_new_3
```

## Known uncertainties / TODO

- Confirm which adjusted 72°F cool candidate the unit accepts:
  - `23 CB 26 01 00 24 03 09 05 00 00 00 84 CE`
  - `23 CB 26 01 00 64 03 09 3D 00 00 00 84 46`
- Capture cool 72-88°F and heat 73-88°F to confirm or correct the mode-specific temperature maps.
- Re-test `Mute_on_new`; it decodes as `23 CB 26 02 00 20 00 00 00 00 00 00 00 45`, but does not match the normal checksum formula. It may be a special frame or a bad capture.
- Determine exactly how byte 5 `24` vs `64` should be interpreted. Current theory: `24` is normal on-state family and `64` is a display/turbo/sleep/alternate cool family.
- Determine if byte 8 fully represents fan and swing, or if some swing state is also packed into byte 5 or another feature byte.
- Confirm whether any modes besides cool need their own temperature offset.

## Project direction

Recommended approach for Home Assistant:

1. Use an ESPHome IR proxy / IR blaster as the transmitter.
2. Keep Home Assistant as the assumed state source of truth.
3. Generate a full packet for every desired state change.
4. Do not model this as simple `temp_up` / `temp_down` unless using a crude fallback.
5. Once the protocol is stable, wrap the packet generator in a Home Assistant script, ESPHome lambda, AppDaemon app, pyscript, or custom integration.
