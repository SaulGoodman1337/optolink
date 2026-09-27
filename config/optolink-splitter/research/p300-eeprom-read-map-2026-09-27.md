# P300 EEPROM_READ map — 2026-09-27

Status: hardware-proven, read-only characterization on the local VDensHO1 / 20C2 controller. No EEPROM write, erase, unlock or private opcode was used.

## Capability result

P300 function `0x05 = EEPROM_READ` is implemented on the local controller. A source-backed historical read at `0x0017/2` returned stable `FC 3A` in 3/3 repetitions. The corresponding source-backed `PORT_READ 0x33` test at `0x0001/1` was rejected with controller error payload `05` in 3/3 repetitions.

EEPROM_READ is distinct from Physical_READ. At the same addresses:

- `EEPROM_READ 0x0005/1 -> 47`, while `Physical_READ -> 08`;
- `EEPROM_READ 0x0017/2 -> FC 3A`, while `Physical_READ -> 97/98 00`.

All tests passed current-fault and fault-history guards.

## Stable low EEPROM/service page

A complete two-pass read of `EEPROM_READ 0x0000..0x00FF` in 16-byte blocks succeeded without errors. The two 256-byte passes were byte-identical (`0/256` changed bytes), proving a persistent, structured address space rather than volatile RAM.

## Address-width and segmentation

The P300 request's high address byte is significant: `0x0005`, `0x0105` and `0x1005` returned different stable values, while `0xFF05` returned controller error `31 01`.

A sparse `x005` scan showed a segmented validity pattern. Successful high segments included `0x1000`, `0x2000`, `0x5000`, `0x6000`, `0x9000`, `0xA000`, `0xD000` and `0xE000`; intervening groups such as `0x3000/0x4000`, `0x7000/0x8000`, `0xB000/0xC000` and `0xF000` rejected the sample with `31 01`.

All successful high segment bases returned the same 16-byte fingerprint:

```text
80 13 10 91 05 10 00 40 13 05 10 00 40 13 17 D2
```

This is therefore a segmented service/alias map, not a linear 64-KiB EEPROM or ROM view.

## Active coding-plug window

The high-segment fingerprint is byte-identical to offset `0x0000` of the independently acquired active coding-plug image `7173085-3_CHL-G_3F1_94V-0_f01.bin`.

A dedicated bounded verifier then read the complete 512-byte interval `0x1000..0x11FF` in chunks of at most 55 bytes. Every returned byte matched the existing active coding-plug dump: **512/512 bytes identical**.

Thus, on this exact controller:

```text
P300 EEPROM_READ 0x1000..0x11FF
        -> active coding-plug image f01[0x000..0x1ff]
```

This classifies the high EEPROM_READ window as coding-plug access, not program-ROM firmware access.

## SFR discriminator result

A separate paired Virtual_READ/Physical_READ scan covered the complete `0x0000..0x03FF` SFR range. With unequal response lengths, DMA1 TCR recorded the expected TX frame-length difference (`8` vs `38`), and free-running timer registers around `0x0380/0x0390` produced timing-dependent differences.

When the Physical_READ stimulus was reduced to the same two-byte payload length as the Virtual_READ control, the DMA1 difference disappeared completely. DMA0, DMA1, UART0/1 and DMA-select state showed no disjoint function-specific values. The remaining differences were confined to running timer registers and were non-constant.

Therefore no persistent Physical_READ-specific handler/dispatch state was found in the sampled SFR space after controlling for frame length and timing.

## Consequence for firmware readout

Two candidate directions are now closed or reclassified:

1. post-request SFR state does not expose a stable Physical_READ-specific handler pointer/selector;
2. P300 `EEPROM_READ 0x05` does expose a useful separate persistent space, but its high service window is the active coding plug rather than MCU program ROM.

The missing historical >16-bit firmware bridge remains most consistent with a separate/private monitor or far-copy service rather than an ordinary catalogued read function.

## Follow-up: BE_READ and second coding-plug image

The complete Vitosoft event catalogue contains 20 `BE_READ` definitions, all fixed one-byte reads without PrefixRead. A bounded local capability test used three representative source-defined addresses (`0x0008`, `0x0057`, `0x00F5`). P300 `BE_READ / 0x35` returned error payload `05` for every request (3/3 per address), with unchanged fault history. This read family is therefore not locally exposed through those documented shapes.

The active coding-plug `f02` image begins `FF 72 00 02 00 00 00 FF ...`, distinct from f01. Fixed EEPROM_READ checks at neighboring 512-byte-style bases did not expose it: `0x1200`, `0x1600`, `0x1800`, `0x1A00`, `0x1C00`, `0x1E00` returned `31 01`, while `0x1400` repeated the f01 alias signature. No adjacent second-chip linear window was found.