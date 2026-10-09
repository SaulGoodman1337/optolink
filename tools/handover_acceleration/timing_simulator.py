"""Deterministic OFFLINE peer for measured ENQ timing sensitivity.

This is not a hardware port or a new Optolink handshake implementation.
No pySerial, systemd, network, CLI port argument, or actual controller I/O.
It uses archived phase durations to schedule artificial response bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque

from .coordinator import (
    EOT, ENQ, ACK, STX, DEVICE_ID, SOFTWARE, GFA, VS1_ID, VS1_SOFTWARE,
    P300_ID, P300_SOFTWARE, ReadOnlyWire, ProtocolError,
)


# In milliseconds, three previously reported measured phase durations:
# P300 initial ENQ, VS1 return ENQ, VS1 additional second ENQ (baseline).
# These are not newly observed controller timings or new measurements.
ARCHIVED_ENQ_MS = (
    (1996.9262860249728, 1997.6557079935446, 2237.470232998021),
    (1998.9537069341168, 1998.1562299653888, 2237.6668649958447),
    (1996.82713591028, 1997.8605279466137, 2237.8985040122643),
)


class VirtualClock:
    def __init__(self):
        self.now = 0.0
        self.largest_sleep = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        if seconds < 0:
            raise AssertionError("negative virtual sleep")
        self.largest_sleep = max(self.largest_sleep, seconds)
        self.now += seconds


@dataclass(frozen=True)
class PeerStep:
    tx: bytes
    replies: tuple[tuple[float, bytes], ...] = ()


def step(tx: bytes, *replies: tuple[float, bytes]):
    return PeerStep(tx, replies)


def enq_step(count: int, first_ms: float, extra_ms: float):
    if count not in (1, 2):
        raise ValueError("unsupported synthetic ENQ count")
    result = [(first_ms / 1000, ENQ)]
    if count == 2:
        result.append(((first_ms + extra_ms) / 1000, ENQ))
    return step(EOT, *result)


def frame(addr: int, payload: bytes):
    body = bytes([1, 1, addr >> 8, addr & 255, len(payload)]) + payload
    checksum = (7 + sum(body)) & 255
    return ACK + bytes([0x41, 7]) + body + bytes([checksum])


def vs1_script(count: int, enq_first_ms: float, enq_extra_ms: float, *,
               device: bytes = DEVICE_ID):
    return [
        enq_step(count, enq_first_ms, enq_extra_ms),
        step(STX + VS1_ID, (0.021, device)),
        step(VS1_SOFTWARE, (0.055, SOFTWARE)),
        step(GFA["P80"], (0.068, b"\x20")),
        step(GFA["P06"], (0.068, b"\x00")),
    ]


def p300_script(enq_ms: float):
    return [
        enq_step(1, enq_ms, 0.0),
        step(b"\x16\x00\x00", (0.013, ACK)),
        step(P300_ID, (0.030, frame(0x00F8, DEVICE_ID))),
        step(ACK),
        step(P300_SOFTWARE, (0.055, frame(0x778C, SOFTWARE))),
        step(ACK),
    ]


class TimedPeer:
    """Only emits fixed replies once their scripted virtual times have elapsed."""
    def __init__(self, clock: VirtualClock, script: list[PeerStep]):
        self.clock = clock
        self.script = deque(script)
        self.pending: deque[list] = deque()  # [available_at, bytearray]
        self.writes: list[tuple[float, bytes]] = []
        self.rx: list[tuple[float, bytes]] = []
        self.closed = False
        self.reset_count = 0

    def write(self, raw: bytes):
        if self.closed or self.pending:
            raise AssertionError("TX during outstanding response or after close")
        if not self.script:
            raise AssertionError("unexpected TX: " + raw.hex())
        item = self.script.popleft()
        if item.tx != raw:
            raise AssertionError("wrong TX: expected %s got %s" %
                                 (item.tx.hex(), raw.hex()))
        now = self.clock.monotonic()
        self.writes.append((now, raw))
        self.pending.extend([now + delay_s, bytearray(reply)]
                            for delay_s, reply in item.replies)
        return len(raw)

    def read(self, n):
        if self.closed:
            raise AssertionError("RX after close")
        if not self.pending or self.pending[0][0] > self.clock.monotonic():
            return b""
        event = self.pending[0]
        raw = bytes(event[1][:n])
        del event[1][:n]
        if not event[1]:
            self.pending.popleft()
        if raw:
            self.rx.append((self.clock.monotonic(), raw))
        return raw

    def reset_input_buffer(self):
        self.pending.clear()   # permissible only before new explicit EOT
        self.reset_count += 1

    def close(self):
        self.closed = True


@dataclass(frozen=True)
class TimingResult:
    enq_count: int
    sample_index: int
    elapsed_ms: float
    p300_ms: float
    return_ms: float
    control_tx_count: int
    all_steps_consumed: bool
    largest_host_sleep_ms: float


def simulate_roundtrip(enqs: int, sample_index: int = 0) -> TimingResult:
    """Cold verified VS1 setup outside sample, same payloads in both variants.

    This coordinator's return verification performs extra VS1 SW/P80/P06
    within the return stage compared with the historical probe; consequently
    the absolute synthetic duration is NOT the historical 4.610 s benchmark.
    The strictly paired *difference* tests removal of one ENQ wait.
    """
    first, back, extra = ARCHIVED_ENQ_MS[sample_index]
    clock = VirtualClock()
    steps = (vs1_script(2, back, extra) + p300_script(first) +
             vs1_script(enqs, back, extra) +
             [step(GFA["P09"], (0.068, b"\x0a")),
              step(GFA["P87"], (0.068, b"\x00"))])
    peer = TimedPeer(clock, steps)
    wire = ReadOnlyWire(peer, clock=clock.monotonic, sleep=clock.sleep)
    wire.verify_vs1(2)  # cold setup is not part of measured roundtrip
    before = clock.now
    wire.verify_p300()
    middle = clock.now
    wire.verify_vs1(enqs)
    wire.vs1_read(GFA["P09"], 1)
    wire.vs1_read(GFA["P87"], 1)
    after = clock.now
    return TimingResult(enqs, sample_index, (after - before) * 1000,
                        (middle - before) * 1000, (after - middle) * 1000,
                        sum(raw == EOT for _, raw in peer.writes),
                        not peer.script and not peer.pending,
                        clock.largest_sleep * 1000)


def compare_profiles():
    return [(simulate_roundtrip(2, i), simulate_roundtrip(1, i))
            for i in range(len(ARCHIVED_ENQ_MS))]
