# Home Assistant Setup

This guide connects the Mountman protocol findings in this repo to Home Assistant and a Seeed Studio XIAO IR Mate / ESPHome controller.

## Recommended Architecture

Recommended testing stack:

```text
Home Assistant climate entity
  -> HACS custom integration: mountman_minisplit
  -> user-provided raw IR transmitter action
  -> XIAO IR Mate or another raw 38 kHz transmitter
  -> Mountman mini-split
```

The HACS integration owns the Mountman protocol logic. The transmitter only receives raw timing arrays and transmits them. This keeps protocol fixes versioned through HACS during testing and keeps firmware management separate.

The repo includes an ESPHome example at:

```text
esphome/xiao-ir-mate-raw-api.yaml
```

That file is for manual flashing. HACS does not install it, copy it into Home Assistant, or manage ESPHome firmware.

## What `button.gym_gym_ir_send` Means

The entity `button.gym_gym_ir_send` looks like the Seeed Studio factory firmware's **Send** button. That firmware stores learned IR commands in numbered slots, then sends the currently selected slot when the Send button is pressed.

That is useful for a quick replay test, but it is not enough for full Mountman climate control by itself:

- The Send button does not take an arbitrary raw timing array as service data.
- It only sends the learned command stored in the selected signal slot.
- The factory firmware stores only a small set of learned slots.
- A mini-split needs many full-state packets, not just one power toggle.

## Path 1: Quick Smoke Test With Factory Firmware

Use this path before reflashing the IR Mate.

1. Copy `flipper-tests/MOUNTMAN_FIRST_TESTS.ir` to a Flipper Zero.
2. In Home Assistant, select an empty signal slot on the IR Mate.
3. Press the IR Mate Learn button.
4. Use the Flipper to send `MOUNTMAN_HEAT_72_CAPTURED` toward the IR Mate receiver.
5. Press `button.gym_gym_ir_send` in Home Assistant.
6. Confirm whether the mini-split responds.

This proves the IR Mate can physically transmit a Mountman-sized raw packet. It does not prove full Home Assistant climate-style control yet.

## Path 2: HACS Integration + Raw Transmitter Action

Use this path for version-managed testing.

### Provide a Raw Transmitter Action

The integration expects a Home Assistant action that accepts this data shape:

```yaml
action: some_domain.some_raw_send_action
data:
  command:
    - 3100
    - 1500
    - 560
    - 2060
    # ...
```

The `command` value is an array of alternating mark/space durations in microseconds. The transmitter should send it as raw IR at 38 kHz with one repeat.

For ESPHome, this is typically a user-defined Native API action. A complete example is included at `esphome/xiao-ir-mate-raw-api.yaml`, and the minimal action usually looks like this conceptually:

```yaml
api:
  actions:
    - action: send_raw
      variables:
        command: int[]
      then:
        - remote_transmitter.transmit_raw:
            carrier_frequency: 38kHz
            code: !lambda "return command;"
            repeat:
              times: 1
```

If the ESPHome node is named `gym`, Home Assistant usually exposes that action as:

```text
esphome.gym_send_raw
```

### Install Through HACS

1. Open HACS.
2. Go to Integrations.
3. Open the three-dot menu.
4. Select Custom repositories.
5. Add:

```text
https://github.com/dylanmaniatakes/Mountman-Minisplit-HA-Control
```

6. Category: Integration.
7. Install `Mountman Mini-Split IR`.
8. Restart Home Assistant.

### Add the Integration

1. Go to Settings > Devices & services.
2. Select Add integration.
3. Search for `Mountman Mini-Split IR`.
4. Use these starting values:

```text
Name: Mountman Mini-Split
Raw IR transmitter action: esphome.gym_send_raw
Default cool packet family: normal
Default fan mode: high
Minimum temperature: 61
Maximum temperature: 72
```

The integration creates an assumed-state climate entity. Add it to a dashboard like any other thermostat/climate device.

### First HACS Integration Tests

Use Developer Tools > Actions.

Captured real heat 72F packet:

```yaml
action: mountman_minisplit.send_state
target:
  entity_id: climate.mountman_mini_split
data:
  mode: heat
  temp_f: 72
  fan: high
  family: normal
```

Predicted cool 72F normal-family candidate with byte 8 forced to `0x05`:

```yaml
action: mountman_minisplit.send_state
target:
  entity_id: climate.mountman_mini_split
data:
  mode: cool
  temp_f: 72
  fan: high
  family: normal
  b8_override: 5
```

Predicted cool 72F alternate-family high-fan candidate:

```yaml
action: mountman_minisplit.send_state
target:
  entity_id: climate.mountman_mini_split
data:
  mode: cool
  temp_f: 72
  fan: high
  family: alternate
```

Power off:

```yaml
action: mountman_minisplit.send_state
target:
  entity_id: climate.mountman_mini_split
data:
  mode: "off"
```

## Important IR State Note

IR is one-way. Home Assistant will assume the mini-split is in the last state it sent. If someone uses the physical remote, Home Assistant will not know unless an IR receiver is added and the received Mountman packets are decoded.
