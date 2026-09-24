# Private Vitosoft archive analysis - 2026-09-23

Status: **archive integrity verified; SQL and selected host-code paths analyzed; no new live appliance tests performed**.

This is the current collector checkpoint. It supersedes earlier interpretations where they conflict, especially the supposed firmware-update workflow, universal applicability of all 94 GFA events, P09 scaling, the Neptun pump properties and the KM-BUS/LON member-list name. Historical measurements remain valid; their interpretation must respect the distinctions below.

See also [the consolidated workstream checkpoint](../../../../docs/collector-research-checkpoint.md) and [the machine-readable evidence](private-archive-2026-09-23-evidence.json).

## 1. Source, integrity and coverage

Input: `vitosoft-private-archive-20260923-205048.7z`.

SHA256:

```text
50f8215ea74b1d507c78d28294814db1a5fc65683b3308f23057a2fce8bb4daa
```

The archive was extracted and inspected without running Vitosoft, loading its assemblies for execution, contacting an appliance, or initiating an update. Extracted paths were checked for traversal; only directories and regular files were accepted.

| Check | Result |
| --- | ---: |
| Compressed bytes | 319,029,638 |
| Archive entries, including directories | 15,551 |
| Regular files | 15,351 |
| Uncompressed file bytes | 4,129,216,971 |
| Manifest entries hash-verified | 15,350 |
| Missing or mismatching manifest entries | 0 |
| Unmanifested files | Only `archive-manifest.sha256` itself |
| Installation files preserved | 7,105 |
| SQL tables exported and actual CSV row counts checked | 144 |
| SQL rows across those tables | 608,740 |
| ILDASM output files | 89 |
| Substantive IL outputs | 85 |
| Protected-only IL outputs | 4 copies, representing 2 distinct binaries |
| DUMPBIN outputs, excluding stderr companions | 106 |
| CORFLAGS outputs, excluding stderr companions | 89 |

The earlier `archive-stats.json` snapshot reports slightly fewer files/bytes than the final archive. This is consistent with report files generated after that snapshot; it is not a manifest-integrity failure.

Both the deep and SQL wrapper error-text files contain a blank `Collector exit code:` value. This is not reliable evidence that those stages failed: their independently checked outputs exist. SQL actual CSV counts match both `RowsExported` and `CountBig` for every exported table, with no recorded table error.

The four protected outputs are the MobileClient/Support copies of `FlowCalibration.dll`, including the `Echt` and `Test` variants. They contain `Protected module -- cannot disassemble`, not useful IL. Three copies share one binary hash; the test variant has another. No ILSpy fallback output was found in this archive. The raw DLLs remain available privately, so a future focused analysis need not recollect the whole installation.

The reflection stage also contains 9,343 error records. Reflection coverage and successful ILDASM coverage are different measurements: a reflection dependency failure does not invalidate an independently generated IL dump.

**Coverage boundary:** every manifest entry was hash-checked, but this report is a targeted semantic investigation, not an assertion that every method or resource in all 15,351 files has been understood. Particularly, the protected FlowCalibration implementation and actual WB2A firmware have not been recovered here.

### Retained provenance

Paths below are relative to the installation's `ServiceTool` directory. Raw binaries, complete IL dumps, databases, registry exports and machine-specific settings are not published.

| Source | SHA256 |
| --- | --- |
| `MobileClient/MobileClient.exe` | `f05e8ceef23eb94eaef0dca9c25ecbdd0fc83ae4e859d0fc7740f5bc78fd6136` |
| `MobileClient/vsmInterfaceCore.dll` | `1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d` |
| `MobileClient/vsmInterfaceCommon.dll` | `ac47b8ede5c4fc7e66eccf1d7f8b32c9c0c186093c7e5a49787a208675f5cb7f` |
| `MobileClient/ViessmannCommonObjects.dll` | `3fbbb4f9ed10ae37383a1cf3024a3a0934676beac77df744bf5cb29c8e1a41c9` |
| `MobileClient/Config/ecnEventType.xml` | `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba` |
| `Support/DP/DPDefinitions.xml` | `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3` |
| `Web/XmlDocuments/Textresource_de.xml` | `bd760a53bcf5058560677d4fdd52b557afbc4e2200cede966a944acc9c7ac2dd` |

