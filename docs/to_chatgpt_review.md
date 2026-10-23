## Boot Experiment B — 23 October 2026

**Verdict: Boot B PASS — the first real amd64 ring-3 process ran from an
embedded flat image with no pathname/namespace bootstrap. This is not
Storage Level B.**

- Third opt-in branch `plan9.ini oboot=user` at `main()`. It creates one
  `kproc`, validates a 113-byte flat a.out image (entry `0x200028`,
  text 73, zero data/BSS), builds one user text page and a 16 MiB stack
  with a zeroed `Tos` page, sets `kp=0`, and enters via the existing
  `touser()` `SYSRET`.
- Observed: `KERNEL-READY pid=1 entry=0x200028 text=73 image=113
  slash=nil dot=nil`; `KERNEL-TO-USER pc=0x200028`; user syscalls
  `CS=0x2b SS=0x23 user=1`. `alarm` (`nr=6`) and `sleep` (`nr=17`)
  produced entry/return pairs; later user entries at distinct PCs prove
  user-mode continuation after return.
- Counters over the measured boot: `userinit=0 proc0=0 init0=0`;
  `namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0` both before user
  entry and after four user syscalls. No `Chan`, FD,
  `bind`/`mount`/`open`/`exec`, `/boot`, console or O storage.
- Residual state is reported: `kproc` still creates the process `Pgrp`;
  `slash/dot/fgrp/egrp/rgrp` are nil. `chandevreset` still ran
  (`rootreset` metadata, `sdreset` hardware probe); `chandevinit`,
  `alarm` and `closeproc` kprocs did not.
- Controls remain PASS: Boot A `oboot=probe` heartbeats,
  `tools/test-o-boot.sh` (three O-only MicroPython boots), and
  `tools/test-o-pathless.sh` (native storage Level A).
- Not claimed: Storage Level B, OID-resident executables, MicroPython,
  console/FD userspace, removal of `Dev`/`Chan`/`namec`, or a general
  loader. The optional malformed-image injection test is NOT RUN;
  pre-entry image validation exists.

**Earliest remaining legacy dependence:** none in the executed Boot B
path. For the next step (OID-resident executable), the smallest change
is to let this ring-3 process invoke the existing non-file
`OVOLOPEN PARTUUID=`, `OSPACEOPEN` and `OEXECUTE` syscalls over the
native SD/GE/O provider. Because the call originates in user mode,
`up->dbgreg` already exists for `execo()`/`execregs()`; no pathname,
`Chan`, `bind`, `mount` or `/boot` lookup is needed. Not implemented
here.

Source: `ba6b8ab` + `ddf9899` plus this docs follow-up. Evidence:
`docs/O-BOOT-EXPERIMENT-B.md`, `docs/STATUS.md`,
`build/verification/test-oboot-user-experiment-b.log`,
`build/verification/test-oboot-user-boot-experiment-b.log`,
`build/verification/test-oboot-probe-experiment-b.log`,
`build/verification/test-o-boot-experiment-b.log`,
`build/verification/test-o-pathless-experiment-b.log`.

---

## Previous review note — Boot Experiment A

**Boot Experiment A: PASS** (kernel-only probe; Storage Level A untouched).

- Implementation: `6c6e112`; docs: `235ad0d` (pushed to `main`).
- Probe boot: `oboot=probe` → `pid=1 slash=nil dot=nil`, `userinit/proc0/init0=0`, `namec/newchan/walk/devwalk/mount/exec=0`, then two post-scheduler heartbeats.
- Normal O boot gate PASS (`run()` 1→2→3); positive control showed real legacy counts (`namec=38 … exec=1`).
- Residuals reported: `kproc` still creates a `Pgrp`; `chandevreset` (`rootreset`, `sdreset`, other reset hooks) ran before the branch; `chandevinit`/`alarm`/`closeproc` did not.
- Logs: `build/verification/test-oboot-probe-experiment-a.log`, `test-o-boot-experiment-a.log`, `test-o-pathless-experiment-a.log`; report: `docs/O-BOOT-EXPERIMENT-A.md`.
- Note: `WHAT=kernel` alone failed because this tree's bootdir references `ohandle`/`oexec`; the successful build used `WHAT=all`.

**Next boundary (answer only):** keep this branch, but construct a user process from bytes already available to the kernel (embedded/native-O), reuse `execo`/`oexecute` segment setup and `touser`, and omit `proc0`'s `namec("#/")`/`cclone` plus all `bind`/`open`/`mount`/path-`exec`.
