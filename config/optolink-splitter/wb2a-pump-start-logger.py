#!/usr/bin/env python3
"""WB2A / VDensHO1 read-only pump/start comparison logger.

Purpose:
  Compare otherwise similar burner starts in space-heating and DHW operation
  without changing controller state.

Fast runtime set:
  0x7660 / 2   internal-pump output object; byte 1 is pump speed [%]
  0x7663 / 2   A1/M1 heating-circuit pump output; byte 1 is pump speed [%]
  0x650A / 1   DHW preparation status
  0x6513 / 1   storage charging pump state
  0x0A10 / 1   diverter-valve state
  0x27E7 / 1   A1 minimum pump-speed coding E7
  0x7500 / 1   actuator-test selector
  0xA152 / 2   relay-state block; byte 0 bit 0x20 = internal pump
  0x55D3 / 11  GG1/GFA runtime block incl. flame, 0x55DC modulation, 0x55DD
  0x55E0 / 17  RKR/restart/startup-optimization runtime structure
  0x2544 / 2   A1/M1 flow-temperature target, little-endian / 10
  0x0810 / 2   boiler actual temperature, little-endian / 10

One-time read-only configuration snapshot:
  0x572E                 external-extension presence
  0x572F                 vent/fill service program
  0x7751                 read-only latent K51 candidate; NOT in exact VDensHO1 profile
  0x7752                 hydraulic-separator sensor coding K52
  0x7500                 actuator-test selector (read only)
  0x5730/31/32/34        internal-pump identity/target/external influences
  0x779B                 external-demand flow-temperature target
  0x0A48 / 4             external-extension software-index block
  0x27E5..0x27E9         A1 pump identity/max/min/reduced-mode configuration
  0x37E5..0x37E9         M2 equivalents
  0x6762/65/6C/6F        DHW pump overrun/valve type/DHW pump speed/power limit
  0x0A54 / 4             internal-pump software-index block
  0x1070 / 16            coding-plug GWG70..76 structure

No writes are performed.

Interpretation:
  The generated exact VDensHO1 catalog places both InternePumpeDrehzahl
  (0x7660) and HKP_A1Drehzahl (0x7663) in byte offset 1 of a two-byte object,
  with percent units. The local 20C2 hardware has now confirmed 0x7660=01 64
  during DHW overrun, i.e. output on and internal-pump speed 100 %.
"""

import argparse
import csv
import socket
import sys
import time
from datetime import datetime
from pathlib import Path


class OptolinkTcp:
    def __init__(self, host: str, port: int, timeout: float = 5.0, idle_timeout: float = 0.35):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.sock = None
        self.rxbuf = bytearray()

    def connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.rxbuf.clear()

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.rxbuf.clear()

    def _recv_response(self) -> str:
        if self.sock is None:
            raise ConnectionError("TCP socket is not connected")

        if b"\n" in self.rxbuf:
            line, _, rest = self.rxbuf.partition(b"\n")
            self.rxbuf = bytearray(rest)
            return line.decode("utf-8", errors="replace").strip("\r\0 ")

        self.sock.settimeout(self.timeout)
        while True:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                if self.rxbuf:
                    line = bytes(self.rxbuf)
                    self.rxbuf.clear()
                    return line.decode("utf-8", errors="replace").strip("\r\n\0 ")
                raise TimeoutError("timeout waiting for optolink-splitter response")

            if not chunk:
                raise ConnectionError("optolink-splitter closed the TCP connection")

            self.rxbuf.extend(chunk)
            if b"\n" in self.rxbuf:
                line, _, rest = self.rxbuf.partition(b"\n")
                self.rxbuf = bytearray(rest)
                return line.decode("utf-8", errors="replace").strip("\r\0 ")

            self.sock.settimeout(self.idle_timeout)

    def request_any(self, command: str) -> str:
        if self.sock is None:
            raise ConnectionError("TCP socket is not connected")
        self.sock.sendall((command + "\n").encode("ascii"))
        return self._recv_response()

    def request(self, command: str) -> bytes:
        response = self.request_any(command)
        parts = response.split(";", 2)
        if len(parts) != 3:
            raise RuntimeError(f"unexpected response for {command!r}: {response!r}")
        retcode, address, payload = parts
        if retcode != "1":
            raise RuntimeError(
                f"Optolink error for {command!r}: "
                f"retcode={retcode}, address={address}, payload={payload}"
            )
        try:
            return bytes.fromhex(payload.strip())
        except ValueError as e:
            raise RuntimeError(f"invalid hex payload for {command!r}: {payload!r}") from e


