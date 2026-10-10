#!/usr/bin/env python3
"""Pure, offline Vitotrol KM-Bus frame model from archived WB2A master TX.

Does NOT open a port, send frames, write RAM, change codings, or claim
real WB2A slave reception. Intended for fixture-driven vitotrol research.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import math

SRC_CONTROLLER = 0x00
CLASS_VITOTROL = 0x11
READ_MULTIPLE = 0x33
SEND_MULTIPLE = 0xB3
IDENTITY_FIRST = 0xF8
IDENTITY_COUNT = 0x04

KNOWN_MASTER_HEX = (
    "1100330a0101f80449ef",
    "1100330a0201f80484ca",
)
IDENTITY_V200 = bytes.fromhex("11340005")
IDENTITY_V300_SAMPLE = bytes.fromhex("11380011")


class FrameRejected(ValueError):
    """No successful emulation may be inferred for unverified frames."""


def crc16_kermit(data: bytes) -> int:
    if type(data) is not bytes:
        raise FrameRejected("exact byte array required")
    crc=0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc=(crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc & 0xffff


def append_crc(data: bytes) -> bytes:
    checksum=crc16_kermit(data)
    return data+checksum.to_bytes(2,"little")


def validate_frame(frame: bytes):
    if (type(frame) is not bytes or len(frame)<8 or len(frame)>64
            or frame[3]!=len(frame) or crc16_kermit(frame)!=0):
        raise FrameRejected("length/CRC/bytes invalid")
    return frame


@dataclass(frozen=True)
class Discovery:
    slot: int
    destination: int
    source: int
    command: int
    start_register: int
    count: int


def decode_master_identity_query(frame: bytes) -> Discovery:
    frame=validate_frame(frame)
    if (len(frame)!=10 or frame[0]!=CLASS_VITOTROL
            or frame[1]!=SRC_CONTROLLER or frame[2]!=READ_MULTIPLE
            or frame[4] not in (1,2) or frame[5]!=1
            or frame[6]!=IDENTITY_FIRST or frame[7]!=IDENTITY_COUNT):
        raise FrameRejected("not a proven WB2A Vitotrol identity query")
    return Discovery(frame[4],frame[0],frame[1],frame[2],frame[6],frame[7])


def model_identity_reply(query: bytes, *, identity: bytes = IDENTITY_V200):
    """Construct an offline-only candidate reply; never dispatch to hardware."""
    discovery=decode_master_identity_query(query)
    if type(identity) is not bytes or len(identity)!=4 or identity[0]!=0x11:
        raise FrameRejected("only explicit 4-byte class 0x11 identity")
    payload=bytes([
        SRC_CONTROLLER,CLASS_VITOTROL,SEND_MULTIPLE,16,
        discovery.slot,1,
        0xF8,identity[0],0xF9,identity[1],
        0xFA,identity[2],0xFB,identity[3]])
    response=append_crc(payload)
    validate_frame(response)
    return response


def decode_candidate_slave_reply(frame: bytes):
    """Classify a hypothetical B3 reply, never assert actual RX on the boiler."""
    frame=validate_frame(frame)
    if (len(frame)!=16 or frame[0]!=SRC_CONTROLLER
            or frame[1]!=CLASS_VITOTROL or frame[2]!=SEND_MULTIPLE
            or frame[4] not in (1,2) or frame[5]!=1
            or frame[6:14:2]!=bytes.fromhex("f8f9fafb")):
        raise FrameRejected("not an F8..FB Vitotrol identity reply")
    return {
        "classification":"CANDIDATE_KMBUS_SLAVE_REPLY_OFFLINE_ONLY",
        "slot":frame[4],
        "identity_bytes":frame[7:14:2].hex(),
        "physical_uart1_rx_verified":False,
        "controller_write_authorized":False,
    }


def decode_master_ping(frame: bytes) -> int:
    frame=validate_frame(frame)
    if (len(frame)!=8 or frame[0]!=CLASS_VITOTROL or
            frame[1]!=SRC_CONTROLLER or frame[2]!=0x00
            or frame[4] not in (1,2) or frame[5]!=1):
        raise FrameRejected("unknown or invalid Vitotrol master PING")
    return frame[4]


def model_pong(query: bytes) -> bytes:
    slot=decode_master_ping(query)
    return append_crc(bytes([0x00,0x11,0x80,0x08,slot,0x01]))


def model_room_temp_record(slot: int, tenths_c: int, *,
                           heating_circuit: int = 1) -> bytes:
    """Documented 0xBF record, purely offline, no write or I/O access."""
    if (type(slot) is not int or slot not in (1,2) or
            type(heating_circuit) is not int or heating_circuit not in (1,2,3)
            or type(tenths_c) is not int or not 50 <= tenths_c <= 350):
        raise FrameRejected("bounded known physical room-temperature fixture")
    value=tenths_c.to_bytes(2,"little")
    body=bytes([0,0x11,0xbf,0x0c,slot,1,0x1f+heating_circuit,
                value[0]^0xaa,value[1]^0xaa,0xaa])
    return append_crc(body)


def decode_master_status(frame: bytes) -> dict:
    """Recognize controller status-record envelopes; payload semantics unknown.

    No state is inferred from opaque bytes; this is not a hardware RX proof.
    """
    frame=validate_frame(frame)
    if (frame[0]!=CLASS_VITOTROL or frame[1]!=SRC_CONTROLLER
            or frame[2]!=0xBF or frame[4] not in (1,2)
            or frame[5]!=1 or len(frame)<9 or frame[6] not in (0x1c,0x1d,0x1e,0x1f)):
        raise FrameRejected("not a known controller status-record envelope")
    return {"slot":frame[4],"record":frame[6],
            "opaque_payload_hex":frame[7:-2].hex(),
            "decoded_status_verified":False}


class OfflineVitotrolState:
    """Model-only discovery->PING/PONG->periodic temperature, no transport.

    A real software-only WB2A emulation path and UART1 RX access remain
    UNVERIFIED. A stale room-temperature source causes NO reply rather
    than fabricated liveness; this is a simulator safety assertion only.
    """

    def __init__(self, *, slot: int = 1,
                 identity: bytes = IDENTITY_V200,
                 stale_after_s: float = 90.0):
        if slot not in (1,2) or type(slot) is not int:
            raise FrameRejected("known slot required")
        if type(stale_after_s) not in (int,float) or not 30 <= stale_after_s <= 300:
            raise FrameRejected("bounded source freshness interval required")
        if type(identity) is not bytes or len(identity)!=4 or identity[0]!=0x11:
            raise FrameRejected("explicit class 0x11 identity required")
        self.slot=slot
        self.identity=identity
        self.stale_after_s=float(stale_after_s)
        self.discovered=False
        self.temperature=None
        self.updated_at=None
        self.last_temp_sent_at=None
        self.last_seen_at=None
        self.last_status_record=None

    def update_temperature(self, tenths_c: int, *, at_s: float):
        if type(at_s) not in (int,float) or not math.isfinite(at_s) or at_s < 0:
            raise FrameRejected("finite timestamp required")
        if self.updated_at is not None and at_s < self.updated_at:
            raise FrameRejected("temperature timestamp moved backwards")
        # Validate bounds via the audited offline formatter.
        model_room_temp_record(self.slot,tenths_c)
        self.temperature=tenths_c
        self.updated_at=float(at_s)

    def respond(self, frame: bytes, *, at_s: float) -> bytes | None:
        if type(at_s) not in (int,float) or not math.isfinite(at_s) or at_s < 0:
            raise FrameRejected("finite timestamp required")
        if self.last_seen_at is not None and at_s < self.last_seen_at:
            raise FrameRejected("master clock moved backwards")
        frame=validate_frame(frame)
        if (frame[0]!=CLASS_VITOTROL or frame[1]!=SRC_CONTROLLER
                or frame[4]!=self.slot):
            return None
        if frame[2]==0xBF:
            decoded=decode_master_status(frame)
            self.last_seen_at=float(at_s)
            self.last_status_record=decoded
            return None
        if frame[2]==READ_MULTIPLE:
            discovery=decode_master_identity_query(frame)
            if discovery.slot!=self.slot:
                return None
            self.discovered=True
            self.last_seen_at=float(at_s)
            return model_identity_reply(frame,identity=self.identity)
        if frame[2]!=0x00:
            return None
        decode_master_ping(frame)
        self.last_seen_at=float(at_s)
        if (not self.discovered or self.temperature is None
                or self.updated_at is None
                or not 0 <= at_s-self.updated_at <= self.stale_after_s):
            return None
        if (self.last_temp_sent_at is None or
                at_s-self.last_temp_sent_at >= 30):
            reply=model_room_temp_record(self.slot,self.temperature)
            self.last_temp_sent_at=at_s
            return reply
        return model_pong(frame)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slot",type=int,choices=(1,2),default=1)
    p.add_argument("--variant",choices=("v200","v300_sample"),default="v200")
    args=p.parse_args()
    query=bytes.fromhex(KNOWN_MASTER_HEX[args.slot-1])
    identity=IDENTITY_V200 if args.variant=="v200" else IDENTITY_V300_SAMPLE
    reply=model_identity_reply(query,identity=identity)
    print(json.dumps({
        "mode":"OFFLINE_ONLY_NO_SERIAL",
        "master_query_hex":query.hex(),
        "candidate_reply_hex":reply.hex(),
        "reply_decoder":decode_candidate_slave_reply(reply),
        "actual_vitotrol_device_present_verified":False,
    },sort_keys=True,indent=2))


if __name__=="__main__":
    main()
