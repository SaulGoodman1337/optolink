"""Real fan speed (GFA P06) in permanent P300 operation via short VS1 windows.

Background: the WB2A only answers GFA_READ (0x6B) in VS1/KW mode; in P300 it
rejects GFA access. Research 2026-11-25 (thread "Gebläsedrehzahl über P300
finden") showed that no P300-readable RAM byte follows the fan speed: the
best candidate 0x0F20 stays at 84 while the modulation falls from 66 % to
40 % after every start. So the only real value is P06 via VS1.

This module runs inside the splitter main loop (single serial owner) and,
while the burner is running, occasionally performs one short window:

  P300 --EOT/ENQ/STX--> VS1: GFA_READ P80 (must be 0x20), P06, P09, P87
       --EOT/ENQ/16 00 00--> P300, identity read 0x00F8 as proof

No writes of any kind, only these four GFA reads plus the protocol
handshakes that upstream uses itself (optolinkvs1.init_protocol,
optolinkvs2.init_vs2). A window blocks the main loop for ~5-8 s; the pump
guard cannot write during that time, so the firmware's coded E7 = 100 %
applies (fail-safe direction). Windows only happen with the flame on, where
the pump guard boosts anyway.

Schedule: first window START_DELAY_S (15 s) after flame-on (start ramp), then every
`interval` minutes while the flame stays on. After the flame has been off for
OFF_ZERO_S the fan has stopped (post-purge is over) and 0 is published with
source "Brenner aus" (no telegram).

Failures: a failed window (no ENQ, P80 wrong, FF) is retried at the next
due time; after MAX_FAILS consecutive failures windows pause for
BLOCK_S. If the return to P300 fails twice, the splitter's link watchdog
re-initialises P300 after 60 s (existing link-recovery behaviour).

MQTT (below <mqtt_topic>):
  geblaesedrehzahl_gfa_p06, gfa_modulationssollwert_p09, gfa_p80_typ,
  gfa_status3_p87          same topics/format as the VS1 poll items
  fan_p06/status           JSON (retained)
  fan_p06/enabled/set|state  ON|OFF (default ON)
  fan_p06/interval/set|state minutes 1..30 (default 5)
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")

VERSION = "1.0.0"

GFA_P80, GFA_P06, GFA_P09, GFA_P87 = 0x4050, 0x4006, 0x4009, 0x4057
P80_EXPECTED = 0x20
READ_STATUS = (0x01, 0x55D3, 9)      # byte5 0x20 = flame (own read only without flame_fn)

START_DELAY_S = 15.0      # first window after flame-on: inside the start ramp (high load);
                          # night burns last only 35-40 s
OFF_ZERO_S = 60.0         # flame off this long -> fan stopped, publish 0
STATUS_PERIOD_S = 5.0     # own 0x55D3 read period when no flame_fn is given
INTERVAL_MIN, INTERVAL_MAX, INTERVAL_DEFAULT = 1, 30, 5
MAX_FAILS = 3
CFG_DEFAULT_AFTER_S = 10.0   # publish default config states if none were retained
BLOCK_S = 1800.0

OK, WARTET, AUS, FEHLER, GESPERRT = "OK", "WARTET", "AUS", "FEHLER", "GESPERRT"


class Backend:
    """Serial primitives of the upstream splitter (imported lazily)."""

    def __init__(self, ser):
        import optolinkvs1, optolinkvs2, vs12_adapter  # type: ignore
        self.ser, self.vs1, self.vs2, self.adapter = ser, optolinkvs1, optolinkvs2, vs12_adapter

    def do_request(self, fc, addr, n, data=b""):
        return self.adapter.do_request(self.ser, fc, addr, n, data)

    def to_vs1(self):
        ok = bool(self.vs1.init_protocol(self.ser))
        if ok:
            self.vs1.reset_sync()
        return ok

    def gfa(self, addr):
        rc, _, data = self.vs1.read_gfa_ext(addr, 1, self.ser)
        return rc, (bytes(data) if data is not None else b"")

    def to_p300(self):
        if not self.vs2.init_vs2(self.ser):
            return False
        rc, _, data = self.adapter.read_datapoint_ext(0x00F8, 2, self.ser)
        return rc == 0x01 and data is not None and len(data) == 2


class FanP06:
    def __init__(self, settings, logger, backend, flame_fn=None, mqtt_factory=None,
                 clock=time.monotonic):
        self.s, self.log, self.b = settings, logger, backend
        self.flame_fn = flame_fn
        self.clock = clock
        self.active = not getattr(settings, "vs1protocol", True)
        self.topic = str(getattr(settings, "mqtt_topic", "openv")).rstrip("/")
        self.base = self.topic + "/fan_p06"
        self.enabled = True
        self.interval_s = INTERVAL_DEFAULT * 60.0
        self.flame = None
        self.flame_since = None
        self.flame_off_since = None
        self.next_status = 0.0
        self.last_window = None
        self.fails = 0
        self.blocked_until = 0.0
        self.windows = 0
        self.failures = 0
        self.last = {}           # last measurement
        self.last_ms = None
        self.zero_published = False
        self.state, self.reason = WARTET, "noch keine Messung"
        self.lock = threading.Lock()
        self.client = None
        self.cfg_seen = set()           # config names restored from retained state or /set
        self.cfg_published = False
        self.started = self.clock()
        if mqtt_factory is None and getattr(settings, "mqtt_broker", None):
            mqtt_factory = self._paho_client
        if mqtt_factory is not None:
            try:
                c = mqtt_factory()
                c.on_message = self._on_message
                self.client = c
                if getattr(c, "on_connect", None) is None:
                    self._on_connect(c, None, None, 0)
            except Exception as exc:
                self.log.warning(f"fan_p06: MQTT setup failed: {exc}")
        self.log.info(f"fan_p06 {VERSION}: {'aktiv (P300 + VS1-Fenster)' if self.active else 'inaktiv (VS1)'}")

    # ---- MQTT -------------------------------------------------------------
    def _paho_client(self):
        import paho.mqtt.client as paho
        s = self.s
        cid = "olswitch_fanp06_" + str(s.mqtt_topic).replace("/", "").replace(" ", "")
        try:
            c = paho.Client(paho.CallbackAPIVersion.VERSION2, cid)
        except Exception:
            c = paho.Client(client_id=cid)
        creds = getattr(s, "mqtt_user", None)
        if creds is not None and str(creds).strip():
            user, _, pwd = str(creds).strip().partition(":")
            c.username_pw_set(user, password=(pwd or None))
        if getattr(s, "mqtt_tls_enable", False):
            import ssl
            skip = bool(getattr(s, "mqtt_tls_skip_verify", False))
            c.tls_set(ca_certs=getattr(s, "mqtt_tls_ca_certs", None),
                      certfile=getattr(s, "mqtt_tls_certfile", None),
                      keyfile=getattr(s, "mqtt_tls_keyfile", None),
                      cert_reqs=(ssl.CERT_NONE if skip else ssl.CERT_REQUIRED))
            c.tls_insecure_set(skip)
        c.on_connect = self._on_connect
        host, _, port = str(s.mqtt_broker).partition(":")
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        c.connect_async(host, int(port or 1883))
        c.loop_start()
        return c

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        topics = ("enabled", "interval")
        client.subscribe([(f"{self.base}/{t}/set", 0) for t in topics]
                         + [(f"{self.base}/{t}/state", 0) for t in topics])
        self._publish_status(force=True)

    def _on_message(self, client, userdata, msg):
        try:
            name, kind = msg.topic[len(self.base) + 1:].split("/", 1)
            payload = msg.payload.decode(errors="replace").strip()
            if kind == "state" and not msg.retain:
                return
            if kind not in ("set", "state"):
                return
            self.cfg_seen.add(name)
            with self.lock:
                if name == "enabled":
                    self.enabled = payload.upper() in ("ON", "1", "TRUE", "EIN")
                    if self.enabled:
                        self.fails, self.blocked_until = 0, 0.0
                    out = "ON" if self.enabled else "OFF"
                elif name == "interval":
                    v = int(float(payload))
                    if not INTERVAL_MIN <= v <= INTERVAL_MAX:
                        return
                    self.interval_s = v * 60.0
                    out = str(v)
                else:
                    return
            if kind == "set":
                client.publish(f"{self.base}/{name}/state", out, retain=True)
            self._publish_status(force=True)
        except Exception as exc:
            self.log.warning(f"fan_p06: bad message {msg.topic}: {exc}")

    def _pub(self, topic, value, retain=True):
        if self.client is None:
            return
        try:
            self.client.publish(topic, value, retain=retain)
        except Exception:
            pass

    def _publish_status(self, force=False):
        now = self.clock()
        age = None if self.last.get("t") is None else round(now - self.last["t"])
        st = {"state": self.state, "reason": self.reason, "enabled": self.enabled,
              "interval_min": round(self.interval_s / 60.0, 1),
              "rpm": self.last.get("rpm"), "p09": self.last.get("p09"),
              "p87": self.last.get("p87"), "source": self.last.get("source"),
              "measured_at": self.last.get("wall"), "age_s": age,
              "window_ms": self.last_ms, "windows": self.windows, "failures": self.failures,
              "flame": self.flame, "protocol": "P300" if self.active else "VS1",
              "version": VERSION, "timestamp": int(time.time())}
        self._pub(f"{self.base}/status", json.dumps(st))

    # ---- logic --------------------------------------------------------------
    def _set_flame(self, flame, now):
        if flame and not self.flame:
            self.flame_since, self.flame_off_since = now, None
            self.zero_published = False
        elif not flame and self.flame:
            self.flame_off_since = now
        elif flame is False and self.flame is None:
            self.flame_off_since = now
        self.flame = flame

    def due(self, now):
        if not (self.active and self.enabled and self.flame and self.flame_since is not None):
            return False
        if now < self.blocked_until:
            return False
        if now - self.flame_since < START_DELAY_S:
            return False
        if self.last_window is None or self.last_window < self.flame_since:
            return True
        return now - self.last_window >= self.interval_s

    def tick(self, now=None):
        """At most one telegram, or one complete VS1 window. Returns retcode or None."""
        if not self.active:
            return None
        now = self.clock() if now is None else now
        try:
            rc = None
            if not self.cfg_published and now - self.started >= CFG_DEFAULT_AFTER_S:
                # nothing retained yet (first install): publish the defaults so HA
                # shows the switch/number state instead of "unknown"
                self.cfg_published = True
                if "enabled" not in self.cfg_seen:
                    self._pub(f"{self.base}/enabled/state", "ON" if self.enabled else "OFF")
                if "interval" not in self.cfg_seen:
                    self._pub(f"{self.base}/interval/state", str(int(self.interval_s // 60)))
            if self.flame_fn is not None:
                f = self.flame_fn()
                if f is not None:
                    self._set_flame(bool(f), now)
            elif now >= self.next_status:
                self.next_status = now + STATUS_PERIOD_S
                fc, addr, n = READ_STATUS
                rc, _, data = self.b.do_request(fc, addr, n, b"")
                if rc == 0x01 and data is not None and len(data) == n:
                    self._set_flame(bool(data[5] & 0x20), now)
                return rc
            with self.lock:
                is_due = self.due(now)
            if is_due:
                return self.window(now)
            if (self.flame is False and self.flame_off_since is not None
                    and now - self.flame_off_since >= OFF_ZERO_S and not self.zero_published):
                self.zero_published = True
                self.last = {"rpm": 0, "p09": self.last.get("p09"), "p87": self.last.get("p87"),
                             "source": "Brenner aus", "t": now,
                             "wall": _now_iso()}
                self._pub(f"{self.topic}/geblaesedrehzahl_gfa_p06", "0")
                self._set_state(OK if self.enabled else AUS, "Brenner aus, Gebläse steht")
            elif not self.enabled:
                self._set_state(AUS, "ausgeschaltet")
            return rc
        except Exception as exc:
            self.log.warning(f"fan_p06: {exc}")
            return None

    def _set_state(self, state, reason):
        if (state, reason) != (self.state, self.reason):
            self.state, self.reason = state, reason
            self._publish_status(force=True)

    def window(self, now):
        """P300 -> VS1 -> 4 GFA reads -> P300. Returns the retcode for olbreath()."""
        t0 = self.clock()
        self.last_window = now
        self.windows += 1
        vals, err = {}, None
        try:
            if not self.b.to_vs1():
                err = "kein VS1-Handshake"
            else:
                for name, addr in (("p80", GFA_P80), ("p06", GFA_P06), ("p09", GFA_P09), ("p87", GFA_P87)):
                    rc, data = self.b.gfa(addr)
                    if rc != 0x01 or len(data) != 1 or data[0] == 0xFF:
                        err = (f"GFA {name} = FF" if rc == 0x01 and data[:1] == b"\xff"
                               else f"GFA {name} rc={rc:#04x}")
                        break
                    vals[name] = data[0]
                if err is None and vals.get("p80") != P80_EXPECTED:
                    err = f"P80={vals.get('p80')!r} statt 0x20"
        except Exception as exc:
            err = f"Ausnahme VS1: {exc}"
        back = False
        for _ in range(2):
            try:
                if self.b.to_p300():
                    back = True
                    break
            except Exception as exc:
                self.log.warning(f"fan_p06: P300 return failed: {exc}")
        self.last_ms = int((self.clock() - t0) * 1000)
        if not back:
            err = (err + "; " if err else "") + "Rückkehr nach P300 fehlgeschlagen"
        if err is None:
            self.fails = 0
            self.last = {"rpm": vals["p06"] * 30, "p09": round(vals["p09"] * 0.3922, 1),
                         "p87": vals["p87"], "source": "GFA P06 (VS1-Fenster)",
                         "t": self.clock(), "wall": _now_iso()}
            self._pub(f"{self.topic}/geblaesedrehzahl_gfa_p06", str(vals["p06"] * 30))
            self._pub(f"{self.topic}/gfa_modulationssollwert_p09", str(self.last["p09"]))
            self._pub(f"{self.topic}/gfa_p80_typ", f"{vals['p80']:02x}")
            self._pub(f"{self.topic}/gfa_status3_p87", f"{vals['p87']:02x}")
            self.log.info(f"fan_p06: P06 {vals['p06'] * 30} rpm, P09 {self.last['p09']} %, "
                          f"window {self.last_ms} ms")
            self._set_state(OK, "gemessen")
            self._publish_status(force=True)
        else:
            self.failures += 1
            self.fails += 1
            self.log.warning(f"fan_p06: window failed ({err}), {self.last_ms} ms")
            if self.fails >= MAX_FAILS:
                self.blocked_until = self.clock() + BLOCK_S
                self._set_state(GESPERRT, f"{self.fails} Fehlversuche, Pause {int(BLOCK_S / 60)} min: {err}")
            else:
                self._set_state(FEHLER, err)
        return 0x01 if back else 0xFF

    def reset_link(self, backend=None, flame_fn=None):
        if backend is not None:
            self.b = backend
        if flame_fn is not None:
            self.flame_fn = flame_fn
        self.next_status = 0.0


_obj = None


def get(settings, logger, backend, flame_fn=None, mqtt_factory=None):
    """Module singleton; survives splitter-internal restarts of the main loop."""
    global _obj
    if _obj is None:
        _obj = FanP06(settings, logger, backend, flame_fn, mqtt_factory)
    else:
        _obj.reset_link(backend, flame_fn)
    return _obj
