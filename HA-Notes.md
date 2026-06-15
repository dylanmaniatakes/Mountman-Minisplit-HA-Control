# HA-Notes: Mountman Mini-Split via Home Assistant + ESPHome IR Proxy

These notes describe a practical path to control the Mountman mini-split from Home Assistant using an ESPHome-based infrared proxy / transmitter.

Status: protocol mapping is partially reverse engineered and good enough to begin testing. Full climate control still needs more captures for untested temperatures/features.

## Current platform context

Home Assistant 2026.4 introduced native infrared support and infrared proxies. The infrared integration is a building-block integration, not something added directly as a normal end-user integration; device integrations and hardware integrations use it underneath. ESPHome provides an experimental IR/RF proxy component that exposes IR transmitter/receiver entities to Home Assistant and accepts raw timing sequences at runtime.

References:

- Home Assistant 2026.4 release notes: https://www.home-assistant.io/blog/2026/04/01/release-20264/
- Home Assistant Infrared integration docs: https://www.home-assistant.io/integrations/infrared/
- ESPHome IR/RF Proxy docs: https://esphome.io/components/ir_rf_proxy/
- ESPHome Infrared component docs: https://esphome.io/components/infrared/
- ESPHome Remote Transmitter docs: https://esphome.io/components/remote_transmitter/

Important caveat: ESPHome marks the IR/RF proxy and infrared component as experimental. Exact service/action naming in Home Assistant may shift while the API settles. Use Developer Tools > Actions to inspect the currently exposed actions for the ESPHome infrared entity.

## Current setup files

For the Seeed Studio XIAO IR Mate path:

- `custom_components/mountman_minisplit/` is the HACS-installable Home Assistant custom integration.
- `esphome/xiao-ir-mate-raw-api.yaml` is a manual ESPHome firmware example. HACS does not install or manage it.
- `home-assistant/SETUP.md` explains how to interpret the factory firmware's Send button entity, such as `button.gym_gym_ir_send`, how to install the HACS integration, and what raw transmitter action the integration expects.
- The generic ESPHome firmware exposes the dynamic sender as a Native API action, not as a normal device entity. Look for the action in Developer Tools > Actions, usually as `esphome.<node_name>_send_raw`.

The factory firmware Send button is useful for replaying a learned slot. Full Mountman control is better served by the HACS integration plus a user-provided raw-send action because mini-split commands are full-state packets.

## Recommended hardware

Use an ESP32-based IR blaster/proxy if possible.

Why ESP32:

- ESP32 variants commonly have RMT hardware for more accurate IR timing.
- This Mountman packet is long: 112 bits / 14 bytes plus header/trailer.
- Accurate timing matters more for AC-style IR than for many simple TV buttons.

Good options:

- ESP32 dev board + IR LED driver transistor
- Seeed XIAO IR Mate / compatible ESPHome IR proxy hardware
- Any tested ESPHome infrared proxy hardware with a strong IR emitter

Avoid relying on a bare GPIO pin directly driving an IR LED for the final install. Use a transistor/MOSFET driver and appropriate resistor so the IR LED has enough range.

## ESPHome proxy YAML skeleton

Adjust pins for the target ESPHome board.

```yaml
esphome:
  name: mountman-ir-proxy
  friendly_name: Mountman IR Proxy

esp32:
  board: esp32dev
  framework:
    type: esp-idf

logger:

api:

ota:
  platform: esphome

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

# Optional but useful during setup
web_server:
  port: 80

remote_transmitter:
  id: ir_tx
  pin: GPIO4
  carrier_duty_percent: 33%

# Optional receiver for later learning/debugging.
# Use a 38 kHz demodulating IR receiver module.
remote_receiver:
  id: ir_rx
  pin:
    number: GPIO5
    inverted: true
    mode:
      input: true
      pullup: true
  dump: raw

infrared:
  - platform: ir_rf_proxy
    name: IR Proxy Transmitter
    id: ir_proxy_tx
    remote_transmitter_id: ir_tx

  - platform: ir_rf_proxy
    name: IR Proxy Receiver
    id: ir_proxy_rx
    receiver_frequency: 38kHz
    remote_receiver_id: ir_rx
```

Notes:

- For IR transmit only, the receiver block and second infrared entity can be removed.
- The Flipper captures report around `0.330000` duty cycle, so the repo firmware uses `carrier_duty_percent: 33%`. If range is poor after the packet format is confirmed, `50%` is a reasonable follow-up experiment because it drives the IR LED harder.
- Keep the IR emitter physically aimed at the mini-split receiver window.

## Mountman packet generation model

The Mountman packet is 14 bytes.

```text
23 CB 26 01 00 [B5] [B6] [TEMP_A] [B8] 00 00 00 [TEMP_B] [CHECKSUM]
```

Checksum:

```python
checksum = sum(first_13_bytes) & 0xFF
```