The core production XML hashes match the earlier collected source set. The new value is primarily relational SQL context and executable method bodies, not a newly installed device-definition version.

## 2. SQL update tables: complete export, empty content

Both priority tables were exported successfully:

```text
dbo.ecnUpdateDefinition       0 rows
dbo.ecnDeviceSoftwareUpdate   0 rows
```

The first table really contains definition fields such as `DeviceTypeId`, `UsingIdentification`, software-version fields, `ConnectionString`, release metadata and names. The second contains per-device update/status/version fields. Their existence is real, but the captured database contains no rows for the WB2A or any other device in these two tables.

**Conclusion:** this installation snapshot contains no local update definition or device-update record from which a matching WB2A firmware package can be obtained. This does not prove that no other Vitosoft installation, server, service tool or historical distribution ever supplied one.

### Do not join device type and datapoint profile as though they were the same ID

`ecnDeviceType` contains a device type with ID 54, `Viessmann Anlage`. `ecnDatapointType` is a different table with 399 entries; its ID 60 is VDensHO1 and ID 208 is VDensHO1_4. An update-definition `DeviceTypeId` must not simply be compared with datapoint-profile ID 60.

### Previously unexplained version-like pairs are profile-selection bounds

Joining `ecnTableExtension` with `ecnTableExtensionValue` resolves the binary-scan observations:

| Datapoint profile | ID | Identification | IdentificationExtension | IdentificationExtensionTill |
| --- | ---: | --- | --- | --- |
| VDensHO1 | 60 | `20C2` | `0100` | `0103` |
| VDensHO1_4 | 208 | `20C2` | `0104` | `019F` |

Relevant extension definitions are IDs 6, 7 and 8; composite keys are `60;24` and `208;24`. These values describe selection of a datapoint-definition profile. They are **not** evidence of available firmware upgrades, source/target update versions or downloadable release ranges.

Extension ID 63 is `VSKO`; the captured VDensHO1 value is serialized Boolean true. Thus the exact profile explicitly enables the VSKO capability in Vitosoft's data model.

The selected serialized scalar values were decoded with bounded recognition of string/Boolean/Int32 records, not by executing .NET BinaryFormatter deserialization. The definition version remains `0.0.26.4683`.

## 3. Correction: the apparent update implementation is not a WB2A flasher

Method bodies disambiguate the earlier string-based inference:

| Symbol | Actual inspected role |
| --- | --- |
| `ecnMobileClient.vsmconnector.softwareupdate` | Vitosoft PC application software-download/install workflow |
| `SWDownloadBL::InstallSoftware` | Obtains the installer path and launches a process |
| `DeviceReadDataLogic::ReadyForUpdate` | Checks data-read/cache items and completion of static/dynamic request blocks |
| `BeginUpdate` / `EndUpdate` calls in the inspected MobileClient executable | Windows Forms ComboBox display refresh batching |

Source: `tool-dumps/ildasm/MobileClient_MobileClient.exe.il`, especially `SWDownloadBL::InstallSoftware` lines 336820-336852 and `DeviceReadDataLogic::ReadyForUpdate` lines 364996-365054. ComboBox call sites include lines 386707/386746, 389201/389247 and 389377/389416.

The SQL device-update model is a separate real schema. It does not turn these unrelated PC/UI methods into device-programming methods. The earlier plan to connect all these names into a single heater firmware-update transaction is superseded.

No authenticated WB2A executable firmware image was identified. A filename scan found no common `.bin`, `.hex`, `.mot`, `.s19`, `.s28`, `.s37`, `.rom`, `.fw`, `.dfu`, `.img` or `.ugw` firmware file in the installation. This limited negative result does not exclude an embedded or proprietary container. No working complete controller-ROM/flash readout path was established either.

## 4. GFA metadata must be filtered by burner variant

The exact VDensHO1 join still contains 581 events, including **94 distinct GFA_READ events across several burner variants**. It is incorrect to treat all 94 as one universal local register list.

The SQL group/display-condition join reveals these branches:

