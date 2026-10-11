#!/usr/bin/env python3
"""Native-P300 Vitotrol-300 RAM-staging experimental driver for VDensHO1/20C2.

This is a REAL P300 Physical_WRITE bridge to the observed KM-Bus RAM
candidate at 0x1642, NOT an asserted UART1 RX-ISR/participant emulator.
The boiler has not accepted the virtual remote after this write alone.

Never opens a serial port or changes the serial owner/protocol mode.
Only uses the one existing optolink-splitter in native P300 mode via its
MQTT command client, and only fixed, original Vitotrol-300 frames.
Reversible controller changes are restored on completion or exceptions.
An independent external watchdog is still necessary for abrupt process loss.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "wb2a-vitotrol-offline.py"
SPEC = importlib.util.spec_from_file_location("vitotrol_p300_bridge_protocol", MODEL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("exact local Vitotrol offline protocol helper required")
model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = model
SPEC.loader.exec_module(model)

DEVICE = bytes.fromhex("20c2000300000103")
RX_BLOCK_ADDR = 0x1640
RX_START = 0x1642
RX_BLOCK_SIZE = 32
RX_CAPACITY = 30
FRAME_ORIGINAL_B3 = bytes.fromhex("0011b3100101f811f938fa01fb0a1db1")
FRAME_ORIGINAL_B1 = bytes.fromhex("0011b10a0101001219d5")
FRAME_ORIGINAL_ROOM_206 = bytes.fromhex("0011bf0c01012064aaaae42a")
FRAME_ORIGINAL_PONG = bytes.fromhex("001180080101f95c")
REPLAY = (FRAME_ORIGINAL_B3, FRAME_ORIGINAL_B1,
          FRAME_ORIGINAL_ROOM_206, FRAME_ORIGINAL_PONG)
MONITOR = (
    ("a0", 0x27A0, 1),
    ("b0", 0x27B0, 1),
    ("type", 0x7342, 1),
    ("swindex", 0x0A5C, 4),
    ("room_raw", 0x0896, 2),
    ("sensor", 0x089C, 1),
    ("current_fault", 0x5738, 1),
)
RESPONSE_PATTERN = re.compile(r"<- openv/resp:\s*([0-9]+);0x([0-9a-fA-F]+);([^\r\n]*)")
SETTINGS = Path("/opt/optolink/settings_ini.py")
AUDIT_FLAGS = {
    "optolink_native_p300_required": True,
    "physical_ram_write_proven": True,
    "km_bus_uart_rx_interrupt_triggered": False,
    "remote_accepted_by_controller": False,
    "controller_firmware_state_commit_proven": False,
}


class BridgeRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    code: int
    address: int
    data: bytes


def parse_response(output: str, expected_address: int) -> Response:
    if type(output) is not str or type(expected_address) is not int:
        raise BridgeRejected("typed controller response required")
    matches = list(RESPONSE_PATTERN.finditer(output))
    if len(matches) != 1:
        raise BridgeRejected("exactly one MQTT controller reply required")
    row = matches[0]
    code = int(row[1])
    addr = int(row[2], 16)
    val = row[3].strip()
    if addr != expected_address:
        raise BridgeRejected("controller response address mismatch")
    if code != 1:
        raise BridgeRejected(f"controller returned error code={code} data={val[:60]}")
    if val.lower() in ("none", "?"):
        result = b""
    else:
        try:
            result = bytes.fromhex(val)
        except ValueError as exc:
            raise BridgeRejected("malformed controller response hex") from exc
    return Response(code, addr, result)


class OptolinkP300Client:
    """Restricted client for the already-running single-owner P300 splitter."""
    def __init__(self, *, runner=subprocess.run):
        self.runner = runner

    def request(self, command: str, expected_address: int) -> Response:
        if type(command) is not str or not command:
            raise BridgeRejected("nonempty command required")
        if (not command.startswith(("read;", "writeraw;", "request;"))
                or len(command) > 280 or re.search(r"[^0-9A-Za-z;]", command)):
            raise BridgeRejected("invalid command boundary")
        argv = ["optolink-debug", "request", command, "--timeout", "7"]
        result = self.runner(argv, capture_output=True, text=True, timeout=12, check=False)
        if result.returncode:
            raise BridgeRejected("optolink-debug returned unsuccessful status")
        return parse_response(result.stdout, expected_address)

    def read(self, addr: int, n: int) -> bytes:
        if (addr, n) not in {(0x00F8, 8), *[(a, b) for _, a, b in MONITOR]}:
            raise BridgeRejected("virtual read outside known monitor set")
        result = self.request(f"read;0x{addr:04x};{n}", addr).data
        if len(result) != n:
            raise BridgeRejected("short virtual read")
        return result

    def physical_read(self) -> bytes:
        data = self.request("request;3;0x1640;32", RX_BLOCK_ADDR).data
        if len(data) != RX_BLOCK_SIZE:
            raise BridgeRejected("short physical RX read")
        return data

    def write_config(self, addr: int, value: int):
        if (addr, value) not in {
            (0x27A0, 0), (0x27A0, 1),
            (0x27B0, 0), (0x27B0, 3),
            (0x7342, 0), (0x7342, 0x74),
        }:
            raise BridgeRejected("unlisted coding/type write forbidden")
        reply = self.request(f"writeraw;0x{addr:04x};{value:02x}", addr)
        if reply.data and reply.data != bytes((value,)):
            raise BridgeRejected("controller wrote unexpected config value")

    def physical_write(self, addr: int, data: bytes):
        if (addr != RX_START or type(data) is not bytes or
                not 8 <= len(data) <= RX_CAPACITY):
            raise BridgeRejected("only fixed observed 0x1642 RX-buffer writes")
        self.request(f"request;4;0x1642;{len(data)};{data.hex()}", RX_START)


def validate_v300_frame(frame: bytes):
    model.validate_frame(frame)
    if (frame[0] != 0 or frame[1] != 0x11
            or frame[4] != 1 or frame[5] != 1
            or frame not in REPLAY):
        raise BridgeRejected("only exact captured original V300 slot-1 replies")
    if frame[2] == 0xB3:
        model.decode_candidate_slave_reply(frame)
    elif frame[2] == 0xB1:
        if frame != FRAME_ORIGINAL_B1:
            raise BridgeRejected("unknown remote register")
    elif frame[2] == 0xBF:
        model.decode_candidate_slave_room_temp(frame)
    elif frame[2] != 0x80:
        raise BridgeRejected("unknown remote command")
    return frame


def require_native_p300(settings: Path = SETTINGS, *, require_root: bool = True):
    if require_root and os.geteuid() != 0:
        raise BridgeRejected("must run as root to protect experiment and recovery")
    try:
        tree = ast.parse(settings.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError) as exc:
        raise BridgeRejected("settings unavailable") from exc
    flags = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "vs1protocol":
                    flags.append(ast.literal_eval(node.value))
    if flags != [False]:
        raise BridgeRejected("native P300 is required; do not toggle VS1 here")


def monitor(client: OptolinkP300Client) -> dict:
    return {key:client.read(addr, n).hex() for key, addr, n in MONITOR}


def acceptance(status: dict) -> dict:
    # A manually written 0x7342 type or successful Physical_WRITE is NOT
    # sufficient evidence of remotely accepted participant/liveness.
    sw = bytes.fromhex(status["swindex"])
    sensor = bytes.fromhex(status["sensor"])
    is_candidate = bool(any(sw)) and sensor != b"\x03" and (
        status["room_raw"] == "ce00")
    return {
        "software_index_nonzero":bool(any(sw)),
        "room_sensor_status_changed_from_03":sensor != b"\x03",
        "room_raw_hex":status["room_raw"],
        "expected_20_6c_room_raw_hex":"ce00",
        "candidate_participant_and_room_acknowledgement":is_candidate,
        "type_is_not_necessarily_registered":True,
        "physical_rx_isr_verified":False,
        "accepted_remote_proven":False,  # requires repeated, current reads
    }


class VitotrolP300Stager:
    """One bounded four-response replay on P300, with readback and restoration."""
    def __init__(self, client: OptolinkP300Client, *, pause=time.sleep):
        self.client = client
        self.pause = pause

    def check_preflight(self) -> tuple[dict, bytes]:
        identity=self.client.read(0x00F8, 8)
        if identity != DEVICE:
            raise BridgeRejected("not the expected VDensHO1 / 20C2 / 0103")
        state=monitor(self.client)
        if (state["a0"]!="00" or state["b0"]!="00"
                or state["type"]!="00" or state["current_fault"]!="00"):
            raise BridgeRejected("baseline not suitable for bounded test")
        ram=self.client.physical_read()
        # We are copying the observed frame buffer, not the actual physical bus.
        if len(ram)!=32:
            raise BridgeRejected("invalid original RAM backup")
        return state,ram

    def inject(self, frame: bytes):
        validate_v300_frame(frame)
        self.client.physical_write(RX_START, frame)
        got=self.client.physical_read()
        if got[2:2+len(frame)] != frame:
            raise BridgeRejected("physical RAM readback mismatch after injection")
        return {"written_frame":frame.hex(),"physical_readback_exact":True,
                "physical_uart_rx_event_proven":False}

    def experiment(self, *, configure_type: bool = False, preflight: bool = True):
        before,backup = self.check_preflight() if preflight else (monitor(self.client),self.client.physical_read())
        events=[]
        failures=[]
        began=False
        observations=[]
        try:
            began=True
            if configure_type:
                self.client.write_config(0x7342,0x74)
            self.client.write_config(0x27A0,1)
            self.client.write_config(0x27B0,3)
            observations.append({"stage":"enabled","values":monitor(self.client)})
            for frame in REPLAY:
                events.append(self.inject(frame))
            self.pause(.5)
            observations.append({"stage":"after_all_four_frames_0_5s",
                                 "values":monitor(self.client)})
            self.pause(.5)
            observations.append({"stage":"after_all_four_frames_1s",
                                 "values":monitor(self.client)})
        finally:
            if began:
                for step in (lambda:self.client.write_config(0x27B0,0),
                             lambda:self.client.write_config(0x27A0,0),
                             lambda:self.client.write_config(0x7342,0),
                             lambda:self.client.physical_write(RX_START,backup[2:32])):
                    try:
                        step()
                    except Exception as exc:
                        failures.append(str(exc)[:120])
        if failures:
            raise BridgeRejected("recovery incomplete: " + ", ".join(failures))
        after=monitor(self.client)
        ram=self.client.physical_read()
        if (after["a0"]!="00" or after["b0"]!="00" or after["type"]!="00"
                or ram[2:18] != backup[2:18]):
            raise BridgeRejected("coding/type/original RX buffer did not restore")
        two=[acceptance(row["values"]) for row in observations[-2:]]
        stable = all(row["candidate_participant_and_room_acknowledgement"]
                     for row in two)
        return {
            "mode":"REAL_NATIVE_P300_RAM_STAGING_NOT_UART_RX_EMULATION",
            "identity_20c2_0103_verified":True,
            "before":before,
            "frames_staged":events,
            "observations":observations,
            "last_active_acceptance_check":{
                **acceptance(observations[-1]["values"]),
                "accepted_remote_proven":stable,
                "two_separated_participant_and_room_readbacks":stable,
            },
            "restored_state":after,
            "rx_buffer_restored_first_16_bytes":True,
            "source_frames":"OPENV_2018_ORIGINAL_VITOTROL_300_UART_TX",
            "external_process_independent_rollback_required":True,
            **AUDIT_FLAGS,
            "remote_accepted_by_controller":stable,
        }


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--execute",action="store_true",
                     help="perform only the documented P300 RAM-staging experiment")
    cli.add_argument("--configure-type",action="store_true",
                     help="also select previously tested 0x7342=0x74 temporarily")
    args=cli.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"PLAN_ONLY_NO_CONTROLLER_IO",
                          "frame_hex":[x.hex() for x in REPLAY],
                          "controller_writes_sent":0,
                          "hardware_vitotrol_accepted":False},indent=2))
        return 0
    require_native_p300()
    result=VitotrolP300Stager(OptolinkP300Client()).experiment(
        configure_type=args.configure_type)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["last_active_acceptance_check"]["accepted_remote_proven"] else 4


if __name__=="__main__":
    raise SystemExit(main())
