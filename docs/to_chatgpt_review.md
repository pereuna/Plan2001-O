**`D2a OUTPUT PASS`** (diagnostic only; not D2b/D2c).

- New `IOWRITE` syscall 62 and process-local `Proc.iomask` handles (1 OUT, 2 DIAG), granted only to `oboot=mp`, preserved across `OEXECUTE`, cleared on `newproc` reuse. No `Fgrp`, `Chan`, `namec`, path or fake FD.
- `p9_console_write` routes to native OUT; `p9_dprintf` routes `main.c`/`p9space.c` diagnostics to native DIAG. Probing is enabled only for `-O`, so build-VM seeding remains legacy-safe. `fdtochan` now returns `Ebadfd` for nil `up->fgrp`.
- Evidence: `IOWRITE h=2 n=72 ret=72`, UART text `space: O volume selected: PARTUUID=...`, `OBOOT-D2A: OUTPUT ... counters namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`; no post-MP `PWRITE(fd=2)`.
- Current MP: `len=2195102 sha256=96a82678...bf5c086`; host, seed and kernel `OEXECUTE` digest agree. User negatives handle 99, length -1, length 65537 all return -1; legacy `pwrite(2,...)` returns -1 without panic. Missing OID negative passes.
- **`NEXT BLOCKER = BIND`** from `boot.py:41`: `bindmount`/`namec` needs `up->slash`; the `/dev` destination hits `chan.c:1342-1343` with `slash=nil` and faults (`kernel fault read addr=0x0`). `space.open('init')`, `p9_space_boot`, run() and commit are **NOT REACHED**.
- **`LEGACY COMPATIBILITY = PASS`**: Boot A/B/C, normal O/MicroPython three-boot, pathless storage, exec, argv and handles gates pass.
- **`STREAM API LIMITS`**: provisional fixed handles and one console-UART backend; no registry, input, PTY, screen, kbmap, 9P or general device model. Invalid pointers are `validaddr`-guarded before copy; not separately injected into the pid-1 positive boot.

Commits: `4c2ae36`, `182be33`, docs `81cb563` (pushed). Evidence: `docs/O-BOOT-EXPERIMENT-D2A.md`, `build/verification/test-oboot-output-{experiment,pos,missing}-experiment-d2a.log`.
