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

## Transport diagnostic after first live run

The first live run could not reach the comparison phase because all generic
`request;...` calls timed out, including the positive 0x41 control.

A follow-up control established:

~~~text
service: active

r;0x00F8;8;raw;False
-> 1;0xf8;20c2000300000103

request;0x01;0x00F8;8;;0x00
-> timeout

request;0x41;0x00F8;8;;0x00
-> timeout
~~~

This is especially diagnostic because the current upstream splitter source
constructs **byte-identical VS2 telegrams** for these two requests:

~~~text
ordinary Virtual_READ 0x00F8/8
generic request fct=0x01 addr=0x00F8 len=8 protid=0 data=""
    -> 41 05 00 01 00 F8 08 06
~~~

Therefore the controller cannot explain the difference if the generic
`do_request()` branch is actually reached. The live command-dispatch/source
version must be checked first.

### Read-only dispatcher/raw diagnostic

~~~bash
DBG=/usr/local/bin/optolink-debug

echo "========== LIVE MODULE =========="
/opt/optolink/venv/bin/python - <<'PY'
import inspect
import requests_util
print("module:", requests_util.__file__)
src = inspect.getsource(requests_util.response_to_request)
print("has request/req branch:", '["request", "req"]' in src or "['request', 'req']" in src)
print("--- matching lines ---")
for i, line in enumerate(src.splitlines(), 1):
    if "request" in line.lower() or "unknown command" in line.lower():
        print(f"{i:03d}: {line}")
PY

echo
echo "========== SOURCE GREP =========="
grep -n -A12 -B5 'cmnd in.*request' /opt/optolink/requests_util.py || true
grep -n 'unknown command received' /opt/optolink/requests_util.py || true

echo
echo "========== BYTE-IDENTICAL RAW VIRTUAL_READ =========="
"$DBG" request "raw;4105000100F80806" --timeout 10

echo
echo "========== RAW KMBUS_RAM_READ 0x41 =========="
"$DBG" request "raw;4105004100F80846" --timeout 12

echo
echo "========== REQUEST WARNINGS =========="
journalctl -u optolink-splitter.service --since "5 minutes ago" --no-pager \
  | grep -Ei 'unknown command|request|timeout|nack|error' \
  | tail -n 100 || true
~~~

The second raw frame is the same no-write 0x41 read request encoded directly:

~~~text
41 05 00 41 00 F8 08 46
~~~

where `46` is the modulo-256 VS2 checksum.

Interpretation:

- raw 0x01 succeeds + raw 0x41 succeeds -> live controller path is fine;
  generic `request` dispatcher/version is the problem;
- raw 0x01 succeeds + raw 0x41 fails -> generic dispatcher is not the only
  issue; re-evaluate current 0x41 controller state/transport;
- live module lacks `request/req` branch -> deployed splitter is older or
  otherwise different from the source version previously analyzed.

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
