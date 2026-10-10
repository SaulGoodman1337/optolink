#!/usr/bin/env python3
"""Offline-only report on bounded VS1/MQTT observations, never P300 RPM."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import math

SOURCE="VS1_MQTT_PUBLISHED_NOT_P300_RPM"
ALLOWED=frozenset(("p06","p09","flame"))


def summarize(root: Path):
    files=sorted(root.glob("vs1-????-??-??.jsonl"))
    records=0
    counts=Counter()
    last_seen={}
    positive=[]
    peaks=[]
    episode=None
    previous_p06=None
    for path in files:
        with path.open("r",encoding="utf-8") as handle:
            for line in handle:
                records+=1
                if records>400000:
                    raise ValueError("archive record limit exceeded")
                item=json.loads(line)
                kind=item.get("metric")
                if (item.get("schema")!=1 or item.get("source")!=SOURCE
                        or kind not in ALLOWED or item.get("retained") is not False):
                    raise ValueError("not a trusted nonretained VS1 observation")
                stamp=datetime.fromisoformat(item["utc"])
                if stamp.tzinfo is None:
                    raise ValueError("non timezone-aware capture")
                mono=item["monotonic_s"]
                if type(mono) not in (int,float) or not math.isfinite(mono):
                    raise ValueError("non-finite monotonic stamp")
                if kind in last_seen and mono<=last_seen[kind]:
                    raise ValueError("nonmonotonic observation")
                last_seen[kind]=mono
                counts[kind]+=1
                if kind != "p06":
                    continue
                raw=item["value_display"]
                try:
                    value=float(raw)
                except (TypeError,ValueError) as exc:
                    raise ValueError("invalid published display value") from exc
                if not math.isfinite(value) or value<0 or value>100000:
                    raise ValueError("invalid P06 display value")
                peaks.append(value)
                if value>0:
                    if episode is None or (previous_p06 is not None
                                          and mono-previous_p06>15):
                        if episode is not None:
                            positive.append(episode)
                        episode={
                            "start_utc":item["utc"],"end_utc":item["utc"],
                            "samples":0,"peak_published_display":0
                        }
                    episode["samples"]+=1
                    episode["end_utc"]=item["utc"]
                    episode["peak_published_display"]=max(
                        episode["peak_published_display"],value)
                elif episode is not None:
                    positive.append(episode)
                    episode=None
                previous_p06=mono
    if episode is not None:
        positive.append(episode)
    status_file=root/"progress.json"
    status=json.loads(status_file.read_text()) if status_file.exists() else {}
    return {
        "mode":"PASSIVE_VS1_MQTT_ONLY",
        "p300_rpm_verified":False,
        "p300_samples":0,
        "p06_display_is_not_a_new_p300_register":True,
        "files":len(files),"records":records,"by_metric":dict(counts),
        "positive_p06_episodes":len(positive),
        "longest_positive_episodes":sorted(
            positive,key=lambda x:x["samples"],reverse=True)[:6],
        "max_positive_p06_published_display":max(peaks,default=0),
        "last_seen_monotonic_s":last_seen,
        "observer_connected":status.get("connected"),
        "observer_observation_final":status.get("observation_final"),
        "observer_termination_reason":status.get("termination_reason"),
        "observer_remaining_s":status.get("remaining_s"),
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir",type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(summarize(args.dir),sort_keys=True,indent=2))


if __name__=="__main__":
    main()
