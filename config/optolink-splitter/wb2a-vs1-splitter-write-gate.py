#!/usr/bin/env python3
"""Final bounded real-splitter VS1 write-path integration gate for WB2A/20C2.

This runs the actual optolink-splitter in temporary permanent-VS1 mode and
exercises its production MQTT /set path:

  mqtt_util.handle_set_topic
    -> splitter command queue
    -> requests_util.response_to_request
    -> vs12_adapter.write_datapoint_ext
    -> stock optolinkvs1.write_datapoint_ext / F4

The MQTT namespace is changed to a unique temporary base so existing Home
Assistant entities cannot write into this test instance. Party is stopped.

Target is only the ordinary one-byte day room setpoint 0x2306:
baseline -> +/-1 C -> exact baseline.

After the target write, cleanup always tries to restore the original byte. If
the running splitter path cannot verify that restore, a direct stock VS1/F4
fallback is attempted after stopping the temporary splitter.

No coding, EEPROM, GFA_WRITE, burner/gas-valve, actuator or safety write is
implemented.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
from typing import Any

VERSION = "1.0.1"
ROOT = Path("/opt/optolink")
SETTINGS = ROOT / "settings_ini.py"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"

STOCK_HELPER = Path("/root/wb2a-stock-vs1-smoke.py")
STOCK_HELPER_SHA256 = "eb94c4eab0e690ac38a53ceaa2389749d2432fb1ed5f49e15a340cf038d9ab35"
OPTO_VS1_BLOB = "cff6b4d8d52ca4ee1f79c310dd9377dba1a18270"
TARGET_ADDR = 0x2306
DP_NAME = "heizkreis_m1_raumsolltemperatur_normal"
BASELINE_MIN = 10
BASELINE_MAX = 30


class GateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GateError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_stock_helper():
    data = STOCK_HELPER.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != STOCK_HELPER_SHA256:
        raise GateError(f"stock smoke helper hash mismatch: {actual}")
    return load_module(STOCK_HELPER, "wb2a_stock_vs1_smoke_pinned")


def load_stock_vs1():
    path = ROOT / "optolinkvs1.py"
    actual = git_blob_sha(path)
    if actual != OPTO_VS1_BLOB:
        raise GateError(f"stock optolinkvs1.py blob mismatch: {actual}")

    old_cwd = os.getcwd()
    added = False
    try:
        os.chdir(ROOT)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
            added = True
        return load_module(path, "wb2a_stock_vs1_splitter_gate")
    finally:
        os.chdir(old_cwd)
        if added:
            try:
                sys.path.remove(str(ROOT))
            except ValueError:
                pass


def choose_target(baseline: int) -> int:
    if not BASELINE_MIN <= baseline <= BASELINE_MAX:
        raise GateError(
            f"0x2306 baseline {baseline} outside conservative {BASELINE_MIN}..{BASELINE_MAX} C gate"
        )
    return baseline + 1 if baseline < BASELINE_MAX else baseline - 1


def parse_retcode(payload: str) -> int:
    parts = payload.strip().split(";")
    if not parts:
        raise GateError("empty splitter response")
    text = parts[0].strip().lower()
    return int(text[2:], 16) if text.startswith("0x") else int(text, 10)


def parse_raw_read(payload: str, expected_addr: int) -> int:
    parts = payload.strip().split(";")
    if len(parts) < 3:
        raise GateError("short splitter read response: " + payload)
    if parse_retcode(payload) != 1:
        raise GateError("splitter read retcode is not success: " + payload)

    addr_text = parts[1].strip().lower()
    try:
        if addr_text.startswith("0x"):
            candidates = [int(addr_text, 16)]
        else:
            candidates = [int(addr_text, 16), int(addr_text, 10)]
    except ValueError as exc:
        raise GateError("invalid response address: " + payload) from exc
    if expected_addr not in candidates:
        raise GateError(
            f"response address {addr_text!r} does not resolve to 0x{expected_addr:04X}"
        )

    raw = parts[2].strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) != 2:
        raise GateError("expected one raw byte in response: " + payload)
    return int(raw, 16)


def wait_topic(capture, topic: str, timeout_s: float, predicate=None) -> str:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        snap = capture.snapshot()
        if topic in snap:
            value = snap[topic][0]
            last = value
            if predicate is None or predicate(value):
                return value
        time.sleep(0.05)
    raise GateError(f"timeout waiting for {topic}; last={last!r}")


def publish(client, topic: str, payload: str):
    if client is None:
        raise GateError("MQTT client unavailable")
    info = client.publish(topic, payload, qos=0, retain=False)
    try:
        info.wait_for_publish(timeout=2.0)
    except TypeError:
        info.wait_for_publish()
    if getattr(info, "rc", 0) != 0:
        raise GateError(f"MQTT publish rc={info.rc} for {topic}")


def direct_restore(port: str, baseline: int, log) -> bool:
    """Last-resort exact baseline restore through already hardware-validated stock F4."""
    import serial

    vs1 = load_stock_vs1()
    ser = None
    try:
        ser = serial.serial_for_url(
            url=port,
            baudrate=4800,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_TWO,
            bytesize=serial.EIGHTBITS,
            exclusive=True,
            timeout=0,
        )
        if not vs1.init_protocol(ser):
            raise GateError("direct fallback VS1 init failed")
        time.sleep(0.15)

        ret, addr, data = vs1.read_datapoint_ext(TARGET_ADDR, 1, ser)
        if ret != 1 or addr != TARGET_ADDR or len(data) != 1:
            raise GateError("direct fallback pre-read failed")
        current = int(data[0])
        log(f"DIRECT_FALLBACK_PRE=0x{current:02X}")

        if current != baseline:
            time.sleep(0.15)
            ret, addr, reply = vs1.write_datapoint_ext(TARGET_ADDR, bytes([baseline]), ser)
            log(
                f"DIRECT_FALLBACK_F4 ret=0x{ret:02X} addr=0x{addr:04X} "
                f"reply={bytes(reply).hex() or '-'}"
            )
            if ret != 1 or addr != TARGET_ADDR or len(reply) != 1:
                raise GateError("direct fallback F4 failed")

        time.sleep(0.25)
        ret, addr, data = vs1.read_datapoint_ext(TARGET_ADDR, 1, ser)
        if ret != 1 or addr != TARGET_ADDR or len(data) != 1:
            raise GateError("direct fallback final read failed")
        final = int(data[0])
        log(f"DIRECT_FALLBACK_FINAL=0x{final:02X}")
        return final == baseline
    finally:
        if ser is not None:
            ser.close()


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_choose_target_up(self):
            self.assertEqual(choose_target(21), 22)

        def test_choose_target_down(self):
            self.assertEqual(choose_target(30), 29)

        def test_choose_target_gate(self):
            for x in (9, 31):
                with self.assertRaises(GateError):
                    choose_target(x)

        def test_parse_read(self):
            self.assertEqual(parse_raw_read("1;0x2306;15", 0x2306), 0x15)
            self.assertEqual(parse_raw_read("1;2306;16", 0x2306), 0x16)
            self.assertEqual(parse_raw_read("1;8966;15", 0x2306), 0x15)

        def test_parse_retcode(self):
            self.assertEqual(parse_retcode("1;0x2306;00"), 1)
            self.assertEqual(parse_retcode("0x01;2306;00"), 1)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("VS1_SPLITTER_WRITE_GATE_TESTS=5/5")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A real-splitter VS1 write gate {VERSION}: plan only.\n"
            "Uses a unique temporary MQTT namespace and changes only 0x2306 by 1 C, then restores it.\n"
            "--execute required."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: --execute requires root", file=sys.stderr)
        return 1
    if not STOCK_HELPER.is_file():
        print("ERROR: missing pinned stock helper at /root/wb2a-stock-vs1-smoke.py", file=sys.stderr)
        return 1

    stock = load_stock_helper()
    stock.verify_stock_runtime()

    if (ROOT / "poll_list.py").exists():
        raise GateError("legacy poll_list.py exists; refusing final write gate")

    settings_bytes = SETTINGS.read_bytes()
    settings_text = settings_bytes.decode("utf-8")
    settings_stat = SETTINGS.stat()
    assignments = stock.parse_top_level_assignments(settings_text)
    port = assignments.get("port_optolink")
    if not isinstance(port, str) or not port:
        raise GateError("cannot resolve port_optolink from settings_ini.py")

    effective = stock.load_effective_settings()
    if effective.get("vs1protocol") is not False:
        raise GateError("require normal production vs1protocol=False baseline")
    if effective.get("port_vitoconnect") is not None:
        raise GateError("require port_vitoconnect=None")
    if not stock.unit_running(stock.systemctl_show(SPLITTER)):
        raise GateError("require splitter active/running before gate")

    party_running = stock.unit_running(stock.systemctl_show(PARTY))

    token = f"vs1writegate_{time.strftime('%H%M%S')}_{os.getpid()}"
    base = "openv_" + token
    temp_listen = base + "/cmnd"
    temp_resp = base + "/resp"
    fstr = str(effective.get("mqtt_fstr") or "{dpname}")
    state_suffix = fstr.format(dpaddr=TARGET_ADDR, dpname=DP_NAME)
    state_topic = base + "/" + state_suffix
    set_topic = state_topic + "/set"

    temp_settings = dict(effective)
    temp_settings.update({
        "vs1protocol": True,
        "mqtt_topic": base,
        "mqtt_listen": temp_listen,
        "mqtt_respond": temp_resp,
        "tcpip_port": None,
        "olbreath": 0.15,
    })

    expected = {
        state_topic: "state",
        temp_resp: "resp",
        base + "/LWT": "lwt",
    }

    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = Path("/root") / f"wb2a-vs1-splitter-write-gate-{stamp}-{os.getpid()}.log"
    backup = Path("/root") / f"settings_ini.py.vs1-splitter-write-gate-{stamp}-{os.getpid()}.bak"
    backup.write_bytes(settings_bytes)
    os.chmod(backup, 0o600)

    log_handle = log_path.open("a", encoding="utf-8", buffering=1)
    def log(msg: str):
        line = dt.datetime.now().astimezone().isoformat(timespec="milliseconds") + " " + msg
        print(line, flush=True)
        log_handle.write(line + "\n")

    capture = None
    baseline = None
    target = None
    target_attempted = False
    target_verified = False
    restore_verified = False
    fallback_used = False
    temp_started = False
    settings_restored = False
    normal_splitter_restored = False
    failures: list[str] = []

    previous_handlers = {}
    def abort(signum, _frame):
        raise GateError(f"interrupted by signal {signum}; entering cleanup")

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous_handlers[sig] = signal.signal(sig, abort)

    try:
        log(f"WB2A real-splitter VS1 write gate {VERSION}")
        log("WRITE_PATH=mqtt /set -> splitter queue -> requests_util -> vs12_adapter -> stock F4")
        log(f"TEMP_MQTT_BASE={base}")
        log("TARGET=0x2306 ordinary day room setpoint; bounded +/-1 C")
        log("NO_OTHER_WRITE_NAMESPACE=yes")

        if party_running:
            log("Stopping " + PARTY)
            stock.run(["systemctl", "stop", PARTY], timeout=15)
        log("Stopping " + SPLITTER)
        stock.run(["systemctl", "stop", SPLITTER], timeout=15)

        patched = stock.patch_assignments_exact(
            settings_text,
            {
                "vs1protocol": True,
                "mqtt_topic": base,
                "mqtt_listen": temp_listen,
                "mqtt_respond": temp_resp,
                "tcpip_port": None,
                "olbreath": 0.15,
            },
        )
        stock.atomic_write_like(SETTINGS, patched.encode("utf-8"), settings_stat)
        log("TEMP_SETTINGS_APPLIED=yes")

        capture = stock.MqttCapture(temp_settings, expected, log)
        capture.start()

        start_epoch = time.time()
        log("Starting temporary permanent-VS1 splitter")
        stock.run(["systemctl", "start", SPLITTER], timeout=15)
        temp_started = True

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not stock.unit_running(stock.systemctl_show(SPLITTER)):
            time.sleep(0.1)
        if not stock.unit_running(stock.systemctl_show(SPLITTER)):
            raise GateError("temporary VS1 splitter did not become active/running")
        pid0 = stock.systemctl_show(SPLITTER).get("MainPID")
        log("VS1_MAINPID=" + str(pid0))

        ok, _ = stock.wait_for_journal_marker("VS1/KW protocol initialized", start_epoch, timeout_s=8.0)
        if not ok:
            raise GateError("temporary splitter did not log VS1/KW protocol initialized")
        log("JOURNAL_VS1_INITIALIZED=yes")

        # Read baseline through the running splitter's request dispatcher.
        capture.clear()
        publish(capture.client, temp_listen, "r;0x2306;1;raw;False")
        response = wait_topic(capture, temp_resp, 5.0)
        baseline = parse_raw_read(response, TARGET_ADDR)
        target = choose_target(baseline)
        log(f"BASELINE_2306=0x{baseline:02X} ({baseline} C)")
        log(f"TARGET_2306=0x{target:02X} ({target} C)")

        # Actual production /set path.
        capture.clear()
        target_attempted = True
        log(f"MQTT_SET_CHANGE topic={set_topic} value={target}")
        publish(capture.client, set_topic, str(target))

        write_resp = wait_topic(capture, temp_resp, 5.0)
        log("CHANGE_RESPONSE=" + write_resp)
        if parse_retcode(write_resp) != 1:
            raise GateError("splitter change write returned non-success")

        changed_state = wait_topic(
            capture,
            state_topic,
            6.0,
            lambda v: abs(float(v) - float(target)) < 0.001,
        )
        log("CHANGED_STATE=" + changed_state)
        target_verified = True

        # Restore through the same production /set path.
        capture.clear()
        log(f"MQTT_SET_RESTORE topic={set_topic} value={baseline}")
        publish(capture.client, set_topic, str(baseline))

        restore_resp = wait_topic(capture, temp_resp, 5.0)
        log("RESTORE_RESPONSE=" + restore_resp)
        if parse_retcode(restore_resp) != 1:
            raise GateError("splitter restore write returned non-success")

        restored_state = wait_topic(
            capture,
            state_topic,
            6.0,
            lambda v: abs(float(v) - float(baseline)) < 0.001,
        )
        log("RESTORED_STATE=" + restored_state)

        # Final explicit F7 read through the same dispatcher.
        capture.clear()
        publish(capture.client, temp_listen, "r;0x2306;1;raw;False")
        final_resp = wait_topic(capture, temp_resp, 5.0)
        final_value = parse_raw_read(final_resp, TARGET_ADDR)
        log(f"FINAL_SPLITTER_F7_2306=0x{final_value:02X} ({final_value} C)")
        if final_value != baseline:
            raise GateError(
                f"final splitter F7 value 0x{final_value:02X} != baseline 0x{baseline:02X}"
            )
        restore_verified = True

        journal = stock.journal_since(start_epoch - 0.25)
        hits, flags = stock.analyze_journal(journal)
        if hits or flags["unexpected_restart"]:
            raise GateError(f"journal errors/restart detected: hits={hits}, flags={flags}")
        state_now = stock.systemctl_show(SPLITTER)
        if state_now.get("MainPID") != pid0:
            raise GateError(f"MainPID changed {pid0} -> {state_now.get('MainPID')}")
        log("JOURNAL_UNEXPECTED_RESTART=no")
        log("VS1_MAINPID_STABLE=yes")

    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("GATE_FAILED=" + failures[-1])
    finally:
        # Protect cleanup from a second ordinary termination signal.
        ignored = {}
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            ignored[sig] = signal.signal(sig, signal.SIG_IGN)

        try:
            # If a target write was attempted but restore was not verified,
            # first retry through the running production /set path.
            if target_attempted and not restore_verified and baseline is not None:
                if capture is not None and stock.unit_running(stock.systemctl_show(SPLITTER)):
                    for attempt in range(1, 3):
                        try:
                            capture.clear()
                            log(f"MQTT_CLEANUP_RESTORE attempt={attempt} value={baseline}")
                            publish(capture.client, set_topic, str(baseline))
                            wait_topic(
                                capture,
                                state_topic,
                                5.0,
                                lambda v: abs(float(v) - float(baseline)) < 0.001,
                            )
                            restore_verified = True
                            log("MQTT_CLEANUP_RESTORE_VERIFIED=yes")
                            break
                        except Exception as exc:
                            log(f"MQTT cleanup restore attempt {attempt} failed: {exc}")

            if capture is not None:
                try:
                    capture.stop()
                except Exception as exc:
                    failures.append("MQTT capture stop: " + str(exc))
                capture = None

            # Stop temporary splitter before settings restore and before any
            # direct serial fallback.
            try:
                if stock.unit_running(stock.systemctl_show(SPLITTER)):
                    log("Stopping temporary VS1 splitter")
                    stock.run(["systemctl", "stop", SPLITTER], timeout=15)
            except Exception as exc:
                failures.append("temporary splitter stop: " + str(exc))

            if target_attempted and not restore_verified and baseline is not None:
                try:
                    log("DIRECT_F4_FALLBACK_RESTORE=starting")
                    fallback_used = True
                    if not direct_restore(port, baseline, log):
                        failures.append("direct F4 fallback did not verify baseline")
                    else:
                        restore_verified = True
                        log("DIRECT_F4_FALLBACK_RESTORE=verified")
                except Exception as exc:
                    failures.append("direct F4 fallback restore failed: " + str(exc))

            # Restore original settings byte-for-byte.
            try:
                stock.atomic_write_like(SETTINGS, settings_bytes, settings_stat)
                restored_sha = sha256_bytes(SETTINGS.read_bytes())
                original_sha = sha256_bytes(settings_bytes)
                log("ORIGINAL_SETTINGS_SHA256=" + original_sha)
                log("RESTORED_SETTINGS_SHA256=" + restored_sha)
                if restored_sha != original_sha:
                    raise GateError("settings restore SHA mismatch")
                settings_restored = True
                log("SETTINGS_RESTORED=yes")
            except Exception as exc:
                failures.append("settings restore: " + str(exc))

            safe_to_restart = settings_restored and (
                (not target_attempted) or restore_verified
            )
            if safe_to_restart:
                restore_epoch = time.time()
                try:
                    log("Restoring normal splitter")
                    stock.run(["systemctl", "start", SPLITTER], timeout=15)
                    deadline = time.monotonic() + 5.0
                    while time.monotonic() < deadline and not stock.unit_running(stock.systemctl_show(SPLITTER)):
                        time.sleep(0.1)
                    if not stock.unit_running(stock.systemctl_show(SPLITTER)):
                        raise GateError("normal splitter did not return active/running")
                    ok, _ = stock.wait_for_journal_marker(
                        "VS2/300 protocol initialized", restore_epoch, timeout_s=10.0
                    )
                    log("RESTORED_BASELINE_PROTOCOL=" + ("VS2/300" if ok else "NOT_CONFIRMED"))
                    if not ok:
                        failures.append("normal splitter did not re-establish VS2/300")
                    else:
                        normal_splitter_restored = True
                except Exception as exc:
                    failures.append("normal splitter restore: " + str(exc))
            else:
                log("FAIL_CLOSED_SPLITTER_STOPPED=yes")
                failures.append(
                    "splitter left stopped because baseline/settings restoration was not verified"
                )

            if party_running and normal_splitter_restored:
                try:
                    log("Restoring " + PARTY)
                    stock.run(["systemctl", "start", PARTY], timeout=15)
                    time.sleep(0.5)
                    if not stock.unit_running(stock.systemctl_show(PARTY)):
                        raise GateError("party emulator did not return active/running")
                    log("PARTY_RESTORED=yes")
                except Exception as exc:
                    failures.append("party restore: " + str(exc))
            elif party_running:
                log("FAIL_CLOSED_PARTY_STOPPED=yes")

            if target_attempted and not restore_verified:
                failures.append("original 0x2306 baseline was not verified restored")

            if not failures:
                try:
                    backup.unlink()
                    log("BACKUP_REMOVED=yes")
                except Exception as exc:
                    failures.append("backup removal: " + str(exc))
            else:
                log("BACKUP_RETAINED=" + str(backup))

        finally:
            for sig, handler in ignored.items():
                signal.signal(sig, handler)
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
            log("TARGET_WRITE_VERIFIED=" + ("yes" if target_verified else "no"))
            log("RESTORE_VERIFIED=" + ("yes" if restore_verified else "no"))
            log("DIRECT_FALLBACK_USED=" + ("yes" if fallback_used else "no"))
            result_ok = (
                target_verified
                and restore_verified
                and settings_restored
                and normal_splitter_restored
                and not failures
            )
            log("RESULT=" + ("PASS" if result_ok else "FAIL"))
            for failure in failures:
                log("ERROR: " + failure)
            log("LOG=" + str(log_path))
            log_handle.close()

    return 0 if (
        target_verified
        and restore_verified
        and settings_restored
        and normal_splitter_restored
        and not failures
    ) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        print("ERROR: " + (str(exc) or type(exc).__name__), file=sys.stderr)
        raise
