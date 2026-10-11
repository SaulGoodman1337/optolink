#!/usr/bin/env python3
"""Offline-only, SHA-attested KM-Bus Ethernet/UDP pcapng archive auditor.

Public OpenV #387 materials from third-party KM-Bus setups, NOT the WB2A.
No serial device, network access, Optolink write or physical boiler control.
The pcapng timestamps represent captured ETHERNET packets (not wire edges).
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import zipfile

SOURCE = {
    "master": {
        "zip_sha256": "1672ec6a2a16396fcefa388feb327dccdc26aadda41d9fc4cedd029e3081a68c",
        "member": "Capture_busKM_1h.pcapng",
        "member_sha256": "1d813a6f2f8adddd149bac21acf6613694c33d7ef43b07a6f72e77fac60ff175",
        "packet_count": 5269,
    },
    "emulator": {
        "zip_sha256": "54205e0c803de432676c3d252fdb4b3a827ebb53a128d34cf5cc6d866644fa13",
        "member": "KM3.pcapng",
        "member_sha256": "5b72401e5e8b1d9ffba2ecb201150df54e26a836bb73db1c486a72d2d43407af",
        "packet_count": 701,
    },
}
MAX_ZIP = 1_000_000
MAX_PCAP = 1_000_000
MAX_PACKETS = 8_000


class PcapRejected(ValueError):
    pass


@dataclass(frozen=True)
class CapturedFrame:
    timestamp_s: float
    km_bus: bytes
    udp_source_port: int
    udp_dest_port: int


def _crc16(frame: bytes) -> int:
    crc = 0
    for byte in frame:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc & 0xffff


def _timestamp_resolution(block: bytes, off: int, end: int) -> int:
    """Read if_tsresol from exactly one IDB; default is microseconds."""
    resolution = None
    while off + 4 <= end:
        code, n = struct.unpack_from("<HH", block, off)
        off += 4
        if code == 0:
            if n:
                raise PcapRejected("malformed end of IDB options")
            break
        if n > end - off or off + ((n + 3) & ~3) > end:
            raise PcapRejected("truncated pcapng option")
        content = block[off:off+n]
        off += (n + 3) & ~3
        if code == 9:
            if n != 1 or resolution is not None:
                raise PcapRejected("invalid or duplicate timestamp resolution")
            exponent = content[0]
            if exponent & 0x80:
                # Binary resolution is supported but intentionally bounded.
                if (exponent & 0x7f) > 30:
                    raise PcapRejected("unsupported high precision timestamp")
                resolution = 1 << (exponent & 0x7f)
            else:
                if exponent > 9:
                    raise PcapRejected("unsupported high precision timestamp")
                resolution = 10 ** exponent
    return 1_000_000 if resolution is None else resolution


def _udp_km_frame(eth: bytes) -> tuple[bytes, int, int]:
    if len(eth) < 42 or eth[12:14] != b"\x08\x00":
        raise PcapRejected("non-Ethernet/IPv4 packet")
    offset = 14
    vihl = eth[offset]
    ihl = (vihl & 0x0f) * 4
    if ((vihl >> 4) != 4 or ihl < 20 or offset + ihl + 8 > len(eth)
        or eth[offset + 9] != 17):
        raise PcapRejected("not a complete IPv4 UDP packet")
    if struct.unpack_from(">H", eth, offset + 6)[0] & 0x3fff:
        raise PcapRejected("fragmented IPv4 unsupported")
    total = struct.unpack_from(">H", eth, offset + 2)[0]
    if total < ihl + 8 or offset + total > len(eth):
        raise PcapRejected("IP packet truncated or incorrectly sized")
    udp = offset + ihl
    src, dst, udp_size, _checksum = struct.unpack_from(">HHHH", eth, udp)
    if udp_size < 16 or udp_size != total - ihl:
        raise PcapRejected("UDP length inconsistent with IPv4 packet")
    packet = eth[udp+8:udp+udp_size]
    if not 8 <= len(packet) <= 64 or packet[3] != len(packet):
        raise PcapRejected("KM-Bus packet length invalid")
    if _crc16(packet):
        raise PcapRejected("KM-Bus CRC16/Kermit invalid")
    # The public controller polls non-Vitotrol slots 04, 11..13,
    # EC/ED/EE as well as 01..03. Never impose our local WB2A slot list
    # on an unrelated capture; enforce the observed source subclass instead.
    if (packet[5] != 1
        or packet[2] not in (0x00, 0x31, 0x33, 0x3f, 0x80, 0xb1, 0xb3, 0xbf)):
        raise PcapRejected("unexpected KM-Bus class, slot or command shape")
    return packet, src, dst


def parse_pcapng(blob: bytes) -> tuple[CapturedFrame, ...]:
    if type(blob) is not bytes or not 60 <= len(blob) <= MAX_PCAP:
        raise PcapRejected("bounded, complete binary pcapng input required")
    if blob[:4] != bytes.fromhex("0a0d0d0a"):
        raise PcapRejected("missing little-endian section header")
    offset = 0
    section = False
    denominator = None
    frames = []
    last_tick = None
    while offset + 12 <= len(blob):
        typ, size = struct.unpack_from("<II", blob, offset)
        if size < 12 or size % 4 or size > len(blob) - offset:
            raise PcapRejected("invalid/truncated pcapng block size")
        if struct.unpack_from("<I", blob, offset+size-4)[0] != size:
            raise PcapRejected("pcapng block length trailer mismatch")
        if typ == 0x0a0d0d0a:
            if section or offset != 0 or size < 28:
                raise PcapRejected("more than one or invalid section header")
            if blob[offset+8:offset+12] != bytes.fromhex("4d3c2b1a"):
                raise PcapRejected("unsupported endian marker")
            section = True
        elif typ == 1:
            if not section or denominator is not None or size < 20:
                raise PcapRejected("unsupported or repeated interface")
            link, _reserved, _snaplen = struct.unpack_from("<HHI", blob, offset+8)
            if link != 1:
                raise PcapRejected("only Ethernet linktype 1 supported")
            denominator = _timestamp_resolution(blob, offset+16, offset+size-4)
        elif typ == 6:
            if denominator is None or size < 32 or len(frames) >= MAX_PACKETS:
                raise PcapRejected("packet before interface or too many packets")
            iface, hi, lo, captured, original = struct.unpack_from("<IIIII", blob, offset+8)
            padded = (captured + 3) & ~3
            if iface != 0 or captured != original or captured < 42 or offset+28+padded > offset+size-4:
                raise PcapRejected("invalid interface or truncated packet")
            pkt, src, dst = _udp_km_frame(blob[offset+28:offset+28+captured])
            ticks = (hi << 32) | lo
            if last_tick is not None and ticks < last_tick:
                raise PcapRejected("non-monotonic captured packet times")
            last_tick = ticks
            frames.append(CapturedFrame(ticks/denominator, pkt, src, dst))
        else:
            raise PcapRejected("unsupported block inside pinned capture")
        offset += size
    if offset != len(blob) or denominator is None or not frames:
        raise PcapRejected("trailing garbage or empty capture")
    return tuple(frames)


def _nearest_rank(data: list[float], percentile: float) -> float | None:
    if not data:
        return None
    ordered = sorted(data)
    return round(ordered[int((len(ordered)-1)*percentile)], 6)


def audit_frames(frames: tuple[CapturedFrame, ...]) -> dict:
    if not frames or any(type(x) is not CapturedFrame for x in frames):
        raise PcapRejected("typed, nonempty capture frames required")
    class_cmd = Counter(f"{f.km_bus[0]:02x}{f.km_bus[1]:02x}{f.km_bus[2]:02x}"
                        for f in frames)
    ports = Counter(f"{f.udp_source_port}->{f.udp_dest_port}" for f in frames)
    status = Counter(f"{f.km_bus[6]:02x}" for f in frames
                     if f.km_bus[:3] == bytes.fromhex("1100bf"))
    status_len = Counter(f"{f.km_bus[6]:02x}/{len(f.km_bus)}" for f in frames
                         if f.km_bus[:3] == bytes.fromhex("1100bf"))
    slave_status = Counter(f"{f.km_bus[6]:02x}" for f in frames
                           if f.km_bus[:3] == bytes.fromhex("0011bf"))
    slave_status_len = Counter(f"{f.km_bus[6]:02x}/{len(f.km_bus)}" for f in frames
                               if f.km_bus[:3] == bytes.fromhex("0011bf"))
    discovery = Counter(str(f.km_bus[4]) for f in frames
                        if f.km_bus[:3] == bytes.fromhex("110033")
                        and f.km_bus[6:8] == bytes.fromhex("f804"))
    pings = [f.timestamp_s for f in frames
             if f.km_bus[:3] == bytes.fromhex("110000")]
    gaps = [b-a for a,b in zip(pings,pings[1:])]
    # For BF record 0x11, find a strictly *later* PING; this is not an
    # electrical RX response deadline, only inter-UDP-message spacing.
    by_record = [f.timestamp_s for f in frames
                 if f.km_bus[:3] == bytes.fromhex("1100bf")
                 and f.km_bus[6] == 0x11]
    import bisect
    gap_to_ping = []
    for t in by_record:
        j = bisect.bisect_right(pings, t)
        if j < len(pings):
            gap_to_ping.append(pings[j]-t)
    return {
        "total_validated_km_bus_udp_packets":len(frames),
        "first_ethernet_packet_utc":datetime.fromtimestamp(frames[0].timestamp_s,timezone.utc).isoformat(),
        "last_ethernet_packet_utc":datetime.fromtimestamp(frames[-1].timestamp_s,timezone.utc).isoformat(),
        "elapsed_capture_s":round(frames[-1].timestamp_s-frames[0].timestamp_s,6),
        "class_direction_command_counts":dict(sorted(class_cmd.items())),
        "udp_ports":dict(sorted(ports.items())),
        "master_class11_bf_record_counts":dict(sorted(status.items())),
        "master_class11_bf_record_lengths":dict(sorted(status_len.items())),
        "source_class11_bf_record_counts":dict(sorted(slave_status.items())),
        "source_class11_bf_record_lengths":dict(sorted(slave_status_len.items())),
        "master_class11_f8_discovery_slots":dict(sorted(discovery.items())),
        "class11_ping_count":len(pings),
        "class11_ping_interpacket_gap_s":{
            "minimum":_nearest_rank(gaps,0),
            "median":_nearest_rank(gaps,0.5),
            "p90":_nearest_rank(gaps,0.9),
            "maximum":_nearest_rank(gaps,1),
        },
        "master_bf11_to_next_ping_ethernet_gap_s":{
            "observations":len(gap_to_ping),
            "minimum":_nearest_rank(gap_to_ping,0),
            "median":_nearest_rank(gap_to_ping,0.5),
            "p90":_nearest_rank(gap_to_ping,0.9),
            "maximum":_nearest_rank(gap_to_ping,1),
        },
        "frames_from_slave_class11":class_cmd.get("0011bf",0),
        "all_packets_crc_valid":True,
        "local_wb2a_capture":False,
        "physical_km_bus_waveform_or_response_deadline_proven":False,
        "safe_optolink_internal_vitotrol_injection_proven":False,
        "controller_write_authorized":False,
        "active_controller_io":False,
    }


def audit_zip(kind: str, data: bytes) -> dict:
    if kind not in SOURCE or type(data) is not bytes or not 0 < len(data) <= MAX_ZIP:
        raise PcapRejected("known capture kind with bounded ZIP required")
    expected = SOURCE[kind]
    sha = hashlib.sha256(data).hexdigest()
    if sha != expected["zip_sha256"]:
        raise PcapRejected("public capture ZIP SHA mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members=z.infolist()
            if (len(members) != 1 or members[0].filename != expected["member"]
                or members[0].is_dir() or members[0].file_size > MAX_PCAP
                or members[0].file_size < 100):
                raise PcapRejected("unexpected ZIP members or size")
            extracted=z.read(members[0])
    except (zipfile.BadZipFile,RuntimeError,EOFError) as exc:
        raise PcapRejected("corrupted ZIP member") from exc
    if hashlib.sha256(extracted).hexdigest() != expected["member_sha256"]:
        raise PcapRejected("public pcapng member SHA mismatch")
    frames=parse_pcapng(extracted)
    if len(frames) != expected["packet_count"]:
        raise PcapRejected("unexpected captured packet count")
    report=audit_frames(frames)
    report.update({
        "source":"PUBLIC_OPENV_ISSUE_387_CAPTURE_ARCHIVE_NOT_LOCAL_WB2A",
        "archive_kind":kind,
        "zip_sha256":sha,
        "pcapng_sha256":hashlib.sha256(extracted).hexdigest(),
        "pcapng_member":expected["member"],
        "source_identity_and_integrity_verified":True,
    })
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kind",choices=tuple(SOURCE))
    p.add_argument("zip_path",type=Path)
    args=p.parse_args()
    path=args.zip_path
    try:
        if (path.is_symlink() or not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_size > MAX_ZIP):
            raise PcapRejected("regular pinned ZIP path required")
        print(json.dumps(audit_zip(args.kind,path.read_bytes()),indent=2,sort_keys=True))
    except (PcapRejected,OSError) as exc:
        p.error(str(exc))


if __name__=="__main__":
    main()
