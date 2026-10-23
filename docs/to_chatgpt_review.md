**Boot Experiment A: PASS** (kernel-only probe; Storage Level A untouched).

- Implementation: `6c6e112`; docs: `235ad0d` (pushed to `main`).
- Probe boot: `oboot=probe` → `pid=1 slash=nil dot=nil`, `userinit/proc0/init0=0`, `namec/newchan/walk/devwalk/mount/exec=0`, then two post-scheduler heartbeats.
- Normal O boot gate PASS (`run()` 1→2→3); positive control showed real legacy counts (`namec=38 … exec=1`).
- Residuals reported: `kproc` still creates a `Pgrp`; `chandevreset` (`rootreset`, `sdreset`, other reset hooks) ran before the branch; `chandevinit`/`alarm`/`closeproc` did not.
- Logs: `build/verification/test-oboot-probe-experiment-a.log`, `test-o-boot-experiment-a.log`, `test-o-pathless-experiment-a.log`; report: `docs/O-BOOT-EXPERIMENT-A.md`.
- Note: `WHAT=kernel` alone failed because this tree's bootdir references `ohandle`/`oexec`; the successful build used `WHAT=all`.

**Next boundary (answer only):** keep this branch, but construct a user process from bytes already available to the kernel (embedded/native-O), reuse `execo`/`oexecute` segment setup and `touser`, and omit `proc0`'s `namec("#/")`/`cclone` plus all `bind`/`open`/`mount`/path-`exec`.
