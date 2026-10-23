# Boot Experiment C: ring-3 OID executable over native O, no pathname

**Date:** 23 October 2026. **Source state:** implementation commit
`3374eb954638bae08131ac9099bf09f8e7c923ca`, plus this documentation
follow-up. Runtime evidence below was produced from that committed
source with the normal amd64 `WHAT=all` build, a clean
`tools/selfroot`, and disposable QEMU images.

**Verdict: Boot C PASS.** The observed chain is:

```text
UEFI -> native kernel/scheduler -> embedded minimal user loader
     -> OVOLOPEN(PARTUUID=...) -> OSPACEOPEN(1, "init")
     -> OEXECUTE(OID 0x4f45584543000004)
     -> new ring-3 executable image from the disposable O volume
     -> post-exec user syscalls and successful returns
```

No runtime pathname lookup, `Chan`, `/boot`, `bind`, `mount`, path
`exec`, filesystem or FD-backed console is used. This is **Boot
Experiment C**; it is not the older top-down **Storage Level C** and it
does not execute MicroPython or a Python Environment.

## What was combined

| Source | What it contributes |
| --- | --- |
| Boot Experiment B (`ba6b8ab` + `ddf9899`) | A real ring-3 first process from an embedded flat image, with `userinit/proc0/init0/startboot` absent and zero path counters. |
| Storage Level A (`e384300`) | `PARTUUID=` discovery directly from enumerated SD units, partition-relative `sdblockrw`, GE sync and driver flush without `namec`/`Chan`. |
| Boot Experiment C | The Boot-B process calls the existing user native-O syscalls and replaces itself, via `OEXECUTE`/`execo`, with a genuine O-resident executable. |

## Executed call graph

```text
UEFI loader
  -> main.c:main, bootargsinit
  -> normal machine/memory/trap/clock/PCI/APIC/timer/page initialization
  -> procinit0, initseg, links
  -> chandevreset (device reset hooks only)
  -> preallocpages, pageinit
  -> o_user_bootstrap                         main.c:279-281, ouser.c:230
  -> kproc("*ouser*", ouserproc)
  -> schedinit / sched
  -> ouserproc                                ouser.c:121
       choose embedded obootoid image
       ouserimage validation
       user text page + 16 MiB stack + zeroed Tos page
       Oargs block on the user stack (volume spec, Space name, OID, target name)
  -> otouser(sp, arg)                         l.s:873, SYSRET
  -> embedded loader at 0x200028              cs=0x2b, ss=0x23
       ovolopen(spec, len)                    syscall 54
       ospaceopen(1, "init", 4)               syscall 55
       oexecute(h, OID, argv, 1)              syscall 60
  -> sysoexecute -> onativeget -> execo       devgefs.c:964, sysproc.c:494
       object read through the native O volume/GE/SD path
       execparse / segments / execcommit
       oprocexec drops the old process-local O handles
       execregs modifies the live user syscall Ureg
  -> new O-resident target at its own entry
       ospaceget(1, OID, ...) -> -1           old handle is gone
       alarm(0x42), sleep(0x1234), sleep(0x5678)
```

The original embedded loader and the O-resident target are distinct:

* loader image: `obootoid`, 403 bytes, text 363, embedded in the kernel;
* target image: `obootctarget`, 2,088 bytes, seeded only in the
  disposable O image, entry exercised after `OEXECUTE`.

## PARTUUID and OID handoff

`tools/gefsdisk` generates a fresh GPT GUID for every image. The test
therefore passes `obootvol=PARTUUID=@PARTUUID@` in `INI`; the tool now
substitutes `@PARTUUID@` in arbitrary `INI` lines as well as in `INIT=`
(the substitution is backward compatible and the saved `plan9.ini` is
checked by the gate). The kernel reads the bounded
`getconf("obootvol")` value and copies it into an `Oargs` structure on
the first user stack page. `otouser` delivers a pointer to that block in
BP, so the embedded loader reads the exact generated PARTUUID without a
file or a global data segment.

The target OID is the fixed fixture value:

```text
0x4f45584543000004
```

It is not a universal catalog or allocator contract.

## Byte provenance

`sys/src/cmd/obootctarget/obootctarget.c` is compiled by the ordinary
amd64 tools and installed as `obootctarget`. The host gate computes the
file length and an 8-bit byte sum. `tools/mkovol RAWEXEC=FILE` passes the
file to the build VM; `tools/oseed.py` copies it to `seed/rawexec`,
reads that copy back to verify it is unchanged, and writes
`seed/rawexecoid` with the fixed OID. `sys/src/cmd/gefs/ream.c` seeds
`rawexec`/`rawexecoid` as ordinary O records. No header patch is applied
to this raw path; the legacy `NATIVEEXEC` behavior is untouched.

