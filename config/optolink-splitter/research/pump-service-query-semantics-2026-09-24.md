# WB2A internal-pump service-query semantics - 2026-09-24

The exact WB2A service manual and Vitosoft expose different views of internal-pump identity.

## Service display

The service short query describes a pump-type display with:
- 0: none
- 1: Wilo
- 2: Grundfos

It also displays a software status for the speed-controlled pump.

## Vitosoft coding view

Vitosoft event 884 at 0x5730 is coding address 30 and uses:
- 0: staged
- 1: speed-controlled
- 2: speed-controlled with volume-flow information

The local value is 0x5730 = 01. In this coding context it proves only that the internal pump is speed-controlled.

Vitosoft also has event 885, named K30_KennungIntPumpeKM, in the diagnostic-system view at the same base address. Its value conversion must be kept separate from event 884 until the conversion table is recovered.

## Local software index

The already measured internal-pump block is:

```text
0x0A54 = 01 11 01 01
software-index field = byte 3 = 01
```

The installed physical pump is Grundfos G-HE / UPM3 with KM-BUS.

## Conclusion

Do not translate raw 0x5730 = 01 into manufacturer Wilo. Keep these evidence layers separate:
1. coding-30 pump capability;
2. service/diagnostic manufacturer display;
3. physical pump manufacturer.

This also keeps the earlier Virtual_WILO path closed for the local WB2A unless a direct event/function mapping is found.

## v6 value-list resolution

The Collector-v6 All-Devices metadata resolves the two events at the same raw byte as follows:

```text
event 884 K30_KennungIntPumpe:
  0 = stufig
  1 = drehzahlgeregelt
  2 = drehzahlgeregelt mit Volumenstrom

event 885 K30_KennungIntPumpeKM:
  0 = nicht vorhanden
  1 = vorhanden
  2 = drehzahlgeregelt mit Volumenstrom
```

Both use `Virtual_READ/Virtual_WRITE`, `NoConversion`, block length 1, byte position 0, and address `0x5730`. The semantic difference is entirely in the ValueList.

Therefore local raw `0x5730=01` means:

- **event 884 / coding 30:** speed-controlled;
- **event 885 / diagnostic view:** present.

It does **not** mean Wilo in either Vitosoft event.

The WB2A service short-query manufacturer display `0=none, 1=Wilo, 2=Grundfos` is therefore a third presentation that is not the event-885 ValueList. A documented WB2A/G-HE KM-BUS example reports short query 8 as `210000`, consistent with internal pump type Grundfos (`2`), pump software status `1`, and absent optional A1/M2 pumps.

## Remaining question

- Determine the controller data source used to assemble the service short-query manufacturer digit. It is not raw coding 30 and not the event-885 ValueList.
- Do not reopen Virtual_WILO based on `0x5730=01`; the local manufacturer remains established from physical pump evidence, not that byte.
