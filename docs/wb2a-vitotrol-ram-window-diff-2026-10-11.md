# WB2A/20C2: 64-byte locality audit for candidate RAM address literals (2026-10-11)

Status: **offline / read-only / no Vitotrol acceptance proven**. No new Optolink traffic, P300 window, controller write, configuration change or serial-port owner.

## Source and scope

The historical `p300-fullram-results/run-20261009T083607Z-144293/snapshots` contains 79 complete independent 20,480-byte RAM images, mapping device addresses `0x0400..0x53FF`. The previously published pinned-archive verifier attested those images. This supplemental comparison uses `sudo od` on the already-stored image files; it does **not** reverify their cryptographic manifests by itself.

For three 64-byte windows (`center - 32` through `center + 31`, inclusive), the script counts distinct entire windows and byte offsets that vary between the 79 images. Windows are **not atomic simultaneous samples**; the full-RAM acquisition read 640 separate 32-byte blocks per snapshot.

| Center / interpretation | 64-byte windows distinct / 79 | Variable offsets / 64 | Variable offsets in +/-8 region |
| --- | ---: | ---: | ---: |
| `0x0B6D`, possible LE16 literal `0x1642` followed by `0A FE` | **78** | **26** | **1** (offset -2) |
| `0x33A3`, second LE16 literal `0x1642` followed by `1C 6A` | **1** | **0** | **0** |
| `0x161A`, independent DMA0/UART1 TX-RAM source (dynamic control) | **79** | **22** | **9** |

At `0x0B6D`, the four anchor bytes `42 16 0A FE` were unchanged in all 79 images, even though the surrounding 64-byte window varied. At `0x33A3`, the **whole 64-byte window** was unchanged in all 79 images; a raw matching `42 16` pair should therefore not be promoted to an RX pointer. The DMA0/UART1 TX buffer is a separate known-active comparison location; its variability is not evidence that either RX candidate is active.

**Interpretation limit:** these aggregate locality statistics can prioritize `0x0B6D` over the static region at `0x33A3` for further *offline* descriptor analysis, but do **not** establish pointer typing, producer ownership, UART1-RX vector/ISR, KM-Bus parser, or a firmware state-commit routine. No `INTB` register value or program-ROM was recovered, and no Optolink-based injection interface has been established.

## Reproduce on the retained private RAM images

The shell-based aggregator below intentionally never opens a new serial connection and cannot write to the appliance:

```bash
D=/root/p300-trial-work/p300-fullram-results/run-20261009T083607Z-144293/snapshots
for item in 0b6d:1869 33a3:12163 161a:4602; do
  key=${item%%:*}; start=${item#*:}
  echo "WINDOW_$key"
  for i in $(seq 1 79); do
    f="$D/s$(printf '%05d' "$i").bin"
    sudo od -An -v -tx1 -j "$start" -N 64 "$f" | tr -d ' \n'
    printf '\n'
  done | awk '{
    n++; wins[$0]++;
    for(j=1;j<=64;j++){x=substr($0,2*j-1,2);k=j ":" x;if(!(k in hit)){hit[k]=1;u[j]++}}
  } END {
    v=0;near=0;for(j=1;j<=64;j++){if(u[j]>1){v++;if(j>=25 && j<=40)near++}}
    for(x in wins)uniq++;
    print "samples=" n,"unique_windows=" uniq,"varying_bytes=" v,"near_anchor_8=" near
  }'
done
```

The offsets above are **image-file** offsets (`device_address - 0x0400 - 32`), not CPU addresses. Confirm the 79 source files and their hashes through the established full-RAM archive auditor before relying on new acquisitions.

## Acceptance boundary

The genuine WB2A still has no verified Vitotrol participant and no valid room-sensor status; the previous bounded `B0:3` test was rolled back to `B0:0`. No live Vitotrol response was accepted. Firmware extraction or another independently established safe Optolink ingress mechanism is required before any RX/ISR/State-Commit hypothesis can become a controller test.

## Pinned-archive Python cross-check

The companion purely offline runner `tools/wb2a-vitotrol-ram-window-locality.py` validates the exact original full-RAM bundle SHA256, its manifest, all 79 image hashes and per-image 20C2/0103 metadata before producing the same window statistics. It reads an ordinary local tar.gz file only; root privileges and the physical appliance are not required when an authorized readable **private** archive copy already exists.

```bash
python3 tools/wb2a-vitotrol-ram-window-locality.py --archive /private/offline/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz
python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_window_locality.py' -q
```

The archive remains outside Git. **Verified on 11 October 2026:** the standalone Python runner also executed against the original private archive (`SHA256 94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`), verified the manifest and all **79/79** images and reproduced the `od` locality counts above. These are still non-atomic historical snapshots, not an on-wire or UART1-ISR trace.
