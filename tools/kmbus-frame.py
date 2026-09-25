#!/usr/bin/env python3
"""Build and verify Viessmann KM-BUS Vitotrol telegrams.

Reference protocol notes:
  config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md

This tool only builds byte strings. It does not access serial hardware and does
not transmit anything to a boiler.
"""

from __future__ import annotations

import argparse


def parse_int(value: str) -> int:
    return int(value, 0)


def crc16_kermit(data: bytes) -> int:
    """KM-BUS CRC: reflected 0x1021, init 0, xorout 0 (Kermit/0x8408)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


def append_crc(data: bytes) -> bytes:
    crc = crc16_kermit(data)
    return data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def fmt(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def identity(slot: int, device_id: int, sn1: int, sn2: int) -> bytes:
    body = bytes(
        [
            0x00,
            0x11,
            0xB3,
            0x10,
            slot,
            0x01,
            0xF8,
            0x11,
            0xF9,
            device_id,
            0xFA,
            sn1,
            0xFB,
            sn2,
        ]
    )
    return append_crc(body)


def pong(slot: int) -> bytes:
    return append_crc(bytes([0x00, 0x11, 0x80, 0x08, slot, 0x01]))


def room_temp(slot: int, circuit: int, temp_c: float) -> bytes:
    if circuit not in (1, 2, 3):
        raise SystemExit("circuit must be 1, 2, or 3")

    raw = int(round(temp_c * 10)) & 0xFFFF
    low = raw & 0xFF
    high = (raw >> 8) & 0xFF
    record = 0x20 + circuit - 1

    body = bytes(
        [
            0x00,
            0x11,
            0xBF,
            0x0C,
            slot,
            0x01,
            record,
            low ^ 0xAA,
            high ^ 0xAA,
            0xAA,
        ]
    )
    return append_crc(body)


def discovery(slot: int) -> bytes:
    return append_crc(bytes([0x11, 0x00, 0x33, 0x0A, slot, 0x01, 0xF8, 0x04]))


def master_read(slot: int, block: int) -> bytes:
    if slot not in (1, 2, 3):
        raise SystemExit("slot must be 1, 2, or 3")
    if not 0 <= block <= 0xFF:
        raise SystemExit("block must fit in one byte")

    record = 0x14 + slot
    return append_crc(
        bytes([0x00, 0x11, 0xBF, 0x0A, slot, 0x01, record, block ^ 0xAA])
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build/check Viessmann KM-BUS Vitotrol frames"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    crc_parser = sub.add_parser("crc")
    crc_parser.add_argument("hexbytes")

    identity_parser = sub.add_parser("identity")
    identity_parser.add_argument("--slot", type=parse_int, default=1)
    identity_parser.add_argument("--device-id", type=parse_int, default=0x34)
    identity_parser.add_argument("--sn1", type=parse_int, default=0)
    identity_parser.add_argument("--sn2", type=parse_int, default=5)

    pong_parser = sub.add_parser("pong")
    pong_parser.add_argument("--slot", type=parse_int, default=1)

    temp_parser = sub.add_parser("room-temp")
    temp_parser.add_argument("--slot", type=parse_int, default=1)
    temp_parser.add_argument("--circuit", type=int, default=1)
    temp_parser.add_argument("--temp", type=float, required=True)

    discovery_parser = sub.add_parser("discovery")
    discovery_parser.add_argument("--slot", type=parse_int, default=1)

    read_parser = sub.add_parser("master-read")
    read_parser.add_argument("--slot", type=parse_int, default=1)
    read_parser.add_argument("--block", type=parse_int, required=True)

    args = parser.parse_args()

    if args.command == "crc":
        raw = bytes.fromhex(
            args.hexbytes.replace(":", " ").replace("-", " ")
        )
        crc = crc16_kermit(raw)
        print(f"CRC value: 0x{crc:04X}")
        print(f"Wire CRC:  {crc & 0xFF:02X} {(crc >> 8) & 0xFF:02X}")
        print(f"Frame:     {fmt(append_crc(raw))}")
    elif args.command == "identity":
        print(fmt(identity(args.slot, args.device_id, args.sn1, args.sn2)))
    elif args.command == "pong":
        print(fmt(pong(args.slot)))
    elif args.command == "room-temp":
        print(fmt(room_temp(args.slot, args.circuit, args.temp)))
    elif args.command == "discovery":
        print(fmt(discovery(args.slot)))
    elif args.command == "master-read":
        print(fmt(master_read(args.slot, args.block)))


if __name__ == "__main__":
    main()
