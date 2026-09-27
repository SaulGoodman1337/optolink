# High-address bridge static audit — 2026-09-26

Scope: Arbeitsschritt 2 only. Goal is to identify a source-backed mechanism that can carry more than 16 address bits, or an explicit selector/page/bank plus low 16-bit address. No live request was sent.

## Exact 2098/V200KW2 exceptional read surface

The recovered V200KW2/2098 event set contains only five non-ordinary FCRead rows:

| Event | Address | FCRead | Prefix | Meaning |
| --- | --- | --- | --- | --- |
| BedienparameterA1M1FunktionReset | 0xA051 | Remote_Procedure_Call | 00 | reset operation |
| BedienparameterM2FunktionReset | 0xA051 | Remote_Procedure_Call | 01 | reset operation |
| BedienparameterM3FunktionReset | 0xA051 | Remote_Procedure_Call | 02 | reset operation |
| RPCWink | 0xA000 | Remote_Procedure_Call | none | generic RPC wink, handler 22 |
| Oelverbrauch_Reset | 0x7574 | undefined | none | write-only reset object |

None exposes a target-address field, page/bank selector, ROM window, copy buffer or program-memory semantics.
## Address-width audit of recovered serializers

The V200KW2 serializer-focus export contains 108 targeted source contexts.

Searches were applied for:
- eventType.Address;
- BitConverter.GetBytes(...);
- bytes[2] / bytes[3];
- shifts by 16 or 24;
- PrefixRead / PrefixWrite;
- BlockDataToDevice construction.

Result:
- no serializer context combines eventType.Address with byte index 2 or 3;
- no recovered serializer shifts an address by 16 or 24 bits;
- the bytes[2]/bytes[3] hits are 32-bit *values* (for example impulse-counter / LON threshold values), not address bytes;
- MultiRequestDictionary stores event addresses in the ordinary event-address domain and does not construct a wider target.

This resolves the earlier serializer-summary flag `contains_address_byte2_or3=true`: the flag came from broad contextual matching and does not identify a 24/32-bit address serializer.
## Confirmed proxy architecture, but still 16-bit

The recovered VitosorpAccessController is a genuine fixed-endpoint address proxy:

~~~text
read endpoint: 0xA400
payload:       target_hi target_lo length
write endpoint:0xA401
payload:       target_hi target_lo data_len data...
~~~

Implementation uses only:
~~~text
bytes2[1]
bytes2[0]
~~~

from BitConverter.GetBytes(eventType.Address).

It is important positive architectural evidence that Viessmann uses address-in-payload services, but it remains strictly 16-bit and has no V200KW2/2098 event binding in the recovered catalog.

## Current conclusion

No recovered Vitosoft serializer or exact V200KW2 RPC row provides:
- a 20-bit/24-bit/32-bit target address;
- a high-address byte;
- a page/bank/window selector;
- ROM-to-RAM copy semantics;
- a program-memory read service.

Therefore no source-backed high-address bridge has yet been recovered, and no live selector/RPC probe is justified from this evidence.

The remaining likely forms are controller-private rather than catalog-driven:
1. a hidden application monitor/service not represented by Vitosoft events;
2. a selector stored in ordinary RAM/physical memory before a low-address read;
3. a ROM-to-RAM mailbox/copy routine;
4. a legacy/private GWG service sequence preserved only in old traces/source.

## Stronger type-level result

The decompiled Vitosoft core makes the normal event-address width explicit:

~~~text
EventType._Address : ushort
MRKey.MinAddress   : ushort
MRKey.MaxAddress   : ushort
BaseDataService    : eventType.Address = Convert.ToUInt16(item.Address, 16)
MultiRequest       : pAddress is ushort
~~~

This is stronger than an absence-of-pattern search. The ordinary Vitosoft EventType/MultiRequest path cannot represent a target address above 0xFFFF at all.

Therefore any genuine M16C program-ROM bridge must sit *outside* the normal EventType address field, for example:

- a selector/page value carried in request payload or PrefixRead;
- a fixed service endpoint whose payload contains an independent wider pointer;
- a controller-side mailbox/window whose selector is stored separately;
- a private monitor protocol not modeled as a normal Vitosoft event.

The recovered VitosorpAccessController is an example of the fixed-service-endpoint pattern, but its payload still serializes only the two bytes of the ushort event address.

### Reclassification of the serializer-summary flag

The previous `contains_address_byte2_or3=true` aggregate flag is not evidence of a wide address. Direct inspection shows that the relevant bytes[2]/bytes[3] operations belong to 32-bit *data values* such as counters/thresholds. No inspected method takes byte 2 or 3 from EventType.Address.

This closes the ordinary Vitosoft event/serializer path as the missing >16-bit carrier. Further Arbeitsschritt-2 effort should concentrate on independent selector/mailbox state or a private service protocol, not on finding a wider EventType.Address encoding.