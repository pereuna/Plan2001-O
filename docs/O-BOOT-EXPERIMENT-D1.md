# Boot Experiment D1: O-resident MicroPython entry and first blocker

**Date:** 23 October 2026. **Source state:** implementation commit
`4d1d75f969e2fd4ed35247af43bbfac1c33393cb`, plus this documentation
follow-up. Runtime evidence below was produced from that committed
source with the normal amd64 `WHAT=all` build, a clean
`tools/selfroot`, and disposable QEMU images.

## Verdict

```text
D1 EXEC PASS
D1 STARTUP highest proven milestone =
    real MicroPython entry + mp_init/main reached + p9_space_o's
    OVOLOPEN completed; MicroPython's first fd-2 diagnostic write then
    faults the kernel because the process has no Fgrp.
FIRST LEGACY DEPENDENCY =
    PWRITE (syscall 51) fd 2, user PC 0x279db4, from
    p9space.c:366 fprint("space: O volume selected")
    -> libc write.c:7 pwrite
    -> kernel sysfile.c:145/147 fdtochan: f = up->fgrp (nil); lock(f)
    -> kernel fault write addr=0x8, panic.
```

This is **D1 diagnostic success**, not a working MicroPython boot. The
O-resident interpreter is entered for real and runs long enough to
complete `mp_init` and the second `ovolopen` inside `p9_space_o`; it then
needs an inherited file-descriptor facility for its first `fprint(2, ...)`
and the kernel panics before `boot.py`.

This is not the older top-down **Storage Level B/C**, not a console
implementation, and not a claim of a pathless MicroPython REPL.

## Executed call graph

```text
UEFI loader
  -> main.c:main, bootargsinit (oboot=mp, obootvol=PARTUUID=...)
  -> normal kernel init, procinit0, initseg, links, chandevreset, pageinit
  -> o_user_bootstrap                         main.c:286-288, ouser.c
  -> kproc("*ouser*"), schedinit / sched
  -> ouserproc: embedded one-page loader, Oargs on user stack
  -> otouser -> ring 3 at 0x200028            cs=0x2b, ss=0x23
       OVOLOPEN(obootvol)                     syscall 54
       OSPACEOPEN(1, "init", 4)               syscall 55
       OEXECUTE(OID_MP_EXEC, six args)         syscall 60
  -> sysoexecute -> onativeget via native GE/O/SD
  -> execo / execcommit / execregs
  -> real MicroPython entry at 0x275abc       text=micropython
       p9_space_o -> OVOLOPEN(PARTUUID=...)   syscall 54, ret 1
       fprint(2, "space: O volume selected") syscall 51 PWRITE fd 2
       kernel fdtochan: up->fgrp == nil
       kernel fault/panic: write addr=0x8
```

The initial loader and the O-resident interpreter remain distinct:

* loader image: `obootoid`, 494 bytes, text 454, embedded in the kernel;
* MicroPython: 2,194,156 bytes, seeded unchanged at `OID_MP_EXEC =
  0x4f45584543000003`, executed only from the disposable O volume.

## Six-argument contract

The kernel passes the exact existing `oinit.c:argvec` form:

```text
argc = 6
argv[0] = "micropython"
argv[1] = "-O"
argv[2] = "PARTUUID=<fresh GUID>"
argv[3] = "-S"
argv[4] = "init"
argv[5] = "-B"
argv[6] = nil
```

The strings live in the `Oargs` block on the first user stack, are copied
by `oexecute` through its bounded `execargcopy` path, and survive until
the syscall copies them. The observed kernel marker is:

```text
OBOOT-D1: ARGV argc=6 <micropython> <-O> <PARTUUID=45c2b8ec-...> <-S> <init> <-B>
```

The C experiment's fixed OID `0x4f45584543000004` and one-argument
contract are unchanged; D1 selects `OID_MP_EXEC` and the six arguments
only under `oboot=mp`.

## Byte provenance

The host `build/selfroot/amd64/bin/micropython` is unchanged:

```text
length = 2,194,156 bytes
sha256 = 41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc
```

`tools/mkovol` seeded that byte sequence with its normal default
MicroPython path. The seed log records:

```text
seed: mpexec 2194156 4f45584543000003 41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc unchanged
seed: object mp oid=0x4f45584543000003 len=2194156
```

The kernel independently hashes the bytes returned by `onativeget` and
prints the same digest before `execo`:

```text
OBOOT-D1: OEXECUTE oid=0x4f45584543000003 len=2194156 sha256=41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc ver=0x1
```

Thus the interpreter is not embedded in the kernel and is not a
substitute fixture. The `RAWEXEC`/`NATIVEEXEC` OIDs are not used for D1.

## Phase table

| Milestone | Status | Evidence |
| --- | --- | --- |
| UEFI -> kernel/scheduler -> embedded loader | **REACHED** | `OBOOT-D1: KERNEL-TO-USER ...` |
| First user-mode loader entry | **REACHED** | `*ouser*` syscalls at `cs=0x2b ss=0x23`; `OVOLOPEN` ret 1; `OSPACEOPEN` h=1 |
| `OEXECUTE(OID_MP_EXEC)` | **REACHED** | `OEXECUTE ... len=2194156 sha256=4115...`; return `text=micropython pc=0x275abc` |
| MicroPython entry / libc startup | **REACHED** | post-exec `Ureg` PC `0x275abc`, `text=micropython` |
| `main` reached | **REACHED** | `p9_space_o`'s `OVOLOPEN` syscall follows entry; source order `main.c:168 -> :169` |
| `mp_init` completed | **REACHED** (source order + observed next call) | `p9_space_o` is called only after `mp_init`; its `OVOLOPEN` is observed |
| `p9_space_o` entered | **REACHED** | MicroPython-originated syscall 54 at PC `0x281060`, ret 1 |
| `p9_space_o` completed | **NOT REACHED** | first `fprint(2, ...)` follows the `OVOLOPEN`; no return/next stage observed |
| `boot.py` entered | **NOT REACHED** | depends on `p9_space_o` returning; it does not |
| `space.open('init')` | **NOT REACHED** | after `boot.py` in `main.c:177-181` |
| `p9_space_boot` / run() / commit | **NOT REACHED** | later stages |

The earliest stop is therefore **before** the expected `boot.py` device
bindings and before `p9_console.c`; that is an observed fact, not an
inference from file order.

## First inherited dependency

The first user-originated inherited-facility request is:

```text
OBOOT-D1: SYSCALL-ENTRY pid=1 nr=51 arg0=0x2 text=micropython pc=0x279db4 ...
fault: nlocks 1, proc 1 micropython, addr 0x8, lock 0xffffffff802fb318 ...
panic: kernel fault: write addr=0x8
```

`nr=51` is `PWRITE`; `arg0=0x2` is fd 2. Source:

* `sys/src/cmd/micropython/p9space.c:366`:
  `fprint(2, "space: O volume selected: %s\n", spec);`
* `sys/src/libc/9sys/write.c:7`: `pwrite(fd, buf, n, -1LL)`.
* `sys/src/9/port/sysfile.c:762`: `fdtochan(fd, OWRITE, 1, 1)`.
* `sys/src/9/port/sysfile.c:145-147`:
  `f = up->fgrp; lock(f);` with `up->fgrp == nil`.

The kernel does not return `EBADF` here; it faults on the nil `Fgrp`.
This is the first legacy dependency: a process-local file-descriptor
table (at minimum fd 2, or an equivalent bounded diagnostic sink), not a
pathname lookup. `OBOOT-D1` sent the write attempt; no `namec`, `Chan`,
walk, mount or path `exec` was entered.

The preceding D1 prefix has no path activity:

```text
OBOOT-D1: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-D1: AFTER-SYSCALLS n=4 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
```

