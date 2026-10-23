## Boot Experiment D2a — 23 October 2026

**`D2a OUTPUT PASS` (diagnostic only).**
`NEXT BLOCKER = BIND (#¤ then /dev) from boot.py: bindmount/namec needs
up->slash; slash is nil, so the second namec faults at chan.c:1342-1343
(kernel fault read addr=0x0).`
`LEGACY COMPATIBILITY = PASS (normal O/MicroPython three-boot gate).`
`STREAM API LIMITS = provisional fixed process-local handles 1 OUT / 2
DIAG to the one console UART; no registry/input/PTY/screen/kbmap/9P.`

- New `IOWRITE` syscall 62 and `Proc.iomask` grant. Only `oboot=mp`
  grants `1|2` before ring 3; `newproc` clears the grant, `OEXECUTE`
  preserves it for the same PID. The syscall validates the grant,
  lengths (0, negative, >64 KiB), console UART, and `validaddr`s/copies
  user bytes before `putstrn`. No FD, `Fgrp`, `Chan`, `namec` or path.
- `fdtochan` now returns `Ebadfd` for nil `up->fgrp` instead of locking
  nil. The loader's user `pwrite(2,...)` returns -1 without panic.
- MicroPython port: `p9_console_write` uses native OUT when enabled;
  `p9_dprintf` routes `main.c`/`p9space.c` diagnostics via DIAG. Native
  probing is enabled only for `-O` runs, so build-VM seeding (no `-O`)
  never calls the new syscall. Legacy `write(1)`/`fprint(2)` preserved.
- Evidence: unchanged/current MP `len=2195102 sha256=96a82678...bf5c086`;
  seed and kernel `OEXECUTE` digest agree. UART line
  `space: O volume selected: PARTUUID=...` appears; immediately before,
  `IOWRITE h=2 n=72 ret=72`; no post-MP `PWRITE(fd=2)`.
  `OBOOT-D2A: OUTPUT ... counters ... all zero`.
- User negatives: unbound handle 99, length -1, length 65537 all return
  -1; nil-`Fgrp` legacy PWRITE returns -1. Missing OID returns -1,
  preserves the handle (`OSPACEGET ret=0xd1`), prints no MicroPython text
  and does not panic.
- Downstream: MicroPython `p9_space_o` returned and `boot.py` executed.
  First `bind` entered `namec`; `/dev` destination then faulted on nil
  `up->slash`. `space.open('init')`, `p9_space_boot`, run() and commit
  were not reached. This is a diagnosed downstream failure, not D2b.
- Source: `4c2ae36` + `182be33` plus docs follow-up. Evidence:
  `docs/O-BOOT-EXPERIMENT-D2A.md`, `docs/STATUS.md`,
  `build/verification/test-oboot-output-experiment-d2a.log`,
  `build/verification/test-oboot-output-pos-experiment-d2a.log`,
  `build/verification/test-oboot-output-missing-experiment-d2a.log`.

**NEXT D2b EXPERIMENT:** give `boot.py`'s device `bind`/`namec` path the
minimal namespace root/destination it needs, or a smaller explicit
capability equivalent, then identify the next dependency. Not implemented
here.

---

## Previous review note — Boot Experiment D1

**`D1 EXEC PASS`** (diagnostic only; not a working MicroPython boot).

- **Highest proven startup milestone:** real O-resident MicroPython entry (`text=micropython`, `pc=0x275abc`), `main`/`mp_init` reached, and `p9_space_o` entered with its native `OVOLOPEN` completed (nr 54, ret 1). `boot.py`, `space.open('init')`, `p9_space_boot`, run() and commit were **NOT REACHED**.
- **Image provenance:** unchanged `OID_MP_EXEC` is 2,194,156 bytes, SHA-256 `41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc`; host, `mkovol` seed and kernel-read digest agree.
- **First legacy dependency:** `PWRITE` syscall 51, fd `2`, user PC `0x279db4`, from `p9space.c:366` `fprint("space: O volume selected")` → `write.c:7 pwrite` → `sysfile.c:145-147 fdtochan`, where `up->fgrp == nil` causes `kernel fault: write addr=0x8` and panic. The attempt is reported explicitly; zero path counters do not hide it.
- **Negative:** with `NOMPEXEC=1`, `OEXECUTE` returns `-1`, the handle survives (`OSPACEGET` ret `0xd1`), and the loader reports `alarm(0xbaf)` with no MicroPython and no panic.
- **Controls PASS:** Boot A/B/C, normal O/MicroPython, pathless storage, native exec, argv and handles. Commits `4d1d75f` + docs `4d4e714` pushed. Evidence: `docs/O-BOOT-EXPERIMENT-D1.md`, `build/verification/test-oboot-mp-*-experiment-d1.log`.

**`NEXT D2 EXPERIMENT =`** provide the smallest process-local FD/console facility that lets MicroPython's fd-2 diagnostic write return normally without `/dev/cons` or `kbdfs`, then observe the next real startup dependency.
