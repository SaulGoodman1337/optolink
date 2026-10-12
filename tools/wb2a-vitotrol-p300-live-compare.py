#!/usr/bin/env python3
"""Strict, entirely offline comparison of native-P300 Vitotrol live JSON."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

A0_VARIANTS={"legacy_v300_a0_01":"01","v300_original":"02",
             "v200_reference":"01"}
class EvidenceRejected(ValueError):
    pass

def accepted(state):
    if not isinstance(state,dict):
        raise EvidenceRejected("missing regulator readback")
    for key in ("a0","b0","swindex","room_raw","sensor","current_fault"):
        value=state.get(key)
        if not isinstance(value,str) or len(value)%2:
            raise EvidenceRejected("invalid regulator register: "+key)
        try:bytes.fromhex(value)
        except ValueError as exc:raise EvidenceRejected("invalid hex") from exc
    return (state["swindex"]!="00000000" and state["room_raw"] not in
            ("c800","0000") and state["sensor"]!="03")

def summarize_preseed(d,variant):
    if variant not in A0_VARIANTS or d.get("restore_ok") is not True:
        raise EvidenceRejected("unknown or unrestored preseed experiment")
    if any(d.get("baseline_virtual",{}).get(k)!="00" or
           d.get("after_restore",{}).get(k)!="00"
           for k in ("a0","b0","type")):
        raise EvidenceRejected("baseline/restore coding mismatch")
    if d["after_restore"].get("current_fault")!="00":
        raise EvidenceRejected("current controller fault")
    rows=d.get("live_snapshots")
    if not isinstance(rows,list) or not 1<=len(rows)<=16:
        raise EvidenceRejected("invalid observation count")
    current=[];master=[];rx=[];idx=[]
    for row in rows:
        v=row.get("virtual",{})
        accepted(v)
        if v["a0"]!=A0_VARIANTS[variant] or v["b0"]!="03":
            raise EvidenceRejected("wrong type pairing")
        if row.get("rx_descriptor")!="42160afe":
            raise EvidenceRejected("unverified physical descriptor")
        current.append(v)
        master.append(row.get("master_tx",{}).get("frame_at_zero"))
        rx.append(row.get("rx_candidate",{}).get("frame_at_two"))
        idx.append(row.get("rx_descriptor_index"))
    consecutive=any(accepted(a) and accepted(b)
                    for a,b in zip(current,current[1:]))
    if d.get("remote_accepted_by_regulator") and not consecutive:
        raise EvidenceRejected("unconfirmed participant acceptance")
    return dict(model=variant,a0=A0_VARIANTS[variant],samples=len(rows),
        discovery_ram_views=sum(bool(f and f.startswith("1100330a0101f804"))
                                for f in master),
        indices_at_discovery=[i for i,f in zip(idx,master)
                             if f and f.startswith("1100330a0101f804")],
        rx_first=rx[0],rx_last=rx[-1],
        rx_view_counts=dict(sorted(Counter(str(v) for v in rx).items())),
        first_identity_overwritten=bool(rx[0] and rx[0].startswith("0011b3")
          and any(x and x.startswith("0001b1") for x in rx[1:])),
        two_readbacks_acceptance=consecutive,
        original_state_restored=True,rx_isr_verified=False)

def summarize_follower(d):
    if d.get("matched_remote_type_a0")!="02":
        raise EvidenceRejected("not a correctly paired original V300")
    after=d.get("restored",{})
    if (not d.get("original_rx_first16_restored") or
        any(after.get(k)!="00" for k in ("a0","b0","type","current_fault"))):
        raise EvidenceRejected("follower not restored")
    frames=d.get("staged_frames")
    if not isinstance(frames,list) or not isinstance(d.get("staged_frame_count"),int):
        raise EvidenceRejected("no staged message evidence")
    for frame in frames:
        if (not frame.get("readback_exact")
            or frame.get("response")!="0011b3100101f811f938fa01fb0a1db1"
            or not frame.get("master","").startswith("1100330a0101f804")):
            raise EvidenceRejected("invalid follower frame")
    states=d.get("observed_while_active")
    if not isinstance(states,list) or len(states)<2:
        raise EvidenceRejected("two live readbacks missing")
    confirmed=accepted(states[-2]) and accepted(states[-1])
    if d.get("controller_acknowledged_remote") and not confirmed:
        raise EvidenceRejected("false positive remote status")
    return dict(matched_type="v300_original",a0="02",
      master_frames=d["master_frame_counts"],
      staged_ram_responses=d["staged_frame_count"],
      two_readbacks_acceptance=confirmed,
      restored=True,rx_isr_verified=False,
      physical_on_wire_reply_verified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preseed",action="append",default=[])
    p.add_argument("--follower",type=Path)
    args=p.parse_args()
    if not args.preseed and not args.follower:p.error("no reports")
    reports=[]
    for spec in args.preseed:
        variant,sep,name=spec.partition(":")
        if not sep:p.error("preseed must be variant:path")
        reports.append(summarize_preseed(json.loads(Path(name).read_text()),variant))
    follower=summarize_follower(json.loads(args.follower.read_text())) if args.follower else None
    print(json.dumps(dict(preseeds=reports,follower=follower,
      software_vitotrol_registered=bool(
        (follower and follower["two_readbacks_acceptance"]) or
        any(r["two_readbacks_acceptance"] for r in reports)),
      independent_uart_receive_verified=False),indent=2,sort_keys=True))

if __name__=="__main__":
    main()
