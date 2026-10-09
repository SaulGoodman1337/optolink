# WB2A hardware campaign analysis - 2026-10-09

Seven verified single-ENQ VS1/P300 roundtrips averaged 4645.183 ms core duration. The mean combined EOT-to-ENQ host wait was 3977.187 ms. Idle offsets did not improve total elapsed time. Early P300 START and early VS1 ID both failed within 350 ms and production health was subsequently verified via real VS1-GFA P80=20 / P06=00. With a recovery EOT issued about 376 ms after the first EOT, the first observed ENQ still appeared about 1998 ms after the first EOT in both experiments. This is evidence of a continuing observed synchronization cycle, not proof of a universal fixed firmware timer. The on-wire sub-four-second goal is not yet demonstrated.

Source: operator-provided 2026-10-09 LXC terminal outputs. Preserve initial FAILED/NOT_VERIFIED statuses of speculative experiments; the campaign exit code zero signifies restored state after a negative hypothesis, not successful early synchronization.