The `AFTER-SYSCALLS` checkpoint is after the loader's three O calls and
MicroPython's second `OVOLOPEN` (post-exec). It is cumulative, not reset.
The imprecise phrase "path counters are zero" does not mean no file
operation was attempted: the `PWRITE` attempt fails before `namec`
because the missing FD table is detected first.

## Negative case

A fresh O image made with `NOMPEXEC=1` has no `OID_MP_EXEC`. The loader's
`OEXECUTE` returns `-1`; the same handle still queries the existing
209-byte code object (`OSPACEGET` nr 56, ret `0xd1`), proving the handle
survived, and the loader reports `alarm(0xbaf)`. `text=micropython` never
appears and there is no panic. This is a normal negative, not a crash.

Log: `build/verification/test-oboot-mp-missing-experiment-d1.log`.

## Commands and results

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-d1.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-d1.log
tools/test-oboot-mp.sh 2>&1 | tee build/verification/test-oboot-mp-experiment-d1.log
```

Build: **PASS**, `BUILD-DONE`; normal `9pc64` md5
`7b5e22d1816371a131849ea0aa308740`, test-only `9pc64mp` md5
`0a79d3513f1c071507e812486113836e`. Selfroot: **PASS**, clean at
`4d1d75f`; MicroPython SHA unchanged. D1 gate: **PASS**,
`PASS: D1 EXEC, OID_MP_EXEC image transition and first-dependency diagnosis`.
Positive serial log:
`build/verification/test-oboot-mp-pos-experiment-d1.log`; seed log:
`build/verification/test-oboot-mp-mkovol-experiment-d1.log`.

### Controls

| Control | Command | Result | Log |
| --- | --- | --- | --- |
| Boot A | `oboot=probe` disposable boot | **PASS**: heartbeats, zero legacy/path counters | `build/verification/test-oboot-probe-experiment-d1.log` |
| Boot B | `tools/test-oboot-user.sh` | **PASS** | `build/verification/test-oboot-user-experiment-d1.log` |
| Boot C | `tools/test-oboot-oid.sh` | **PASS** | `build/verification/test-oboot-oid-experiment-d1.log` |
| Normal O boot | `tools/test-o-boot.sh` | **PASS**: three O-only boots, `run()` 1 -> 2 -> 3 | `build/verification/test-o-boot-experiment-d1.log` |
| Native O storage | `tools/test-o-pathless.sh` | **PASS** | `build/verification/test-o-pathless-experiment-d1.log` |
| Native exec | `tools/test-o-exec.sh` | **PASS** | `build/verification/test-o-exec-experiment-d1.log` |
| Native argv | `tools/test-o-exec-args.sh` | **PASS** | `build/verification/test-o-exec-args-experiment-d1.log` |
| O handles | `tools/test-o-handles.sh` | **PASS** | `build/verification/test-o-handles-experiment-d1.log` |

The `test-o-pathless` negative cases retain their documented expected
`panic: boot process died: fail` diagnostic; the gate exits 0.

## Why this is not D2

D1 did **not** add a console, a UART reader/writer, FD emulation,
`/dev/cons`, `kbdfs`, a Python `plan9` API change, a fake tree mount, a
`namec`/`Chan` removal, or a graph change. The kernel panic is reported,
not suppressed. The interpreter and `boot.py` are unchanged. The next
work is D2: provide the smallest process-local FD/console facility needed
to get past the first `PWRITE` and expose the next actual dependency.

## Limits

* The observed blocker is MicroPython's **diagnostic** `fprint(2, ...)`
  before `boot.py`; a working D2 console may need more than fd 2, but D1
  does not claim to know the next blocker.
* The process has the `Pgrp` created by `kproc`; `slash`, `dot`, `fgrp`,
  `egrp` and `rgrp` are nil. `chandevreset`, GE/O worker kprocs, the
  native disk path, traps, `execo`/`execcommit`, `execregs` and
  `oprocexec` execute; pathname/console code remains linked but unused.
* No persistence, Python Environment, interactive REPL, commit or space
  restore is reached.