| Event group | Variant | Required P80 chip ID | Group entries |
| ---: | --- | --- | ---: |
| 18635 | CES | `0x23` | 58 |
| 18659 | GFA | `0x20` | 36 |
| 18683 | SCOT | `0x21` | 60 |
| 18707 | DOVER | `0x22` | 35 |

These group counts overlap; they must not be added to infer the 94-event union.

Selection is based on event **8258**, `VSKO_Scot_CES_P80~0x4050`, despite that token's historical name. Enum value 32 is labelled `20h - GFA`, 33 SCOT, 34 Dover and 35 CES. This identifies a protocol variant, not an exact MCU manufacturer/model.

### Display-condition polarity was verified, not guessed

Condition groups 3511, 3536, 3561 and 3586 target the four groups above. Conditions 10163, 10238, 10313 and 10388 compare event 8258 with enum rows 13187, 13183, 13184 and 13186 respectively.

Their stored operator is **1 = NotEqual**, not Equal. Group type **2 = OR** combines exclusion conditions. `DisplayConditionFilterBL::FilterEventTypeGroup` returns a filtering decision, and `EventGroupCacheBL::UpdateDisplayState` negates that decision before setting Display. Therefore the GFA branch is hidden when P80 differs from 0x20, and retained when it equals 0x20, subject to other applicable UI state.

Source: `MobileClient_ecnCommon.dll.il` operator enum around lines 8066-8076; `MobileClient_ecnCore.dll.il`, `ConditionGroupType` 793880-793886, `CheckConditions` 11764-11936, `FilterEventTypeGroup` 12809-12900 and `UpdateDisplayState` 23348-23417.

Previous hardware evidence `Virtual_READ 0x7650 = 0x20` is consistent with the GFA branch. However, Vitosoft selects it using **GFA_READ P80 at 0x4050**. That value must be confirmed through the recovered GFA path rather than silently equating two address spaces.

### Critical P09 correction

| Event | Address | Variant use | Meaning / scaling |
| ---: | --- | --- | --- |
| 8175 | `0x4006` | GFA branch included | Actual fan speed, raw x 30 rpm |
| 8259 | `0x4009` | GFA / Dover | **Modulation setpoint**, raw x 0.3922 percent |
| 8178 / 8233 | `0x4009` | CES / SCOT | Fan speed setpoint, raw x 30 rpm |
| 8179 | `0x400A` | GFA branch included | Fan PWM setpoint, raw x 0.4 percent |

Consequently, the previous blanket statement `0x4009 = blower speed setpoint x 30 rpm` is not valid for the expected local GFA variant. P06 remains the leading real fan-RPM target. Preserve Vitosoft's declared 0.3922 factor for P09 instead of silently substituting a different calibration. A modulation command is not an independently measured thermal-power value.

### Startup parameters excluded from the expected GFA branch

P17 flame-formation time at `0x4011`, C11 at `0x000B`, C13 at `0x000D` and the previously discussed C08 interpretation at `0x0008` are not members of group 18659. They occur in other burner branches. Their membership in the broad 581-event union was insufficient to present them as applicable local WB2A parameters.

The GFA branch's configuration entries are C00 gas type, C01 cascade configuration and C02 offset-reference checking. They are read-only in the extracted definitions. No start-safety adjustment is proposed.

The remaining live targets include P80-P83 identity/version/configuration, P84 operating phase and P85-P88 status bytes. The inspected metadata provides no value table for the P84 phase or these status bytes; vendor phase names and bit meanings must not be invented.

## 5. VSKO / VS1 transport: implementation confirmed, hardware test pending

The full IL supports the earlier protocol-switch model and adds the lifecycle context:

1. Vitosoft saves request/handler state, stops or quiesces normal processing and switches the interface to VS1 for VSKO.
2. The transition uses EOT `0x04`, waits for controller ENQ `0x05`, and uses the VS1 synchronization/STX `0x01` sequence.
3. Its abstract GFA_READ code `0xC9` becomes VS1 command `0x6B`.
4. A one-byte read has the form `6B address-high address-low 01`; replies are handled by expected raw byte count.
5. Leaving VSKO restores the earlier interface and processing state. The VS2 initialization sequence is `16 00 00`.

The distinction explains why sending a GFA command inside an ordinary active VS2/P300 session is not the same operation.

