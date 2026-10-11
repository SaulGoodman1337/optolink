# WB2A/VDensHO1/20C2: UART1-ISR and firmware attribution gate (2026-10-11)

**Status:** static evidence recheck only; no firmware image, ISR discovery, or hardware Vitotrol acceptance. No controller commands, physical port access, coding changes, or injection.

## A critical distinction: Optolink identity is not silicon identity

The connected boiler's controller application is identified over Optolink as **VDensHO1 / 20C2 / software 0103**. That protocol identification is not an independent observation of the main microcontroller's maker, package, model or firmware memory map.

The preserved, earlier physical-board dossier (outside this PR) explicitly distinguishes two hardware families:

- **7424735 / VBC130 comparison board:** independent photographs appear to identify a Renesas/Mitsubishi **M30624FGPFP (M16C/62P)**. This comparison board relates to a different control family.
- **WB2A / GG1 7187393 candidate board:** public examples are documented, but the MCU marking is **unreadable**; the exact locally installed board and its silicon marking have not been independently photographed. The similar 100-pin package alone cannot prove that it contains an M16C.

Source basis: research dossier `regulation-board-7424735-pcb-research.md` (introduction, MCU inference boundary, current outcome and negative MCU-photo result); `m30624-nondestructive-readout-plan.md` explicitly marks the M30624 path **conditional on local MCU identification**. Both reside in the separately maintained `optolink-research` material; do not copy privately sourced photos.

The separate static VitoSoft asset audit (`vdensho1-firmware-boundary-2026-09-25-evidence.json`) also found **no program-ROM image for 20C2**. Its M16C wording in an NRF reset description belongs to **VBC550S/VBC550P**, not to an exact VDensHO1 event. Thus a VitoSoft text occurrence cannot fill the missing local hardware proof.

## Consequence for vector 20 / INTB + 0x50

**Only conditional statement:** on the relevant **Renesas M16C/62P** family, the UART1 receive interrupt is documented at vector 20 with an entry at `INTB + 0x50`. Because the installed WB2A silicon and the actual INTB register are unconfirmed, this is a **processor-family research hypothesis**, not a proven live WB2A vector, handler, or parser.

A complete firmware-to-participant proof would require this chain, in order:

1. Direct local board / MCU identification, or independently verified matching target firmware.
2. An actual, source-supported `INTB` value and UART1-RX interrupt handler in that target.
3. Handler control flow showing KM-Bus frame parsing, including Vitotrol class `0x11`.
4. A demonstrated transition committing sender identity, sensor validity, timeout/watchdog and room temperature into the controller's state.
5. Only then a separately reviewed safe Optolink ingress and a bounded independent rollback plan.

No earlier archived RAM snapshot, M16C manual, VitoSoft function-name dropdown or public comparator PCB provides all five.

## Archived SRAM evidence is descriptive, not an ingress API

At `0x0B6D..0x0B70`, all 79 archived 20-KiB SRAM images hold `42 16 0A FE`. The candidate `0x1642` data was reconstructed from separate **non-atomic** FC03 reads, not from a documented UART1 interrupt trace.

Earlier independent reanalysis reported:

- `0x0B6B = 01` in 72 images, `0A` in 3, `0B` in 4.
- The first eight bytes at `0x1642` are `00 01 B1 0A 01 01 10 FE` in 78 images; the remaining image has `00 01 B1 0A 01 01 00 00`.
- The rare changed RX prefix occurs while `0x0B6B=01`; no synchronous descriptor/RX field transition has been shown.

The extended offline `window_locality()` report now emits explicit descriptor/RX marginal counts and paired counts, while retaining `sampling_order_and_causality_proven=false`. A new synthetic test exercises independent changes and asserts the non-causal flags. It does **not** classify `0x0B6D` as a pointer or identify an interrupt source.

## Defensible status and next decision gate

- **Verified hardware:** the earlier short B0:3 canary was written/read back and independently restored to B0:0. It did not register a Vitotrol.
- **Verified static data:** controller profile, non-atomic full-RAM buffer content, candidate literal matches, host-side VitoSoft metadata, and comparative PCB research.
- **Not established:** local MCU family, live INTB/vector 20/ISR, KM-Bus state commit, Optolink-reachable receive service, or a safe RX-injection mechanism.

**Vitotrol acceptance by the real WB2A: NO.** For unattended research, continue solely with archived/offline materials. Neither `A0` nor `B0` nor any RAM/SFR/EEPROM location is to be modified based on this report.

Reproduction (offline):
```bash
python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_window_locality.py' -v
python3 -m unittest discover -s tests -q
```
