#!/usr/bin/env python3
"""Read-only long-term observer for the P300 fan-speed candidate RAM[0x0F20].

Background (docs/p300-temporal-fullrun-analysis-2026-10-09.md on branch
optolink-p300-migration): RAM 0x0F20 (mirror 0x1C76) is 00 while the burner is
off, 0x54 in most burner phases and ramps up to 0xAC around starts.  It leads
flame-on by ~11 s and drops ~2.6 s before flame-off.  Hypothesis: fan speed
(set or actual) in units of 30 rpm, like GFA P06.  Real P06 is VS1-GFA only.

This tool never opens the serial port.  It sends exactly two kinds of P300
Physical_READ (FC 0x03) telegrams through the running splitter's MQTT
"raw;" request, nothing else:
  * 0x0F20, 11 bytes (candidate + marker + 9-byte status copy), adaptive:
    every FAST_S seconds while the candidate is non-zero or the flame is on,
    else every SLOW_S seconds;
  * every CTX_S seconds one 32-byte context block from CONTEXT_BLOCKS
    (all of them were read thousands of times in the 2026-10 research runs).
No writes, no virtual reads, no GFA/C9/RPC.  Values are logged together with
the latest retained splitter MQTT topics (modulation, flame, temperatures...).

Output (TSV): <outdir>/fan-obs.tsv and <outdir>/fan-ctx.tsv
Run as the optolink user with the splitter venv, e.g.
  runuser -u optolink -- /opt/optolink/venv/bin/python fan-p300-observer.py \
      --outdir /var/tmp/fan-obs --hours 26
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime, timezone

FAST_S = 2.5
SLOW_S = 10.0
CTX_S = 60.0
CANDIDATE = (0x0F20, 11)
CONTEXT_BLOCKS = (0x1C60, 0x0F00, 0x0F40, 0x1C40, 0x1C80)

TOPICS = (
    "brenner_modulationsgrad", "brenner_flamme", "kesseltemperatur",
    "kessel_solltemperatur_effektiv", "heizkreis_m1_vorlauftemperatur",
    "abgastemperatur", "warmwasser_ladestatus", "umschaltventil_stellung",
    "getLeistungIst", "cfdm_leistungswert", "heizkreis_m1_pumpe_drehzahl",
    "geblaesedrehzahl_gfa_p06", "gfa_modulationssollwert_p09",
)


def frame(addr: int, n: int) -> str:
    body = bytes([0x05, 0x00, 0x03, addr >> 8, addr & 0xFF, n])
    return "raw;41" + (body + bytes([sum(body) & 0xFF])).hex().upper()


def parse(payload: str, addr: int, n: int):
    """'1;0641LL0103AAAANN<data>CS' -> data bytes or None."""
    try:
        rc, hexs = payload.split(";", 1)
        raw = bytes.fromhex(hexs)
    except ValueError:
        return None
    if rc.strip() != "1":
        return None
    i = raw.find(bytes([0x41]))
    if i < 0 or len(raw) < i + 8 + n:
        return None
    t = raw[i:]
    if t[2] != 0x01 or t[3] != 0x03 or (t[4] << 8 | t[5]) != addr or t[6] != n:
        return None
    data = t[7:7 + n]
    if (sum(t[1:7 + n]) & 0xFF) != t[7 + n]:
        return None
    return data


class Obs:
    def __init__(self, settings, client, outdir):
        self.s = settings
        self.c = client
        self.base = settings.mqtt_topic.rstrip("/") + "/"
        self.vals = {}
        self.cond = threading.Condition()
        self.resp = []
        self.obs = open(os.path.join(outdir, "fan-obs.tsv"), "a", buffering=1)
        self.ctx = open(os.path.join(outdir, "fan-ctx.tsv"), "a", buffering=1)
        if self.obs.tell() == 0:
            self.obs.write("utc\tmono\tc0f20\tm0f21\tstatus9\t" + "\t".join(TOPICS) + "\n")
        if self.ctx.tell() == 0:
            self.ctx.write("utc\tmono\taddr\tdata\n")

    def on_message(self, client, userdata, m):
        payload = m.payload.decode("utf-8", "replace")
        if m.topic == self.s.mqtt_respond:
            with self.cond:
                self.resp.append(payload)
                self.resp = self.resp[-50:]
                self.cond.notify_all()
        elif m.topic.startswith(self.base):
            self.vals[m.topic[len(self.base):]] = payload

    def read(self, addr, n, timeout=6.0):
        with self.cond:
            self.resp.clear()
        self.c.publish(self.s.mqtt_listen, frame(addr, n))
        end = time.monotonic() + timeout
        with self.cond:
            while time.monotonic() < end:
                for p in self.resp:
                    d = parse(p, addr, n)
                    if d is not None:
                        return d
                self.cond.wait(0.2)
        return None

    def run(self, hours):
        stop = time.monotonic() + hours * 3600
        next_ctx = time.monotonic() + 5
        ctx_i = 0
        while time.monotonic() < stop:
            t0 = time.monotonic()
            utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            d = self.read(*CANDIDATE)
            row = [utc, f"{t0:.3f}"]
            if d is None:
                row += ["", "", ""]
                active = False
            else:
                row += [f"{d[0]}", f"{d[1]}", d[2:].hex()]
                active = d[0] != 0
            row += [self.vals.get(k, "") for k in TOPICS]
            self.obs.write("\t".join(row) + "\n")
            if str(self.vals.get("brenner_flamme", "")).lower() == "true":
                active = True
            if time.monotonic() >= next_ctx:
                a = CONTEXT_BLOCKS[ctx_i % len(CONTEXT_BLOCKS)]
                ctx_i += 1
                cd = self.read(a, 32)
                self.ctx.write(f"{utc}\t{time.monotonic():.3f}\t{a:04X}\t{cd.hex() if cd else ''}\n")
                next_ctx = time.monotonic() + CTX_S
            time.sleep(max(0.2, (FAST_S if active else SLOW_S) - (time.monotonic() - t0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="/var/tmp/fan-obs")
    ap.add_argument("--hours", type=float, default=26.0)
    ap.add_argument("--root", default="/opt/optolink")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    sys.path.insert(0, a.root)
    os.chdir(a.root)
    from c_settings_adapter import settings  # type: ignore
    from homeassistant_publish import connect_mqtt  # type: ignore
    client = connect_mqtt(retries=3, delay=2)
    o = Obs(settings, client, a.outdir)
    client.on_message = o.on_message
    client.subscribe(settings.mqtt_respond)
    client.subscribe(o.base + "#")
    client.loop_start()
    time.sleep(3)
    try:
        o.run(a.hours)
    finally:
        client.loop_stop()


if __name__ == "__main__":
    main()
