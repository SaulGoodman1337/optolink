# Physical_READ far-source / low-RAM copy candidates — 2026-09-26

Status: read-only/offline characterization on exact local VDensHO1 / 20C2. No write, selector, private opcode, erase, unlock or bootloader action was used.

## Search model

After resolving the far-pointer cluster as scheduler records, the paired 0x0400..0x53FF RAM snapshots were scanned for a different shape: a stable 8-byte tuple containing

~~~text
3-byte high program-range pointer
3-byte low-RAM pointer
2-byte small count
~~~

in either source-first or destination-first order.

This search is intentionally narrower than generic far-pointer scanning and is motivated by the M16C's 20-bit memory model and the possibility of ROM-to-RAM copy state.

## Offline result

Exactly two stable tuples satisfy the strict shape in both complete RAM snapshots:

~~~text
RAM 0x1DE5:
AB A2 0E | 01 33 00 | 1D 00
src  = 0xEA2AB
dst  = 0x3301
count= 29

RAM 0x1E6A:
05 07 00 | 7D B2 0F | 07 00
dst  = 0x0705
src  = 0xFB27D
count= 7
~~~
Both high pointers lie in the M16C program-address range and both destinations lie inside the hardware-readable low RAM region.

The corresponding destination data was byte-identical across the two full snapshots:

~~~text
0x3301 / 29:
36 1E CC B4 4D DF 9E F8 EF AB B7 87 DF FE 7D 87
08 88 48 23 32 91 83 B9 E6 D4 11 8E 3E

0x0705 / 7:
64 64 64 64 64 64 64
~~~

The 0x3301 block is unique in the captured RAM image. The seven-byte 0x64 run is not unique and therefore provides weaker content evidence.

## Live stability

A fixed-target read-only probe sampled RAM 0x1DE0/32 and 0x1E60/32 for 16 rounds under the normal identity/fault-history guard.

Candidate A remained exactly:

~~~text
src=0xEA2AB dst=0x3301 count=29
~~~

for all 16 rounds.

Candidate B was normally:

~~~text
src=0xFB27D dst=0x0705 count=7
~~~

One earlier 16-round capture transiently observed the same source with a different low destination/count, but a later 24-round capture remained at 0x0705/7 throughout. Because the surrounding 0x1E60 region is highly dynamic and stack/task-like, the transient is treated as a possible torn/non-atomic observation rather than proof of descriptor mutation.
## Independence from Physical_READ target

A bounded read-only discriminator explicitly issued successful Physical_READ requests to four fixed low-RAM targets:

~~~text
0x0400
0x0700
0x3300
0x53E0
~~~

After each request, both candidate tuples were re-read.

Neither tuple followed the requested Physical_READ address or block:

~~~text
A: src=0xEA2AB dst=0x3301 count=29
B: src=0xFB27D dst=0x0705 count=7
~~~

throughout.

Therefore these tuples are not simply the current P300 Physical_READ request arguments.

## Interpretation boundary

These are the strongest current ROM-to-RAM-shaped byte patterns, but they are not yet proven copy descriptors.

Reasons for caution:
- both occur in task/stack-like RAM around the 0x55 fill regions;
- M16C compiler stack frames can contain saved pointers/arguments;
- no source-side ROM bytes are currently available for byte-exact comparison;
- no recovered host request directly references EA2AB or FB27D;
- no controlled state transition has yet changed source/destination/count in a reproducible way.

The correct classification is therefore:

**high-value far-source / low-RAM copy candidates, not confirmed ROM-copy service state.**
## Why they matter

If either tuple is a real copy descriptor or saved call frame for a copy routine, it would provide exactly the missing architectural primitive:

~~~text
20-bit program source
        |
        v
low-RAM destination + length
        |
        v
Physical_READ-visible result
~~~

This would bridge the current 16-bit Optolink visibility to 20-bit program memory without requiring a wider EventType address.

Candidate A is stronger on destination-content uniqueness and complete live stability.

Candidate B is stronger on the compact source/destination/count shape but sits in a more dynamic stack-like neighborhood and has a non-unique destination payload.

## Next discriminator

The next useful evidence would be one of:
1. a reproducible state change that alters one candidate's source/destination/count while preserving the 3+3+2 structure;
2. source-backed identification of callbacks/routines near EA2AB or FB27D;
3. an independently acquired firmware image allowing comparison of ROM bytes at EA2AB/FB27D with RAM 3301/0705;
4. a passive/trace observation showing one tuple immediately before a known copy/update of its destination block.

No write should be used merely to force such a change.

## Tooling

- tools/analyze-physical-copy-candidates.py — offline paired-snapshot scanner;
- tools/physical-copy-candidate-probe.py — fixed read-only live stability probe.

