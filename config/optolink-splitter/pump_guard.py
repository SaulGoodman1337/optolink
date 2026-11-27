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
  nachlauf_aktiv/set ON|OFF  -> nachlauf_aktiv/state (default ON)
  nachlauf/set 0..30 minutes -> nachlauf/state (default 3)
  vorboost_aktiv/set ON|OFF  -> vorboost_aktiv/state (default OFF)
  vorboost/set 0..10 K       -> vorboost/state (default 1.0)

The boost follows the normal burner cycle only: DHW, valve not on heating,
start sequence, flame and the optional Nachlauf after the burner stopped.
(v1.2 also boosted during the anti-cycling lock; removed again in 1.3.0 on
the user's request.)

Pre-boost (Vorboost, Phase 3): the guard learns at every burner start how far
the boiler temperature (0x0810) was below the effective setpoint (0x555A) when
the firmware started the burner. It boosts already when the boiler is within
`vorboost` K of that learned threshold, so the pump moves heat out of the
boiler before the burner fires at full power for flame stabilisation.
  status       JSON (retained), zustand = state word, protocol = P300|VS1

Burner curve (Brenner-Kennlinie, optional, 1.4.0): during a heating burn the
pump does not have to run at 100 % all the time. After a start hold
(`kurve_start_s`, full start power) the guard sets the pump minimum from the
headroom to the learned switch-off temperature (boiler temperature at the
last heating burner stops): `kurve_min` % far below, rising linearly over
KURVE_SPAN_K to 100 % at `kurve_voll_k` K before switch-off. DHW, valve not
on heating, unknown/stale temperatures or no learned switch-off -> 100 %.
Less flow while firing means the boiler reaches switch-off sooner, so this is
meant for an A/B comparison and is off by default.
  kurve_aktiv/set ON|OFF, kurve_min/set 20..100 %, kurve_voll_k/set 0..15 K,
  kurve_start_s/set 0..300 s

Flue-gas spread (Abgas-Spreizung, optional, 1.5.0): the WB2A has no return
sensor. While firing, the flue-gas temperature (0x0816, same sensor as 0x0808)
follows the return side of the condensing heat exchanger, so
"boiler - flue gas" serves as a spread proxy (measured ~2 K at 100 % pump).
With `spreizung_aktiv` the burner curve becomes a slow step controller after
the start hold: spread below `spreizung_soll` - 0.5 K -> pump -5 %, above
+0.5 K -> +5 % (every SPREIZ_STEP_S, within kurve_min..100). The switch-off
protection (100 % within kurve_voll_k of the learned switch-off temperature)
stays active. Stale flue-gas value -> 100 %.
  spreizung_aktiv/set ON|OFF, spreizung_soll/set 1..20 K
"""
from __future__ import annotations

import json
import threading
import time

VERSION = "1.5.0"

RAM_BLOCK, RAM_E7_OFFSET = 0x20A0, 5          # 0x20A5
HIGH = 100
LOW_MIN, LOW_MAX = 20, 100
NACHLAUF_MAX_MIN = 30
VORBOOST_MAX_K = 10.0
VORBOOST_HYST_K = 0.5          # release the pre-boost only 0.5 K below its trigger
START_MARGIN_DEFAULT_K = 4.0   # coding plug "Einschaltdifferenz" 4 K until learned
START_MARGIN_ALPHA = 0.3       # EMA weight of each observed burner start
KURVE_SPAN_K = 5.0             # linear ramp width below the full-speed point
SPREIZ_STEP_S = 20.0           # flue gas reacts slowly: one 5-% step per 20 s at most
SPREIZ_DEADBAND_K = 0.5
KURVE_STEP = 5                 # pump value granularity (fewer distinct writes)
AUS_ALPHA = 0.3                # EMA weight of each observed switch-off temperature
START_LOOKBACK_S = (3.0, 20.0) # use temperatures 3..20 s before the start: the firmware
                               # drops the effective setpoint (e.g. 16.5) at the start

READ_GFA = (0x01, 0x55D3, 9)     # byte5: 0x20 flame, 0x40 lockout; bytes6/7 GG1 sequence
READ_WW = (0x01, 0x650A, 1)      # 1 = DHW charging active
READ_VALVE = (0x01, 0x0A10, 1)   # 1 = heating
READ_FAULT = (0x01, 0x5738, 1)   # 0 = no fault
READ_E7 = (0x01, 0x27E7, 1)      # heating-pump minimum; NOTE: reads the active RAM copy
                                 # (0x20A5), so it is only meaningful while not lowering
READ_KESSEL = (0x01, 0x0810, 2)  # boiler temperature, int16 LE / 10
READ_SOLL = (0x01, 0x555A, 2)    # effective boiler setpoint, int16 LE / 10
READ_ABGAS = (0x01, 0x0816, 2)   # flue-gas temperature (== 0x0808), int16 LE / 10
READ_RAM = (0x03, RAM_BLOCK, 32)
ALLOWED_READS = {READ_GFA, READ_WW, READ_VALVE, READ_FAULT, READ_E7, READ_KESSEL, READ_SOLL, READ_ABGAS,
                 READ_RAM}

STATE_PERIOD_S = 1.0       # every state key once per second (round robin)
SLOW_PERIOD_S = 10.0       # fault + coded E7, each once per period
TEMP_PERIOD_S = 2.0        # boiler temperature + setpoint, each once per period
TEMP_STALE_S = 10.0        # older -> no pre-boost (lowering itself is not blocked)
RAM_PERIOD_S = 0.1         # RAM supervision while lowering (in practice: every tick)
RAM_QUIET_S = 1.4          # firmware reload seen 1.7-2.7 s after a write: no reads before
STALE_S = 5.0              # state older than this -> no lowering

ABGESENKT, BOOST, AUS, GESPERRT, FEHLER = "ABGESENKT", "BOOST", "AUS", "GESPERRT", "FEHLER"
KENNLINIE = "KENNLINIE"    # lowered to the burner curve value while firing
LOWERING = (ABGESENKT, KENNLINIE)


class GuardLogic:
    """Pure decision logic (no I/O), unit-testable."""

    def __init__(self):
        self.enabled = False
        self.low = 30
        self.nachlauf_aktiv = True
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
        # pre-boost (Vorboost): boost already when the boiler is close to its start threshold
        self.vorboost_aktiv = False
        self.vorboost_k = 1.0              # K before the learned start threshold
        self.kessel = None
        self.soll = None
        self.start_margin = START_MARGIN_DEFAULT_K   # learned (soll - kessel) at burner starts
        self.start_margins = []            # last observed values (for HA/diagnosis)
        self.vorboost_active = False
        self.starts = 0
        # burner curve (Brenner-Kennlinie)
        self.kurve_aktiv = False
        self.kurve_min = 60
        self.kurve_voll_k = 3.0
        self.kurve_start_s = 60.0
        self.aus_temp = None               # learned boiler temperature at heating burner stop
        self.aus_werte = []
        self.flame_since = None
        self.kurve_wert = None             # last computed curve value (diagnosis)
        # flue-gas spread controller (Abgas-Spreizung)
        self.spreizung_aktiv = False
        self.spreizung_soll = 5.0
        self.abgas = None
        self._sp_val = HIGH
        self._sp_last = None
        self._kessel_flame = None
        self._prev_flame = None
        self._prev_burner = None
        self._temp_hist = []               # (t, kessel, soll) for the start lookback

    def update(self, key, value, now):
        if key == "gfa":
            b = value
            self.flame = bool(b[5] & 0x20)
            self.lockout = bool(b[5] & 0x40)
            self.sequence = bool(b[6] or b[7])
            burner = self.flame or self.sequence
            if self.flame and not self._prev_flame:
                self.flame_since = now
                self._sp_val, self._sp_last = HIGH, None
                self._kessel_flame = None
            elif not self.flame and self._prev_flame:
                self._learn_stop(now)
                self.flame_since = None
            self._prev_flame = self.flame
            if burner and self._prev_burner is False:
                self._learn_start(now)
            self._prev_burner = burner
            if burner:
                self.burner_last_active = now
        elif key in ("kessel", "soll", "abgas"):
            v = int.from_bytes(bytes(value[:2]), "little", signed=True) / 10.0
            if not -20.0 <= v <= 110.0:
                return          # implausible: ignore, goes stale -> no pre-boost
            setattr(self, key, v)
            if key == "abgas":
                self.ts[key] = now
                return
            if key == "kessel" and self.flame:
                # peak boiler temperature of this burn = switch-off point
                if self._kessel_flame is None or v >= self._kessel_flame[1]:
                    self._kessel_flame = (now, v)
            if self.kessel is not None and self.soll is not None:
                self._temp_hist = [h for h in self._temp_hist if now - h[0] <= START_LOOKBACK_S[1]]
                self._temp_hist.append((now, self.kessel, self.soll))
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

    def _learn_start(self, now):
        """A burner start began: remember how far below the setpoint the boiler was."""
        self.starts += 1
        if self.ww or self.valve != 1:
            return
        before = [h for h in self._temp_hist
                  if START_LOOKBACK_S[0] <= now - h[0] <= START_LOOKBACK_S[1]]
        if not before:
            return
        _, kessel, soll = before[-1]
        margin = round(soll - kessel, 1)
        if not 0.0 <= margin <= 30.0:
            return
        self.start_margins = (self.start_margins + [margin])[-10:]
        self.start_margin = round((1 - START_MARGIN_ALPHA) * self.start_margin
                                  + START_MARGIN_ALPHA * margin, 2)

    def _learn_stop(self, now):
        """Heating burner stopped: remember the boiler temperature (switch-off point)."""
        if self.ww or self.valve != 1 or self._kessel_flame is None:
            return
        t_k, k_flame = self._kessel_flame
        if now - t_k > 60.0:
            return      # no recent boiler value from this burn
        if self.flame_since is None or now - self.flame_since < self.kurve_start_s:
            return      # very short burns are dominated by the start phase
        k = round(k_flame, 1)
        self.aus_werte = (self.aus_werte + [k])[-10:]
        self.aus_temp = k if self.aus_temp is None else round(
            (1 - AUS_ALPHA) * self.aus_temp + AUS_ALPHA * k, 2)

    def spreizung(self, now):
        """Boiler - flue gas (K), or None when unknown/stale."""
        if self.kessel is None or self.abgas is None:
            return None
        for k in ("kessel", "abgas"):
            if k not in self.ts or now - self.ts[k] > TEMP_STALE_S:
                return None
        return round(self.kessel - self.abgas, 1)

    def kurve(self, now):
        """Pump value for the burner curve, or None (-> 100 %)."""
        self.kurve_wert = None
        if not (self.kurve_aktiv or self.spreizung_aktiv) or not self.flame or self.flame_since is None:
            return None
        if now - self.flame_since < self.kurve_start_s:
            return None
        if "kessel" not in self.ts or now - self.ts["kessel"] > TEMP_STALE_S or self.kessel is None:
            return None
        if self.spreizung_aktiv:
            return self._spreiz_regler(now)
        if self.aus_temp is None:
            return None
        headroom = self.aus_temp - self.kessel
        if headroom <= self.kurve_voll_k:
            return None
        frac = min(1.0, (headroom - self.kurve_voll_k) / KURVE_SPAN_K)
        v = HIGH - frac * (HIGH - self.kurve_min)
        v = int(-(-v // KURVE_STEP) * KURVE_STEP)      # round up to the step
        v = max(LOW_MIN, min(HIGH, v))
        if v >= HIGH:
            return None
        self.kurve_wert = v
        return v

    def _spreiz_regler(self, now):
        sp = self.spreizung(now)
        if sp is None:
            self._sp_val, self._sp_last = HIGH, None
            return None
        if self.aus_temp is not None and self.aus_temp - self.kessel <= self.kurve_voll_k:
            self._sp_val, self._sp_last = HIGH, now      # switch-off protection
            return None
        if self._sp_last is None or now - self._sp_last >= SPREIZ_STEP_S:
            if sp < self.spreizung_soll - SPREIZ_DEADBAND_K:
                self._sp_val -= KURVE_STEP              # spread too small: less flow
            elif sp > self.spreizung_soll + SPREIZ_DEADBAND_K:
                self._sp_val += KURVE_STEP              # spread too large: more flow
            self._sp_val = max(max(LOW_MIN, self.kurve_min), min(HIGH, self._sp_val))
            self._sp_last = now
        if self._sp_val >= HIGH:
            return None
        self.kurve_wert = self._sp_val
        return self._sp_val

    def temps_fresh(self, now):
        return all(k in self.ts and now - self.ts[k] <= TEMP_STALE_S for k in ("kessel", "soll")) \
            and self.kessel is not None and self.soll is not None

    def vorboost(self, now):
        """True when the boiler is within `vorboost_k` of the learned start threshold."""
        if not self.vorboost_aktiv or self.vorboost_k <= 0 or not self.temps_fresh(now):
            self.vorboost_active = False
            return False
        below = self.soll - self.kessel            # grows while the boiler cools down
        trigger = self.start_margin - self.vorboost_k
        if self.vorboost_active:
            self.vorboost_active = below >= trigger - VORBOOST_HYST_K
        else:
            self.vorboost_active = below >= trigger
        return self.vorboost_active

    def fresh(self, now):
        need = {"gfa": STALE_S, "ww": STALE_S, "valve": STALE_S,
                "fault": 3 * SLOW_PERIOD_S, "e7": 3 * SLOW_PERIOD_S}
        return all(k in self.ts and now - self.ts[k] <= lim for k, lim in need.items())

    def decide(self, now):
        """Return (state, reason). Only ABGESENKT (`low`) and KENNLINIE (`kurve_wert`) lower."""
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
            v = self.kurve(now)
            if v is not None:
                if self.spreizung_aktiv:
                    return KENNLINIE, f"Abgas-Spreizung {v} %"
                return KENNLINIE, f"Brenner-Kennlinie {v} %"
            return BOOST, "Flamme"
        if self.sequence:
            return BOOST, "Startsequenz"
        if self.nachlauf_aktiv and self.burner_last_active is not None \
                and now - self.burner_last_active < self.nachlauf_s:
            return BOOST, "Nachlauf"
        if self.vorboost(now):
            return BOOST, "Vorboost"
        if self.low >= HIGH:
            return BOOST, "Normalwert 100"
        return ABGESENKT, "Normalbetrieb"


class PumpGuard:
    """Serial side. `do_request(fc, addr, n, data) -> (rc, addr, data)`."""

    def __init__(self, settings, logger, do_request, mqtt_factory=None, boost_after_start=True):
        self.settings = settings
        # after a (re)start the burner history is unknown: treat it as "just active" so the
        # Nachlauf boost covers a pause that was already running (fail-safe direction)
        self._boost_after_start = boost_after_start
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
        self.next_temp = 0.0
        self.rr_temp = 0
        self.ram = None
        self.last_low_written = None
        self.repairs = 0
        self.writes = 0
        self._target = None
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
        topics = ["enabled", "low", "nachlauf", "nachlauf_aktiv", "vorboost", "vorboost_aktiv",
                  "kurve_aktiv", "kurve_min", "kurve_voll_k", "kurve_start_s",
                  "spreizung_aktiv", "spreizung_soll"]
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
                elif name == "kurve_min":
                    v = int(float(payload))
                    if not LOW_MIN <= v <= LOW_MAX:
                        return
                    self.logic.kurve_min = v
                    out = str(v)
                elif name == "kurve_voll_k":
                    v = round(float(payload), 1)
                    if not 0 <= v <= 15:
                        return
                    self.logic.kurve_voll_k = v
                    out = str(v)
                elif name == "kurve_start_s":
                    v = int(float(payload))
                    if not 0 <= v <= 300:
                        return
                    self.logic.kurve_start_s = float(v)
                    out = str(v)
                elif name == "spreizung_soll":
                    v = round(float(payload), 1)
                    if not 1 <= v <= 20:
                        return
                    self.logic.spreizung_soll = v
                    out = str(v)
                elif name in ("nachlauf_aktiv", "vorboost_aktiv", "kurve_aktiv", "spreizung_aktiv"):
                    val = payload.upper() in ("ON", "1", "TRUE", "EIN")
                    setattr(self.logic, name, val)
                    out = "ON" if val else "OFF"
                elif name == "vorboost":
                    v = round(float(payload), 1)
                    if not 0 <= v <= VORBOOST_MAX_K:
                        return
                    self.logic.vorboost_k = v
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
                  "vorboost_k": lg.vorboost_k, "vorboost": lg.vorboost_active,
                  "vorboost_aktiv": lg.vorboost_aktiv, "nachlauf_aktiv": lg.nachlauf_aktiv,
                  "kurve_aktiv": lg.kurve_aktiv, "kurve_min": lg.kurve_min,
                  "spreizung_aktiv": lg.spreizung_aktiv, "spreizung_soll": lg.spreizung_soll,
                  "abgas": lg.abgas, "spreizung": lg.spreizung(now),
                  "kurve_voll_k": lg.kurve_voll_k, "kurve_start_s": lg.kurve_start_s,
                  "kurve_wert": lg.kurve_wert, "aus_temp": lg.aus_temp, "aus_werte": lg.aus_werte,
                  "kessel": lg.kessel, "soll": lg.soll,
                  "unter_soll": (round(lg.soll - lg.kessel, 1)
                                 if lg.kessel is not None and lg.soll is not None else None),
                  "start_schwelle": lg.start_margin, "start_werte": lg.start_margins,
                  "starts": lg.starts,
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
        if not (value == HIGH or (value == self._target and LOW_MIN <= value < HIGH)):
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
                if self._boost_after_start:
                    self._boost_after_start = False
                    if self.logic.burner_last_active is None:
                        self.logic.burner_last_active = now
                state, reason = self.logic.decide(now)
                low = self.logic.kurve_wert if state == KENNLINIE else self.logic.low
                self._target = low
            self._publish_status(state, reason, now)
            lowering = state in LOWERING
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
            # 4) boiler temperature / setpoint (pre-boost + learning the start threshold)
            if now >= self.next_temp:
                self.next_temp = now + TEMP_PERIOD_S / 3
                spec, key = ((READ_KESSEL, "kessel"), (READ_SOLL, "soll"),
                             (READ_ABGAS, "abgas"))[self.rr_temp % 3]
                self.rr_temp += 1
                return self._read_update(spec, key, now)
            # 5) fast state reads (round robin)
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
        self.next_ram = self.next_slow = self.next_state = self.next_temp = 0.0
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
