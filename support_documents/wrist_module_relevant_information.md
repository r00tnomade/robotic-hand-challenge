# Relevant Information: Wrist Module

Source: [INSPIRE-ROBOTS-WRIST-MODULE-OF-THE-DEXTEROUS-HAND-INSTRUCTIONS.pdf](INSPIRE-ROBOTS-WRIST-MODULE-OF-THE-DEXTEROUS-HAND-INSTRUCTIONS.pdf)

Document metadata:

- Manufacturer: Beijing Inspire-Robots Technology Co., Ltd.
- Document ID: `PRJ-02-TS-U-004`
- Version: `V0.0.2`
- Date: January 2024

## Relevance to the Challenge

The manual describes the wrist module, not the 17 tactile sensors. It still
provides useful state information for the pose-estimation pipeline: wrist yaw
and pitch can be recorded together with each tactile frame as the hand pose.
This will help distinguish object motion from motion caused by the wrist itself.

The wrist angles alone do not determine the object's pose. They must be
combined with finger contacts and tactile measurements.

## Wrist Motion

The wrist has two degrees of freedom:

| Degree of freedom | Range |
| --- | ---: |
| Pitch | -22.66 deg to 22.12 deg |
| Yaw | -25.50 deg to 25.50 deg |

## Registers

Angles use a scale of 100 units per degree. For example, `1125` represents
`11.25 deg`. Register values are 2-byte values unless stated otherwise.

| Address | Access | Meaning | Unit / length |
| ---: | :---: | --- | --- |
| `1020` | R | Actual wrist pitch | 2 bytes, 100 units/deg |
| `1022` | R | Actual wrist yaw | 2 bytes, 100 units/deg |
| `1024` | R | Wrist servo actuator current #2 | 2 bytes, mA |
| `1026` | R | Wrist servo actuator current #1 | 2 bytes, mA |
| `1028` | R | Servo actuator #1 error code | 1 byte |
| `1030` | R | Servo actuator #2 error code | 1 byte |
| `1032` | R | Servo actuator #1 temperature | 1 byte |
| `1033` | R | Servo actuator #2 temperature | 1 byte |
| `1038` | W/R | Target wrist yaw | 2 bytes, 100 units/deg |
| `1040` | W/R | Target wrist pitch | 2 bytes, 100 units/deg |
| `1042` | W/R | Movement profile time | 2 bytes, milliseconds |

The manual's examples read the actuator-current group starting at address
`1024` with a length of 4 bytes. The exact actuator byte ordering should be
verified against the full Dexterous Hand manual or the vendor Python API before
using current values in safety logic.

## RS232 / RS485 Communication

- Baud rate: `115200`
- Data bits: `8`
- Stop bits: `1`
- Parity: none
- Read flag: `0x30`
- Write flag: `0x31`
- Request header: `0xEB 0x90`
- Response header: `0x90 0xEB`
- The hand ID is included in every frame.
- Addresses are transmitted low byte first, followed by high byte.
- The checksum is the low-order byte of the sum of the frame data before the
  checksum, excluding the response frame header.

### Read frame

```text
EB 90 HAND_ID 04 30 ADDRESS_LOW ADDRESS_HIGH REGISTER_LENGTH CHECKSUM
```

### Write frame

```text
EB 90 HAND_ID (REGISTER_LENGTH + 3) 31 ADDRESS_LOW ADDRESS_HIGH DATA... CHECKSUM
```

Angle values are signed 16-bit integers in the examples. For example, `-10.00`
degrees is represented as `-1000`, or hexadecimal `0xFC18` in little-endian
order.

## CAN Communication

- Baud rate: `1000K`.
- Uses extended 29-bit CAN identifiers.
- Standard identifiers and remote frames are not used.
- Identifier fields, from low to high:
  - bits 0-13: `Hand_ID` (up to 16383 devices)
  - bits 14-25: register start address
  - bits 26-28: operation flag
  - bits 29-31: reserved
- Operation flags for the wrist:
  - `4`: read wrist register
  - `5`: write wrist register
- A read request contains one data byte: the number of register bytes to read.
- A read response contains the register data.

## Recommended Data Record

When real hardware becomes available, store wrist state next to every tactile
frame:

```json
{
  "timestamp_ns": 0,
  "hand_id": 1,
  "wrist_pitch_deg": 0.0,
  "wrist_yaw_deg": 0.0,
  "tactile_frame": "pending_vendor_api_mapping",
  "object_id": "unknown",
  "ground_truth_pose": null,
  "slip_label": null
}
```

For the offline prototype, `wrist_pitch_deg` and `wrist_yaw_deg` can be
synthetic values. The tactile fields should remain independent of the wrist
transport code so the same estimator works with generated data and the real
Python API later.

## Open Questions

- The manual does not document the 17 tactile sensors.
- The full Dexterous Hand user manual and vendor Python API are still needed
  to map tactile channels, sensor matrices, sampling rate, and units.
- The hand coordinate frame and the wrist-to-palm transform are not defined in
  this wrist-only document.
- Error-code meanings are not listed here.
