**Boot B PASS** — real amd64 ring-3 entry from an embedded flat image, no pathname/FD/bootstrap.

- `oboot=user`: `KERNEL-READY entry=0x200028 text=73 image=113 slash=nil dot=nil`; user CS/SS `0x2b/0x23`; `alarm` (nr 6) and `sleep` (nr 17) entry/return pairs with distinct user PCs proving post-return continuation.
- Counters zero before entry and after four syscalls: `userinit=0 proc0=0 init0=0`, `namec=newchan=walk=devwalk=mount=exec=0`.
- Controls PASS: Boot A probe, normal O/MicroPython three-boot gate, native pathless storage gate.
- Commits: `ba6b8ab`, `ddf9899`, docs `d526b01` (pushed). Evidence: `docs/O-BOOT-EXPERIMENT-B.md`, `build/verification/test-oboot-user-boot-experiment-b.log`. Optional malformed-image injection: NOT RUN (pre-entry validation exists).
- Residual: `kproc` `Pgrp` present but unused; `slash/dot/fgrp/egrp/rgrp` nil; `chandevreset` still ran (`rootreset`, `sdreset`).

**Earliest remaining legacy dependence:** none in the executed Boot B path. **Smallest next step (not implemented):** have this ring-3 process call existing `OVOLOPEN PARTUUID=`, `OSPACEOPEN`, and `OEXECUTE` over the native SD/GE/O provider; user-mode entry provides `up->dbgreg`, so `execo()`/`execregs()` needs no `namec`, `Chan`, `bind`, `mount`, or `/boot` lookup.
