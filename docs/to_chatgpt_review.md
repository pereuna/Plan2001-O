## Boot Experiment C — 23 October 2026

**Verdict: Boot C PASS — a genuine O-resident ring-3 executable was
opened by PARTUUID and replaced into the first user process via
OEXECUTE, with no pathname activity.**

- Observed chain: embedded one-page loader -> `OVOLOPEN` (`ret=1`, exact
  generated `PARTUUID`) -> `OSPACEOPEN` (`h=1`) -> `OEXECUTE` for fixture
  OID `0x4f45584543000004` -> `execo`/`execcommit` -> new target.
- Kernel printed `OEXECUTE oid=0x4f45584543000004 len=2088 sum=3f
  ver=0x1`; the target is seeded verbatim at that OID, is not embedded in
  the kernel, and its host length/sum match. The target first checks the
  pre-exec O handle (`ospaceget`, syscall 56) and gets `-1`, then runs
  `alarm(0x42)` and sleeps in ring 3 (`cs=0x2b`, `ss=0x23`).
- `SYSCALL-RETURN nr=60 ret=<tos> text=obootctarget pc=0x200098`
  records the real post-exec register transition. Counters before and
  after exec: `userinit=proc0=init0=0`,
  `namec=newchan=walk=devwalk=mount=exec=0`.
- O handle lifecycle is explicit: `sysoexecute` drops its temporary
  handle and `execcommit` calls `oprocexec`/`odropall`; the target cannot
  reuse it.
- Negatives PASS: wrong PARTUUID gives `OVOLOPEN-ERROR`, no fallback,
  no `OSPACEOPEN`/`OEXECUTE`, userspace `alarm(0xbad)`; missing OID gives
  `OEXECUTE=-1`, the same handle still reads the 209-byte code object
  (`ret=0xd1`), then `alarm(0xbaf)`, with no target execution or panic.
- Controls PASS: Boot A probe, Boot B ring-3 probe, normal O/MicroPython
  three-boot gate, native pathless storage, native exec, argv and handle
  gates. `chandevreset`, `Pgrp`, GE/O worker kprocs, traps and
  `execo` execute; `namec`/`Chan`/`Dev` file ops/`devroot`/9P/`bind`/
  `mount`/path exec/`/boot`/console/Fgrp/Egrp/Rgrp/`slash`/`dot` do not.
- Source: `3374eb9` plus docs follow-up. Evidence:
  `docs/O-BOOT-EXPERIMENT-C.md`, `docs/STATUS.md`,
  `build/verification/test-oboot-oid-{experiment,positive,wrong,missing}-experiment-c.log`.

**Next step toward O-resident MicroPython (not implemented):** run the
same ring-3 `OEXECUTE` path with `OID_MP_EXEC` and the existing
`-O`/`-S init` argv, then add a direct serial-backed console/stdin/stdout
so `boot.py` and the REPL no longer need `/dev/cons`, `kbdfs` or an FD
console.

---

## Previous review note — Boot Experiment B

**Boot B PASS** — real amd64 ring-3 entry from an embedded flat image, no pathname/FD/bootstrap.

- `oboot=user`: `KERNEL-READY entry=0x200028 text=73 image=113 slash=nil dot=nil`; user CS/SS `0x2b/0x23`; `alarm` (nr 6) and `sleep` (nr 17) entry/return pairs with distinct user PCs proving post-return continuation.
- Counters zero before entry and after four syscalls: `userinit=0 proc0=0 init0=0`, `namec=newchan=walk=devwalk=mount=exec=0`.
- Controls PASS: Boot A probe, normal O/MicroPython three-boot gate, native pathless storage gate.
- Commits: `ba6b8ab`, `ddf9899`, docs `d526b01` (pushed). Evidence: `docs/O-BOOT-EXPERIMENT-B.md`, `build/verification/test-oboot-user-boot-experiment-b.log`. Optional malformed-image injection: NOT RUN (pre-entry validation exists).
- Residual: `kproc` `Pgrp` present but unused; `slash/dot/fgrp/egrp/rgrp` nil; `chandevreset` still ran (`rootreset`, `sdreset`).

**Earliest remaining legacy dependence:** none in the executed Boot B path. **Smallest next step (not implemented):** have this ring-3 process call existing `OVOLOPEN PARTUUID=`, `OSPACEOPEN`, and `OEXECUTE` over the native SD/GE/O provider; user-mode entry provides `up->dbgreg`, so `execo()`/`execregs()` needs no `namec`, `Chan`, `bind`, `mount`, or `/boot` lookup.
