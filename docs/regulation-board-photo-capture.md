# WB2A regulation-board photo capture for firmware research

Status: **planned hardware evidence capture**

The user will photograph the WB2A regulation/control electronics so the firmware research can move from generic Vitosoft analysis to a board/MCU-specific acquisition plan.

## Goal

Identify:
- main regulation MCU/CPU;
- burner/GFA MCU separately where accessible;
- external flash/EEPROM/serial memories;
- oscillator/crystal markings useful for MCU-family confirmation;
- board part number and hardware revision;
- service/programming/debug headers and unpopulated test pads;
- connector labels that help separate Optolink, KM-BUS, power and burner-control sections.

## Required photo set

Prefer original-resolution photos without rescaling:

1. complete regulation board, component side;
2. complete opposite side if safely accessible;
3. straight-on close-up of every large IC with readable top marking;
4. close-ups of all 8/16-pin memory-like devices;
5. board silkscreen/part number/revision labels;
6. stickers and production labels;
7. all unpopulated pin headers, test-pad groups and edge connectors;
8. crystal/oscillator and nearby MCU area;
9. separate overview/close-ups of burner/GFA electronics if they are a distinct board and can be accessed safely.

Take one overview first, then overlapping close-ups. A second close-up at a slight angle can help with faint laser markings.

## Safety / evidence boundary

This task is photographic documentation only.

- Do not probe unknown headers or test pads electrically.
- Do not short, bridge or power service pads.
- Do not remove or reconnect ICs for the photo session.
- Work only when the appliance is safely de-energized according to the normal service procedure.
- Preserve connector orientation and board placement in the overview photos.

## After the photos are available

Research sequence:
1. transcribe every readable IC marking exactly;
2. identify MCU family from primary-source datasheets;
3. identify internal/external flash architecture;
4. map likely debug/programming interfaces from the actual MCU datasheet;
5. assess readout protection and whether a non-destructive dump is realistic;
6. keep main-regulation firmware, GFA firmware and coding-plug EEPROM as separate targets;
7. archive any future raw firmware only in the private research repository and publish only hashes/derived analysis.
