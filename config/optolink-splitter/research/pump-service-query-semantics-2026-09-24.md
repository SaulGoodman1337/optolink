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

## TODO

- Recover the conversion/value table for Vitosoft event 885 K30_KennungIntPumpeKM.
- Determine whether the service manufacturer display is a conversion of event 885 or is assembled from additional pump-participant data.
