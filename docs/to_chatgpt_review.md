## Boot Experiment D1 — 23 October 2026

**`D1 EXEC PASS` / `D1 STARTUP highest proven milestone = MicroPython
main + mp_init completed; p9_space_o entered and its native OVOLOPEN
completed; boot.py NOT REACHED`.**
`FIRST LEGACY DEPENDENCY = PWRITE (nr 51) fd 2 from p9space.c:366
fprint("space: O volume selected") -> fdtochan lock(nil up->fgrp) ->
kernel fault write addr=0x8, panic.`

- The unchanged O-resident MicroPython is entered by `OEXECUTE`:
  `oid=0x4f45584543000003 len=2194156 sha256=411570... ver=0x1`;
  post-exec `text=micropython pc=0x275abc cs=0x2b ss=0x23`. Host,
  mkovol seed and kernel-read SHA-256 agree; `OID_MP_EXEC` bytes are
  unchanged. The six-argument contract is exactly
  `micropython -O PARTUUID=<fresh> -S init -B`.
- MicroPython then executes a second native `OVOLOPEN` inside
  `p9_space_o` (nr 54, ret 1, PC `0x281060`), so `main`/`mp_init` are
  reached. Its first `fprint(2, ...)` produces `PWRITE` nr 51, arg0=2,
  PC `0x279db4`; `up->fgrp` is nil, so `fdtochan` (`sysfile.c:145-147`)
  faults and the kernel panics. `boot.py`, `space.open('init')`,
  `p9_space_boot`, run() and commit are **NOT REACHED**.
- Prefix counters are zero and remain zero at `AFTER-SYSCALLS n=4`:
  `userinit=proc0=init0=0`, `namec=newchan=walk=devwalk=mount=exec=0`.
  The PWRITE attempt is still reported explicitly; zero path counters do
  not mean no file operation was attempted.
- Negative: with `NOMPEXEC=1`, `OEXECUTE` returns `-1`, the same handle
  still reads the 209-byte code object (`OSPACEGET` ret `0xd1`), the
  loader reports `alarm(0xbaf)`, no `micropython` text and no panic.
- Controls PASS: Boot A, B, C, normal O/MicroPython three-boot gate,
  pathless storage, native exec, argv and handles.
- Source `4d1d75f` plus docs follow-up. Evidence:
  `docs/O-BOOT-EXPERIMENT-D1.md`, `docs/STATUS.md`,
  `build/verification/test-oboot-mp-experiment-d1.log`,
  `build/verification/test-oboot-mp-pos-experiment-d1.log`,
  `build/verification/test-oboot-mp-missing-experiment-d1.log`.

**`NEXT D2 EXPERIMENT =` provide the smallest process-local FD/console
facility that lets MicroPython's fd-2 diagnostic write return normally
without `/dev/cons` or `kbdfs`, then observe the next real startup
dependency. This is a diagnostic boundary, not a D2 implementation.**

---

## Previous review note — Boot Experiment C

**Boot C PASS** — the first ring-3 process opened a generated `PARTUUID=` O volume, loaded a genuinely O-resident executable via `OEXECUTE`, and ran it after the image transition.

- Chain: embedded loader → `OVOLOPEN` (ret 1, exact GUID) → `OSPACEOPEN` (`h=1`) → `OEXECUTE` OID `0x4f45584543000004` (`len=2088 sum=3f ver=0x1`) → `execo`/`execcommit` → target.
- Post-exec proof: `SYSCALL-RETURN nr=60 ... text=obootctarget pc=0x200098 cs=0x2b ss=0x23`; target then gets `ospaceget` → `-1` (old handle gone), `alarm(0x42)`, `sleep(0x1234)`, `sleep(0x5678)`.
- Counters before and after exec: `userinit=proc0=init0=0`; `namec=newchan=walk=devwalk=mount=exec=0`.
- Negatives PASS: wrong GUID fails at `OVOLOPEN` with no fallback; missing OID returns `-1`, handle survives (`ospaceget` returns 209 bytes), target never runs, no panic.
- Controls PASS: Boot A, Boot B, normal O/MicroPython, pathless storage, native exec, argv, handles.
- Commits: `3374eb9` (implementation), `5e3683e` (docs), pushed. Evidence: `docs/O-BOOT-EXPERIMENT-C.md`, `build/verification/test-oboot-oid-*.log`.

**Must execute:** scheduler/`Proc`/`Pgrp`, timers, `chandevreset`, GE/O worker kprocs and native SD block reads, trap/syscall path, `otouser`, `execo`/`execcommit`/`execregs`, `oprocexec`, segment/page allocation. **Linked/initialized only:** `namec`, `Chan`, `Dev` file operations, `devroot`, 9P, `bind`/`mount`/path `exec`, `/boot`, `Fgrp`/`Egrp`/`Rgrp`, `slash`/`dot`, console, and the legacy `userinit`/`proc0`/`init0`/`initcode` chain.

**Next step (not implemented):** point the same ring-3 `OEXECUTE` path at `OID_MP_EXEC` with the existing `-O`/`-S init` argv and add a direct serial-backed console/stdin/stdout so `boot.py` and the REPL no longer depend on `/dev/cons`, `kbdfs`, or an FD console.
