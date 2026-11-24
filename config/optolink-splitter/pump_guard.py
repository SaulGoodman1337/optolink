"""Fail-safe pump guard for the WB2A / VDensHO1 20C2 (permanent P300 only).

Principle (inverted RAM override, proven live 2026-11-24, Phase 0):
  * E7 (0x27E7, heating-pump minimum speed) is persistently coded to 100 %.
  * The firmware keeps a working copy at physical RAM 0x20A5 and reloads the
    coded value roughly every 2.1-2.7 s.
  * While everything is healthy and no boost is wanted, the guard writes the
    normal minimum (e.g. 30 %) into 0x20A5 each time the firmware restored it.
  * For a boost the guard simply stops (and writes 100 once to be faster).
  * Any failure on our side (HA, MQTT, splitter, container, adapter) means no
    more writes, so the firmware returns to 100 % by itself within ~3 s.

The guard runs inside the splitter's main loop (single serial owner). Each
tick performs at most one Optolink telegram; the only exception is a RAM read
that finds the firmware's reload, which is followed by the repair write right
away. Strict allowlist: Physical_WRITE only 0x20A5 with values {low, 100};
reads only the addresses below. The coded
E7 value is never written by this module.

Home Assistant interface (MQTT, below <mqtt_topic>/pump_guard):
  enabled/set  ON|OFF        -> enabled/state (retained, restores after restart)
  low/set      20..100       -> low/state
  nachlauf/set 0..30 minutes -> nachlauf/state
  status       JSON (retained), zustand = state word, protocol = P300|VS1
"""
from __future__ import annotations

import json
import threading
import time

VERSION = "1.0.1"

RAM_BLOCK, RAM_E7_OFFSET = 0x20A0, 5          # 0x20A5
HIGH = 100
LOW_MIN, LOW_MAX = 20, 100
NACHLAUF_MAX_MIN = 30

READ_GFA = (0x01, 0x55D3, 9)     # byte5: 0x20 flame, 0x40 lockout; bytes6/7 GG1 sequence
READ_WW = (0x01, 0x650A, 1)      # 1 = DHW charging active
READ_VALVE = (0x01, 0x0A10, 1)   # 1 = heating
READ_FAULT = (0x01, 0x5738, 1)   # 0 = no fault
READ_E7 = (0x01, 0x27E7, 1)      # heating-pump minimum; NOTE: reads the active RAM copy
                                 # (0x20A5), so it is only meaningful while not lowering
READ_RAM = (0x03, RAM_BLOCK, 32)
ALLOWED_READS = {READ_GFA, READ_WW, READ_VALVE, READ_FAULT, READ_E7, READ_RAM}

STATE_PERIOD_S = 1.0       # every state key once per second (round robin)
SLOW_PERIOD_S = 10.0       # fault + coded E7, each once per period
RAM_PERIOD_S = 0.1         # RAM supervision while lowering (in practice: every tick)
RAM_QUIET_S = 1.4          # firmware reload seen 1.7-2.7 s after a write: no reads before
STALE_S = 5.0              # state older than this -> no lowering

ABGESENKT, BOOST, AUS, GESPERRT, FEHLER = "ABGESENKT", "BOOST", "AUS", "GESPERRT", "FEHLER"


class GuardLogic:
    """Pure decision logic (no I/O), unit-testable."""

    def __init__(self):
        self.enabled = False
        self.low = 30
        self.nachlauf_s = 180.0
        self.flame = self.lockout = False
        self.sequence = False
        self.ww = None
        self.valve = None
        self.fault = None
        self.e7 = None
        self.ts = {}
        self.burner_last_active = None
        self.error = None

    def update(self, key, value, now):
        if key == "gfa":
            b = value
            self.flame = bool(b[5] & 0x20)
            self.lockout = bool(b[5] & 0x40)
            self.sequence = bool(b[6] or b[7])
            if self.flame or self.sequence:
                self.burner_last_active = now
        elif key == "ww":
            self.ww = value[0]
        elif key == "valve":
            self.valve = value[0]
        elif key == "fault":
            self.fault = value[0]
        elif key == "e7":
            self.e7 = value[0]
        else:
            raise KeyError(key)
        self.ts[key] = now

    def fresh(self, now):
        need = {"gfa": STALE_S, "ww": STALE_S, "valve": STALE_S,
                "fault": 3 * SLOW_PERIOD_S, "e7": 3 * SLOW_PERIOD_S}
        return all(k in self.ts and now - self.ts[k] <= lim for k, lim in need.items())

    def decide(self, now):
        """Return (state, reason). Only ABGESENKT allows writing `low`."""
        if self.error:
            return FEHLER, self.error
        if not self.enabled:
            return AUS, "ausgeschaltet"
        if not self.fresh(now):
            return GESPERRT, "Zustand unbekannt"
        if self.e7 != HIGH:
            return GESPERRT, f"E7 codiert {self.e7} statt 100"
        if self.fault or self.lockout:
            return GESPERRT, "Stoerung"
        if self.ww:
            return BOOST, "Warmwasser"
        if self.valve != 1:
            return BOOST, "Ventil nicht Heizen"
        if self.flame:
            return BOOST, "Flamme"
        if self.sequence:
            return BOOST, "Startsequenz"
        if self.burner_last_active is not None and now - self.burner_last_active < self.nachlauf_s:
            return BOOST, "Nachlauf"
        if self.low >= HIGH:
            return BOOST, "Normalwert 100"
        return ABGESENKT, "Normalbetrieb"


