# FlowCalibration / hydraulic-calibration host analysis - 2026-09-24

## Scope

This note closes the current offline investigation of Vitosoft's protected
`FlowCalibration` path as a possible source of an undocumented volatile pump
override for the local Vitodens 200-W WB2A / base `VDensHO1`.

Source snapshot:

- private Collector v6: `vitosoft-private-archive-20260924-143439`;
- archive SHA256: `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`;
- analysis was static only; vendor binaries were not executed;
- only derived reports/hashes/conclusions are retained publicly.

Machine-readable evidence:
[flowcalibration-hydraulic-2026-09-24-evidence.json](flowcalibration-hydraulic-2026-09-24-evidence.json).

## Protected binaries identified

Collector v6 reported four blocked ILDASM paths representing two distinct
FlowCalibration binary states. They are now identified precisely.

| Build | Size | SHA256 | Version |
| --- | ---: | --- | --- |
| production / `Echt` | 660992 | `bd8b8ad3a1e6bf8959246167037ba81366bfb77f41b5ecf5d20c14c9ee6c017f` | 4.0.11.1 |
| explicit `Test` | 667648 | `4aa4af45b01223d23f461c769ee5a06067f7d105c9718f3d43e5c330c5f27ee3` | 4.0.7.1 |

The production hash occurs at the normal MobileClient path and at the GAC
copies including `FlowCalibration (Echt).dll`. Therefore the earlier
"two binary states" result is not an unexplained duplication: it is a
production 4.0.11.1 build plus an older explicit test 4.0.7.1 build.

ILDASM reports `Protected module -- cannot disassemble`. ILSpy can recover
CLR metadata and the public API but the protected core implementation bodies
remain effectively stubbed/obfuscated. The internal numerical calibration
algorithm is therefore still not recovered.

## What the public FlowCalibration contract actually does

The visible interface is a hydraulic-balancing/calibration API. Relevant
concepts include:

- learned and driven valves;
- desired volume flow and valve pressure loss;
- sensor measurements;
- result values `Restförderhöhe` and `MaxPumpendrehzahl`;
- an `IVSMCommunication` object used as the controller-data transport.

The MobileClient copy of `FlowCalibrationInterface.dll` is version 4.0.2.2,
SHA256
`7c108ab42971377a1b1254b0ac7be1349b3385817150f442a9633c7d4e11dbd1`.

The FlowCalibration heater-type enum contains explicit VD3XX variants and the
fallback value `NichtVD3xx = 9`.

## Communication interface recovered

`vsmCommunicationInterface.dll` is not protected:

- version 1.4.2.0;
- size 10752 bytes;
- SHA256
  `5514f4320f535f45db46c44a9d59d43c900b5bd2dd2e96362064df998ca6a83d`;
- named pipe: `vsmCommunicationPipe`;
- `CustomAppId.HydraulicCalibration = 1`;
- exposed process methods: `StartComProcess`, `StopComProcess`,
  `GetComData`;
- returned hydraulic value: `PressureDifference` plus `VolumeFlow`.

The actual implementation of that interface was found in `MobileClient.exe`,
not in a separately named pipe executable.

Relevant host binaries:

| Binary | SHA256 |
| --- | --- |
| `MobileClient.exe` | `f05e8ceef23eb94eaef0dca9c25ecbdd0fc83ae4e859d0fc7740f5bc78fd6136` |
| `ViessmannIPC.dll` | `e87f9c90f05df264a2e2302ae90bce9bdddd8bb84f2481393af4b733c3475c6a` |
| `ViessmannWebFrontend.Web.dll` | `387ce38f9ca27ca335548e6ca1953e1e46cbd2eaefb4ccc612e38fdbecb1aa11` |

## Exact host-side calibration path

The decompiled MobileClient host code resolves the previously opaque workflow.

### Start/read side

The external hydraulic-calibration process starts with the Neptun control:

```text
Neptun_Hydraulischer_Abgleich_Bytes~0x7950
Neptun_Hydraulischer_Abgleich~0x7950
```

The data returned to FlowCalibration is built from exactly three event types:

```text
0x7688  Neptun_ParamFoerderhoehe
0x0C24  Neptun_Durchfluss_STRS1
0x0C26  Neptun_Skalierung_Durchfluss
```

The host conversion is:

```text
PressureDifference = UInt16(value from 0x7688)

VolumeFlowRaw = float value from 0x0C24
Scale         = int value from 0x0C26

if Scale > 0:
    VolumeFlowRaw /= 10 ** Scale

VolumeFlow = UInt16(VolumeFlowRaw)
```

This is the concrete implementation behind
`IVSMCommunication.GetComData(CustomAppId.HydraulicCalibration)`.

### Result-write side

`SendHydraulicCalibrationResult()` resolves these controls:

```text
0x27D3  KD3  heating-curve slope A1
0x27E6  E6   maximum A1/M1 pump speed
0x27D4  KD4  heating-curve level A1
0x27E7  E7   minimum A1/M1 pump speed
0x27E9  E9   reduced A1/M1 pump speed
```

The values are sourced as follows:

