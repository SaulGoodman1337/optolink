# VitoTest V1.8 static function classification — 2026-09-26

## Scope

Static classification of the preserved historical OpenV VitoTest V1.8 binary.
The purpose is to separate protocol functions that are safe and already
hardware-verified on the local VDensHO1/20C2 from read-like but unverified
functions, writes, and simulator-only behavior.

Artifact:

- research/artifacts/vitotest/VitoTest_V1.8.zip
- extracted VitoTest.exe SHA-256:
  b4792e59cce7115fc75322fd921ac3886bb304d542dc249ba0586412b813c4a6

No undocumented request was transmitted during this classification.

## V1.8 user-visible protocol surface

The executable contains UI strings for protocol selection KW, 300er, GWG,
serial-port selection, synchronization/restart synchronization, manual Send,
hexadecimal output, and saving the input/send list.

This confirms that VitoTest is primarily a raw/manual protocol test client with
several protocol-aware synchronization paths, not a semantic firmware dumper.
## Embedded device IDs and default request templates

The V1.8 data section contains these four device IDs consecutively:

~~~text
20 94
20 98
20 B8
20 53
~~~

Thus 2098 is explicitly present in V1.8's static device data.

Immediately following those IDs are three fixed request templates:

~~~text
41 05 00 01 00 F8 02 00    P300 Virtual_READ 00F8/2
01 F7 00 F8 04             VS1/KW Virtual_READ 00F8/4
01 C7 F8 04 04             GWG Virtual_READ F8/4
~~~

This is strong evidence that V1.8 knew the normal identification request in all
three protocol families. It does not establish a low-level memory service on
2098 or 20C2.

## Built-in simulator/responder dispatcher

A compact fixed dispatcher exists at approximately 0x403A44..0x403C7B.
It matches incoming request bodies and emits canned responses. These patterns
are simulator behavior and must not be mistaken for hidden VitoTest client
functions.
| Incoming request body | Static action | Classification |
| --- | --- | --- |
| C7 F8 02 | sends two-byte GWG ID 20 53 | read-like simulator case |
| F7 00 F8 02 | sends two-byte V333MW1 ID 20 B8 | read-like simulator case |
| F7 75 61 0A | sends ten-byte empty error list | read-like simulator case |
| CB BD 01 | canned reply C1 | Physical_READ-style simulator case |
| CB 2F 01 | canned reply F8 | Physical_READ-style simulator case |
| C7 FB 01 | canned reply 2B | Virtual_READ-style simulator case |
| CB 3F 01 | canned reply 00 | Physical_READ-style simulator case |
| CB 9B 03 | canned three-byte zero response | Physical_READ-style simulator case |
| C8 7F 01 42 | canned acknowledgement 04 | **write request; do not send** |

The dispatcher also strips a leading 01 before evaluating the request body,
consistent with the GWG/VS1 framing observed elsewhere.

Notably, this dedicated fixed dispatcher contains no recovered cases for
C5, AE, 9E, 6E, 33, or 43.

Opcode-looking constants elsewhere in the large MFC binary are not sufficient
evidence by themselves because they occur in generic library/control code too.
## Production classification for the local 20C2

| Function | Wire family | Local 20C2 status | Production policy |
| --- | --- | --- | --- |
| Virtual Read F7 | VS1/KW | **hardware verified** | allowed on known addresses |
| GFA Read 6B | VS1/KW | **hardware verified** | allowed on known GFA addresses |
| Virtual Read 01 | P300 | **hardware verified** | allowed on known addresses |
| KMBUS RAM Read 41 | P300 | **hardware verified** | known bounded reads only |
| KMBUS EEPROM Read 43 | P300 | **hardware verified** | known bounded reads only |
| GWG Virtual Read C7 | GWG | proven on 2098 identification, not local 20C2 | dry-run only on 20C2 |
| GWG Physical Read CB | GWG | old GWG simulator/config evidence only | do not blind-test on 20C2 |
| GWG XRAM Read C5 | GWG | no exact-family success recovered | do not blind-test |
| GWG EEPROM Read AE | GWG | no exact-family success recovered | do not blind-test |
| GWG Bedienteil Read 9E | GWG | semantics resolved, no exact-family success | do not blind-test |
| GWG Port Read 6E | GWG | logical-port semantics on old GWG | do not blind-test |
| GWG Physical Write C8 | GWG | write opcode; simulator contains one case | **blocked** |
| other documented GWG writes | GWG | write operations | **blocked** |
| unknown opcode/function | any | unknown | **blocked** |

The VitoTest evidence therefore does not open the workstream-2 gate.
## Consequences for firmware-read research

The V1.8 binary narrows the search rather than expanding the live-test surface:

1. VitoTest explicitly supports 2098 in its static device data.
2. Its visible/default identification paths remain ordinary 16-bit KW/P300 and
   one-byte GWG identification reads.
3. The embedded GWG responder knows several CB physical-address examples and
   one C8 write example, but no ROM/flash/page/bank/copy service was recovered.
4. No dedicated C5/AE/9E/6E/33/43 simulator case is present in the recovered
   fixed dispatcher.
5. Therefore VitoTest V1.8 does not currently provide evidence for the missing
   20-bit M30612 program-ROM bridge.

Current gate remains:

~~~text
Workstream 2: CLOSED

No source-backed selector/monitor/copy sequence
and
no successful relevant low-level memory read on 2098/20C2.
~~~

The next high-information path remains firmware/static analysis or recovery of
a private historical service sequence, not broader production-device fuzzing.