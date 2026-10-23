## Boot Experiment D2b — 23 October 2026

**`D2b SERVER BOOT PASS`.**

- `RUN 1/2/3 = run() -> 1 / 2 / 3`, with `init: done` after each durable
  commit. `SAME DISK = verified`: one combined ESP+O image booted three
  times unchanged; no host reseed or O-volume copy between boots.
- `PERSISTENCE`: boot 1 fresh one-time `odemo` init -> init version 1
  (O version 2); boot 2 restored version 1, no module reinit -> version 2
  (O version 3); boot 3 restored version 2 -> version 3 (O version 4).
  Counter OID 7 / alias 7 unchanged, `n=1/2/3`.
- New `-N` native server mode (`micropython -O PARTUUID=... -S init -N`)
  skips `boot.py`, calls native `space.open('init')`, `p9_space_boot`,
  `p9_space_commit(1)` and `p9_space_report`, then sleeps. `-B` and
  `oboot=mp` are unchanged. New `oboot=server` reuses the same embedded
  loader/`otouser`/`OEXECUTE(OID_MP_EXEC)` and output grant.
- Hidden legacy dependencies fixed on the `-N` path only:
  `p9_spacetime`/`getenv`, libc `nsec()` (`/dev/bintime`) replaced by
  `p9_now()`/`_NSEC`, and native `loadmod` avoids
  `libpath`/`getuser` (`STAT /proc/...`). No `/env`, `/proc`, `/dev`,
  fake FD/Chan or global `getenv` change.
- `NATIVE ONLY`: zero `OBOOT-D2B: LEGACY-ATTEMPT` records; all
  `namec/newchan/walk/devwalk/mount/exec` counters zero at n=4/16/32/64;
  no post-MP BIND/OPEN/PWRITE/FD2PATH. Native `IOWRITE` delivered the
  `run()`, commit and `init: done` messages.
- Hashes: MicroPython `len=2195994 sha256=cb3fe615...723eaa`; seed and
  kernel `OEXECUTE` digest agree. `9pc64` md5
  `5efa866b985bd766b6e5c3df3b37b8cf`.
- Negatives PASS: separate `run()`-raises image reaches
  `init: run failed` / `init: failed, no commit` with no version/COMMIT/
  done; missing `OID_MP_EXEC` returns `-1`, preserves the handle
  (`OSPACEGET ret=0xd1`), no MicroPython/done/commit/panic.
- `LEGACY CONTROLS = PASS`: D2a output diagnostic, Boot A/B/C, normal O
  three-boot, pathless storage, native exec/argv/handles.
- Source `3cfd4ed` plus docs follow-up. Evidence:
  `docs/O-BOOT-EXPERIMENT-D2B.md`, `docs/STATUS.md`,
  `build/verification/test-oboot-server-experiment-d2b.log`,
  `build/verification/test-oboot-server-boot{1,2,3}-experiment-d2b.log`,
  `build/verification/test-oboot-server-{fail,missing}-experiment-d2b.log`.

**NEXT D2c EXPERIMENT:** add the smallest pathless serial input/line
discipline (or equivalent native stdin stream) to `p9_console_read`, then
demonstrate a real REPL interaction without `/dev/cons` or `kbdfs`. Not
implemented here.

---

## Previous review note — Boot Experiment D2a

**`D2a OUTPUT PASS`** (diagnostic only; not D2b/D2c).

- New `IOWRITE` syscall 62 and process-local `Proc.iomask` handles (1 OUT, 2 DIAG), granted only to `oboot=mp`, preserved across `OEXECUTE`, cleared on `newproc` reuse. No `Fgrp`, `Chan`, `namec`, path or fake FD.
- `p9_console_write` routes to native OUT; `p9_dprintf` routes `main.c`/`p9space.c` diagnostics to native DIAG. Probing is enabled only for `-O`, so build-VM seeding remains legacy-safe. `fdtochan` now returns `Ebadfd` for nil `up->fgrp`.
- Evidence: `IOWRITE h=2 n=72 ret=72`, UART text `space: O volume selected: PARTUUID=...`, `OBOOT-D2A: OUTPUT ... counters namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`; no post-MP `PWRITE(fd=2)`.
- Current MP: `len=2195102 sha256=96a82678...bf5c086`; host, seed and kernel `OEXECUTE` digest agree. User negatives handle 99, length -1, length 65537 all return -1; legacy `pwrite(2,...)` returns -1 without panic. Missing OID negative passes.
- **`NEXT BLOCKER = BIND`** from `boot.py:41`: `bindmount`/`namec` needs `up->slash`; the `/dev` destination hits `chan.c:1342-1343` with `slash=nil` and faults (`kernel fault read addr=0x0`). `space.open('init')`, `p9_space_boot`, run() and commit are **NOT REACHED**.
- **`LEGACY COMPATIBILITY = PASS`**: Boot A/B/C, normal O/MicroPython three-boot, pathless storage, exec, argv and handles gates pass.
- **`STREAM API LIMITS`**: provisional fixed handles and one console-UART backend; no registry, input, PTY, screen, kbmap, 9P or general device model. Invalid pointers are `validaddr`-guarded before copy; not separately injected into the pid-1 positive boot.

Commits: `4c2ae36`, `182be33`, docs `81cb563` (pushed). Evidence: `docs/O-BOOT-EXPERIMENT-D2A.md`, `build/verification/test-oboot-output-{experiment,pos,missing}-experiment-d2a.log`.
