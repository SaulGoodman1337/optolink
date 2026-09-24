# KMBUS_RAM_READ 0x41 correlation probe - 2026-09-24

Status: **ready for first live run**
Tracking: GitHub issue **#30**

## Purpose

Determine whether the locally verified VS2/P300 function
`0x41 KMBUS_RAM_READ` is:

1. a broad alias/mirror of ordinary `Virtual_READ`,
2. a partially overlapping logical controller/KM-BUS memory view, or
3. a distinct address space whose overlap at `0x00F8` is special.

This is the first live phase of the KBus read-memory workstream.

## Safety

This probe is **read-only**.

It sends only:

- ordinary `Virtual_READ` requests;
- generic VS2 requests using function `0x41 KMBUS_RAM_READ`.

It performs:

- no writes;
- no address sweep;
- no EEPROM request;
- no KBUS/KMBUS write function;
- no burner/GFA write;
- no coding change.

Stop if the controller reports faults, Optolink becomes unstable, or any
unexpected state change is observed.

## Why these addresses

The first batch deliberately uses datapoints whose local meaning and exact
length are already established.

| Address | Length | Known local meaning | Why useful |
| --- | ---: | --- | --- |
| `0x00F8` | 8 | controller identity `20 C2 00 03 00 00 01 03` | positive control; 0x41 already known to match |
| `0x0A3C` | 1 | final internal-pump command shadow | high-value runtime selector output |
| `0x7660` | 2 | internal pump output/runtime block | dynamic internal-pump state |
| `0x7663` | 2 | A1 runtime/calculated pump request | upstream discriminator |
| `0x5730` | 1 | K30 internal-pump identity/capability | KM-BUS-related static object |
| `0x0A54` | 4 | internal-pump software-index block | KM-BUS participant identity structure |
| `0x27A0` | 1 | A1/M1 remote-control identification | independent KM-BUS participant object |

Exact lengths come from the VDensHO1 metadata and previous local reads.

## Request forms

Ordinary virtual read:

~~~text
r;<address>;<length>;raw;False
~~~

KMBUS RAM read:

~~~text
request;0x41;<address>;<length>;;0x00
~~~

The generic request is encoded by the splitter as a VS2/P300 request with
function code 0x41, the same 16-bit address and requested block length.

## First live command block

Run as one block on the optolink-splitter host:

~~~bash
DBG=/usr/local/bin/optolink-debug

pair_read() {
    label="$1"
    addr="$2"
    len="$3"

    echo
    echo "========== $label  $addr / $len =========="
    "$DBG" request "r;$addr;$len;raw;False"
    "$DBG" request "request;0x41;$addr;$len;;0x00"
}

echo "========== KMBUS RAM CORRELATION - START =========="
date -Is

pair_read "CONTROL identity"        0x00F8 8
pair_read "Pump final command"      0x0A3C 1
pair_read "Internal pump runtime"   0x7660 2
pair_read "A1 pump request"         0x7663 2
pair_read "Internal pump identity"  0x5730 1
pair_read "Internal pump SW block"  0x0A54 4
pair_read "A1 remote identity"      0x27A0 1

echo
echo "========== KMBUS RAM CORRELATION - END =========="
date -Is
~~~

Do not change operating state specifically for the first run. Record whatever
natural controller state is present.

## Classification

For each address classify the pair as:

| Class | Meaning |
| --- | --- |
| `IDENTICAL` | same successful payload from Virtual_READ and 0x41 |
| `DIFFERENT_STABLE` | both succeed but return different stable data |
| `DIFFERENT_DYNAMIC` | both succeed and difference changes between runs |
| `VIRTUAL_ONLY` | Virtual_READ succeeds, 0x41 returns protocol error/timeout |
| `KMBUS_ONLY` | 0x41 succeeds, Virtual_READ does not |
| `ERROR` | neither gives a usable result |

A return code of `1` is the normal successful response in the current
splitter stack. A return code of `3` is a controller Error Message and its
payload must not be interpreted as datapoint data.

## Decision after first run

### If nearly everything is IDENTICAL

