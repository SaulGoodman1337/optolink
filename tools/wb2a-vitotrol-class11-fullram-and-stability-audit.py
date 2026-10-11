#!/usr/bin/env python3
"""Exhaustive archived WB2A RAM scan for native KM classes 0x01 and 0x11.

Reads ONLY previously recorded and SHA/manifest-pinned FC03 FullRAM images.
A CRC-valid sender-0x11 frame at ANY address is counted, not discarded just
because it is outside the expected 0x1642 buffer. A negative archival result
does not establish lack of a transient UART event or firmware code.

Also separates a large immutable, high-entropy SRAM tail from an ACTUAL
controller ROM image; high entropy/stability alone never proves flash mapping.
No network, serial, SFR, controller reads or controller writes.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import io
import json
from math import log2
from pathlib import Path
import statistics
import sys
import tarfile
import zlib

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "wb2a_km_ram_audit_source",ROOT/"wb2a-vitotrol-optolink-rx-audit.py")
if spec is None or spec.loader is None:raise RuntimeError("original audit helper unavailable")
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a
spec.loader.exec_module(a)
SOURCE_SHA=a.KNOWN_ARCHIVES["fullram"]
LOW=0x400
HIGH=0x53ff
RAM_BYTES=20_480
CLASS_TAGS={1:"class01",17:"class11"}
MAX_FRAME=32
MIN_FRAME=8


class EvidenceRejected(ValueError):pass


def raw_frame_scan(raw:bytes)->dict:
    if type(raw) is not bytes or len(raw)!=RAM_BYTES:
        raise EvidenceRejected("exact 20480-byte historical snapshot mandatory")
    prefixes=Counter();plausible=Counter();valid=Counter()
    found=[];wrong_crc=Counter();rejected_length=Counter()
    for source, label in CLASS_TAGS.items():
        header=bytes((0,source))
        offset=0
        while True:
            position=raw.find(header,offset)
            if position<0:break
            offset=position+1
            prefixes[label]+=1
            if position+4>len(raw):
                rejected_length[label]+=1
                continue
            opcode,length=raw[position+2:position+4]
            if length<MIN_FRAME or length>MAX_FRAME or position+length>len(raw):
                rejected_length[label]+=1
                continue
            plausible[label]+=1
            frame=raw[position:position+length]
            if a.crc16_kermit(frame):
                wrong_crc[label]+=1
                continue
            valid[label]+=1
            found.append({"source":label,"physical_ram_address":f"0x{LOW+position:04x}",
                          "opcode":f"0x{opcode:02x}","frame":frame.hex(),
                          "crc16_kermit_valid":True})
    return {
        "prefix_counts":dict(sorted(prefixes.items())),
        "plausible_length_counts":dict(sorted(plausible.items())),
        "wrong_crc_counts":dict(sorted(wrong_crc.items())),
        "wrong_length_counts":dict(sorted(rejected_length.items())),
        "valid_counts":dict(sorted(valid.items())),
        "valid_frames":sorted(found,key=lambda x:(x["physical_ram_address"],x["source"])),
        "only_full_frames_with_in_bounds_length_and_crc":True,
    }


def shannon(raw:bytes)->float:
    if not raw:raise EvidenceRejected("empty entropy input")
    hist=Counter(raw)
    return -sum((count/len(raw))*log2(count/len(raw)) for count in hist.values())


def static_tail(images:list[bytes])->dict:
    if type(images) is not list or not 2<=len(images)<=79:
        raise EvidenceRejected("multiple original complete images required")
    if any(type(raw) is not bytes or len(raw)!=RAM_BYTES for raw in images):
        raise EvidenceRejected("invalid memory image length/type")
    base=images[0]
    start=RAM_BYTES
    for i in range(RAM_BYTES-1,-1,-1):
        if all(x[i]==base[i] for x in images):
            start=i
        else:break
    if start>=RAM_BYTES:raise EvidenceRejected("no identical final memory byte")
    region=base[start:]
    return {
        "physical_ram_begin":f"0x{LOW+start:04x}",
        "physical_ram_end":f"0x{HIGH:04x}",
        "unchanged_bytes":len(region),
        "observed_identical_in_images":len(images),
        "source_tail_sha256":hashlib.sha256(region).hexdigest(),
        "byte_entropy_bits":round(shannon(region),5),
        "bit_one_fraction":round(sum(n.bit_count() for n in region)/(8*len(region)),6),
        "zlib_compressed_bytes":len(zlib.compress(region,9)),
        "entropy_or_stability_proves_rom":False,
        "has_controller_program_base_address":False,
        "interrupt_vectors_decoded":False,
    }


def analyze(images:list[bytes],*,sha:str)->dict:
    if len(images)!=79 or any(type(x) is not bytes or len(x)!=RAM_BYTES for x in images):
        raise EvidenceRejected("79 SHA-attested original RAM images required")
    summaries=[raw_frame_scan(x) for x in images]
    all_valid=[x for row in summaries for x in row["valid_frames"]]
    prefix=Counter();plausible=Counter();wrong_crc=Counter();bad_lengths=Counter()
    for row in summaries:
        prefix.update(row["prefix_counts"])
        plausible.update(row["plausible_length_counts"])
        wrong_crc.update(row["wrong_crc_counts"])
        bad_lengths.update(row["wrong_length_counts"])
    addresses=Counter((f["source"],f["physical_ram_address"]) for f in all_valid)
    unique=Counter((f["source"],f["frame"]) for f in all_valid)
    normal=Counter(images[i][0x166a-LOW:0x166c-LOW].hex() for i in range(79))
    # Independent narrow positivity guard: the known RX window itself MUST
    # contain a valid 10-byte source=0x01 response in each original snapshot.
    rxframes=[]
    for x in images:
        frame=x[0x1642-LOW:0x164c-LOW]
        if (len(frame)!=10 or frame[:2]!=b"\x00\x01" or frame[3]!=10
            or a.crc16_kermit(frame)!=0):
            raise EvidenceRejected("historical expected RX frame absent/corrupt")
        rxframes.append(frame.hex())
    return {
        "mode":"ORIGINAL_FULLRAM_EXHAUSTIVE_CLASS01_CLASS11_FRAME_SEARCH_OFFLINE",
        "source_sha256":sha,
        "target":"20C2/0103","images":79,"image_bytes":RAM_BYTES,
        "physical_ram_span":"0x0400..0x53ff",
        "total_scanned_bytes":len(images)*RAM_BYTES,
        "frame_header_search_at_all_byte_alignments":True,
        "prefix_counts":dict(sorted(prefix.items())),
        "plausible_length_counts":dict(sorted(plausible.items())),
        "wrong_crc_counts":dict(sorted(wrong_crc.items())),
        "wrong_length_counts":dict(sorted(bad_lengths.items())),
        "valid_frame_locations":[{"source":source,"ram":addr,"observations":n}
                                 for (source,addr),n in sorted(addresses.items())],
        "valid_frames":[{"source":source,"frame":frame,"observations":n}
                        for (source,frame),n in sorted(unique.items())],
        "metadata_166a166b_counts":dict(sorted(normal.items())),
        "physical_0x1642_known_rx_positive_control":Counter(rxframes)==Counter(
            f["frame"] for f in all_valid if f["source"]=="class01"
            and f["physical_ram_address"]=="0x1642"),
        "total_valid_class01":sum(f["source"]=="class01" for f in all_valid),
        "total_valid_class11":sum(f["source"]=="class11" for f in all_valid),
        "high_stability_sram_tail":static_tail(images),
        "no_class11_in_these_snapshots_excludes_transient_receives":False,
        "firmware_binary_obtained":False,
        "controller_io":0,"controller_writes":0,
    }


def original_archive(blob:bytes)->dict:
    if (type(blob) is not bytes or len(blob)>a.MAX_ARCHIVE_BYTES
        or hashlib.sha256(blob).hexdigest()!=SOURCE_SHA):
        raise EvidenceRejected("not exact original 79-image archive SHA")
    images=[]
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as t:
        mf=a._manifest(t,"p300-fullram")
        for i in range(1,80):
            base=f"snapshots/s{i:05d}"
            meta=json.loads(a._verified(t,mf,"p300-fullram",base+".json",max_size=8000))
            if meta.get("complete") is not True or meta.get("marker")!="COMPLETE":
                raise EvidenceRejected("snapshot not marked complete")
            image=a._verified(t,mf,"p300-fullram",base+".bin",max_size=RAM_BYTES)
            if len(image)!=RAM_BYTES:raise EvidenceRejected("short memory image")
            images.append(image)
    return analyze(images,sha=SOURCE_SHA)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.original.is_symlink() or not args.original.is_file():
        p.error("SHA-attested regular original archive required")
    r=original_archive(args.original.read_bytes())
    output=json.dumps(r,sort_keys=True,indent=2)+"\n"
    if args.output:args.output.write_text(output)
    print(output)


if __name__=="__main__":main()