For the recorded target:

```text
length    = 2088 bytes
byte sum  = 0x3f (8-bit wrapping sum)
OID       = 0x4f45584543000004
```

The kernel prints the length and checksum of the bytes actually read by
`onativeget`, before `execo`:

```text
OBOOT-C: OEXECUTE oid=0x4f45584543000004 len=2088 sum=3f ver=0x1
```

These match the host target and the seed log, which independently shows
`seed: rawexec 2088 4f45584543000004 ... unchanged`. The target is not
embedded in the kernel.

## Privilege and register transition

`otouser` is a narrow variant of the established `touser`: it performs
`SWAPGS`, clears the kernel scratch registers, loads the fixed user text
entry `UTZERO+0x28`, sets `IF`, switches to the supplied user stack and
delivers the initial argument pointer in BP through `SYSRETQ`.

The first observed user syscalls and the post-exec transition:

```text
OBOOT-C: SYSCALL-ENTRY ... nr=54 ... text=*ouser* pc=0x200156 cs=0x2b ss=0x23 user=1
OBOOT-C: SYSCALL-ENTRY ... nr=55 ... text=*ouser* pc=0x200165 cs=0x2b ss=0x23 user=1
OBOOT-C: SYSCALL-ENTRY ... nr=60 ... text=*ouser* pc=0x200183 cs=0x2b ss=0x23 user=1
OBOOT-C: OEXECUTE oid=0x4f45584543000004 len=2088 sum=3f ver=0x1
OBOOT-C: SYSCALL-RETURN ... nr=60 ret=0x7fffffffefb8 text=obootctarget pc=0x200098 cs=0x2b ss=0x23 user=1
OBOOT-C: SYSCALL-ENTRY ... nr=56 arg0=0x1 text=obootctarget pc=0x2001a1 cs=0x2b ss=0x23 user=1
OBOOT-C: SYSCALL-RETURN ... nr=56 ret=0xffffffffffffffff text=obootctarget ...
OBOOT-C: SYSCALL-ENTRY ... nr=6 arg0=0x42 text=obootctarget pc=0x2001b0 ...
OBOOT-C: SYSCALL-RETURN ... nr=6 ret=0x0 text=obootctarget ...
OBOOT-C: SYSCALL-ENTRY ... nr=17 arg0=0x1234 text=obootctarget pc=0x200192 ...
OBOOT-C: SYSCALL-RETURN ... nr=17 ret=0x0 text=obootctarget ...
OBOOT-C: SYSCALL-ENTRY ... nr=17 arg0=0x5678 text=obootctarget pc=0x200192 ...
```

The `OEXECUTE` syscall returns through the modified `Ureg` with
`text=obootctarget` and a new user PC. The next syscall is from the
target and checks OID handle isolation; the subsequent target
`alarm(0x42)` and sleeps are distinct from the loader's `alarm(0)` and
`sleep(100)`. All observed user records have `cs=0x2b`, `ss=0x23` and
`user=1`.

## Counters and residual structures

The measured boot printed, both before user entry and after the fourth
user syscall (which is post-exec):

```text
OBOOT-C: legacy-calls userinit=0 proc0=0 init0=0
OBOOT-C: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-C: AFTER-SYSCALLS legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
```

No counter is reset.

Inherited structures that **must actually execute** on this path:

* `Proc`/scheduler, `Pgrp` created by `kproc`, kernel stacks and timers;
* `chandevreset` and device reset hooks (`rootreset` metadata,
  `sdreset` probing the SATA/virtio disk);
* GE/O engine and its worker kprocs started by `gestart`, GE/SD block
  reads through `oblockopenpart`/`sdblockrw`;
* trap/syscall entry, `touser`/`otouser`, `execo`/`execcommit`,
  `execregs`, `oprocexec`, segment/page allocation and `flushmmu`.

Structures that remain **linked and/or initialized but are not
executed** on the measured path:

* `namec`, `Chan`, `Dev` open/read/write, `devroot` path lookup, 9P,
  `bind`, `mount`, `/boot` and path `exec`;
* `userinit`, `proc0`, `init0`, `initcode`, `startboot`;
* `Fgrp`, `Egrp`, `Rgrp`, `slash`, `dot` and the console.

The process has the `Pgrp` supplied by `kproc`; `slash`, `dot`, `fgrp`,
`egrp` and `rgrp` are explicitly nil. The top stack page, including the
`Tos` slot, is zeroed. The O handle is not inherited: `sysoexecute`
drops its temporary reference before `execo`, and `execcommit` calls
`oprocexec(up)` -> `odropall`. The target's `ospaceget(1, OID, ...)`
therefore returns `-1`.

## Negative cases

