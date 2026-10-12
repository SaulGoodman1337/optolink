#!/usr/bin/env python3
"""End-to-end ACTUAL 20-bit serial boot read, using FAKE MCU via fresh PTY.

The pinned m16cflasher is unmodified. This test passes addresses 0xF0000
through 0xF01FF to its own read() path, and validates the actual bytes it
transmits to an isolated, software-only simulator. Returns two synthesized
256-byte pages. No system Optolink device is addressed, no real flash is
read, no MCU is touched, no reset, no ID guessed, no write to device.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import threading
import time

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location(
 "wb2a_boot_fake_20bit_pin_checker",HERE/"wb2a-m16c-boot-hardware-preflight-offline.py")
if not s or not s.loader:raise RuntimeError("pinned boot preflight missing")
gate=importlib.util.module_from_spec(s);sys.modules[s.name]=gate;s.loader.exec_module(gate)
START=0xF0000
END=0xF01FF
TX=bytes.fromhex("b07070ff000fff010f")
SYNTHETIC_PAGES=(
 bytes(range(256)),
 bytes((255-i) for i in range(256)),
)
DATA=b"".join(SYNTHETIC_PAGES)


class Refused(ValueError):pass


def test_virtual_20bit_reader():
 if gate.safe_hash(gate.FLASHER,750000)!=gate.EXPECTED_FLASHER_SHA:
  raise Refused("unverified binary must not be run even on synthetic port")
 master,slave=pty.openpty()
 dev=os.ttyname(slave)
 if not dev.startswith("/dev/pts/"):
  raise Refused("not an automatically allocated synthetic PTY")
 bytes_seen=[]
 responded=[]
 errors=[]
 def simulator():
  state="WAIT_BAUD"
  high=None
  page_index=0
  stop=time.monotonic()+6
  while time.monotonic()<stop and page_index<len(SYNTHETIC_PAGES):
   try:rs,_,_=select.select([master],[],[],0.1)
   except (ValueError,OSError):return
   if not rs:continue
   try:new=os.read(master,256)
   except OSError:return
   if not new:return
   for byte in new:
    bytes_seen.append(byte)
    if state=="WAIT_BAUD":
     if byte!=0xB0:errors.append("invalid baud command");return
     os.write(master,bytes((0xB0,)))
     state="WAIT_STATUS0"
    elif state in ("WAIT_STATUS0","WAIT_STATUS1"):
     if byte!=0x70:errors.append("non-read boot command");return
     os.write(master,bytes.fromhex("000c"))
     state="WAIT_STATUS1" if state=="WAIT_STATUS0" else "WAIT_PAGE"
    elif state=="WAIT_PAGE":
     if byte!=0xFF:errors.append("flash page reader must send FF");return
     state="PAGE_ADDR_LOW"
    elif state=="PAGE_ADDR_LOW":
     if byte!=(page_index & 0xFF):errors.append("wrong 20bit page LOW");return
     state="PAGE_ADDR_HIGH"
    elif state=="PAGE_ADDR_HIGH":
     if byte!=0x0F:errors.append("lost 0xF0000 high address bits");return
     os.write(master,SYNTHETIC_PAGES[page_index])
     responded.append(page_index)
     page_index+=1
     state="WAIT_PAGE"
    else:errors.append("unexpected serial state");return
 with tempfile.TemporaryDirectory(prefix="wb2a-fake-20bit-") as t:
  output=Path(t)/"FAKE_NOT_CONTROLLER_ROM.bin"
  thread=threading.Thread(target=simulator,daemon=True)
  thread.start()
  try:
   p=subprocess.run([
    str(gate.FLASHER),"path="+dev,"baud=9600","read",
    "from_addr="+str(START),"to_addr="+str(END),"file="+str(output),
   ],capture_output=True,text=True,timeout=6)
  except subprocess.TimeoutExpired as e:
   raise Refused("real flasher timed out on fake MCU") from e
  finally:
   thread.join(timeout=0.5)
   os.close(slave)
   os.close(master)
  if (p.returncode!=0 or errors or bytes(bytes_seen)!=TX or
      responded!=[0,1] or not output.is_file() or
      output.read_bytes()!=DATA):
   raise Refused("20-bit page wire/data mismatch "+str({
      "rc":p.returncode,"tx":bytes(bytes_seen).hex(),
      "error":errors,"pages":responded,
      "out":p.stdout[:180],"err":p.stderr[:180],
      "file_exists":output.is_file()}))
  return {
   "mode":"FAKE_M16C_20BIT_PAGE_READ_AT_F0000_NO_REAL_HARDWARE",
   "real_executable_sha256":gate.EXPECTED_FLASHER_SHA,
   "virtual_port_type":"NEW_PSEUDOTERMINAL_/dev/pts/N",
   "request_start_address":f"0x{START:05x}",
   "request_end_address":f"0x{END:05x}",
   "transmitted_bootloader_bytes":bytes(bytes_seen).hex(),
   "expected_20bit_page_addresses_hex":["0xF0000","0xF0100"],
   "expected_page_request_frames":["ff000f","ff010f"],
   "actual_pages_256bytes":len(responded),
   "synthetic_RAM_program_bytes":False,
   "synthetic_flash_bytes_returned":len(DATA),
   "synthetic_file_sha256":hashlib.sha256(DATA).hexdigest(),
   "full_20bit_address_passed_untruncated_in_BOOT_PROTOCOL":True,
   "full_20bit_address_passed_untruncated_in_OPTOLINK_P300":False,
   "actual_WB2A_flash_bytes_recovered":False,
   "live_burner_control_affected":False,
   "physical_controller_IO":0,"controller_writes":0,
  }


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--out",type=Path)
 args=p.parse_args()
 result=test_virtual_20bit_reader()
 formatted=json.dumps(result,indent=2,sort_keys=True)+"\n"
 if args.out:args.out.write_text(formatted)
 print(formatted)


if __name__=="__main__":main()