class PumpGuard:
    """Serial side. `do_request(fc, addr, n, data) -> (rc, addr, data)`."""

    def __init__(self, settings, logger, do_request, mqtt_factory=None):
        self.settings = settings
        self.log = logger
        self.do_request = do_request
        self.logic = GuardLogic()
        self.base = str(getattr(settings, "mqtt_topic", "openv")).rstrip("/") + "/pump_guard"
        self.active = not getattr(settings, "vs1protocol", True)
        self.next_state = 0.0
        self.next_slow = 0.0
        self.next_ram = 0.0
        self.rr_state = 0
        self.rr_slow = 0
        self.ram = None
        self.last_low_written = None
        self.repairs = 0
        self.writes = 0
        self.last_pub = 0.0
        self.last_state = None
        self.lock = threading.Lock()
        self.client = None
        if mqtt_factory is None and getattr(settings, "mqtt_broker", None):
            mqtt_factory = self._paho_client
        if mqtt_factory is not None:
            try:
                self._mqtt(mqtt_factory)
            except Exception as exc:  # never break the splitter
                self.log.warning(f"pump_guard: MQTT setup failed: {exc}")
        self.log.info(f"pump_guard {VERSION}: {'aktiv (P300)' if self.active else 'inaktiv (VS1)'}")

    # ---- MQTT -----------------------------------------------------------
    def _paho_client(self):
        import paho.mqtt.client as paho
        s = self.settings
        cid = "olswitch_pumpguard_" + str(s.mqtt_topic).replace("/", "").replace(" ", "")
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

    def _mqtt(self, factory):
        c = factory()
        if c is None:
            raise RuntimeError("no MQTT client")
        c.on_message = self._on_message
        self.client = c
        if getattr(c, "on_connect", None) is None:
            self._on_connect(c, None, None, 0)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        topics = ["enabled", "low", "nachlauf"]
        client.subscribe([(f"{self.base}/{t}/set", 0) for t in topics]
                         + [(f"{self.base}/{t}/state", 0) for t in topics])
        client.publish(f"{self.base}/protocol", "P300" if self.active else "VS1", retain=True)
        self.last_state = None  # republish status after (re)connect
        if not self.active:
            self._publish_status(AUS, "nur im P300-Betrieb", force=True)

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic[len(self.base) + 1:]
            name, kind = topic.split("/", 1)
            payload = msg.payload.decode(errors="replace").strip()
            if kind == "state" and not msg.retain:
                return  # our own echo; only retained state restores config
            if kind not in ("set", "state"):
                return
            with self.lock:
                if name == "enabled":
                    val = payload.upper() in ("ON", "1", "TRUE", "EIN")
                    if val and not self.logic.enabled:
                        self.logic.error = None  # switching on acknowledges an error
                    self.logic.enabled = val
                    out = "ON" if val else "OFF"
                elif name == "low":
                    v = int(float(payload))
                    if not LOW_MIN <= v <= LOW_MAX:
                        return
                    self.logic.low = v
                    out = str(v)
                elif name == "nachlauf":
                    v = float(payload)
                    if not 0 <= v <= NACHLAUF_MAX_MIN:
                        return
                    self.logic.nachlauf_s = v * 60.0
                    out = str(int(v) if v == int(v) else v)
                else:
                    return
            if kind == "set":
                client.publish(f"{self.base}/{name}/state", out, retain=True)
        except Exception as exc:
            self.log.warning(f"pump_guard: bad message {msg.topic}: {exc}")

    def _publish_status(self, state, reason, now=None, force=False):
        now = time.monotonic() if now is None else now
        changed = (state, reason) != self.last_state
        if not (force or changed or now - self.last_pub >= 10):
            return
        if changed and self.last_state is not None:
            self.log.info(f"pump_guard: {state} ({reason})")
        self.last_state = (state, reason)
        self.last_pub = now
        if self.client is None:
            return
        lg = self.logic
        status = {"state": state, "reason": reason, "ram_e7": self.ram, "low": lg.low,
                  "nachlauf_min": round(lg.nachlauf_s / 60.0, 1),
                  "enabled": lg.enabled, "repairs": self.repairs, "writes": self.writes,
                  "flame": lg.flame, "sequence": lg.sequence, "lockout": lg.lockout,
                  "ww": lg.ww, "valve": lg.valve, "e7": lg.e7, "fault": lg.fault,
                  "protocol": "P300" if self.active else "VS1", "version": VERSION,
                  "timestamp": int(time.time())}
        try:
            self.client.publish(f"{self.base}/status", json.dumps(status), retain=True)
            self.client.publish(f"{self.base}/zustand", state, retain=True)
        except Exception:
            pass

    # ---- serial ---------------------------------------------------------
    def _read(self, spec):
        if spec not in ALLOWED_READS:
            raise RuntimeError(f"blocked read {spec}")
        fc, addr, n = spec
        rc, _, data = self.do_request(fc, addr, n, b"")
        if rc != 0x01 or data is None or len(data) != n:
            return rc, None
        return rc, bytes(data)

    def _write_ram(self, value):
        if not (value == HIGH or (value == self.logic.low and LOW_MIN <= value < HIGH)):
            raise RuntimeError(f"blocked RAM value {value}")
        rc, _, _ = self.do_request(0x04, RAM_BLOCK + RAM_E7_OFFSET, 1, bytes([value]))
        self.writes += 1
        return rc

    def tick(self, now=None):
        """Do at most one telegram. Returns retcode or None if nothing was sent."""
        if not self.active:
            return None
        now = time.monotonic() if now is None else now
        try:
            with self.lock:
                state, reason = self.logic.decide(now)
                low = self.logic.low
            self._publish_status(state, reason, now)
            lowering = state == ABGESENKT
            # 1) leaving ABGESENKT: write 100 once right away (faster boost)
            if not lowering and self.ram not in (None, HIGH):
                rc = self._write_ram(HIGH)
                if rc == 0x01:
                    self.ram = HIGH
                else:
                    self.ram = None     # unknown; the firmware reload restores 100 anyway
                return rc
            # 2) RAM supervision while lowering: read, and repair in the same tick
            #    (read + write back-to-back, exactly like the Phase-0 probe)
            if lowering and now >= self.next_ram:
                self.next_ram = now + RAM_PERIOD_S
                rc, data = self._read(READ_RAM)
                if data is None:
                    return rc
                ram = data[RAM_E7_OFFSET]
                prev, self.ram = self.ram, ram
                if ram == low:
                    return rc
                if ram == HIGH or ram == self.last_low_written:
                    if ram == HIGH:
                        # the firmware reload restored 100: proof that E7 is coded 100
                        with self.lock:
                            self.logic.update("e7", bytes([HIGH]), now)
                        if prev not in (None, HIGH):
                            self.repairs += 1
                    rc = self._write_ram(low)
                    if rc == 0x01:
                        self.ram, self.last_low_written = low, low
                        self.next_ram = now + RAM_QUIET_S
                    return rc
                self.logic.error = f"unerwarteter RAM-Wert {ram}"
                return rc
            # 3) slow reads
            if now >= self.next_slow:
                self.next_slow = now + SLOW_PERIOD_S / 2
                # 0x27E7 mirrors the RAM copy: while lowering it would read `low`,
                # so the coded value is then proven by the reload to 100 instead.
                use_e7 = self.rr_slow % 2 == 1 and not lowering and self.ram in (None, HIGH)
                spec, key = (READ_E7, "e7") if use_e7 else (READ_FAULT, "fault")
                self.rr_slow += 1
                return self._read_update(spec, key, now)
            # 4) fast state reads (round robin)
            if now >= self.next_state:
                self.next_state = now + STATE_PERIOD_S / 3
                spec, key = ((READ_GFA, "gfa"), (READ_WW, "ww"), (READ_VALVE, "valve"))[self.rr_state % 3]
                self.rr_state += 1
                return self._read_update(spec, key, now)
            return None
        except Exception as exc:
            with self.lock:
                self.logic.error = f"Ausnahme: {exc}"
            self.log.warning(f"pump_guard: {exc}")
            return None

    def _read_update(self, spec, key, now):
        rc, data = self._read(spec)
        if data is not None:
            with self.lock:
                self.logic.update(key, data, now)
        return rc

    def reset_link(self, do_request=None):
        """Called after a serial re-open: RAM state unknown, keep config."""
        if do_request is not None:
            self.do_request = do_request
        self.ram = None
        self.last_low_written = None
        self.next_ram = self.next_slow = self.next_state = 0.0
        with self.lock:
            self.logic.ts = {}
            self.logic.error = None


_guard = None


def get(settings, logger, do_request, mqtt_factory=None):
    """Module singleton; survives splitter-internal restarts of the main loop."""
    global _guard
    if _guard is None:
        _guard = PumpGuard(settings, logger, do_request, mqtt_factory)
    else:
        _guard.reset_link(do_request)
    return _guard
