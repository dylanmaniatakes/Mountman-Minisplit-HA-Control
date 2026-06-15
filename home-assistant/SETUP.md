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

The integration does not talk to an ESPHome device id directly. It calls a Home Assistant action. That action must be able to accept this data:

```yaml
data:
  command:
    - 3100
    - 1500
    - 560
    - 2060
    # ...
```

An ESPHome device id, ESPHome device name, or button entity id is not enough.

The repo includes an ESPHome example at:

```text
esphome/xiao-ir-mate-raw-api.yaml
```

That file is for manual flashing. HACS does not install it, copy it into Home Assistant, or manage ESPHome firmware.

## Expected ESPHome Device Page

The generic ESPHome firmware in this repo does not recreate the Seeed factory firmware's learned-command UI. After flashing `esphome/xiao-ir-mate-raw-api.yaml`, Home Assistant should show basic device entities such as:

- `Status LED`
- `Vibration Motor`
- `Touch Button`
- `Send Mountman Off Test`
- `Restart`

It is normal if there is no generic `IR Send` entity under the device. ESPHome's `remote_transmitter` and `remote_receiver` blocks define hardware hubs, not visible Home Assistant entities.

The dynamic raw sender is an ESPHome Native API action. Use **Developer Tools > Actions** to find and test it. With the default repo firmware node name, the action is usually:

```text
esphome.gym_send_raw
```

If the firmware was edited before flashing, the action name follows the ESPHome node name. For example, this substitution:

```yaml
substitutions:
  name: gymircontroller
```

usually creates:

```text
esphome.gymircontroller_send_raw
```

If Home Assistant still shows the old Seeed device name after flashing, reload the ESPHome integration entry or restart Home Assistant. If the old names remain confusing, delete the ESPHome device from Home Assistant and add it again with the flashed node's `.local` hostname or IP address.

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
    - -1500
    - 560
    - -2060
    # ...
```

The `command` value is an array of alternating mark/space durations in microseconds. For ESPHome, marks are positive numbers and spaces are negative numbers. The transmitter should send it as raw IR at 38 kHz with one repeat.

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

To test the raw action plumbing directly before installing the HACS integration, use Developer Tools > Actions with a short raw pulse sequence:

```yaml
action: esphome.gym_send_raw
data:
  command:
    - 3100
    - -1500
    - 560
    - -2060
```

That shortened payload is only a syntax/connection test. It is not a complete mini-split command. The `Send Mountman Off Test` ESPHome button and the HACS integration both send complete 227-timing Mountman packets.

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
Maximum temperature: 88
```

The integration creates an assumed-state climate entity. Add it to a dashboard like any other thermostat/climate device.

### Change the Raw Action After Setup

If the ESPHome node name changes or the first action name was entered incorrectly:

1. Go to Settings > Devices & services.
2. Open the `Mountman Mini-Split IR` integration.
3. Select Configure.
4. Update `Raw IR transmitter action`.

Home Assistant reloads the Mountman entity after the options are saved.

### Troubleshooting: Integration Adds But The AC Does Not Respond

This usually means Home Assistant created the Mountman climate entity, but the transmitter action is not pointing at a callable raw sender.

Check these items first:

- Do not enter an ESPHome device id.
- Do not enter an ESPHome device name by itself.
- Do not enter a factory-firmware button entity such as `button.gym_gym_ir_send`.
- Do use an ESPHome user-defined action such as `esphome.gym_send_raw` or `esphome.gymircontroller_send_raw`.

The factory firmware button can replay a learned slot, but it cannot accept the Mountman raw timing array generated by the HACS integration. The custom ESPHome firmware in this repo exposes the needed raw sender through `api.actions`.

To find the action name:

1. Open **Developer Tools > Actions**.
2. Search for `send_raw`.
3. Copy the full action name that starts with `esphome.`.
4. Paste that value into the Mountman integration's `Raw IR transmitter action` option.

If the action is missing, reload the ESPHome integration entry or restart Home Assistant. ESPHome's user-defined action names are based on the ESPHome node name, not the friendly name shown on the device page.

### Troubleshooting: Phone Sees LEDs But Flipper Sees No Packet

If a phone camera can see the IR LEDs firing but a Flipper cannot read a raw packet, the transmitter may be sending carrier without valid mark/space gaps.

For ESPHome `remote_transmitter.transmit_raw`, spaces must be negative:

```yaml
command:
  - 3100
  - -1500
  - 560
  - -2060
```

Flipper `.ir` files use all-positive values for the same signal:

```text
data: 3100 1500 560 2060
```

Those two formats describe the same durations, but ESPHome needs the sign to know when to turn the carrier off.

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