0x41 is likely an alternate/mirrored access path for at least part of the
controller data model. The second run should then target **natural dynamic
transitions** (heating pump start, burner start, DHW) and compare timing rather
than immediately scanning new addresses.

### If static KM-BUS objects match but runtime objects differ

This is a high-value result. It would indicate a partially overlapping logical
memory space. Repeat the differing objects several times and correlate them
with the known pump process.

### If 0x41 fails on most addresses but succeeds at F8

Treat F8 as a special/common identity structure and do not generalize the
address space. Source-derived selectors/functions become the next priority.

### If 0x41 exposes additional successful data where Virtual_READ fails

Preserve the exact address/length/output. That would be direct evidence of a
hidden read namespace.

## Transport correction after first live run

The first live run was planned with the wrong production-transport assumption.

The local splitter is intentionally running permanent **VS1/KW** after the GFA
activation required for blower speed P06 and the other GFA diagnostics. In this
mode:

- normal controller datapoints use VS1 `F7 Virtual_READ`;
- GFA values use VS1 `6B GFA_READ`;
- `vs12_adapter.do_request()` deliberately rejects the generic VS2/P300
  `request` command;
- a P300 frame sent through `raw` is merely injected into the active VS1
  session and does **not** switch the protocol to P300.

The 22:08 journal confirms the intended rejection:

~~~text
request command not supported with VS1/KW, use raw instead
~~~

and both attempted P300 raw frames timed out in the active VS1 session.

Therefore those timeout runs are not evidence about 0x41 support or address
mapping. They are transport-context failures.

### Guarded helper

A dedicated helper is now versioned for exactly this situation:

~~~text
config/optolink-splitter/wb2a-kmbus-p300-read-probe.py
~~~

The updater installs it as:

~~~text
/usr/local/bin/wb2a-kmbus-p300-read-probe
~~~

It requires the normal production setting `vs1protocol=True`, pauses the
single VS1 serial owner, explicitly enters P300, performs only a fixed
allowlist of `0x01 Virtual_READ` and `0x41 KMBUS_RAM_READ` requests, then
restores the previously running services and requires the splitter journal to
show `VS1/KW protocol initialized` again.

Use the built-in offline gate first:

~~~bash
wb2a-kmbus-p300-read-probe --self-test
~~~

Only after that passes:

~~~bash
wb2a-kmbus-p300-read-probe --execute
~~~

The helper does not modify `settings_ini.py` and implements no controller
write function.

### Correct method for future 0x41 tests

`KMBUS_RAM_READ 0x41` is a VS2/P300 function in the current research model.
Future tests must use a bounded **temporary P300 maintenance window**:

1. confirm permanent production state is VS1/KW;
2. stop the Party emulator if running;
3. stop `optolink-splitter.service` so it releases the single serial owner;
4. open the Optolink serial device directly;
5. explicitly initialize P300/VS2;
6. run a normal P300 Virtual_READ positive control;
7. run only the allowlisted read-only 0x41 requests;
8. close the direct serial session;
9. restart `optolink-splitter.service`;
10. restart Party if it was active;
11. verify journal marker `VS1/KW protocol initialized`;
12. verify fresh GFA P80/P06/P09/P87 values.

Do **not** change `vs1protocol=True` permanently and do not feed P300 raw
frames through the live VS1 MQTT command path.

## Follow-up phases

Only after this first matrix:

1. repeat the small dynamic subset during a natural heating/DHW transition;
2. if useful, add a bounded repeat logger for `0x0A3C/0x7660/0x7663`;
3. separately reconstruct one complete Vitosoft-defined
   `KMBUS_EEPROM_READ` transaction including its `PrefixRead`;
4. do not start a 64-KiB sweep.

## Evidence to preserve

For the live run record:

- timestamp;
- controller operating state if known;
- complete stdout;
- response return code;
- response address;
- raw payload;
- classification per pair;
- any observed controller fault/state disturbance.

The result should be added to
`config/optolink-splitter/research/vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json`
and summarized in the canonical KBus research document.
