#!/opt/optolink/venv/bin/python
from __future__ import annotations
import fcntl,os,signal,subprocess,time,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base',HERE/'physical-ram-snapshot.py'); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
PORT=None

def active(u): return b.active(u)
def svc(a,u): return b.svc(a,u)

def main():
 import serial,sys
 if '--self-test' in sys.argv: print('SELFTEST=PASS'); return 0
 fd=os.open(b.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 services=(b.SCHEDULE,b.PARTY,b.SPLITTER); states={u:active(u) for u in services}; stopped=[]; s=None
 def exact(n,timeout=3):
  end=time.monotonic()+timeout; out=bytearray()
  while len(out)<n and time.monotonic()<end: out.extend(s.read(n-len(out)))
  if len(out)!=n: raise RuntimeError(f'timeout {n}/{len(out)}')
  return bytes(out)
 def control(want,timeout=5):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   x=s.read(1)
   if not x: continue
   if x==bytes((want,)): return
   if want==5 and x in (b'\x06',b'\x15'): continue
   if want==6 and x==b'\x05': continue
   raise RuntimeError(f'control got {x.hex()} want {want:02x}')
  raise RuntimeError('control timeout')
 try:
  for u in services:
   if states[u]: svc('stop',u); stopped.append(u)
  import sys as _s; _s.path.insert(0,'/opt/optolink'); from c_settings_adapter import settings
  port=settings.port_optolink
  s=serial.Serial(port=port,baudrate=4800,bytesize=8,parity='E',stopbits=2,timeout=.05,write_timeout=2,exclusive=True)
  time.sleep(.30)
  s.reset_input_buffer()
  t0=time.monotonic(); s.write(b'\x04'); control(5); t1=time.monotonic(); s.write(b'\x16\x00\x00'); control(6); t2=time.monotonic()
  req=b.frame(0x01,0x00F8,2); s.write(req); ack=exact(1); assert ack==b'\x06', ack.hex(); h=exact(2); msg=h+exact(h[1]+1); s.write(b'\x06'); t3=time.monotonic()
  ident=msg[7:-1]
  s.write(b'\x04'); control(5); t4=time.monotonic(); control(5); t5=time.monotonic(); s.write(bytes.fromhex('01f700f802')); vs1=exact(2); t6=time.monotonic()
  print(f'P300_SWITCH_MS={(t2-t0)*1000:.1f}')
  print(f'P300_IDENT_MS={(t3-t2)*1000:.1f} ident={ident.hex()}')
  print(f'VS1_SWITCH_MS={(t5-t3)*1000:.1f}')
  print(f'VS1_IDENT_MS={(t6-t5)*1000:.1f} ident={vs1.hex()}')
  print(f'TOTAL_MS={(t6-t0)*1000:.1f}')
 finally:
  if s:
   try:s.close()
   except:pass
  for u in reversed(stopped):
   try:svc('start',u)
   except:pass
  os.close(fd)
 return 0
if __name__=='__main__': raise SystemExit(main())