**Wrong PARTUUID** (same O image, deliberately wrong `obootvol`):
`OVOLOPEN` errors with `no disk has that partition`, returns `-1`, no
`OSPACEOPEN`/`OEXECUTE` follows, the loader reports failure through
`alarm(0xbad)`, and no filesystem fallback occurs. The path counters
remain zero and there is no panic.

**Missing target OID** (a fresh O image with no `RAWEXEC`): volume and
`init` Space open normally, `OEXECUTE` returns `-1`, the loader queries
the existing code OID (`0xd1` = 209 bytes) through the same handle, which
proves the handle survived the failed load, then reports through
`alarm(0xbaf)`. The target never runs and there is no panic.

Logs: `build/verification/test-oboot-oid-positive-experiment-c.log`,
`test-oboot-oid-wrong-experiment-c.log`,
`test-oboot-oid-missing-experiment-c.log`.

## Commands and results

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-c.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-c.log
tools/test-oboot-oid.sh 2>&1 | tee build/verification/test-oboot-oid-experiment-c.log
```

Build: **PASS**, `BUILD-DONE`; normal `9pc64` md5
`11ca7cbf07f93484188df1f3456e60a1`, test-only `9pc64mp` md5
`46f782940da530a7e4f7d16285fad43f`. Selfroot was prepared from the
committed source `3374eb9`. Boot C gate: **PASS**,
`PASS: Boot Experiment C OID executable over native O, post-exec syscalls and negatives`.

### Controls

| Control | Command | Result | Log |
| --- | --- | --- | --- |
| Boot A | disposable `oboot=probe` boot | **PASS**: two heartbeats, legacy/path counters zero | `build/verification/test-oboot-probe-experiment-c.log` |
| Boot B | `tools/test-oboot-user.sh` | **PASS**: ring-3 `alarm`/`sleep` round trips | `build/verification/test-oboot-user-experiment-c.log` |
| Normal O boot | `tools/test-o-boot.sh` | **PASS**: three O-only boots, `run()` 1 -> 2 -> 3 | `build/verification/test-o-boot-experiment-c.log` |
| Native O storage | `tools/test-o-pathless.sh` | **PASS**: Level A pathless native storage | `build/verification/test-o-pathless-experiment-c.log` |
| Native exec | `tools/test-o-exec.sh` | **PASS**: O executable, rollback | `build/verification/test-o-exec-experiment-c.log` |
| Native argv | `tools/test-o-exec-args.sh` | **PASS**: argv bounds, rollback, race | `build/verification/test-o-exec-args-experiment-c.log` |
| O handles | `tools/test-o-handles.sh` | **PASS**: isolation, exec release, rollback | `build/verification/test-o-handles-experiment-c.log` |

The negative `test-o-pathless` transcript keeps its documented
expected `panic: boot process died: fail` diagnostic for deliberately
missing partitions; the gate itself exits 0 and is **PASS**.

## Limitations

* The target is a small non-file program with no console, FD, Python,
  Environment, shared library or general program catalog. It uses normal
  libc startup and has its own data/BSS, which `execo` handles.
* The initial loader is one page and has no data/BSS. The target OID and
  target name are fixed fixture values; the PARTUUID is passed from
  `plan9.ini`.
* There is one active native O volume and one process-local Space
  handle. No multi-volume, remote, permission or allocator work is
  added.
* `chandevreset` still runs before the branch. `Dev`, `Chan`, `namec`,
  `devroot`, GE/O and the legacy bootstrap remain linked; only the
  listed structures execute.
* This is not **Storage Level B** or **Storage Level C**: MicroPython,
  the Python Environment, imports and the interactive console are not
  loaded or exercised.

## Conclusion

**Boot C PASS.**

On this path the inherited Plan 9 structures that must actually run are
the scheduler/`Proc`/`Pgrp`, timers, device reset hooks, the GE/O engine
and its native SD block reads, traps/syscalls, the `touser`/`otouser`
ring transition, `execo`/`execcommit`/`execregs`, `oprocexec`, and the
segment/page machinery. `namec`, `Chan`, `Dev` file operations,
`devroot` path lookup, 9P, `bind`, `mount`, path `exec`, `/boot`,
`Fgrp`/`Egrp`/`Rgrp`, `slash`/`dot`, the console and the legacy
`userinit`/`proc0`/`init0`/`initcode` bootstrap remain linked or
initialized but do not execute.

The smallest next experiment toward O-resident MicroPython is to point
this same ring-3 `OEXECUTE` path at `OID_MP_EXEC` with the existing
`-O`/`-S init` argv and add a direct serial-backed console/stdin/stdout
so `boot.py` and the REPL no longer require `/dev/cons`, `kbdfs` or an
FD-backed console.