```text
0x27D3 <- calibration result Pitch
0x27E6 <- calibration result MaximalPumpSpeed
0x27D4 <- scenario climate configuration Niveau
0x27E7 <- Vitosoft HydraulicCalibration.MinPumpSpeedVD3XX
0x27E9 <- Vitosoft HydraulicCalibration.MinPumpSpeedReducedVD3XX
```

This independently confirms that E6/E7/E9 are normal Vitosoft pump
configuration controls. It does **not** introduce a new runtime pump address.

## Critical applicability gate

Before the result controls are written, MobileClient calls
`GetFlowCalibrationHeaterType()`.

Named FlowCalibration heater types are returned only for:

- controller type `Boiler_WithOptolink`;
- heating circuit A1;
- scenario category `VD3XX`;
- a supported VD3XX 300/333/343 device type.

Every other scenario returns `NichtVD3xx = 9`.

`SendHydraulicCalibrationResult()` explicitly rejects that value and logs
that a VD3XX heater type was expected. Therefore the automatic result-write
path above is a **VD3XX path**, not evidence that Vitosoft performs those
calibration writes on the local WB2A.

There is still a broader service model in `ViessmannIPC.dll`:

```text
Category.VD2XX_VP200_Vitoladens
Type.VD2XX_Vitodens_200W
```

Such a scenario maps to `HeaterType.NichtVD3xx`. When the FlowCalibration
library itself is started for that fallback type, Vitosoft supplies the
parameter:

```text
dp = HydraulicCalibration.DeltaP
```

This demonstrates a generic/non-VD3xx hydraulic-calculation mode, but it does
not enable the VD3XX result-write workflow.

The pump-choice enum `GF_Alpha2 / Wilo_Yonos / Wilo_Stratos` is used by the
IPC model for Divicon scenarios; it is not an internal WB2A-pump selector.

## Collector-v6 device membership closes the WB2A question

The complete v6 All-Devices graph was filtered against all addresses used by
this workflow.

### Linked to base VDensHO1

The existing A1/GWG controls are valid base-VDensHO1 events:

```text
0x27D3  KD3
0x27D4  KD4
0x27E6  E6
0x27E7  E7
0x27E8  E8
0x27E9  E9
```

The E6/E7/E8/E9 GWG variants are one-byte `Virtual_READ / Virtual_WRITE`
objects. This agrees with the project's existing local E7 tests.

### Not linked to base VDensHO1

Every Neptun/HydraulicCalibration object used by the host workflow is absent
from base VDensHO1 membership:

```text
0x0C24  Neptun_Durchfluss_STRS1
0x0C26  Neptun_Skalierung_Durchfluss
0x7688  Neptun_ParamFoerderhoehe
0x7950  Neptun_Hydraulischer_Abgleich
0x7950  Neptun_Hydraulischer_Abgleich_Bytes
0x7951  Neptun_Interne_Pumpe
0x7951  Neptun_Interne_Pumpe_Drehzahl
0x7953..0x7961  Neptun pump/valve/mixer calibration family
```

Their linked appliance profiles are later `VScotHO1_70/72/90/200*`,
`VSorp` and `Vitovalor`, not base `VDensHO1`.

For example:

- event 8326, `0x7950`: Virtual_READ / Virtual_WRITE, base VDensHO1 false;
- event 8339, `0x7951`: two-byte object, speed byte at position 1,
  Virtual_READ / Virtual_WRITE, base VDensHO1 false;
- event 8370, `0x7688`: two-byte Virtual_READ / Virtual_WRITE,
  base VDensHO1 false;
- event 8320, `0x0C24`: two-byte Virtual_READ, base VDensHO1 false;
- event 8335, `0x0C26`: one-byte Virtual_READ, base VDensHO1 false.

## Conclusion for the WB2A pump research

FlowCalibration is **not a newly demonstrated volatile pump-control path for
the local WB2A**.

That conclusion does not rely on profile membership alone. The project already
has the counterexample `0x0A3C`, which is live-readable despite lacking a
normal profile link. Here the evidence is stronger because:

1. the host's result-write path explicitly rejects `NichtVD3xx`;
2. the entire Neptun read/write group used by the calibration transport is
   absent from base VDensHO1 membership;
3. the only pump controls shared with base VDensHO1 are the already known
   configuration objects E6/E7/E8/E9;
4. no new address between those configuration values and the final
   `0x0A3C ~= 0x7660[1]` command shadow emerged.

Therefore:

- do **not** write `0x7950`, `0x7951` or the other Neptun calibration
  objects on the local WB2A;
- do not treat FlowCalibration's `MaxPumpendrehzahl` result as the hidden
  runtime selector;
- E7 remains a proven effective service/configuration path, but its
  persistence/endurance issue remains unchanged;
- the hidden selector upstream of `0x0A3C` remains a controller-firmware
  question unless another WB2A-specific host object is found.

## Status

The FlowCalibration host-integration workstream is now **closed for the
specific question "does it expose a new WB2A volatile internal-pump override?"**

The protected numerical calibration algorithm itself is still not fully
recovered, but recovering it is no longer a priority for the current WB2A pump
goal because the surrounding host/device applicability boundary is already
sufficiently resolved.
