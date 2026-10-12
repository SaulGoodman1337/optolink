#!/usr/bin/env python3
"""Bench preparation: test pinned M16C Flasher against FAKE POSIX PTY only.

This emulator creates a fresh pseudo-terminal completely disconnected from
any CP2102, Optolink, live boiler, board, USB adapter or hardware UART.
Only two synthetic bootloader read-only commands supported (ver and status).
No flash code, RAM program download, ID guessing, erase, lock, boot pin or
hardware reset, even if the CLI is abused.
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
import threading
import time

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location(
 "wb2a_m16c_boot_fake_pin_gate",
 HERE/"wb2a-m16c-boot-hardware-preflight-offline.py")
if not s or not s.loader:raise RuntimeError("original boot readiness checker missing")
gates=importlib.util.module_from_spec(s);sys.modules[s.name]=gates
s.loader.exec_module(gates)
ALLOWED={
 "ver":(bytes.fromhex("b0fb"),bytes.fromhex("b0")+b"VER4.04\x00"),
 "status":(bytes.fromhex("b070"),bytes.fromhex("b0")+bytes.fromhex("000c")),
}
TIMEOUT=5

class Refused(ValueError):pass

def virtual_test(command):
 if command not in ALLOWED:
  raise Refused("only ver/status over automatically generated POSIX PTY")
 if gates.safe_hash(gates.FLASHER,750000)!=gates.EXPECTED_FLASHER_SHA:
  raise Refused("unattested real M16C offline flasher binary")
 master,slave=pty.openpty()
 path=os.ttyname(slave)
 if path.startswith("/dev/serial") or not path.startswith("/dev/pts/"):
  raise Refused("emulation must use only a newly created /dev/pts/N")
 raw=[]
 observed=[]
 error=[]
 expected_tx=ALLOWED[command][0]
 def fake_bootloader():
  deadline=time.monotonic()+TIMEOUT+2
  while time.monotonic()<deadline and len(observed)<2:
   try:ready,_,_=select.select([master],[],[],0.1)
   except (ValueError,OSError):return
   if not ready:continue
   try:b=os.read(master,1024)
   except OSError:return
   if not b:return
   for one in b:
    observed.append(one)
    if len(observed)>len(expected_tx) or one!=expected_tx[len(observed)-1]:
     error.append("unexpected serial command byte "+hex(one));return
    if len(observed)==1:
     os.write(master,b"\xb0")
    elif command=="ver":
     os.write(master,b"VER4.04\x00")
    elif command=="status":
     os.write(master,bytes.fromhex("000c"))
 thread=threading.Thread(target=fake_bootloader,daemon=True)
 thread.start()
 try:
  child=subprocess.run(
   [str(gates.FLASHER),"path="+path,"baud=9600",command],
   capture_output=True,text=True,timeout=TIMEOUT)
 finally:
  thread.join(timeout=0.3)
  os.close(slave)
  os.close(master)
 out=child.stdout
 if (child.returncode!=0 or error or bytes(observed)!=expected_tx or
     (command=="ver" and "VER4.04" not in out) or
     (command=="status" and "SRD = 0x0c00" not in out)):
  raise Refused("mock M16C bootloader protocol was not matched "+
                str({"command":command,"rc":child.returncode,
                     "actual_tx":bytes(observed).hex(),"errors":error,
                     "stdout":out[:140],"stderr":child.stderr[:140]}))
 return {
  "cmd":command,"simulation":"POSIX_PTY_NEW_UNCONNECTED",
  "actual_flasher_command_bytes":bytes(observed).hex(),
  "expected_bootloader_receive":"VER4.04" if command=="ver" else "SRD 0x0c00",
  "actual_stdout_prefix":out.strip().splitlines()[0],
  "process_returncode":child.returncode,
  "no_real_hardware_serial_IO":True,
  "physical_controller_connected":False,
  "real_bootloader_state_verified":False,
 }


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--out",type=Path)
 args=p.parse_args()
 items=[virtual_test(command) for command in ("ver","status")]
 report={
  "mode":"BOOTLOADER_DRY_RUN_FAKE_PTY_ONLY",
  "original_binary_sha256":gates.EXPECTED_FLASHER_SHA,
  "original_repo_commit":gates.EXPECTED_FLASHER_COMMIT,
  "synthetic_checks":items,
  "safe_software_communication_simulation_success":len(items)==2,
  "user_controller_boot_MODE_entered":False,
  "actual_heater_program_ROM_read":False,
  "commands_transmitted_to_heater":0,
  "boot_or_flash_writes":0,
 }
 text=json.dumps(report,indent=2,sort_keys=True)+"\n"
 if args.out:args.out.write_text(text)
 print(text)


if __name__=="__main__":main()
