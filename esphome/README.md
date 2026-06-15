# ESPHome Firmware Examples

This folder contains firmware examples for manual use. HACS does not install, copy, flash, or manage anything in this folder.

## Recommended File

```text
esphome/xiao-ir-mate-raw-api.yaml
```

This firmware turns a Seeed Studio XIAO IR Mate into a simple raw IR transmitter. It exposes a Home Assistant action that accepts a raw timing array:

```yaml
action: esphome.gym_send_raw
data:
  command:
    - 3100
    - -1500
    - 560
    - -2060
```

The HACS integration generates the Mountman packet and timing array, then calls this action.

ESPHome raw timing values are signed:

- Positive numbers are marks, where the 38 kHz IR carrier is on.
- Negative numbers are spaces, where the carrier is off.

This is different from Flipper `.ir` files, which store the same alternating mark/space durations as all-positive numbers.

## What Appears In Home Assistant

After flashing the example firmware, the ESPHome device page should show normal entities such as:

- `Status LED`
- `Vibration Motor`
- `Touch Button`
- `Send Mountman Off Test`
- `Restart`

It is normal for there to be no generic `IR Send` entity on the device page. ESPHome's `remote_transmitter` and `remote_receiver` components are hardware hubs. They provide transmit/receive plumbing for automations and actions, but they do not create visible Home Assistant entities by themselves.

The dynamic raw sender is an ESPHome Native API action. Look for it in Home Assistant under **Developer Tools > Actions**, not in the device entity list.

With the default node name in this repo, the action is usually:

```text
esphome.gym_send_raw
```

If the ESPHome node name is changed, the action name changes too. For example:

```yaml
substitutions:
  name: gymircontroller
```

usually exposes:

```text
esphome.gymircontroller_send_raw
```

If Home Assistant still shows an older device name or the action is missing after flashing, reload the ESPHome integration entry or restart Home Assistant. If the device was previously installed under the Seeed factory firmware name, deleting and re-adding the ESPHome device can also clear stale entity registry names.

## Test Button

`Send Mountman Off Test` is a fixed smoke-test button. It sends one captured Mountman OFF packet through the IR LEDs. This button proves the ESPHome transmitter path is working, but the HACS integration does not use it for normal climate control.

## Why the Firmware Is Generic

The protocol is still being tested. Keeping Mountman packet generation in the HACS integration means protocol fixes can be installed through HACS without reflashing the ESPHome device.

The ESPHome device only needs to know how to transmit signed raw 38 kHz IR timings.
