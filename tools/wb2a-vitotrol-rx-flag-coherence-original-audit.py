#!/usr/bin/env python3
"""Bounded offline 79-image WB2A 20C2 RX-flag/descriptor coherence test.

Read complete historical SHA-pinned P300 full-RAM images only; never imports
serial, opens an Optolink port, publishes MQTT, changes boiler codings or
writes M16C RAM/UART/IRQ/DMA registers. The 640 per-image reads are not atomic:
even perfect 79-image association does not establish a flag bit, ISR timing,
queue ownership or legal write/injection target.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
 "wb2a_rx_flag_near_pointer_helper",HERE/"wb2a-vitotrol-near-rx-rom-candidates.py")
if spec is None or spec.loader is None:
 raise RuntimeError("SHA-pinned 20C2 full-RAM helper missing")
near=importlib.util.module_from_spec(spec);sys.modules[spec.name]=near;spec.loader.exec_module(near)
verify=near.audit
ORIG="/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz"
SAMPLES=79
SIZE=20_480
BASE=0x0400
RX=0x1642
META=0x166A
STATE=0x0B6B
PTRS=(0x0B51,0x0B55,0x0B5C)
DESC=0x0B6D
TX=0x161A
BASELINE_RX=bytes.fromhex("0001b10a010110fe23d8")
RARE_RX=bytes.fromhex("0001b10a010100004353")
BASELINE_PTRS={
  0x0B51:bytes.fromhex("3f200f00"),
  0x0B55:bytes.fromhex("b6cb0f00"),
  0x0B5C:bytes.fromhex("20240f00"),
}
BASELINE_META=bytes.fromhex("060001")
RARE_META=bytes.fromhex("0a0401")
DESC_BYTES=bytes.fromhex("42160afe")


class Refused(ValueError):pass


def val(im,addr,n):
 if type(im) is not bytes or len(im)!=SIZE:
  raise Refused("exact 20 KiB immutable historical image required")
 off=addr-BASE
 if off<0 or off+n>len(im):raise Refused("RAM address outside 0x0400..0x53ff")
 return im[off:off+n]


def classify(images):
 if (type(images) not in (tuple,list) or len(images)!=SAMPLES
     or any(type(x) is not bytes or len(x)!=SIZE for x in images)):
  raise Refused("need 79 complete byte-exact historical RAM images")
 rows=[]
 for index,img in enumerate(images,1):
  rx=val(img,RX,10)
  meta=val(img,META,3)
  scheduler=val(img,STATE,1)[0]
  ptrs={f"0x{addr:04x}":val(img,addr,4).hex() for addr in PTRS}
  changed_ptrs=tuple(addr for addr in PTRS if
                     val(img,addr,4)!=BASELINE_PTRS[addr])
  desc=val(img,DESC,4)
  if desc!=DESC_BYTES:raise Refused(f"not the historical 20C2 descriptor in image {index}")
  if rx not in (BASELINE_RX,RARE_RX):
   raise Refused(f"unknown 0x1642 RX frame in image {index}")
  if meta not in (BASELINE_META,RARE_META):
   raise Refused(f"unknown 0x166A-C meta variant in image {index}")
  if scheduler not in (1,10,11):
   raise Refused(f"unknown 0x0B6B value in image {index}")
  rows.append({
   "index":index,
   "rx_type":"rare" if rx==RARE_RX else "common",
   "rx_hex":rx.hex(),
   "rx_crc_valid":verify.crc16_kermit(rx)==0,
   "meta_hex":meta.hex(),
   "scheduler_status":f"{scheduler:02x}",
   "pointer_cochange_3_of_3":len(changed_ptrs)==3,
   "pointer_partial_change":0<len(changed_ptrs)<3,
   "pointer_readings":ptrs,
   "tx_master_prefix":val(img,TX,4).hex(),
  })
 if not all(r["rx_crc_valid"] for r in rows):
  raise Refused("historical RX positive CRC proof failed")
 rare=[x["index"] for x in rows if x["rx_type"]=="rare"]
 outliers=[x["index"] for x in rows if x["scheduler_status"]!="01"]
 pointer=[x["index"] for x in rows if x["pointer_cochange_3_of_3"]]
 partial=[x["index"] for x in rows if x["pointer_partial_change"]]
 meta_rare=[x["index"] for x in rows if x["meta_hex"]==RARE_META.hex()]
 byte0a=[x["index"] for x in rows if x["scheduler_status"]=="0a"]
 byte0b=[x["index"] for x in rows if x["scheduler_status"]=="0b"]
 if not all(r["tx_master_prefix"].startswith(("0100","2000","ff00")) for r in rows):
  raise Refused("unexpected comparison master-TX frame class")
 return {
   "mode":"OFFLINE_20C2_P300_79_RAM_RX_FLAG_COHERENCE_NOT_ISR",
   "complete_RAM_images":len(rows),
   "RAM_cpu_range":"0x0400..0x53ff",
   "source_nonatomic_640_sequential_FC03_reads_per_image":True,
   "rx_crc_valid_samples":sum(r["rx_crc_valid"] for r in rows),
   "rx_common_samples":len(rows)-len(rare),
   "rx_rare_sample_indices":rare,
   "rx_variant_counts":dict(sorted(Counter(r["rx_hex"] for r in rows).items())),
   "metadata_166a_c_counts":dict(sorted(Counter(r["meta_hex"] for r in rows).items())),
   "metadata_rare_sample_indices":meta_rare,
   "status_0b6b_counts":dict(sorted(Counter(r["scheduler_status"] for r in rows).items())),
   "status_0b6b_non01_indices":outliers,
   "status_0b6b_0a_indices":byte0a,
   "status_0b6b_0b_indices":byte0b,
   "simultaneous_3_pointer_anomaly_indices":pointer,
   "partial_3_pointer_anomaly_indices":partial,
   "cochanged_pointer_triplet_when_0b6b_0a":len(set(pointer)&set(byte0a)),
   "meta_166a_abnormal_is_only_rare_rx_same_image":meta_rare==rare and len(rare)==1,
   "0b6b_abnormal_detects_rare_RX":bool(set(rare)&set(outliers)),
   "0b6b_abnormal_false_positive_count":len(set(outliers)-set(rare)),
   "0b6b_default_when_only_rare_rx":all(rows[i-1]["scheduler_status"]=="01" for i in rare),
   "0b6b_0a_only_at_pointer_triplet_anomaly":set(byte0a)<=set(pointer),
   "rx_source_class_0x11_accepted":False,
   "RX_consumer_callback_owner_proven":False,
   "0b6b_writable_RX_ready_flag_proven":False,
   "166a_b_writable_RX_ready_flag_proven":False,
   "0b6d_actual_RAM_pointer_typed":False,
   "RAM_RO_0b6b_response_orphan_not_call_target":True,
   "no_new_live_controller_IO":True,
   "controller_writes":0,
 }


def source_verified(raw:bytes):
 if type(raw) is not bytes or not 0<len(raw)<=verify.MAX_ARCHIVE_BYTES:
  raise Refused("bounded original tar.gz required")
 verifier=verify.audit_bundle("fullram",raw)
 imgs=[]
 with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as f:
  manifest=verify._manifest(f,"p300-fullram")
  for i in range(1,SAMPLES+1):
   key=f"snapshots/s{i:05d}"
   meta=json.loads(verify._verified(
       f,manifest,"p300-fullram",key+".json",max_size=8000))
   image=verify._verified(
       f,manifest,"p300-fullram",key+".bin",max_size=SIZE)
   if (len(image)!=SIZE
       or meta.get("marker")!="COMPLETE"
       or meta.get("complete") is not True
       or meta.get("device_id")!="20c2" or meta.get("software")!="0103"
       or meta.get("bytes_stored")!=SIZE
       or meta.get("range_start")!="0x0400"
       or meta.get("range_last_inclusive")!="0x53ff"
       or meta.get("direction") not in ("ascending","descending")):
    raise Refused("invalid fullram original metadata provenance")
   imgs.append(image)
 result=classify(imgs)
 result["source_original_sha256"]=verifier["archive_sha256"]
 result["source_sha256_verified_by_original_bundle_helper"]=True
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--archive",type=Path,default=Path(ORIG))
 p.add_argument("--out",type=Path)
 args=p.parse_args()
 a=args.archive
 if (a.is_symlink() or not stat.S_ISREG(a.stat().st_mode) or
     a.suffixes[-2:]!=[".tar",".gz"] or a.stat().st_size>verify.MAX_ARCHIVE_BYTES):
  p.error("requires bounded pinned original tar.gz archive only")
 result=source_verified(a.read_bytes())
 output=json.dumps(result,indent=2,sort_keys=True)+"\n"
 if args.out:args.out.write_text(output)
 print(output)


if __name__=="__main__":main()