Primary methods in `MobileClient_vsmInterfaceCore.dll.il`:

- `VS1Message::getVS1MessageFromLDAPMessage`, lines 429-590;
- `VS1::createVS1Connection`, lines 1139-1281;
- `VS1::sendVS1Message`, lines 1283-1510;
- `VSManager::StartCommunicationVS1` and `ChangeInterface`, around 6629-6800 and 8312-8412;
- `VSMSDK::IsSDKCommandRunnable`, VSKO entry/exit around 18348-18590;
- `RequestCreator::CheckSDKCommandState`, lines 106526-106600.

This is **host-implementation evidence**, not a successful local GFA read. A future prober must exclusively own the serial port, pause the normal splitter before switching, restore P300 on success and on failure, then restore the service. It must not coexist with normal MQTT/TCP polling during the switched session. Do not add GFA_WRITE or process writes.

Recommended first read order: P80 identity; then, only with the matching variant, P06 actual RPM, P09 modulation command, P10 PWM and P84 phase. Record raw replies as well as decoded values. The previously disproved `0x55D3[6:7] = rpm` mapping remains prohibited.

## 6. Pump-address properties resolve to Neptun hydraulic calibration

The previously promising abstract properties in `ViessmannCommonObjects.dll` now have concrete constants:

| Purpose | Address family |
| --- | --- |
| Hydraulic calibration state | `0x7950` |
| Internal pump state/speed | `0x7951`, speed in byte 1 of a two-byte object |
| Other pump/valve calibration objects | `0x7953..0x7959` |
| Heating-circuit pump 1/2/3 calibration | `0x795A`, `0x795C`, `0x795E` |
| Mixer calibration | `0x7960`, `0x7961` |
| Generic min/reduced/max heating-pump settings | E7 / E9 / E6 paths |

Source: `MobileClient_ViessmannCommonObjects.dll.il`, `Constants.HydraulicCalibration`, lines 7367-7399.

Event 8339, `Neptun_Interne_Pumpe_Drehzahl~0x7951`, is a real Virtual_READ/Virtual_WRITE definition. Its device membership is later VScotHO1 variants, VSorp and Vitovalor, **not base VDensHO1**. The machine-readable evidence retains the specific member names.

This lead has now been followed through the protected FlowCalibration layer and the unprotected MobileClient host integration. The production FlowCalibration binary is version 4.0.11.1 (SHA256 `bd8b8ad3a1e6bf8959246167037ba81366bfb77f41b5ecf5d20c14c9ee6c017f`); the second protected state is an explicit test build 4.0.7.1. ILSpy exposes public metadata but not the protected numerical algorithm.

More importantly, `MobileClient.exe` resolves the complete surrounding workflow. It starts/stops Neptun hydraulic calibration at `0x7950`, reads `0x7688/0x0C24/0x0C26`, and for supported VD3XX scenarios writes calculated results to KD3/KD4 and the already known E6/E7/E9 controls. The result writer explicitly rejects `NichtVD3xx`.

Collector-v6 device membership confirms that `0x7950`, `0x7951`, `0x7688`, `0x0C24`, `0x0C26` and the wider `0x7953..0x7961` Neptun group are linked to later VScot/VSorp/Vitovalor profiles, not base VDensHO1. The base VDensHO1 does retain the normal GWG E6/E7/E8/E9 objects.

Therefore FlowCalibration is now closed as a source of a **new demonstrated volatile WB2A pump override**. Do not write `0x7950/0x7951` on the WB2A or treat calibration mode as normal runtime control. Existing measurements still distinguish A1 demand (`0x7663`) from the final internal-pump command (`0x0A3C`, correlated with `0x7660[1]`). The selector between them remains a controller-side/firmware question.

Detailed follow-up: [flowcalibration-hydraulic-2026-09-24.md](flowcalibration-hydraulic-2026-09-24.md).

## 7. E7 storage semantics and EEPROM status remain unresolved

The exact event-1016 description of `0x778B` says that status is periodically set and can be read and **only reset**, explaining its zero minimum/maximum. It does not define this object as an EEPROM-write counter or a transient write-busy pulse.

