#!/opt/optolink/venv/bin/python
"""BLE tyre-pressure cap on the expansion vessel (MAG) -> Home Assistant.

A cheap Bluetooth TPMS valve cap screwed onto the Schrader valve of the
heating expansion vessel measures the gas side of the vessel:

* while the water pressure is below the vessel precharge it shows the
  precharge (Vordruck),
* as soon as the water pressure is higher, the membrane lies against the gas
  side and the cap follows the system pressure.

So the value is a free system-pressure sensor during operation and shows
precharge loss when the vessel is isolated and drained on the water side.

Reception: the caps only advertise; Home Assistant receives them through its
Bluetooth adapters / ESPHome Bluetooth proxies. This service subscribes to
Home Assistant's raw advertisement stream (websocket command
``bluetooth/subscribe_advertisements``), decodes the configured caps and
publishes them as their own MQTT-discovery device. It never opens the
Optolink port and never talks to the boiler.

Supported format ("ITPMS / WODHMIEY", Spedal / Shenzhen Xlink caps,
verified live 2026-11-26 against the boiler manometer, 1.23 vs ~1.3 bar):
manufacturer id 0x00AC (172), service UUID 0xFBB0, 15 payload bytes

    b0      battery voltage = b0 * 0.01 + 1.22 V
    b1      pressure raw, bar = raw * 0.03144 (gauge)
    b2      temperature = b2 - 55 degC
    b3      status/alarm flags (reported raw)
    b6      pressure high byte flag (only when 0 or 1; the Spedal caps send
            0xFF here, which breaks the HACS "tpms_ble" fallback)
    b9..14  sensor MAC, reversed

Configuration ``/etc/optolink/mag-tpms.json``::

    {
      "sensors": [{"address": "61:41:00:02:FF:B2", "id": "mag",
                   "name": "MAG Ausdehnungsgefäß"}],
      "ha_url": "ws://homeassistant:8123/api/websocket",   # optional
      "stale_minutes": 360                                 # optional
    }

Evaluation (``<base>/tpms/<id>/auswertung``): a rolling 24 h window of
pressure and cap temperature (one sample per minute, persisted in
``/var/lib/optolink-mag-tpms``) gives min/max pressure and the classic
expansion-vessel check: pressure "cold" (median at the lowest cap
temperatures) vs. "warm" (median at the highest). A healthy vessel keeps the
cold/warm swing small (a few tenths of a bar for a full heat-up); a large
swing means missing precharge or an undersized vessel. ``hub_pro_10k``
normalises the swing to 10 K of temperature change (needs >= 10 K spread).

``ha_url`` defaults to port 8123 on the MQTT broker host. The Home Assistant
long-lived token is read from ``$CREDENTIALS_DIRECTORY/ha-token`` (systemd
LoadCredential) or ``/etc/optolink/ha-token``.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import signal
import sys
import time

APP_DIR = "/opt/optolink"
CONFIG_FILE = os.environ.get("OPTOLINK_MAG_TPMS_CONFIG", "/etc/optolink/mag-tpms.json")
TOKEN_FILE = "/etc/optolink/ha-token"
STATE_DIR = os.environ.get("OPTOLINK_MAG_TPMS_STATE_DIR", "/var/lib/optolink-mag-tpms")
WINDOW_S = 24 * 3600
SAMPLE_S = 60
MANUFACTURER_ID = 172
SERVICE_UUID = "0000fbb0-0000-1000-8000-00805f9b34fb"
PRESSURE_STEP_BAR = 0.03144


def norm_mac(mac: str) -> str:
    return mac.strip().upper()


def decode_itpms(data: bytes, address: str | None = None) -> dict | None:
    """Decode the 0x00AC manufacturer payload. Returns None if not plausible."""
    if len(data) < 7:
        return None
    if len(data) >= 15 and address is not None:
        embedded = ":".join(f"{b:02X}" for b in data[9:15][::-1])
        if embedded != norm_mac(address):
            return None
    raw = data[1] + (256 if data[6] == 1 else 0)
    voltage = round(data[0] * 0.01 + 1.22, 2)
    return {
        "druck": round(raw * PRESSURE_STEP_BAR, 2),
        "druck_roh": raw,
        "temperatur": data[2] - 55,
        "batterie_spannung": voltage,
        "batterie": battery_percent(voltage),
        "status": data[3],
    }


def battery_percent(voltage: float) -> int:
    """CR1632-ish lithium cell: 3.0 V full, 2.5 V empty (linear, clamped)."""
    pct = (voltage - 2.5) / 0.5 * 100
    return int(max(0, min(100, round(pct))))


def extract(adv: dict, addresses: set[str]) -> tuple[str, dict] | None:
    """Pick and decode a HA advertisement dict if it belongs to a configured cap."""
    addr = norm_mac(adv.get("address", ""))
    if addr not in addresses:
        return None
    mfr = adv.get("manufacturer_data") or {}
    payload = mfr.get(str(MANUFACTURER_ID)) or mfr.get(MANUFACTURER_ID)
    if not payload:
        return None
    try:
        data = bytes.fromhex(payload)
    except ValueError:
        return None
    values = decode_itpms(data, addr)
    if values is None:
        return None
    values["rssi"] = adv.get("rssi")
    values["empfaenger"] = adv.get("source")
    ts = adv.get("time")
    when = datetime.datetime.fromtimestamp(ts if ts else time.time(), datetime.timezone.utc)
    values["zuletzt"] = when.isoformat(timespec="seconds")
    return addr, values


def _median(values: list[float]) -> float:
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


class PressureWindow:
    """Rolling window of (ts, bar, degC) samples for the cold/warm check."""

    def __init__(self, window_s: float = WINDOW_S, sample_s: float = SAMPLE_S):
        self.window_s = window_s
        self.sample_s = sample_s
        self.samples: list[list[float]] = []

    def add(self, ts: float, bar: float, temp: float) -> bool:
        if self.samples and ts - self.samples[-1][0] < self.sample_s:
            return False
        self.samples.append([ts, bar, temp])
        self.prune(ts)
        return True

    def prune(self, now: float):
        cut = now - self.window_s
        while self.samples and self.samples[0][0] < cut:
            self.samples.pop(0)

    def summary(self, now: float | None = None) -> dict:
        if now is not None:
            self.prune(now)
        out = {k: None for k in ("druck_min", "druck_max", "druck_kalt", "druck_warm",
                                 "temp_kalt", "temp_warm", "druckhub", "hub_pro_10k")}
        out["proben"] = len(self.samples)
        if len(self.samples) < 10 or self.samples[-1][0] - self.samples[0][0] < 3600:
            return out
        bars = [s[1] for s in self.samples]
        temps = [s[2] for s in self.samples]
        t_min, t_max = min(temps), max(temps)
        p_cold = _median([s[1] for s in self.samples if s[2] <= t_min + 1])
        p_warm = _median([s[1] for s in self.samples if s[2] >= t_max - 1])
        spread = t_max - t_min
        out.update({
            "druck_min": round(min(bars), 2),
            "druck_max": round(max(bars), 2),
            "druck_kalt": round(p_cold, 2),
            "druck_warm": round(p_warm, 2),
            "temp_kalt": t_min,
            "temp_warm": t_max,
            "druckhub": round(p_warm - p_cold, 2),
            "hub_pro_10k": round((p_warm - p_cold) / spread * 10, 3) if spread >= 10 else None,
        })
        return out

    def load(self, path: str):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.samples = [list(map(float, s[:3])) for s in data if len(s) >= 3]
        except (OSError, ValueError, TypeError):
            self.samples = []

    def save(self, path: str):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.samples, fh)
        os.replace(tmp, path)


ENTITIES = [
    # key, name, extra discovery fields
    ("druck", "Druck", {"device_class": "pressure", "unit_of_measurement": "bar",
                        "state_class": "measurement", "suggested_display_precision": 2,
                        "icon": "mdi:gauge"}),
    ("temperatur", "Temperatur", {"device_class": "temperature", "unit_of_measurement": "°C",
                                  "state_class": "measurement"}),
    ("batterie", "Batterie", {"device_class": "battery", "unit_of_measurement": "%",
                              "state_class": "measurement", "entity_category": "diagnostic"}),
    ("batterie_spannung", "Batteriespannung", {"device_class": "voltage", "unit_of_measurement": "V",
                                               "state_class": "measurement",
                                               "suggested_display_precision": 2,
                                               "entity_category": "diagnostic"}),
    ("rssi", "Signal", {"device_class": "signal_strength", "unit_of_measurement": "dBm",
                        "state_class": "measurement", "entity_category": "diagnostic"}),
    ("zuletzt", "Zuletzt empfangen", {"device_class": "timestamp", "entity_category": "diagnostic"}),
    ("empfaenger", "Empfänger", {"entity_category": "diagnostic", "icon": "mdi:bluetooth"}),
    ("status", "Status roh", {"entity_category": "diagnostic", "icon": "mdi:information-outline"}),
]


EVAL_ENTITIES = [
    ("druck_min", "Druck Minimum 24 h", {"device_class": "pressure", "unit_of_measurement": "bar",
                                         "state_class": "measurement", "suggested_display_precision": 2}),
    ("druck_max", "Druck Maximum 24 h", {"device_class": "pressure", "unit_of_measurement": "bar",
                                         "state_class": "measurement", "suggested_display_precision": 2}),
    ("druck_kalt", "Druck kalt 24 h", {"device_class": "pressure", "unit_of_measurement": "bar",
                                       "state_class": "measurement", "suggested_display_precision": 2,
                                       "icon": "mdi:snowflake-thermometer"}),
    ("druck_warm", "Druck warm 24 h", {"device_class": "pressure", "unit_of_measurement": "bar",
                                       "state_class": "measurement", "suggested_display_precision": 2,
                                       "icon": "mdi:sun-thermometer"}),
    ("temp_kalt", "Temperatur kalt 24 h", {"device_class": "temperature", "unit_of_measurement": "°C",
                                           "entity_category": "diagnostic"}),
    ("temp_warm", "Temperatur warm 24 h", {"device_class": "temperature", "unit_of_measurement": "°C",
                                           "entity_category": "diagnostic"}),
    ("druckhub", "Druckhub kalt/warm 24 h", {"device_class": "pressure", "unit_of_measurement": "bar",
                                             "state_class": "measurement",
                                             "suggested_display_precision": 2,
                                             "icon": "mdi:arrow-expand-vertical"}),
    ("hub_pro_10k", "Druckhub pro 10 K", {"unit_of_measurement": "bar/10K", "state_class": "measurement",
                                          "suggested_display_precision": 3,
                                          "icon": "mdi:chart-bell-curve"}),
    ("proben", "Proben 24 h", {"state_class": "measurement", "entity_category": "diagnostic",
                               "icon": "mdi:counter"}),
]


def discovery_messages(base: str, sensor: dict) -> list[tuple[str, dict]]:
    mac = norm_mac(sensor["address"])
    sid = sensor.get("id") or mac.replace(":", "").lower()
    uid = "optolink_tpms_" + mac.replace(":", "").lower()
    state = f"{base}/tpms/{sid}/state"
    avail = f"{base}/tpms/{sid}/availability"
    device = {
        "identifiers": [uid],
        "connections": [["bluetooth", mac]],
        "name": sensor.get("name") or f"TPMS {mac}",
        "manufacturer": "Shenzhen Xlink (Spedal)",
        "model": "BLE TPMS Ventilkappe (ITPMS 0xFBB0)",
    }
    out = []
    for key, name, extra in ENTITIES:
        cfg = {
            "name": name,
            "unique_id": f"{uid}_{key}",
            "default_entity_id": f"sensor.{sid}_{key}",
            "state_topic": state,
            "value_template": "{{ value_json.%s }}" % key,
            "availability_topic": avail,
            "device": device,
        }
        cfg.update(extra)
        out.append((f"homeassistant/sensor/{uid}/{key}/config", cfg))
    for key, name, extra in EVAL_ENTITIES:
        cfg = {
            "name": name,
            "unique_id": f"{uid}_{key}",
            "default_entity_id": f"sensor.{sid}_{key}",
            "state_topic": f"{base}/tpms/{sid}/auswertung",
            "value_template": "{{ value_json.%s }}" % key,
            "availability_topic": avail,
            "device": device,
        }
        cfg.update(extra)
        out.append((f"homeassistant/sensor/{uid}/{key}/config", cfg))
    return out


def load_config(path: str = CONFIG_FILE) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    sensors = cfg.get("sensors") or []
    if not sensors:
        raise RuntimeError(f"no sensors configured in {path}")
    for s in sensors:
        s["address"] = norm_mac(s["address"])
    cfg.setdefault("stale_minutes", 360)
    return cfg


def read_token() -> str:
    cred = os.environ.get("CREDENTIALS_DIRECTORY")
    path = os.path.join(cred, "ha-token") if cred else TOKEN_FILE
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def _load_settings():
    sys.path.insert(0, APP_DIR)
    from c_settings_adapter import settings  # type: ignore
    if not getattr(settings, "mqtt_broker", None):
        raise RuntimeError("mqtt_broker is not configured in settings_ini.py")
    return settings


def _make_client(settings):
    import ssl
    from paho.mqtt import client as mqtt

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"optolink-mag-tpms-{os.getpid()}")
    userpass = getattr(settings, "mqtt_user", None)
    if userpass and str(userpass).lower() != "none":
        user, password = str(userpass).split(":", 1)
        client.username_pw_set(user, password)
    if getattr(settings, "mqtt_tls_enable", False):
        skip = bool(getattr(settings, "mqtt_tls_skip_verify", False))
        client.tls_set(ca_certs=getattr(settings, "mqtt_tls_ca_certs", None),
                       certfile=getattr(settings, "mqtt_tls_certfile", None),
                       keyfile=getattr(settings, "mqtt_tls_keyfile", None),
                       cert_reqs=ssl.CERT_NONE if skip else ssl.CERT_REQUIRED)
        client.tls_insecure_set(skip)
    client.reconnect_delay_set(min_delay=2, max_delay=60)
    host, port = settings.mqtt_broker.rsplit(":", 1)
    return client, host, int(port)


class Service:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.settings = _load_settings()
        self.base = str(getattr(self.settings, "mqtt_topic", "openv")).rstrip("/")
        self.sensors = {s["address"]: s for s in cfg["sensors"]}
        self.last_seen: dict[str, float] = {}
        self.online: dict[str, bool] = {}
        self.windows: dict[str, PressureWindow] = {}
        self.last_save = 0.0
        for addr in self.sensors:
            w = PressureWindow()
            w.load(self._window_file(addr))
            self.windows[addr] = w
        self.client, host, port = _make_client(self.settings)
        self.mqtt_host = host
        self.client.on_connect = self._on_connect
        self.client.connect_async(host, port, keepalive=60)
        self.client.loop_start()
        self.ha_url = cfg.get("ha_url") or f"ws://{host}:8123/api/websocket"

    def _window_file(self, addr: str) -> str:
        return os.path.join(STATE_DIR, f"window-{addr.replace(':', '').lower()}.json")

    def _sid(self, addr: str) -> str:
        s = self.sensors[addr]
        return s.get("id") or addr.replace(":", "").lower()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        for s in self.sensors.values():
            for topic, payload in discovery_messages(self.base, s):
                client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=True)
            addr = s["address"]
            if addr in self.online:
                self._set_online(addr, self.online[addr], force=True)
            self._publish_eval(addr)
        print(f"MQTT connected ({reason_code}), discovery published", flush=True)

    def _set_online(self, addr: str, online: bool, force: bool = False):
        if not force and self.online.get(addr) == online:
            return
        self.online[addr] = online
        topic = f"{self.base}/tpms/{self._sid(addr)}/availability"
        self.client.publish(topic, "online" if online else "offline", qos=1, retain=True)

    def handle(self, adv: dict):
        hit = extract(adv, set(self.sensors))
        if not hit:
            return
        addr, values = hit
        self.last_seen[addr] = time.time()
        self.client.publish(f"{self.base}/tpms/{self._sid(addr)}/state",
                            json.dumps(values, ensure_ascii=False), qos=1, retain=True)
        self._set_online(addr, True)
        now = time.time()
        if self.windows[addr].add(now, values["druck"], values["temperatur"]):
            self._publish_eval(addr)
            if now - self.last_save > 600:
                self._save_windows()
                self.last_save = now

    def _publish_eval(self, addr: str):
        summary = self.windows[addr].summary(time.time())
        self.client.publish(f"{self.base}/tpms/{self._sid(addr)}/auswertung",
                            json.dumps(summary), qos=1, retain=True)

    def _save_windows(self):
        for addr, w in self.windows.items():
            try:
                w.save(self._window_file(addr))
            except OSError as exc:
                print(f"cannot save window: {exc}", flush=True)

    def check_stale(self):
        limit = float(self.cfg["stale_minutes"]) * 60
        now = time.time()
        for addr in self.sensors:
            seen = self.last_seen.get(addr)
            if seen is not None and now - seen > limit:
                self._set_online(addr, False)

    async def ws_session(self, token: str):
        import websockets

        async with websockets.connect(self.ha_url, max_size=None, ping_interval=30) as ws:
            json.loads(await ws.recv())
            await ws.send(json.dumps({"type": "auth", "access_token": token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"Home Assistant auth failed: {auth.get('type')}")
            await ws.send(json.dumps({"id": 1, "type": "bluetooth/subscribe_advertisements"}))
            print(f"subscribed to Home Assistant BLE advertisements ({self.ha_url})", flush=True)
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                except asyncio.TimeoutError:
                    self.check_stale()
                    continue
                if msg.get("type") == "result" and not msg.get("success", True):
                    raise RuntimeError(f"subscribe failed: {msg.get('error')}")
                event = msg.get("event") or {}
                for adv in (event.get("add") or []) + (event.get("change") or []):
                    if isinstance(adv, dict):
                        self.handle(adv)
                self.check_stale()

    async def run(self):
        delay = 5
        while True:
            try:
                await self.ws_session(read_token())
            except Exception as exc:  # noqa: BLE001 - keep running, retry
                print(f"websocket error: {exc!r}; retry in {delay} s", flush=True)
                self.check_stale()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)
            else:
                delay = 5


def self_test() -> int:
    addr = "61:41:00:02:FF:B2"
    v = decode_itpms(bytes.fromhex("a12758051500ff020ab2ff02004161"), addr)
    assert v and v["druck"] == 1.23 and v["temperatur"] == 33 and v["batterie_spannung"] == 2.83, v
    assert decode_itpms(bytes.fromhex("a12758051500ff020ab2ff02004162"), addr) is None
    hi = decode_itpms(bytes.fromhex("a1105805150001020ab2ff02004161"), addr)
    assert hi and hi["druck_roh"] == 272, hi
    adv = {"address": addr.lower(), "rssi": -90, "source": "AA", "time": 1795693287.0,
           "manufacturer_data": {"172": "a12758051500ff020ab2ff02004161"}}
    got = extract(adv, {addr})
    assert got and got[1]["druck"] == 1.23 and got[1]["zuletzt"].startswith("2026-11-26"), got
    assert extract(adv, {"00:00:00:00:00:00"}) is None
    msgs = discovery_messages("openv", {"address": addr, "id": "mag", "name": "MAG"})
    assert msgs[0][0] == "homeassistant/sensor/optolink_tpms_614100" "02ffb2/druck/config"
    assert msgs[0][1]["state_topic"] == "openv/tpms/mag/state"
    w = PressureWindow()
    for i in range(120):  # 2 h: 30 degC/1.20 bar heating up to 60 degC/1.50 bar
        w.add(1000.0 + i * 60, 1.20 + i * 0.0025, 30 + i * 0.25)
    sm = w.summary()
    assert sm["druck_kalt"] == 1.2 and sm["druckhub"] == 0.29 and 0.09 < sm["hub_pro_10k"] < 0.11, sm
    assert PressureWindow().summary()["druckhub"] is None
    print("optolink-mag-tpms self-test OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="run decoder self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not os.path.exists(CONFIG_FILE):
        print(f"{CONFIG_FILE} missing; nothing to do", flush=True)
        return 0
    service = Service(load_config())

    def _stop(signum, frame):
        service._save_windows()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    asyncio.run(service.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
