# WB2A / GG1 controller hardware architecture - 2026-09-24

## Scope

Current firmware research target: European Vitodens 200 WB2A / VDensHO1 controller hardware.

The exact 2004 WB2A service documentation separates:
- A1 main PCB / Grundleiterplatte;
- A3 Optolink;
- A4 burner-control unit / Feuerungsautomat;
- A5 operator unit;
- A6 coding plug;
- KM-BUS and the internal circulation pump as distinct connected functions.

This is the architecture to use for further research. Older VR20/LGM29 material must not be transferred to this GG1 generation without matching part-number evidence.

## Public GG1 family evidence

Independent WB2A examples document GG1 production numbers such as 7185329 and 7187362. One WB2A example explicitly pairs GG1 7187362 with PCB 7187393.

A separate WB2A repair report describes PCB 84346904 as a standing daughterboard on the main controller PCB. Used controller assemblies are also listed with both 7187393 and 84346904.

Important boundary:
- 7187393 is currently a strong family-level PCB candidate;
- 84346904 is a confirmed family-level standing daughterboard;
- neither number is yet confirmed from the local appliance itself;
- no source found so far explicitly proves that 84346904 equals service block A4 Feuerungsautomat.

## Software-domain correlation

Already measured locally:

```text
main regulation:
  0x778C = 01
  0x778D = 03
  raw pair = 0x0103

burner/GFA:
  P80 = 20
  P81 = 02
  P82 = 06
  P83 = 76

coding card:
  0x7656 = 20 15 02 01
  type / device-id / GWG-revision / GFA-revision
```

The removable coding plug is a separate two-EEPROM configuration domain. It must not be treated as executable controller firmware.

## MCU and nonvolatile memory status

The processor and executable firmware storage are **not yet identified**.

Available public photos are sufficient to confirm the board/daughterboard topology, but not to read processor or memory markings reliably. Package shape alone is insufficient for identification.

Required next evidence:
1. exact local GG1 and PCB production numbers;
2. readable markings of the largest digital ICs on main board and daughterboard;
3. readable markings of any external Flash/EPROM/EEPROM devices;
4. oscillator/crystal markings near each processor;
5. location and labeling of unpopulated service/test headers.

Only after exact IC identification should datasheets and supported read/debug interfaces be mapped.

## Firmware-readout boundary

Vitosoft/Optolink research found no generic FLASH_READ, ROM_READ or bootloader-dump function for base VDensHO1. Therefore any future firmware acquisition must be tied to a concrete processor, memory device, or documented service interface.

Keep these targets separate:
- main-regulation firmware;
- burner/GFA firmware;
- coding-plug EEPROM contents.

## Current conclusion

The Vitosoft/host datapoint layer is exhausted for the hidden pump selector upstream of 0x0A3C.

The next firmware research step is hardware identification of the European WB2A/GG1 electronics, not further guessed virtual-address probing.

## TODO

- [ ] Confirm the local appliance's own GG1 and PCB numbers when convenient.
- [ ] Find a source explicitly mapping 84346904 to a functional service block, or keep it unidentified.
- [ ] Locate higher-resolution 7187393 / 84346904 board photos with readable IC markings.
- [ ] Build a processor/memory/oscillator inventory from exact markings.
- [ ] Map documented service/test interfaces only after the MCU family is known.
- [ ] Keep main-regulation and burner/GFA firmware research separate.


## 2026-09-25 update: historical Optolink firmware-readout lead

The local-board working model has been narrowed further:

- exact-board online evidence strongly favors GG1 PCB `7187393`;
- the owner reports from memory that the installed board matches the 7187393
  variant with screw terminals;
- the main MCU is still unreadable in exact-board online photographs;
- for current analysis only, `M30624FGPFP / M16C/62P` is used as a
  **working hypothesis**, not as a confirmed local marking.

A new historical lead materially changes the firmware-acquisition workstream.
OpenV's KM-BUS documentation states that a Vitotronic 200 KW2 using
`M30612MC` had about 128 KiB of code and that its software could be read via
Optolink. Git history shows that KarlKoch introduced the MCU/readout statement
and the approximately 57,000-line disassembly note together in commit
`da56ba2f73ae09d03597d75210d8a76444595503` on 2010-10-04.

This is evidence that an M16C-era Viessmann controller firmware acquisition
through the Optolink side existed historically. The exact request/service is
still unknown and must not be transferred directly to WB2A.

The obvious historical OpenV candidate, `OptoLinkLogger v0.0.4`, has now
been disassembled and closed as the mechanism: its "Dump Data" feature sends
ordinary VS1 `F7 <addr_hi> <addr_lo> <len>` virtual reads, serializes only
16 address bits and defaults to `0x0800 / 0x1000`. It therefore does not
directly expose M16C program flash.

Canonical detailed note:

`firmware-optolink-readout-research-2026-09-25.md`

Research priority is now to recover the specific M30612-era Optolink readout
mechanism before any new live WB2A firmware-read probe is attempted.
