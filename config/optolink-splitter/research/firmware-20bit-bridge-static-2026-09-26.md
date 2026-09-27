# Firmware 20-bit bridge static reconstruction — 2026-09-26

Status: **static/source analysis only; no new live request in this workstep**

## Question

The locally verified P300 `Physical_READ / 0x03` gives a distinct 16-bit
physical/service address space. Program ROM/flash on the relevant M16C families
is above 64 KiB. This pass asks which recovered host-side mechanism can carry
the missing high address or invoke a controller-side proxy.

## Hard host-model boundary

Recovered Vitosoft core declares:

~~~text
EventType.Address : ushort
MultiRequestDictionary.pAddress : ushort
LDAPMessage(... pAddress, pDataLength, blockData ...)
~~~

Normal Vitosoft event addressing is therefore structurally 16-bit. No recovered
serializer computes `Address >> 16` or `Address >> 24`.

Consequently a 20-bit firmware address cannot be represented by
`EventType.Address` alone. A bridge must use separate request payload bytes,
persistent selector state, or a dedicated controller-side service.
## Positive architectural precedent: fixed-endpoint address proxy

The recovered `VitosorpAccessController` RPC converter implements a genuine
proxy pattern.

Read side:

~~~text
original 16-bit target address
       |
       +--> payload = target_hi, target_lo, requested_length
       |
RPC endpoint = 0xA400
~~~

Exact recovered behavior:

~~~text
bytes = BitConverter.GetBytes(eventType.Address)
eventType.Address = 0xA400
BlockDataToDevice = { bytes[1], bytes[0], length }
~~~

The corresponding write endpoint is `0xA401`.

This proves that Viessmann host/controller architecture supports fixed service
endpoints which carry a secondary address inside the payload. It does **not**
solve the firmware problem because this specific proxy forwards only a
16-bit target and no captured event on the target families uses it.

A 20-bit firmware monitor could nevertheless use the same architectural
pattern with an additional page/high-address byte.
## RPC payload capacity

The generic RPC read converter copies `PrefixRead` bytes verbatim into
`BlockDataToDevice`; the generic LDAP message constructor then sends that
byte array after the ordinary function/address/length fields.

Thus the P300/LDAP transport can carry selector/address bytes beyond the
16-bit event address. The missing bridge is not constrained by frame capacity;
it is constrained by the absence of a recovered endpoint and payload meaning.

Global current Vitosoft metadata contains 1,010 RPC read rows. PrefixRead
lengths are:

| PrefixRead payload | Rows |
| --- | ---: |
| empty | 114 |
| 1 byte | 863 |
| special textual `0xNN` reset values | 3 |
| 3 bytes | 30 |

All actual 3-byte RPC PrefixRead rows belong to the M-Bus data-header service
at `0xA095` (patterns such as `00 00 00`, `00 01 00`,
`01 00 00` ...). No second 3-byte RPC service in the recovered event
catalogue is a ROM/flash/page/bank monitor.

Therefore multi-byte selector payloads are an established mechanism, but the
catalogued examples do not expose program memory.
## Exact V200KW2 / 2098 RPC surface

The recovered exact 2098 profile has 465 unique event rows:

~~~text
FCRead:
459 Virtual_READ
  4 Remote_Procedure_Call
  1 undefined
  1 blank
~~~

The four RPC rows are only:

- three Bedienparameter reset operations at `0xA051`, prefixes
  `00`, `01`, `02`;
- `RPCWink~0xA000`.

`RPCWink` uses RPC handler 22 = `RPCWriteStandard`. The recovered
serializer clears its payload and uses block length zero for the write path.
It is not a hidden address-bearing selector.

No exact 2098 event exposes a page/high-address payload.
## Physical_READ catalogue versus actual 20C2 implementation

The complete current Vitosoft metadata contains 78 `Physical_READ` rows,
51 unique addresses:

~~~text
minimum address: 0x20
maximum address: 0xDD
maximum block length: 3
rows with PrefixRead: 0
~~~

The catalogue therefore uses Physical_READ only as a compact low-byte service
map.

This is materially narrower than the real local 20C2 implementation already
measured through P300 function `0x03`:

~~~text
0x0400 / 16  -> success, dynamic internal state
0x53F0 / 16  -> success, stable 16-byte block
0xF000 / 16  -> success
0xFFF0 / 16  -> success
~~~

The controller consequently accepts a much wider 16-bit Physical_READ address
space than Vitosoft's event catalogue documents.

This is the strongest current reason not to equate catalogue absence with
controller absence.
## Programming/ROM vocabulary found elsewhere

Recovered metadata contains real programming-oriented concepts on other
controller families, for example:

- calculated ROM checksum `0x08F0`;
- linker ROM checksum `0x08F4`;
- programming-position flags;
- virtual-to-RPC programming-position conversions.

Their recovered memberships are VBC550S/VBC550P or old GWG families, not
VDensHO1/20C2 or V200KW2/2098. They are architectural precedents only.

No recovered host-side method named or behaving like a generic
ROM/flash/page/bank/copy monitor is linked to the two target families.

## Current bridge model

The evidence now favors this shape:

~~~text
Optolink P300/LDAP
  |
  +-- ordinary 16-bit address ------------------------+
  |                                                   |
  +-- optional request payload / selector bytes       |
                                                      v
                                            controller service
                                                |
                         +----------------------+-------------------+
                         |                                          |
                  16-bit Physical_READ                     private monitor/proxy
                         |                                          |
                  RAM/service window                    20-bit far ROM access
                                                                    |
                                                           low-memory response
~~~

The left-hand branch is hardware-verified. The right-hand branch is the
missing mechanism.
## What is ruled out by this pass

Do not spend live-test budget on these without new source evidence:

- treating the normal Vitosoft event address as 20-bit;
- assuming `RPCWink` is a firmware selector;
- assuming generic 3-byte PrefixRead means high address;
- treating the M-Bus `0xA095` three-byte prefixes as a ROM page service;
- attaching selector bytes to Physical_READ merely because the transport can
  carry them;
- interpreting the existing Physical_READ catalogue as the full controller
  implementation.

## Highest-value next static target

The next source question is now narrow:

> Find a controller-side or historical host sequence that combines a fixed
> service endpoint / selector payload with a subsequent readable low-memory
> window, or directly returns bytes from a 20-bit target.

Search priority:

1. raw `LDAPMessage` constructors outside normal event serialization where
   request data contains address-like bytes;
2. fixed endpoints that rewrite an original address, analogous to A400/A401;
3. monitor/copy/mailbox semantics in older OpenV/private-source remnants;
4. controller traces where a setup request is immediately followed by repeated
   Physical_READ of the same low 16-bit window.

Until one of those appears, no guessed selector/payload should be sent to the
production controller.