Known temperature fields:

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
    # Continue the same inferred pattern through 88F.
}
```

Known mode/feature fields:

| State | B5 | B6 | B8 |
|---|---:|---:|---:|
| Off, from captured state | `20` | `03` | `3D` |
| Cool normal candidate | `24` | `03` | varies |
| Cool alternate/display/turbo family | `64` | `03` | varies |
| Heat | `24` | `01` | `05` in captured temps |
| Dry/dehumidify | `24` | `02` | `00` |
| Fan only | `24` | `07` | `05` |
| Eco on | `A4` | `03` | `3D` in capture |
| Turbo on | `64` | `43` | `3D` in capture |
| Anti-mildew on | `64` | `23` | `3D` in capture |

Known fan/swing-ish B8 values:

| B8 | Observed meaning |
|---:|---|
| `38` | Fan auto, swing-on-ish family |
| `3A` | Fan low, swing-on-ish family |
| `3B` | Fan medium, swing-on-ish family |
| `3D` | Fan high, swing-on-ish family |
| `05` | Swing off / default / heat-family captured value |
| `00` | Used in dehumidify and mode heat transition captures |

## Python command generator

Use this as the canonical generator while testing.

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
    # Continue the same inferred pattern through 88F.
}

B8_FAN = {
    "auto": 0x38,
    "low": 0x3A,
    "medium": 0x3B,
    "high": 0x3D,
    "offish": 0x05,
}


def checksum(payload_13):
    return sum(payload_13) & 0xFF


def packet_to_raw_timings(packet):
    """Return Flipper-style all-positive mark/space timings."""

    raw = [3100, 1500]
    for byte in packet:
        for bit_index in range(8):
            bit = (byte >> bit_index) & 1
            raw.append(560)
            raw.append(2060 if bit else 1040)
    raw.append(560)
    return raw


def packet_to_esphome_raw_timings(packet):
    """Return ESPHome signed timings.

    ESPHome uses positive numbers for carrier-on marks and negative numbers for
    carrier-off spaces. A phone camera may still see the LEDs flash if the
    spaces are accidentally positive, but a receiver such as a Flipper will not
    decode a proper frame because the off gaps are missing.
    """

    flipper_raw = packet_to_raw_timings(packet)
    return [value if index % 2 == 0 else -value for index, value in enumerate(flipper_raw)]


def build_mountman_packet(mode="cool", temp_f=72, fan="high", family="normal"):
    temp_a, temp_b = TEMP_MAP_F[temp_f]

    if mode == "cool":
        b5 = 0x24 if family == "normal" else 0x64
        b6 = 0x03
        b8 = B8_FAN[fan]
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
    elif mode == "off":
        # Captured off command from a 65-ish/high/swing-on-ish state.
        payload = [0x23, 0xCB, 0x26, 0x01, 0x00, 0x20, 0x03, 0x0D, 0x3D, 0x00, 0x00, 0x00, 0x84]
        return payload + [checksum(payload)]
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    payload = [0x23, 0xCB, 0x26, 0x01, 0x00, b5, b6, temp_a, b8, 0x00, 0x00, 0x00, temp_b]
    return payload + [checksum(payload)]


packet = build_mountman_packet(mode="cool", temp_f=72, fan="high", family="normal")
print("Packet:", " ".join(f"{b:02X}" for b in packet))
print("Raw timings:", packet_to_raw_timings(packet))
```

## First test commands

Test these before wiring up dashboards or automations.

### Cool 72°F, normal family, B8=05

```text
23 CB 26 01 00 24 03 09 05 00 00 00 80 CA
```

### Cool 72°F, alternate family, fan high / swing-on-ish

```text
23 CB 26 01 00 64 03 09 3D 00 00 00 80 42
```

### Heat 72°F, captured real packet

```text
23 CB 26 01 00 24 01 09 05 00 00 00 80 C8
```

## Home Assistant helper design

Use helpers as the assumed state store.

```yaml
input_boolean:
  mountman_power:
    name: Mountman Power

input_number:
  mountman_target_temp:
    name: Mountman Target Temp
    min: 61
    max: 88 # 73-88F is inferred and should be confirmed with captures
    step: 1
    unit_of_measurement: "°F"

input_select:
  mountman_mode:
    name: Mountman Mode
    options:
      - cool
      - heat
      - dry
      - fan_only

  mountman_fan:
    name: Mountman Fan
    options:
      - auto
      - low
      - medium
      - high

  mountman_family:
    name: Mountman Packet Family
    options:
      - normal
      - alternate
```

## Sending from Home Assistant

There are two implementation paths.

### Path A: Use IR proxy runtime raw sends

This is the desired direction with the new IR proxy support. The ESPHome IR/RF proxy component can accept raw timing arrays at runtime, which avoids recompiling firmware for each learned code.

Because the feature is new/experimental, check the exact action name in:

```text
Developer Tools > Actions
```

Look for actions exposed by the ESPHome infrared entity or the infrared domain. The payload should be an alternating array of mark/space timings in microseconds, with a 38 kHz carrier and repeat count of 1.

For the repo's ESPHome Native API action, generate the raw timing array with `packet_to_esphome_raw_timings(packet)`. ESPHome spaces must be negative.

Expected parameters, conceptually:

