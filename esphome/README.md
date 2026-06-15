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
    - 1500
    - 560
    - 2060
```

The HACS integration generates the Mountman packet and timing array, then calls this action.

## Why the Firmware Is Generic

The protocol is still being tested. Keeping Mountman packet generation in the HACS integration means protocol fixes can be installed through HACS without reflashing the ESPHome device.

The ESPHome device only needs to know how to transmit raw 38 kHz IR timings.