`0x778E` still has no extracted bit/enum definition. The earlier observed baseline 0x03 is not evidence of a Boolean EEPROM fault. Low-level fields may contain a generic write function even where AccessMode is Read; a function name alone is not permission to write a diagnostic object.

The previous E7 100 -> 99 -> 100 test established readback and successful restoration, but not RAM-only behavior, persistence policy, EEPROM endurance or a safe per-burner-cycle write rate. Unchanging 0x778B/0x778E cannot settle those questions.

Vitosoft's event optimization and multi-request handling concern host-side request aggregation/caching. They must not be presented as firmware EEPROM wear leveling or delayed nonvolatile commits.

**Consequence:** dynamic flame-by-flame E7 rewriting is still not justified as the final policy. A dedicated volatile path or independently established storage behavior is needed. The archive does not replace that missing evidence.

## 8. The enticing KM-BUS/LON system-block name is an LON RPC collection

`OptolinkHandler::rpcA010` constructs the named block `sysblock_KMBus_LonMemberList` from 16 events `Teilnehmerliste_LON_00` through `_15`.

Their source-defined access is:

```text
address:      0xA010
function:     Remote_Procedure_Call
prefixes:     00 through 0F
block length: 6
value length: 2
conversion:   HexByte2DecimalByte
```

Source: `MobileClient_vsmInterfaceCore.dll.il`, `OptolinkHandler::rpcA010`, lines 96739-96895; corresponding low-level event definitions and `RPCConverter::convertRPC_A010_Teilnehmerliste_LON`.

Therefore the word KMBus in the block name is not enough to bind it to `KBUS_MEMBERLIST_READ = 0x5D`, enumerate the physical internal pump/Vitotrol bus, or inject slave telegrams. `KMBusEquipment` is also present as an equipment-type enum, not by itself a transport implementation.

The controlled A0-only Vitotrol failure and the existing physical KM-BUS emulator reference remain the current state. No source-supported Optolink-only raw Vitotrol injection method was established by this pass. The physical emulator, ordinary virtual participant diagnostics, LON RPCs and legacy KBus gateway functions must remain separate workstreams.

## 9. Software identity and coding-plug diagnostics

Earlier local hardware results remain:

```text
0x778C / 0x778D = 01 / 03  raw regulation-version pair 0x0103
0x00FB         = 03       device software index
0x7330[0]      = 01       programming-unit software index
0x0A54[3]      = 01       internal-pump software index
```

The SQL selection range does not supply an official release-name/display-format mapping for 0x0103. Main regulation, GFA, programming unit, pump, Vitosoft data definitions and coding-card revision must remain distinct.

The expected GFA branch adds source-defined read-only coding-plug diagnostics:

| GFA address | Purpose |
| --- | --- |
| `0x405A` | P90 coding-plug FA type |
| `0x4064` | P100 minimum-power representation, declared factor 0.3922 |
| `0x4065..0x4066` | VI coding-plug identity fields |
| `0x4067..0x4069` | Separate day/month/year fields |
| `0x406A` | P106 coding-plug CRC diagnostic value |
| `0x406B..0x406C` | FA40/FA41 identity fields |

All require variant and hardware validation. A one-byte CRC diagnostic does not reveal the physical plug checksum algorithm, memory offsets, writable image format or recovery procedure. Separate date fields do not turn the existing raw revision `2015:0201` into a calendar date.

The two spare coding plugs and the available programmer remain useful for a later read-only bench comparison after exact chip, voltage and pinout identification. No full physical coding-plug dump or supported modification path was recovered in this archive. `KMBUS_EEPROM_READ` still must not be renamed a coding-plug dump merely because its name contains EEPROM.

## 10. Time programs: source-backed representation for a future editor

Exact VDensHO1 weekly events include:

| Event | Address | Program |
| ---: | --- | --- |
| 7191 | `0x2000` | A1/M1 heating |
| 7192 | `0x2100` | Domestic hot water |
| 7193 | `0x2200` | Circulation |

The definitions provide Virtual_READ/Virtual_WRITE and a 56-byte weekly representation: seven days, eight bytes per day, four on/off pairs per day. MappingType 1 / PhaseCT and the descriptions identify the 5+3 time encoding.