def read_exact(client: OptolinkTcp, address: str, length: int) -> bytes:
    raw = client.request(f"read;{address};{length}")
    if len(raw) < length:
        raise RuntimeError(
            f"{address} returned {len(raw)} bytes, expected {length}: {raw.hex()}"
        )
    return raw[:length]


def u16le(raw: bytes) -> int:
    return raw[0] | (raw[1] << 8)


def parse_args():
    p = argparse.ArgumentParser(
        description="WB2A read-only pump/burner-start comparison logger"
    )
    p.add_argument("--host", default="127.0.0.1", help="splitter host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=65234, help="splitter TCP port (default: 65234)")
    p.add_argument(
        "--mode",
        choices=("heating", "dhw", "auto"),
        default="auto",
        help="run label only; does not change controller state (default: auto)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="minimum cycle interval in seconds (default: 1.0; actual cycle may be slower)",
    )
    p.add_argument(
        "--output",
        help="CSV path; default: /root/wb2a_pump_<mode>_YYYYmmdd_HHMMSS.csv",
    )
    return p.parse_args()


def capture_probes(client: OptolinkTcp, probe_path: Path) -> None:
    probes = [
        ("K2E_external_extension_present", "0x572E", 1),
        ("K2F_vent_fill_program", "0x572F", 1),
        ("K51_candidate_hydr_sep_internal_pump", "0x7751", 1),
        ("K52_hydraulic_separator_sensor", "0x7752", 1),
        ("actuator_test_selector", "0x7500", 1),
        ("external_extension_software_index", "0x0A48", 4),
        ("K9B_external_demand_flow_target_c", "0x779B", 1),
        ("K30_internal_pump_id", "0x5730", 1),
        ("K31_internal_pump_target_pct", "0x5731", 1),
        ("K32_external_block_pump_effect", "0x5732", 1),
        ("K34_external_demand_pump_effect", "0x5734", 1),
        ("internal_pump_software_index", "0x0A54", 4),
        ("A1_E5_pump_id", "0x27E5", 1),
        ("A1_E6_max_pct", "0x27E6", 1),
        ("A1_E7_min_pct", "0x27E7", 1),
        ("A1_E8_reduced_selector", "0x27E8", 1),
        ("A1_E9_reduced_pct", "0x27E9", 1),
        ("M2_E5_pump_id", "0x37E5", 1),
        ("M2_E6_max_pct", "0x37E6", 1),
        ("M2_E7_min_pct", "0x37E7", 1),
        ("M2_E8_reduced_selector", "0x37E8", 1),
        ("M2_E9_reduced_pct", "0x37E9", 1),
        ("K62_storage_pump_overrun", "0x6762", 1),
        ("K65_diverter_valve_type", "0x6765", 1),
        ("K6C_DHW_internal_pump_pct", "0x676C", 1),
        ("K6F_DHW_power_limit_pct", "0x676F", 1),
        ("coding_plug_GWG70_76", "0x1070", 16),
    ]

    with probe_path.open("w", encoding="utf-8") as pf:
        pf.write("# WB2A pump/start read-only configuration snapshot\n")
        pf.write(f"# {datetime.now().isoformat(timespec='seconds')}\n")
        pf.write("# No writes performed.\n")
        for label, address, length in probes:
            command = f"read;{address};{length}"
            try:
                response = client.request_any(command)
            except Exception as e:
                response = f"ERROR: {e}"
            line = f"{label:38s} {command:20s} -> {response}"
            print("  " + line)
            pf.write(line + "\n")


def main():
    args = parse_args()
    logfile = (
        Path(args.output)
        if args.output
        else Path(f"/root/wb2a_pump_{args.mode}_{datetime.now():%Y%m%d_%H%M%S}.csv")
    )
    probe_path = logfile.with_suffix(".probes.txt")

    client = OptolinkTcp(args.host, args.port)

    print("WB2A Pumpen-/Brennerstart-Logger")
    print("================================")
    print(f"Splitter: {args.host}:{args.port}")
    print(f"Mode label: {args.mode} (label only; no controller write)")
    print(f"CSV:      {logfile}")
    print(f"Probes:   {probe_path}")
    print("Interval: minimum %.2f s" % args.interval)
    print("Reads:    7660/2 7663/2 650A/1 6513/1 0A10/1 27E7/1 7500/1 A152/2 55D3/11 55E0/17 2544/2 0810/2")
    print("Writes:   none")
    print("Ctrl-C beendet")
    print()

    try:
        client.connect()
    except OSError as e:
        print(f"TCP connect failed: {e}", file=sys.stderr)
        return 2

    print("Read-only configuration snapshot:")
    capture_probes(client, probe_path)
    print()

    fields = [
        "timestamp",
        "mode_label",
        "cycle_ms",
        "event",
        "raw_7660",
        "pump_output_raw",
        "pump_speed_pct",
        "raw_7663",
        "a1_pump_output_raw",
        "a1_pump_speed_pct",
        "raw_650a",
        "ww_status_raw",
        "raw_6513",
        "storage_pump_raw",
        "raw_0a10",
        "diverter_raw",
        "raw_27e7",
        "a1_e7_min_pct",
        "raw_7500",
        "actuator_test_raw",
        "raw_a152",
        "internal_pump_relay",
        "burner_relay",
        "raw_55d3",
        "gfa_b0",
        "gfa_b1",
        "gfa_b2",
        "gfa_b3",
        "gfa_b4",
        "gfa_b5",
        "gfa_b6",
        "gfa_b7",
        "gfa_b8",
        "flame",
        "lockout",
        "modulation_55dc_pct",
        "status_55dd_hex",
        "seconds_since_flame_start",
        "raw_55e0",
        "rkr_enable_candidate",
        "rkr_boiler_target_c_candidate",
        "opt_target_c_candidate",
        "55e0_b14_hex",
        "restart_release_b0",
        "raw_2544",
        "flow_target_c",
        "raw_0810",
        "boiler_actual_c",
    ]

    previous_flame = None
    previous_pump_speed = None
    previous_a1_pump_speed = None
    previous_ww = None
    previous_storage = None
    previous_diverter = None
    previous_e7 = None
    previous_actuator_test = None
    previous_internal_pump_relay = None
    previous_gfa_state = None
    previous_b14 = None
    flame_start_mono = None

    with logfile.open("w", newline="", buffering=1, encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        try:
            while True:
                cycle_start = time.monotonic()
                events = []

                try:
                    raw7660 = read_exact(client, "0x7660", 2)
                    raw7663 = read_exact(client, "0x7663", 2)
                    raw650a = read_exact(client, "0x650A", 1)
                    raw6513 = read_exact(client, "0x6513", 1)
                    raw0a10 = read_exact(client, "0x0A10", 1)
                    raw27e7 = read_exact(client, "0x27E7", 1)
                    raw7500 = read_exact(client, "0x7500", 1)
                    rawa152 = read_exact(client, "0xA152", 2)
                    raw55d3 = read_exact(client, "0x55D3", 11)
                    raw55e0 = read_exact(client, "0x55E0", 17)
                    raw2544 = read_exact(client, "0x2544", 2)
                    raw0810 = read_exact(client, "0x0810", 2)
                except Exception as e:
                    print(
                        f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  "
                        f"READ_ERROR {e}; reconnecting",
                        file=sys.stderr,
                    )
                    client.close()
                    time.sleep(0.25)
                    try:
                        client.connect()
                    except OSError as reconnect_error:
                        print(f"Reconnect failed: {reconnect_error}", file=sys.stderr)
                        time.sleep(1.0)
                    continue

                now_mono = time.monotonic()

                pump_output = raw7660[0]
                pump_speed = raw7660[1]
                a1_pump_output = raw7663[0]
                a1_pump_speed = raw7663[1]
                ww_status = raw650a[0]
                storage_pump = raw6513[0]
                diverter = raw0a10[0]
                e7_min = raw27e7[0]
                actuator_test = raw7500[0]
                internal_pump_relay = int(bool(rawa152[0] & 0x20))
                burner_relay = int(bool(rawa152[0] & 0x02))

                flame = bool(raw55d3[5] & 0x20)
                lockout = bool(raw55d3[5] & 0x40)
                modulation = raw55d3[9]
                status55dd = raw55d3[10]
                gfa_state = (raw55d3[5], raw55d3[6], raw55d3[7])

                rkr_enable = raw55e0[0]
                rkr_target = u16le(raw55e0[1:3]) / 10.0
                opt_target = u16le(raw55e0[10:12]) / 10.0
                b14 = raw55e0[14]
                restart_release = int(bool(b14 & 0x01))

                flow_target = u16le(raw2544) / 10.0
                boiler_actual = u16le(raw0810) / 10.0

                if previous_flame is not None and flame != previous_flame:
                    if flame:
                        flame_start_mono = now_mono
                        events.append("FLAME_START")
                    else:
                        flame_start_mono = None
                        events.append("FLAME_STOP")
                elif previous_flame is None and flame:
                    flame_start_mono = now_mono

                if previous_pump_speed is not None and pump_speed != previous_pump_speed:
                    events.append(f"PUMP_{previous_pump_speed}->{pump_speed}")
                if previous_a1_pump_speed is not None and a1_pump_speed != previous_a1_pump_speed:
                    events.append(f"A1PUMP_{previous_a1_pump_speed}->{a1_pump_speed}")
                if previous_ww is not None and ww_status != previous_ww:
                    events.append(f"WW_{previous_ww:02x}->{ww_status:02x}")
                if previous_storage is not None and storage_pump != previous_storage:
                    events.append(f"SLP_{previous_storage:02x}->{storage_pump:02x}")
                if previous_diverter is not None and diverter != previous_diverter:
                    events.append(f"UV_{previous_diverter:02x}->{diverter:02x}")
                if previous_e7 is not None and e7_min != previous_e7:
                    events.append(f"E7_{previous_e7}->{e7_min}")
                if previous_actuator_test is not None and actuator_test != previous_actuator_test:
                    events.append(
                        f"ACTOR_{previous_actuator_test:02x}->{actuator_test:02x}"
                    )
                if (
                    previous_internal_pump_relay is not None
                    and internal_pump_relay != previous_internal_pump_relay
                ):
                    events.append(
                        f"PUMPRELAY_{previous_internal_pump_relay}->{internal_pump_relay}"
                    )
                if previous_gfa_state is not None and gfa_state != previous_gfa_state:
                    events.append(
                        "GFA_"
                        f"{previous_gfa_state[0]:02x}/{previous_gfa_state[1]:02x}/{previous_gfa_state[2]:02x}"
                        "->"
                        f"{gfa_state[0]:02x}/{gfa_state[1]:02x}/{gfa_state[2]:02x}"
                    )
                if previous_b14 is not None and b14 != previous_b14:
                    events.append(f"B14_{previous_b14:02x}->{b14:02x}")

                previous_flame = flame
                previous_pump_speed = pump_speed
                previous_a1_pump_speed = a1_pump_speed
                previous_ww = ww_status
                previous_storage = storage_pump
                previous_diverter = diverter
                previous_e7 = e7_min
                previous_actuator_test = actuator_test
                previous_internal_pump_relay = internal_pump_relay
                previous_gfa_state = gfa_state
                previous_b14 = b14

                flame_age = (
                    None
                    if not flame or flame_start_mono is None
                    else now_mono - flame_start_mono
                )

                cycle_end = time.monotonic()
                event_text = "|".join(events)

                writer.writerow({
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "mode_label": args.mode,
                    "cycle_ms": f"{(cycle_end - cycle_start) * 1000.0:.0f}",
                    "event": event_text,
                    "raw_7660": raw7660.hex(),
                    "pump_output_raw": pump_output,
                    "pump_speed_pct": pump_speed,
                    "raw_7663": raw7663.hex(),
                    "a1_pump_output_raw": a1_pump_output,
                    "a1_pump_speed_pct": a1_pump_speed,
                    "raw_650a": raw650a.hex(),
                    "ww_status_raw": ww_status,
                    "raw_6513": raw6513.hex(),
                    "storage_pump_raw": storage_pump,
                    "raw_0a10": raw0a10.hex(),
                    "diverter_raw": diverter,
                    "raw_27e7": raw27e7.hex(),
                    "a1_e7_min_pct": e7_min,
                    "raw_7500": raw7500.hex(),
                    "actuator_test_raw": actuator_test,
                    "raw_a152": rawa152.hex(),
                    "internal_pump_relay": internal_pump_relay,
                    "burner_relay": burner_relay,
                    "raw_55d3": raw55d3.hex(),
                    "gfa_b0": raw55d3[0],
                    "gfa_b1": raw55d3[1],
                    "gfa_b2": raw55d3[2],
                    "gfa_b3": raw55d3[3],
                    "gfa_b4": raw55d3[4],
                    "gfa_b5": raw55d3[5],
                    "gfa_b6": raw55d3[6],
                    "gfa_b7": raw55d3[7],
                    "gfa_b8": raw55d3[8],
                    "flame": int(flame),
                    "lockout": int(lockout),
                    "modulation_55dc_pct": modulation,
                    "status_55dd_hex": f"0x{status55dd:02x}",
                    "seconds_since_flame_start": "" if flame_age is None else f"{flame_age:.2f}",
                    "raw_55e0": raw55e0.hex(),
                    "rkr_enable_candidate": rkr_enable,
                    "rkr_boiler_target_c_candidate": f"{rkr_target:.1f}",
                    "opt_target_c_candidate": f"{opt_target:.1f}",
                    "55e0_b14_hex": f"0x{b14:02x}",
                    "restart_release_b0": restart_release,
                    "raw_2544": raw2544.hex(),
                    "flow_target_c": f"{flow_target:.1f}",
                    "raw_0810": raw0810.hex(),
                    "boiler_actual_c": f"{boiler_actual:.1f}",
                })

                evt = f"  {event_text}" if event_text else ""
                age_txt = "-" if flame_age is None else f"{flame_age:5.1f}s"
                print(
                    f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  "
                    f"P={pump_speed:3d}% OUT={pump_output:02x}  "
                    f"A1P={a1_pump_speed:3d}% A1OUT={a1_pump_output:02x}  "
                    f"WW={ww_status:02x} SLP={storage_pump:02x} UV={diverter:02x}  "
                    f"E7={e7_min:3d}% ACT={actuator_test:02x} PR={internal_pump_relay} BR={burner_relay}  "
                    f"FL={int(flame)} MOD={modulation:3d}% T={age_txt}  "
                    f"GFA={gfa_state[0]:02x}/{gfa_state[1]:02x}/{gfa_state[2]:02x}  "
                    f"RKR={rkr_enable:02x} OPT={opt_target:4.1f}C b14={b14:02x}  "
                    f"VS={flow_target:4.1f}C IST={boiler_actual:4.1f}C  "
                    f"cycle={(cycle_end - cycle_start) * 1000.0:.0f}ms"
                    f"{evt}"
                )

                remaining = args.interval - (time.monotonic() - cycle_start)
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            print()
            print(f"Gespeichert: {logfile}")
            print(f"Probes:      {probe_path}")
        finally:
            try:
                if client.sock is not None:
                    client.sock.sendall(b"exit\n")
            except OSError:
                pass
            client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())