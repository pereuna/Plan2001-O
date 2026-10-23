**`D1 EXEC PASS`** (diagnostic only; not a working MicroPython boot).

- **Highest proven startup milestone:** real O-resident MicroPython entry (`text=micropython`, `pc=0x275abc`), `main`/`mp_init` reached, and `p9_space_o` entered with its native `OVOLOPEN` completed (nr 54, ret 1). `boot.py`, `space.open('init')`, `p9_space_boot`, run() and commit were **NOT REACHED**.
- **Image provenance:** unchanged `OID_MP_EXEC` is 2,194,156 bytes, SHA-256 `41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc`; host, `mkovol` seed and kernel-read digest agree.
- **First legacy dependency:** `PWRITE` syscall 51, fd `2`, user PC `0x279db4`, from `p9space.c:366` `fprint("space: O volume selected")` → `write.c:7 pwrite` → `sysfile.c:145-147 fdtochan`, where `up->fgrp == nil` causes `kernel fault: write addr=0x8` and panic. The attempt is reported explicitly; zero path counters do not hide it.
- **Negative:** with `NOMPEXEC=1`, `OEXECUTE` returns `-1`, the handle survives (`OSPACEGET` ret `0xd1`), and the loader reports `alarm(0xbaf)` with no MicroPython and no panic.
- **Controls PASS:** Boot A/B/C, normal O/MicroPython, pathless storage, native exec, argv and handles. Commits `4d1d75f` + docs `4d4e714` pushed. Evidence: `docs/O-BOOT-EXPERIMENT-D1.md`, `build/verification/test-oboot-mp-*-experiment-d1.log`.

**`NEXT D2 EXPERIMENT =`** provide the smallest process-local FD/console facility that lets MicroPython's fd-2 diagnostic write return normally without `/dev/cons` or `kbdfs`, then observe the next real startup dependency.