`CircuitTimesConverter::ConvertFromTime53` and `ConvertToTime53` in `MobileClient_ViessmannCommonObjects.dll.il`, lines 4507-4589, establish:

```text
normal time byte = (hour << 3) | (minute / 10)
0xC0 = 24:00
0xFF = unused / no time, not midnight
```

The vendor decoder is permissive for some noncanonical bytes. An editor should validate canonical times rather than reproduce that permissiveness. A strict offline round-trip check passed for 00:00 through 24:00 in ten-minute increments plus the unused value (146 values).

This supports designing an offline editor/validator. It is not a live write test, proof of atomic weekly updates, or permission to overwrite a user's programs without backup. Before enabling writes, verify weekday/slot ordering against the existing dashboard, preserve the full raw week, test read-after-write and recovery, and exclude overlapping/invalid intervals according to verified controller behavior. The production dashboard remains unchanged/display-only in this analysis.

## 11. A5/A6 explanation and operational distinctions

Exact event 1075 describes A5 as a room-setpoint-relative heating-pump switching boundary. For settings 1..15:

```text
pump-off boundary: outdoor temperature > room setpoint + (6 - A5) K
A5 = 0 disables this HPL function
```

Example: A5=5 corresponds to outdoor temperature exceeding room setpoint +1 K. The generic A5 wording alone does not resolve which internal outdoor-temperature filtering stage is used.

Exact event 1078 describes A6 as a fixed threshold for **damped outdoor temperature**: at the configured 5..35 degrees C threshold, the heating-circuit pump is turned off and that heating circuit does not request heat from the boiler controller. A6=36 disables the function.

Important dashboard wording: A6 suppresses the affected circuit's heating request; it is not evidence that DHW or every other possible boiler request is globally disabled. A5 is not a fixed outdoor-temperature limit independent of the room setpoint. The extracted text does not settle every priority interaction or frost-protection exception.

## 12. What did not become resolved

The archive does not by itself settle:

- the exact cause of the observed approximately 12-second post-flame interval, its safe adjustability, or the physical explanation of every modulation transition;
- the complete OPT ramp timing, extra `0x55E0` bits or every RKR state;
- an independently measured thermal-kW mapping for modulation;
- a volatile burner-selective WB2A pump override or E7 endurance;
- a working WB2A firmware flasher, full firmware dump, or exact board/MCU architecture;
- physical coding-plug offsets/checksum/write recovery;
- Optolink-only Vitotrol slave injection;
- the unexamined methods in protected FlowCalibration binaries.

Existing hardware results still support a separate DHW pump path, the importance of heat removal during startup and the distinction between startup failure and ordinary minimum-load cycling. This pass does not justify altering flame-safety behavior.

## 13. Reproducibility and next actions

For the SQL findings, join the exported tables by CompanyId as well as their IDs: `ecnDatapointType`, `ecnTableExtension`, `ecnTableExtensionValue`, `ecnEventTypeGroup`, `ecnEventTypeEventTypeGroupLink`, `ecnDisplayConditionGroup`, `ecnDisplayCondition` and `ecnEventValueType`. Resolve event access using the retained production XML/normalized low-level rows. Preserve group membership and display-condition polarity, not only addresses.

For the method findings, use the original IL line numbers and class/method names above. The raw archive hash and individual binary hashes bind the findings to a reproducible source snapshot. Publish only small derived maps, hashes, original tools and explanations; not full proprietary decompilations, databases, credentials or personal machine inventory.

Priority order after this analysis:

1. Build and review an exclusive-port, read-only VS1/VSKO prober with guaranteed service/interface restoration; confirm P80 before selecting the register interpretation.
2. Capture P06/P09/P10/P84 across a natural burner start if the identity test succeeds.
3. Keep pump-policy and E7 persistence work open; do not substitute Neptun, WILO or rejected legacy codings.
4. Treat firmware SQL searching as completed for this snapshot; move remaining acquisition questions to a specific new source or board/MCU identification rather than repeating the same empty-table query.
5. Develop time-program validation offline before enabling any writes.
6. Continue selective protected-assembly or physical coding-plug investigation from the preserved raw sources, without rerunning the entire collector merely because one analysis stage is incomplete.

No production profile, dashboard, controller parameter or live appliance state was changed for this report.
