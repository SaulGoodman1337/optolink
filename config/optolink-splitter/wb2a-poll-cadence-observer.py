#!/usr/bin/env python3
"""Passive MQTT cadence observer for the VDensHO1 phased poll scheduler.

No Optolink command is sent. No forcepoll/reset/reloadpoll is sent.
The script only subscribes to normal state topics and measures arrival times.
It is meaningful when mqtt_no_redundant=False, because then every successful
poll is published even when the value is unchanged.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import math
import statistics
import sys
import threading
import time

sys.path.insert(0, "/opt/optolink")

from c_settings_adapter import settings
from c_polllist import poll_list


DEFAULT_NAMES = (
    "kesseltemperatur",
    "brenner_modulationsgrad",
    "geblaesedrehzahl_gfa_p06",
    "gfa_modulationssollwert_p09",
    "gfa_status3_p87",
    "aussentemperatur",
    "gfa_p80_typ",
)


def percentile(values, q):
    if not values:
        return None
    seq = sorted(values)
    if len(seq) == 1:
        return seq[0]
    pos = (len(seq) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return seq[lo]
    return seq[lo] + (seq[hi] - seq[lo]) * (pos - lo)


def mqtt_client():
    import paho.mqtt.client as paho

    try:
        client = paho.Client(
            paho.CallbackAPIVersion.VERSION2,
            client_id=f"wb2a_cadence_{int(time.time())}",
        )
    except Exception:
        client = paho.Client(client_id=f"wb2a_cadence_{int(time.time())}")

    creds = settings.mqtt_user
    if creds is not None and str(creds).strip():
        text = str(creds).strip()
        if ":" in text:
            user, password = text.split(":", 1)
            client.username_pw_set(user, password=password or None)
        else:
            client.username_pw_set(text)

    if bool(settings.mqtt_tls_enable):
        import ssl

        skip = bool(settings.mqtt_tls_skip_verify)
        client.tls_set(
            ca_certs=settings.mqtt_tls_ca_certs,
            certfile=settings.mqtt_tls_certfile,
            keyfile=settings.mqtt_tls_keyfile,
            cert_reqs=ssl.CERT_NONE if skip else ssl.CERT_REQUIRED,
            tls_version=getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS),
        )
        client.tls_insecure_set(skip)

    return client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--names", nargs="*", default=list(DEFAULT_NAMES))
    args = ap.parse_args()
    if not 20 <= args.seconds <= 1800:
        raise SystemExit("--seconds must be 20..1800")

    # Local profile initialization only. This does not contact Optolink.
    poll_list.make_list()

    if settings.mqtt_no_redundant:
        raise SystemExit(
            "REFUSED: mqtt_no_redundant=True; MQTT arrivals would not equal poll cadence."
        )

    metadata = {}
    for index, item in enumerate(poll_list.items):
        name = item[1]
        if name in args.names:
            metadata[name] = {
                "group": item[0],
                "phase": poll_list.item_phases[index],
                "addr": item[2],
            }

    missing = [name for name in args.names if name not in metadata]
    if missing:
        raise SystemExit("Missing poll items: " + ", ".join(missing))

    base = str(settings.mqtt_topic).rstrip("/")
    fstr = settings.mqtt_fstr or "{dpname}"
    topics = {}
    for name, meta in metadata.items():
        suffix = fstr.format(dpaddr=meta["addr"], dpname=name)
        topics[f"{base}/{suffix}"] = name

    arrivals = defaultdict(list)
    values = {}
    connected = threading.Event()
    subscribed = threading.Event()
    error = {"text": None}

    client = mqtt_client()

    def on_connect(c, userdata, flags, reason_code, properties=None):
        failed = bool(getattr(reason_code, "is_failure", False))
        if not failed:
            try:
                failed = int(reason_code) != 0
            except (TypeError, ValueError):
                failed = False
        if failed:
            error["text"] = f"MQTT connect rejected: {reason_code}"
            return
        connected.set()
        for topic in topics:
            c.subscribe(topic, qos=0)

    sub_count = {"n": 0}

    def on_subscribe(c, userdata, mid, reason_codes=None, properties=None):
        sub_count["n"] += 1
        if sub_count["n"] >= len(topics):
            subscribed.set()

    start_mono = {"value": None}

    def on_message(c, userdata, msg):
        if msg.retain:
            return
        name = topics.get(str(msg.topic))
        if name is None:
            return
        now = time.monotonic()
        if start_mono["value"] is None:
            return
        arrivals[name].append(now)
        values[name] = msg.payload.decode("utf-8", errors="replace")

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    host, port_text = str(settings.mqtt_broker).rsplit(":", 1)
    client.connect(host, int(port_text), keepalive=30)
    client.loop_start()

    if not connected.wait(5):
        raise SystemExit(error["text"] or "MQTT connect timeout")
    if not subscribed.wait(5):
        raise SystemExit(error["text"] or "MQTT subscribe timeout")

    # Ignore any delivery racing with subscription setup.
    time.sleep(0.5)
    arrivals.clear()
    values.clear()
    start_mono["value"] = time.monotonic()

    print(f"PASSIVE_ONLY=yes")
    print(f"SECONDS={args.seconds}")
    print(f"mqtt_no_redundant={settings.mqtt_no_redundant}")
    print(f"olbreath={settings.olbreath}")
    print(f"poll_interval={settings.poll_interval}")
    print("No forcepoll/reset/reloadpoll command will be sent.")
    print()
    for name in args.names:
        meta = metadata[name]
        print(
            f"WATCH {name} group={meta['group']} phase={meta['phase']} "
            f"topic={next(t for t,n in topics.items() if n == name)}"
        )

    time.sleep(args.seconds)

    client.disconnect()
    client.loop_stop()

    print()
    print("=== CADENCE ===")
    for name in args.names:
        stamps = arrivals[name]
        intervals = [
            stamps[i] - stamps[i - 1]
            for i in range(1, len(stamps))
        ]
        meta = metadata[name]
        if intervals:
            print(
                f"{name:38s} group={meta['group']:7s} phase={meta['phase']:3d} "
                f"msgs={len(stamps):3d} "
                f"min={min(intervals):6.3f}s "
                f"median={statistics.median(intervals):6.3f}s "
                f"p95={percentile(intervals, 0.95):6.3f}s "
                f"max={max(intervals):6.3f}s "
                f"last={values.get(name, '?')}"
            )
        else:
            print(
                f"{name:38s} group={meta['group']:7s} phase={meta['phase']:3d} "
                f"msgs={len(stamps):3d} intervals=INSUFFICIENT "
                f"last={values.get(name, '?')}"
            )


if __name__ == "__main__":
    main()