```yaml
target:
  entity_id: infrared.mountman_ir_proxy_transmitter
data:
  carrier_frequency: 38000
  repeat_count: 1
  timings:
    - 3100
    - -1500
    - 560
    - -2060
    # ... rest of generated raw timings
```

Do not treat that YAML as guaranteed exact service syntax. Use Developer Tools > Actions to confirm the current action schema in the installed HA/ESPHome version.

### Path B: ESPHome script fallback

If the generic IR proxy action is awkward or not exposed clearly yet, define ESPHome scripts/buttons for known states and call them from Home Assistant. This is less elegant but reliable.

The manual ESPHome example in this repo uses a hybrid of these ideas: the real HACS path calls a dynamic Native API action, while a visible `Send Mountman Off Test` button sends one fixed captured OFF packet for hardware smoke testing.

Example for one fixed command:

```yaml
button:
  - platform: template
    name: "Mountman Cool 72 Test"
    on_press:
      - remote_transmitter.transmit_raw:
          carrier_frequency: 38kHz
          code: [3100, -1500, 560, -2060] # replace with full ESPHome signed timing array
```

Downside: every new fixed command requires editing YAML and flashing again. That is exactly what the new proxy is meant to avoid.

## Automation flow

Basic automation pattern:

1. User changes any helper.
2. Automation calls `script.mountman_send_state`.
3. Script builds/selects the packet for the current helper state.
4. Script sends raw timings through the IR proxy.
5. HA helper values remain the assumed current state.

Pseudo-flow:

```yaml
alias: Mountman helper changed
triggers:
  - trigger: state
    entity_id:
      - input_boolean.mountman_power
      - input_number.mountman_target_temp
      - input_select.mountman_mode
      - input_select.mountman_fan
actions:
  - action: script.mountman_send_state
```

The hard part is step 3. Home Assistant/Jinja can do some list math, but this is much cleaner in one of these places:

- `pyscript`
- AppDaemon
- Node-RED function node
- small custom integration
- ESPHome lambda/script with parameters, once the command set is stable

## Recommended v1 scope

Do not try to support every remote button on day one.

Start with:

- Off
- Cool 61-72°F, plus inferred 73-88°F values awaiting capture confirmation
- Heat 67-72°F
- Fan auto/low/medium/high in cool mode
- Swing on/off after confirming B8/family behavior
- Eco on/off after confirming exact fields

Then expand:

- 73-88°F, to confirm or correct the inferred temperature map
- Sleep
- Turbo
- Anti-mildew
- Display
- Mute, only after the odd mute frame is understood

## Testing checklist

1. Place IR transmitter close to the mini-split receiver window.
2. Load `flipper-tests/MOUNTMAN_FIRST_TESTS.ir` onto the Flipper, or generate equivalent raw timings with `python3 tools/mountman_ir.py`.
3. Test `MOUNTMAN_HEAT_72_CAPTURED` first because it is a captured real packet, not predicted.
4. Test both predicted `Cool_72` packets.
5. Log which packet actually changes the unit to 72°F.
6. Repeat the accepted packet 3-5 times from different starting states.
7. Test with fan/swing variations only after temp is proven.
8. Keep the physical remote away from casual use once HA is live, or HA's assumed state will drift.

The generated first-test file currently contains:

- `MOUNTMAN_HEAT_72_CAPTURED`
- `MOUNTMAN_COOL_72_NORMAL_B8_05_PREDICTED`
- `MOUNTMAN_COOL_72_ALT_HIGH_PREDICTED`
- `MOUNTMAN_POWER_OFF_CAPTURED`

To regenerate it:

```bash
python3 tools/mountman_ir.py first-tests
```

To produce a Home Assistant-style raw timing payload for one command:

```bash
python3 tools/mountman_ir.py generate --mode heat --temp 72 --format ha-yaml
```

The `ha-yaml` output is still conceptual because the Home Assistant / ESPHome IR proxy API is experimental. Confirm the exact action in Developer Tools > Actions.

## State drift notes

IR is one-way. Home Assistant will not know if someone uses the physical remote unless an IR receiver also listens for the remote and decodes those packets.

Options:

- Simple mode: HA is the only controller; hide the real remote.
- Better mode: Add an IR receiver to the ESPHome proxy and update HA helpers when the physical remote is used.
- Best mode: Write a custom integration that can both transmit and decode the Mountman protocol.

## GitHub repo suggestion

Suggested layout:

```text
mountman-minisplit-ir/
├── README.md
├── HA-Notes.md
├── captures/
│   ├── Remote.ir
│   ├── Remote2.ir
│   └── Remote2(1).ir
├── flipper-tests/
│   └── MOUNTMAN_COOL_72_V2_multi.ir
└── tools/
    ├── decode_flipper.py
    └── generate_mountman.py
```

## Final warning

This protocol map is based on one remote/unit capture set. It may apply to other Mountman-branded mini-splits, but cheap mini-splits often share OEM hardware under different labels, and the same brand can ship different remotes. Treat this as a reverse-engineering starting point, not a universal Mountman spec.
