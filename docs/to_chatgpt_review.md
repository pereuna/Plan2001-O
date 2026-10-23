## Boot Experiment A — 23 October 2026

**Verdict: PASS — a kernel-only first task ran after scheduling without
the legacy user bootstrap. This is a boot-boundary result only.**

- Opt-in `plan9.ini oboot=probe` branches at the existing `main()`
  handoff from `userinit()` to `ouserinit()`. The latter creates one
  minimal `kproc`; the generic `kproc`/`schedinit`/driver code and the
  normal `userinit`/`proc0`/`init0` code are unchanged apart from
  counters.
- Measured probe transcript: `KPROC-RUNNING pid=1 slash=nil dot=nil`,
  `legacy-calls userinit=0 proc0=0 init0=0`,
  `path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`,
  followed by two post-scheduler heartbeats. The task then sleeps.
- Positive control on the normal boot: `namec=38 newchan=110 walk=57
  devwalk=82 mount=7 exec=1`. The zero probe counts are therefore a
  real bypass, not dead instrumentation.
- The normal O boot still passes three O-only boots and reaches
  O-resident MicroPython (`run()` 1 -> 2 -> 3); no `OBOOT-A` marker
  appears without the option.
- Residual effects are reported honestly: `kproc` still creates a
  `Pgrp`; `chandevreset` still runs `rootreset` and hardware reset hooks
  (including `sdreset`) before the branch. `chandevinit`, the `alarm`
  and `closeproc` kprocs, `slash`/`dot`, path lookup, mount and path
  exec are absent from the probe path. This does **not** prove zero
  filesystem-related kernel code anywhere.
- Not claimed: pathless GE/O access, native OID persistence, pathless
  executables or MicroPython, or removal of `Chan`/`namec`/`devroot`.
  Storage Level A remains a separate PASS from the earlier work.

**Smallest next boot-boundary change (answer only, not implemented):**
keep this branch and create a *user* process whose text/stack image comes
from bytes already available to the kernel (an embedded or native-O
buffer), reusing the existing `execo`/`oexecute` segment construction and
`touser` entry, while omitting `proc0`'s `namec("#/")`/`cclone` and all
`bind`/`open`/`mount`/path-`exec`. That separates image construction plus
user entry from pathname initialization without changing `initcode.c` or
the one-page bootstrap image. Console/stdin remains a later boundary.

Source: `6c6e112efb201bd5d927e3276877714d56c1a92f` plus this docs
follow-up. Evidence: `docs/O-BOOT-EXPERIMENT-A.md`, `docs/STATUS.md`,
`build/verification/test-oboot-probe-experiment-a.log`,
`build/verification/test-o-boot-experiment-a.log`,
`build/verification/test-o-pathless-experiment-a.log`.

---

## Previous review note — Storage Level A

**Verdict: A PASS; B/C NOT YET.**

- Implemented pathless Level A O storage: direct SD unit iteration/GPT discovery, partition-relative block I/O, GE sync, and driver flush without `namec`/kernel `Chan`.
- Instrumented window measured zero added events on all three boots: `namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1` unchanged across open/GE start. `sdvirtio: flush PASS` and all `oblocktest` bounds checks passed.
- B remains blocked by `initcode.c:startboot` bind/open/path-exec and the one-page initcode limit; C by `boot.py`/`p9console.c` console and fd/namespace dependencies.
- All required gates pass, including `test-o-pathless`, `test-o-register`, `test-o-bytefile`, and the nine existing O-only gates.

Commits pushed: `e384300` (implementation), `1229bca` (documentation). Full evidence: `docs/O-BOOT-DEPENDENCIES.md`, `docs/STATUS.md`, `build/verification/test-o-pathless-final.log`.