## 60-second natural-state correlation run

A fixed read-only correlation probe observed both candidate tuples, both destination blocks, and ordinary burner/runtime anchors for 60 seconds without forcing any controller state change.

Observed runtime state for all 66 samples:

~~~text
flame = 0
fan rpm = 0
burner modulation = 0.0 %
CFDM = 0.0 %, off
boiler temperature = 48.0 C
~~~

During this idle interval both candidate tuples and both destination payloads remained byte-identical for every sample. The probe reported zero state transitions and the final fault-history guard passed.

This is useful negative evidence: neither candidate is a rapidly changing communication scratch tuple or timer-like structure during idle operation. It does not test behavior across burner start/stop or another natural control transition.

The next live discriminator should therefore be triggered by a naturally occurring burner/control-state change rather than extending the same idle observation window.

## Attempted active-burner capture after user trigger

The user reported that heating was enabled and the burner was running, so the fixed copy-correlation probe was started immediately.

By the time exclusive P300 acquisition began, the validated local burner block showed flame off, fan rpm zero and modulation zero for the complete 60-second window. Boiler temperature fell from approximately 48.3 C to 33.0 C. Both copy-shaped tuples and both destination blocks remained unchanged throughout.

A subsequent five-minute watcher using the normal splitter/MQTT path repeatedly read the full 0x55D3/11 block and waited for any nonzero 0x55DC modulation, flame bit or fan rpm. No burner re-entry occurred before the watcher timed out.

Conclusion: this attempt did not capture an active burner transition. It adds another post-run/cooling stability observation but does not advance the active-state discriminator.

## 2026-09-27 forced reduced-setpoint burner-start capture

A bounded live test used the already hardware-verified A1 reduced room setpoint at 0x2307 as the only stimulus. The original value was read as 21 C, temporarily changed to 37 C with exact P300 readback, and restored to 21 C with exact readback after the acquisition.

The trigger produced a real burner startup inside the same exclusive P300 session. Fan rpm became nonzero after about 2.4 s, modulation rose from 0 to 30/34 and then into the high 60s, and the flame bit became active at about 13.3 s. Boiler temperature subsequently rose from 26.5 C to about 51 C during the 60-second window.

Across 77 samples covering idle, fan pre-run, modulation ramp, ignition and sustained flame, candidate A stayed exactly EA2AB -> 3301 / 29, candidate B stayed exactly FB27D -> 0705 / 7, and both destination payloads remained byte-identical. Change counters were zero for both candidate tuples and both destination blocks.

This is strong negative evidence against either tuple being a live burner-state-dependent ROM-to-RAM copy descriptor. They may still be static descriptors, saved call frames, or structures associated with another subsystem, but burner startup does not activate or mutate them.

Post-test verification: 0x2307 restored to 21 C, device identity 20C2 confirmed, current GFA fault 0, current alarm byte clear, fault-history guard passed, and splitter/party/schedule services were restored active.

## 2026-09-27 strict 32-bit far-pointer descriptor scan

Because confirmed scheduler callbacks are stored as 32-bit little-endian values (0x000Fxxxx), the paired full RAM snapshots were rescanned for non-overlapping contiguous layouts using far32 plus low-RAM pointer plus count. This intentionally removed the permissive overlapping-window heuristic used during initial exploration.

The strict scan reduced hundreds of incidental shapes to four hits. Two are duplicate communication-adjacent records at 0x1926/0x1939. A candidate around 0x113B was resolved as another 11-byte scheduler chain: records beginning at 0x1139 and 0x1144 contain callbacks 0xE97F1 and 0xE9815 respectively and follow next16|callback32|tick16|period16|flag8.

The strongest remaining exact shape was RAM 0x1C90 = 01 c7 0c 00 58 0d 20 00, interpretable as far32 0xCC701 | RAM 0x0D58 | count 32. The 8-byte descriptor was identical in both full snapshots and in 32/32 live samples. However the complete 32-byte RAM block at 0x0D58 changed in every live sample and also differed between the paired full snapshots.

This behavior is poor evidence for a literal ROM 0xCC701 -> RAM 0x0D58 / 32 copy descriptor, because an immutable ROM source should not continuously produce a different full destination payload. A static callback/context/size or task-state descriptor is more plausible. No write or invocation was attempted.

A preceding-target correlation test also varied four known Physical_READ targets (0x0400, 0x0700, 0x3300, 0x53E0) before fixed RAM samples. Outside the known rotating P300 communication ring, no fixed-offset field reproducibly tracked the preceding target. This weakens the simple selector-shadow hypothesis for the sampled candidate regions.