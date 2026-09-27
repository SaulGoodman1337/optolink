# VitoTest 1.6 / 1.7 / 1.8 protocol diff — 2026-09-26

## Scope

Static comparison of the preserved historical VitoTest executables from the OpenV wiki archive.

| Version | EXE size | SHA-256 |
| --- | ---: | --- |
| 1.6 | 409600 | 1accbd49d7db5861a218db8005bf8fd315cb988b09ed34cd2521008256ea070e |
| 1.7 | 1728512 | d3ce7ddead54f3bd542f4ef04825f5147d162252a1078b97ed09243aac048f20 |
| 1.8 | 1729024 | b4792e59cce7115fc75322fd921ac3886bb304d542dc249ba0586412b813c4a6 |

No request was transmitted for this static comparison.

## Changelog chronology

The V1.8 archive's History.txt records:

- 1.4 (2007-11-27): protocol type 3 / GWG implemented;
- 1.6 (2009-09-01): incomplete XML configuration code removed and build cleaned for distribution;
- 1.6 (2009-11-29): V100KC2/KW corrections and Device-ID fix;
- 1.7 (2013-02-23): persisted settings, last ten Send commands, synchronized-send option;
- 1.8 (2013-11-10): explicit protocol selector using OpenV names 300er/KW/GWG and protocol-dependent Device-ID requests.
## Embedded identification templates

All three binaries contain the consecutive two-byte device IDs:

~~~text
20 94
20 98
20 B8
20 53
~~~

The adjacent fixed request templates evolve as follows.

### V1.6

~~~text
41 05 00 01 00 F8 02 00
01 F7 00 F8 02
F7 00 F8 02
~~~

The binary contains no fixed `01 C7 F8 04 04` template.

### V1.7

~~~text
41 05 00 01 00 F8 02 00
01 F7 00 F8 04
F7 00 F8 02
~~~

Again, no fixed `01 C7 F8 04 04` template was found.

### V1.8

~~~text
41 05 00 01 00 F8 02 00
01 F7 00 F8 04
01 C7 F8 04 04
~~~

This matches the 1.8 changelog: Device-ID acquisition became explicitly protocol-selectable.
## Simulator dispatcher is semantically unchanged

Despite compiler/toolchain changes, the compact VitoTest simulator/responder dispatcher is present in all three versions with the same request cases.

| Request body recognized | Simulator response/action |
| --- | --- |
| `C7 F8 02` | two-byte GWG ID |
| `F7 00 F8 02` | two-byte KW/V333 ID |
| `F7 75 61 0A` | ten-byte empty error-list response |
| `CB BD 01` | one-byte canned response |
| `CB 2F 01` | one-byte canned response |
| `C7 FB 01` | one-byte canned response |
| `CB 3F 01` | one-byte canned response |
| `CB 9B 03` | three-byte canned response |
| `C8 7F 01 42` | write request; canned ACK |

The 1.6 dispatcher sits around VA `0x4042F4..0x40458D`; the 1.7 and 1.8 dispatchers are relocated but preserve the same semantic chain.
No additional fixed dispatcher branch for `C5`, `AE`, `9E`, `6E`, `33`, `43`, ROM/flash, page, bank, selector, copy or monitor service was recovered in any of the three builds.

Opcode-looking constants elsewhere in the executables are not sufficient evidence: the later builds statically link a much larger MFC runtime and contain many unrelated comparisons.

## Interpretation

The version diff closes an important ambiguity:

1. GWG support itself predates V1.6, but the simulator's low-level cases are already the same in 1.6 as in 1.8.
2. V1.7 mainly adds UI/state persistence and synchronized-send behavior.
3. V1.8 adds explicit protocol selection and a fixed GWG identification template.
4. No new hidden firmware-read primitive appears between 1.6 and 1.8.
5. The V1.6 note about removed incomplete XML configuration is historically interesting, but the distributed 1.6 binary no longer contains that code.

Therefore the missing KarlKoch firmware-read mechanism is unlikely to be a VitoTest 1.6→1.8 feature that can be recovered simply by comparing these public executables. The remaining high-value historical target would be an older pre-cleanup VitoTest/working tree or private source around the 2009 XML-configuration removal.