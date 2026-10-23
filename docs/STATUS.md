# Implementation status — Plan2001-O

**Status date:** 23 October 2026. **Current runtime evidence baseline:**
`main` at implementation commit `e3843009a79f762f30e70a459fffafb7c85e9a8f`
(pathless Level A O storage), preceded by `a9c3247`/`077ba29`, with the
registration gate rerun at clean test commit `09cb651` (local native OID
registration). The previous baseline was
`bf2117e0c6a01310d5cfc7acaaeb06534ad10eca` (native O byte objects by
OID); earlier baselines were
`016ccffebfe8c9baa93f09c7e6599315e65e4751`,
`b41a102384efa81b17cdc5f923415b123341f8ca` and
`4678fada0d66f83b310291320e57aba12068934d`.
**Boot Experiment A** was separately implemented and verified at
`6c6e112efb201bd5d927e3276877714d56c1a92f` (23 October 2026); it is a
boot-boundary result and does not replace the storage Level A baseline.
**Boot Experiment B** was separately implemented at `ba6b8ab` plus
`ddf9899` (23 October 2026); it is a distinct userspace-entry result and
does not replace either storage Level A or Boot A.
**Boot Experiment C** was implemented at `3374eb9` (23 October 2026);
it combines Boot B's ring-3 entry with native O reads and an
`OEXECUTE` image replacement, and does not rename the earlier Storage
Levels A/B/C.
**Boot Experiment D1** was implemented at `4d1d75f` (23 October 2026);
it starts the unchanged O-resident MicroPython, proves the image
transition and diagnoses its first inherited FD dependency. It is a
diagnostic result, not a working pathless MicroPython boot.

Original imported source: `pereuna/Plan2001`, branch `poc-o-only`,
commit `436ed30c894c4060638341ecebe82004d457f496`
(20 October 2026); imported without its Git ancestry.

This document is the **single source of truth for current verification**.
The architecture is in [README.md](../README.md), past source-branch
experiments in [POC.md](POC.md), and the implemented on-disk contract in
[O-FORMAT.md](O-FORMAT.md). The [OBJECT-MODEL.md](OBJECT-MODEL.md) document is an **architectural proposal**, not a new implementation claim: a file is object byte content without a mandatory directory root or Unix metadata; GE/O does not inherit Python's class/type hierarchy. This documentation-only refinement does not alter the runtime evidence below.

## Evidence levels

| Level | Current evidence |
| --- | --- |
| **Implemented** | The imported source contains GE/O O-profile volumes, versioned `(SpaceID, OID)` objects, the native O syscall boundary with process-owned O Space handle tables, a bounded native executable-object path with a snapshot-based, capacity-bounded argv copy, an O-resident Environment and `.mpy` loader, and a persistent MicroPython `init` Space. The normal amd64 `pc64` boot now embeds only `oinit`/`kbdfs` (and the separate `ohandle`/`oexec` harnesses) and loads the real MicroPython executable from O. A `pc64mp` kernel remains explicitly test-only for historical embedded-MicroPython gates. |
| **Demonstrated in the source branch** | Five reported GE/O QEMU regression gates, including three boots of one ESP + O image with counter `1 -> 2 -> 3` and preserved Counter OID/alias. See [POC.md](POC.md). |
| **Statically verified in Plan2001-O** | Documentation references and repository metadata checked at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`; details below. |
| **Runtime verified in Plan2001-O** | **PASS:** on 23 October 2026 the full amd64 build, selfroot, the new native byte-object gate (`tools/test-o-bytefile.sh`) and all nine existing O-only gates passed with KVM at implementation commit `bf2117e`; earlier runs used `016ccff`, `b41a102` and `4678fad`. See the records below and `build/verification/*.log`. |
| **Pathless storage, Level A** | **PASS (23 October 2026):** a `PARTUUID=` O volume is discovered in GPT from enumerated SD units and used for GE block I/O, sync and driver flush with no new kernel `Chan`/`namec`/walk/mount/path-exec event in the measured window. Bootstrap and console remain legacy, so Levels B/C are **NOT YET**. See [O-BOOT-DEPENDENCIES.md](O-BOOT-DEPENDENCIES.md). |
| **Boot Experiment A (kernel-only probe)** | **PASS (23 October 2026):** with `plan9.ini oboot=probe`, the normal `9pc64` kernel initialized hardware and the scheduler, ran a minimal `kproc` (`pid=1`, `slash=nil`, `dot=nil`), produced two post-scheduler heartbeats, and did not execute `userinit`/`proc0`/`init0`/`startboot` or any `namec`/walk/mount/path-exec. The normal O boot remained PASS. This is not a storage or pathless-executable claim; see [O-BOOT-EXPERIMENT-A.md](O-BOOT-EXPERIMENT-A.md). |
| **Boot Experiment B (ring-3 userspace probe)** | **PASS (23 October 2026):** with `plan9.ini oboot=user`, the normal `9pc64` kernel built a user address space from a 113-byte embedded image, entered ring 3 at `0x200028` (`cs=0x2b`, `ss=0x23`), and observed user syscalls `alarm(0)` and `sleep(100)` with returns and continued execution. `userinit/proc0/init0=0`, all path counters `0`, `slash/dot=nil`, and the normal O and Boot A controls remained PASS. This is not Storage Level B and does not use GE/O or MicroPython; see [O-BOOT-EXPERIMENT-B.md](O-BOOT-EXPERIMENT-B.md). |
| **Boot Experiment C (ring-3 OID executable)** | **PASS (23 October 2026):** with `plan9.ini oboot=oid` and a generated `obootvol=PARTUUID=...`, the embedded first user loader ran `OVOLOPEN` (ret 1), `OSPACEOPEN` (h=1) and `OEXECUTE` for OID `0x4f45584543000004`; the 2,088-byte O-resident target replaced the image and ran its own `ospaceget`, `alarm(0x42)` and `sleep` syscalls in ring 3. `userinit/proc0/init0=0` and every path counter stayed 0 before and after exec. Wrong-PARTUUID and missing-OID negatives passed. This is not Storage Level B/C and does not run MicroPython; see [O-BOOT-EXPERIMENT-C.md](O-BOOT-EXPERIMENT-C.md). |
| **Boot Experiment D1 (O-resident MicroPython diagnosis)** | **PASS (23 October 2026), diagnostic only:** with `plan9.ini oboot=mp` and the generated `obootvol=PARTUUID=...`, the embedded loader ran `OEXECUTE` for `OID_MP_EXEC` and the kernel verified the unchanged 2,194,156-byte MicroPython image by SHA-256. MicroPython entered ring 3 (`text=micropython`, `pc=0x275abc`), completed `mp_init`/`main` and a second native `OVOLOPEN` inside `p9_space_o`. Its first `fprint(2, ...)` caused `PWRITE` (nr 51, fd 2) and a kernel fault because `up->fgrp` is nil; `boot.py` was not reached. This is not a working boot or a D2 console result; see [O-BOOT-EXPERIMENT-D1.md](O-BOOT-EXPERIMENT-D1.md). |
| **Proposed, not implemented** | Native GE/O relationship indexes/edges, per-Python-object O records, general native executable-object loading (catalog, architecture selection, dynamic linking), general persistent namespaces, object IPC and a remote protocol. |

Never promote source inspection or a successful source-branch test into
a **current-repository runtime PASS**. A missing result is **NOT RUN**,
not PASS and not FAIL.

## Boot Experiment D1 — 23 October 2026

**Source state:** implementation commit
`4d1d75f969e2fd4ed35247af43bbfac1c33393cb`, plus this documentation
follow-up. This is a **diagnostic** experiment; it does not claim a
working O-resident MicroPython boot.

**Implemented**

- `plan9.ini oboot=mp` is a fifth branch at `main()`
  (`sys/src/9/pc64/main.c:232`, `:286`). It reuses C's embedded
  `obootoid` loader and `otouser` ring-3 setup; only the OID and the six
  MicroPython arguments differ.
- The six arguments are exactly the existing `oinit.c:argvec` form:
  `micropython -O PARTUUID=<fresh> -S init -B`, delivered in the user
  `Oargs`/argv block and copied by the existing `oexecute` argv path.
- D1-specific `OBOOT-D1:` markers trace the selected PID through a
  bounded 64-syscall window and print cumulative legacy/path counters at
  n=4, 16, 32 and 64. `devgefs.c` prints the OID length and SHA-256 read
  by `onativeget` for D1, using libsec, instead of a small checksum.
- The unchanged default MicroPython is seeded at `OID_MP_EXEC` by the
  normal `tools/mkovol` path. No MicroPython source, `boot.py`,
  `p9console.c`, default executable bytes or O on-disk format was
  changed.

**Commands**

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-d1.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-d1.log
tools/test-oboot-mp.sh 2>&1 | tee build/verification/test-oboot-mp-experiment-d1.log
tools/test-oboot-user.sh
tools/test-oboot-oid.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A: separate oboot=probe QEMU boot
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; `9pc64` md5 `7b5e22d1816371a131849ea0aa308740`, test-only `9pc64mp` md5 `0a79d3513f1c071507e812486113836e`. `build/verification/build-experiment-d1.log` |
| selfroot | **PASS** | clean at `4d1d75f`; MicroPython SHA `41157020158b3e295475bc40fb79eefae188dad27f852d5eb2dd5e33cfb751bc`, 2,194,156 bytes, unchanged. `build/verification/selfroot-experiment-d1.log` |
| D1 gate | **PASS (diagnostic)** | `PASS: D1 EXEC, OID_MP_EXEC image transition and first-dependency diagnosis`. `build/verification/test-oboot-mp-experiment-d1.log`, `build/verification/test-oboot-mp-pos-experiment-d1.log` |
| OID image transition | **PASS** | `OEXECUTE oid=0x4f45584543000003 len=2194156 sha256=411570... ver=0x1`; post-exec `text=micropython pc=0x275abc cs=0x2b ss=0x23`. |
| MicroPython startup | **REACHED `p9_space_o`** | Post-exec native `OVOLOPEN` (nr 54) at PC `0x281060` returned 1; first fd-2 `PWRITE` (nr 51, arg0=2) at PC `0x279db4`. |
| First dependency | **PASS (diagnosis)** | `fprint(2, ...)` at `p9space.c:366` -> `pwrite` -> `fdtochan` (`sysfile.c:145-147`) with `up->fgrp == nil` -> `kernel fault: write addr=0x8`. |
| `boot.py` / `space.open` / boot/commit | **NOT REACHED** | Blocked by the first fd-2 write; reported, not hidden. |
| Counters | **PASS** | Pre-entry and `AFTER-SYSCALLS n=4` both show `userinit=proc0=init0=0`; all `namec/newchan/walk/devwalk/mount/exec` zero. |
| Missing `OID_MP_EXEC` | **PASS (negative)** | `OEXECUTE` returns `-1`; the same handle reads the existing 209-byte code object (`OSPACEGET` ret `0xd1`); `alarm(0xbaf)`; no `micropython` text and no panic. `build/verification/test-oboot-mp-missing-experiment-d1.log` |
| Boot A/B/C/normal O/pathless/exec/argv/handles controls | **PASS** | Logs `build/verification/test-oboot-probe-experiment-d1.log`, `test-oboot-user-experiment-d1.log`, `test-oboot-oid-experiment-d1.log`, `test-o-boot-experiment-d1.log`, `test-o-pathless-experiment-d1.log`, `test-o-exec-*-experiment-d1.log`, `test-o-handles-experiment-d1.log`. |

**Fate:** the process reaches MicroPython `p9_space_o`, attempts `PWRITE`
to fd 2, and the kernel panics on the nil `Fgrp` in `fdtochan`. This is
an observed diagnostic result, not a successful MicroPython boot. No
console, FD emulation, `boot.py` change, pathname machinery or fallback
was added.

**Next D2 objective:** supply the smallest process-local FD/console
facility that lets MicroPython's fd-2 diagnostic write return normally,
without a `/dev/cons` pathname or `kbdfs`, then observe the next actual
startup dependency.

## Boot Experiment C — 23 October 2026

**Source state:** implementation commit
`3374eb954638bae08131ac9099bf09f8e7c923ca`, plus this documentation
follow-up. The build, selfroot and runtime evidence were produced from
that committed source with disposable QEMU images. This is **Boot
Experiment C**, distinct from the earlier top-down **Storage Level C**.

**Implemented**

- `plan9.ini oboot=oid` is a fourth branch at `main()`
  (`sys/src/9/pc64/main.c:230`, `:279`). It reuses the Boot-B
  `o_user_bootstrap()`/scheduler/ring-3 path but selects a second
  embedded one-page loader image.
- `sys/src/9/pc/obootoid.c` reads an argument block placed on the user
  stack and calls the existing user syscalls `ovolopen`,
  `ospaceopen(1,"init",4)` and `oexecute`. It has no pathname, FD,
  console, filesystem or writable global data.
- `sys/src/9/pc64/ouser.c` validates the loader image, creates a user
  text page and 16 MiB stack, zeroes the `Tos` page, reads the bounded
  `obootvol` value from `plan9.ini`, writes the `Oargs` block on the
  user stack, and enters user mode through the new `otouser`
  (`sys/src/9/pc64/l.s:873`), which delivers a user argument in BP.
- The target `sys/src/cmd/obootctarget/obootctarget.c` is built by the
  ordinary amd64 tools. `tools/mkovol RAWEXEC=FILE` seeds it verbatim
  at fixture OID `0x4f45584543000004` through `tools/oseed.py` and
  `sys/src/cmd/gefs/ream.c`; this is separate from the legacy
  `NATIVEEXEC` header-patching path.
- `tools/gefsdisk` now substitutes `@PARTUUID@` in arbitrary `INI`
  lines as well as `INIT=`, allowing the fresh per-image GUID to be
  handed to userspace. `tools/test-oboot-oid.sh` is the gate.

**Commands**

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-c.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-c.log
tools/test-oboot-oid.sh 2>&1 | tee build/verification/test-oboot-oid-experiment-c.log
tools/test-oboot-user.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A: separate oboot=probe QEMU boot, see docs/O-BOOT-EXPERIMENT-A.md
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; `9pc64` md5 `11ca7cbf07f93484188df1f3456e60a1`, test-only `9pc64mp` md5 `46f782940da530a7e4f7d16285fad43f`. `build/verification/build-experiment-c.log` |
| selfroot | **PASS** | clean selfroot at `3374eb9`, `gefs` and `obootctarget` present. `build/verification/selfroot-experiment-c.log` |
| Boot C gate | **PASS** | `PASS: Boot Experiment C OID executable over native O, post-exec syscalls and negatives`. `build/verification/test-oboot-oid-experiment-c.log` |
| Native O open | **PASS** | `OVOLOPEN spec=PARTUUID=<generated> dev=#S/sdF0/data off=68157440 size=201326592 ret=1`; `OSPACEOPEN-HANDLE h=1`. `build/verification/test-oboot-oid-positive-experiment-c.log` |
| OID byte identity | **PASS** | `OEXECUTE oid=0x4f45584543000004 len=2088 sum=3f ver=0x1`; host target length 2,088 and 8-bit sum `0x3f`; seed log shows `seed: rawexec 2088 ... unchanged`. |
| Ring-3 exec transition | **PASS** | `SYSCALL-RETURN nr=60 ... text=obootctarget pc=0x200098 cs=0x2b ss=0x23 user=1`; target then runs `ospaceget` (nr 56, `-1`), `alarm(0x42)` and two sleeps. |
| Counters | **PASS** | Pre-entry and post-exec `AFTER-SYSCALLS` both show `userinit=proc0=init0=0` and `namec=newchan=walk=devwalk=mount=exec=0`. |
| O handle lifecycle | **PASS** | `sysoexecute` releases its temporary handle; `execcommit` calls `oprocexec`/`odropall`; target `ospaceget(1, OID, ...)` returns `-1`. |
| Wrong PARTUUID | **PASS** | `OVOLOPEN-ERROR ... no disk has that partition`, ret `-1`, no `OSPACEOPEN`/`OEXECUTE`, user `alarm(0xbad)`, no panic; log `test-oboot-oid-wrong-experiment-c.log`. |
| Missing OID | **PASS** | `OEXECUTE` returns `-1`; query of the existing code OID returns `0xd1` (209 bytes) on the same handle; user `alarm(0xbaf)`; target never runs; log `test-oboot-oid-missing-experiment-c.log`. |
| Boot A control | **PASS** | `oboot=probe` heartbeats and zero legacy/path counters. `build/verification/test-oboot-probe-experiment-c.log` |
| Boot B control | **PASS** | `PASS: Boot Experiment B ring-3 user probe, two syscall round trips`. `build/verification/test-oboot-user-experiment-c.log` |
| Normal O boot control | **PASS** | Three O-only boots, MicroPython from O, `run()` 1 -> 2 -> 3. `build/verification/test-o-boot-experiment-c.log` |
| Native O storage control | **PASS** | Level A pathless native GE/O storage. `build/verification/test-o-pathless-experiment-c.log` |
| Native exec/argv/handles controls | **PASS** | `test-o-exec`, `test-o-exec-args`, `test-o-handles`. Logs `build/verification/test-o-exec-*-experiment-c.log`, `test-o-handles-experiment-c.log`. |

**Residual state:** the process has the `Pgrp` created by `kproc`;
`slash`, `dot`, `fgrp`, `egrp` and `rgrp` are nil. `chandevreset` still
runs before the branch (`rootreset` metadata, `sdreset` controller
probe). GE/O engine/worker kprocs, traps, `execo`/`execcommit`,
`execregs`, `oprocexec`, segment/page allocation and `otouser` execute;
`namec`, `Chan`, `Dev` file operations, `devroot` path lookup, 9P,
`bind`, `mount`, path `exec`, `/boot`, the console and the legacy
bootstrap do not. The initial loader has no data/BSS; the O-resident
target has ordinary libc data/BSS handled by `execo`.

**Remaining limits:** one fixed fixture OID, one target program, one
active native O volume and one Space handle. No general program catalog,
permissions, remote access, MicroPython, Python Environment or pathless
console is implemented. `chandevreset` and inherited linked code remain.
On-disk GE/O format, `OID_MP_EXEC` and the default boot are unchanged.

## Boot Experiment B — 23 October 2026

**Source state:** implementation commits
`ba6b8ab325d5e222539b5a050bedfd1a4f636d7b` (opt-in ring-3 boot
probe) and `ddf98993353c02f8ef6df59e715cf7e37aec904a` (pre-fault the
`Tos` page), plus this documentation follow-up. The build and runtime
evidence were produced from that source content with disposable QEMU
images. This is **Boot Experiment B**, distinct from **Storage Level B**
(MicroPython from GE/O), which remains **NOT YET**.

**Implemented**

- `plan9.ini oboot=user` is a third branch at the existing `main()`
  handoff (`sys/src/9/pc64/main.c:228`, `:272`). It calls
  `o_user_bootstrap()` instead of `userinit()` or Boot A's
  `ouserinit()`.
- `sys/src/9/pc64/ouser.c` creates one `kproc`, validates a flat
  a.out image (`magic`, expanded entry `UTZERO+0x28`, alignment, text
  and whole-image bounds, zero data/BSS), copies it to one user text
  page, builds a 16 MiB user stack with a zeroed top stack page for the
  `Tos` slot, sets `kp=0`, and enters ring 3 through the existing
  `touser()` `SYSRET` path.
- The image is built by the ordinary amd64 tools from
  `sys/src/9/pc/obootuser.c` to `obootuser.out`
  (`6l -l -R1 -s`) and `obootuser.i`; it is linked into the kernel, not
  embedded in `devroot`. It performs `alarm(0)`, `sleep(100)`,
  `sleep(100)` and then sleeps. It has no console, FD, environment or
  pathname dependency.
- `sys/src/9/pc64/trap.c` prints guarded `OBOOT-B: SYSCALL-ENTRY` and
  `SYSCALL-RETURN` records for the probe PID when `userureg()` is true,
  and reprints the legacy/path counters after four user syscalls. No
  generic syscall ABI, error handling or driver was changed.
- `tools/test-oboot-user.sh` is the repeatable gate. It builds a
  disposable ESP with `oboot=user`, no `root=` and no `init=`, boots
  QEMU, asserts ordered markers, user selectors, syscall round trips,
  distinct user PCs and zero counters, and stops the VM.

**Commands**

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-b.log
tools/test-oboot-user.sh 2>&1 | tee build/verification/test-oboot-user-experiment-b.log
# controls
# oboot=probe QEMU boot (documented in docs/O-BOOT-EXPERIMENT-A.md)
tools/test-o-boot.sh 2>&1 | tee build/verification/test-o-boot-experiment-b.log
tools/test-o-pathless.sh 2>&1 | tee build/verification/test-o-pathless-experiment-b.log
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; normal `9pc64` md5 `f27c24cc102ed216b2deae098763a4b4`, test-only `9pc64mp` md5 `d260f7c2d934f9b268c5eb3057809d37`. `build/verification/build-experiment-b.log` |
| Boot B gate | **PASS** | `PASS: Boot Experiment B ring-3 user probe, two syscall round trips`. `build/verification/test-oboot-user-experiment-b.log`, `build/verification/test-oboot-user-boot-experiment-b.log` |
| Ring-3 entry | **PASS** | `KERNEL-READY entry=0x200028 text=73 image=113 slash=nil dot=nil`; `KERNEL-TO-USER pc=0x200028`; user `cs=0x2b ss=0x23 user=1`. |
| User syscalls and return | **PASS** | `nr=6` `alarm`, `nr=17` `sleep`; entry/return pairs, with subsequent user entries at `0x200070` and `0x200061`; `AFTER-SYSCALLS` counters all zero. |
| Legacy/path machinery absent | **PASS** | `legacy-calls userinit=0 proc0=0 init0=0`; `path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`; no `OBOOT-A`, panic, fault or suicide. |
| Boot A control | **PASS** | `KPROC-RUNNING`, heartbeats 1/2, legacy/path counters zero. `build/verification/test-oboot-probe-experiment-b.log` |
| Normal O boot control | **PASS** | Three O-only boots, `run()` 1 -> 2 -> 3, MicroPython from O. `build/verification/test-o-boot-experiment-b.log` |
| Native O storage control | **PASS** | `PASS: Level A pathless native GE/O storage window, persistence and bounds`. `build/verification/test-o-pathless-experiment-b.log` |
| Malformed user image | **NOT RUN** | Kernel validation exists and panics before execution, but no injection mode was added (optional check). |

**Residual state:** `kproc` creates the process `Pgrp`; it is present and
unused. `slash`, `dot`, `fgrp`, `egrp`, `rgrp`, `parent`, `tt` and
`trend` are explicitly nil, and `alarm=0`, `parentpid=0`. The top stack
page including the `Tos` slot is zeroed. `chandevreset` still ran before
the branch, including `rootreset` directory metadata and `sdreset`
hardware probing (`#S/sdE: ich: sata-I with 6 ports`); `chandevinit`,
the `alarm` kproc and the `closeproc` kproc did not run.

**Remaining limits:** the probe is a 113-byte flat image with no
console, FDs, environment or writable data outside its stack. It is not
a general userspace runtime, not Storage Level B, and does not load
MicroPython or any OID. The optional malformed-image injection test was
not implemented.

**Next step (not implemented):** from this ring-3 process, use the
existing `OVOLOPEN PARTUUID=`, `OSPACEOPEN` and `OEXECUTE` syscalls over
the native SD/GE/O provider. Because the call originates in user mode,
the existing syscall path supplies `up->dbgreg`, so `execo()` can make
the next process transition without `namec`, `Chan`, `bind`, `mount` or
a `/boot` pathname.

## Boot Experiment A — 23 October 2026

**Source state:** implementation commit
`6c6e112efb201bd5d927e3276877714d56c1a92f` (`kernel: add opt-in
kernel-only boot probe`), plus this documentation follow-up. The full
build and runtime logs were produced from that source content with
disposable QEMU images. This is distinct from **Storage Level A** above
and does not change its evidence.

**Implemented:** an opt-in `plan9.ini oboot=probe` branch at the
existing `main()` handoff (`sys/src/9/pc64/main.c:225`, `:268`). It calls
`ouserinit()` instead of `userinit()`. `ouserinit()`
(`sys/src/9/port/userinit.c:140`) sets `up = nil`, keeps `eve`, and
creates one `kproc` that prints its PID and namespace state, sleeps on
the existing timer primitive, prints two heartbeats, and then sleeps
indefinitely. Guards count entry to `userinit`, `proc0` and `init0`.
There is no new driver, filesystem, O-storage, console, syscall or
user-image work. `chandevreset` and all device reset hooks remain in the
boot before the branch.

**Commands**

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-a.log
NOROOTFS=1 CONSOLE=0 ROOTIMG=build/amd64/ohand-root.gefs KERNEL=9pc64 \
  INI='oboot=probe' tools/gefsdisk build/amd64/obootprobe.img
# one QEMU boot of obootprobe.img with OVMF, serial to a file,
# intentionally stopped after 30 s once both heartbeats appeared
tools/test-o-boot.sh 2>&1 | tee build/verification/test-o-boot-experiment-a.log
tools/test-o-pathless.sh 2>&1 | tee build/verification/test-o-pathless-experiment-a.log
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; normal `9pc64` md5 `0fcf61f2bd1e8c6dd700fce08e2be30b`, test-only `9pc64mp` md5 `845997f60d9fde2d987923b4ec5a017e`. `build/verification/build-experiment-a.log` |
| Probe boot | **PASS** | No root filesystem and no `init=`: `OBOOT-A: MAIN entry oboot=probe`, `OBOOT-A: HANDOFF probe ouserinit`, `KPROC-RUNNING pid=1 slash=nil dot=nil`, `legacy-calls userinit=0 proc0=0 init0=0`, `path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`, `HEARTBEAT 1 ticks=103`, `HEARTBEAT 2 ticks=204`. `build/verification/test-oboot-probe-experiment-a.log`, `build/amd64/obootprobevm/serial.log` |
| Probe task lifetime | **PASS** | The task remained alive and used `tsleep` after scheduler entry; QEMU was stopped by the host after 30 s (`timeout` exit 124), not by a kernel panic. `build/amd64/obootprobevm/qemu.log` |
| Legacy chain skipped | **PASS** | Direct counters and the existing `opath` counters show `userinit=0 proc0=0 init0=0` and `exec=0`; the boot has no `/boot/oinit` execution. `build/verification/test-oboot-probe-experiment-a.log` |
| Normal O boot unchanged | **PASS** | `PASS: three O-only boots, persistent Counter and run() from O (no FS)`; `run()` 1 -> 2 -> 3, no `OBOOT-A` marker. `build/verification/test-o-boot-experiment-a.log` |
| Positive control | **PASS** | Normal `tools/test-o-pathless.sh` boot showed real namespace activity: `namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1`. `build/verification/test-o-pathless-experiment-a.log` |

**Residual effects:** `kproc` still creates and shares a `Pgrp`; the
probe task has `slash=nil` and `dot=nil`. `chandevreset` ran before the
branch, including `devroot`'s `rootreset` (static directory entries) and
`devsd`'s `sdreset` (visible as `#S/sdE: ich: sata-I with 6 ports`).
`chandevinit`, the `alarm` kproc and the `closeproc` kproc were not
called on the probe path. No claim of zero filesystem-related reset code
is made.

**Remaining limits:** this is a first-process bypass, not a device,
storage, console or user-image experiment. The embedded `/boot` entries
and all `Chan`/`namec`/`devroot` code remain linked. The normal boot
still uses the legacy `userinit`/`proc0`/`init0`/`initcode` chain. The
suggested next boundary (not implemented) is to build a user process
from already-available bytes and enter user mode directly, skipping the
namespace seeding and path exec.

## Normal O-loaded MicroPython boot — 22 October 2026

**Source state:** HEAD `016ccffebfe8c9baa93f09c7e6599315e65e4751`, with
this task's source changes in an **uncommitted working tree**. This record
is not a claim about a clean committed revision. Earlier experiment records
below are unchanged history.

**Normal boot chain:** UEFI -> `9pc64` kernel -> embedded `/boot/oinit`
and `/boot/kbdfs` -> O volume and flat `init` Space -> the bounded native
loader executes `OID_MP_EXEC` (`0x4f45584543000003`) -> MicroPython ->
persistent `init` Space (`run()`/commit) or an interactive REPL. There is
no embedded `/boot/mp` and no pathname-based MicroPython `exec` on this
path.

**Implemented in this change**

- The normal `pc64` bootdir is `kbdfs`, `oinit`, `ohandle` and `oexec`;
  `micropython`/`mp` is absent. The previous `pc64omp` default candidate
  is removed. `pc64mp`/`9pc64mp` remains only as a clearly marked
  **test-only** embedded-MicroPython kernel for the historical Stage 1-4
  and legacy file/DMOBJ/REPL gates.
- `tools/mkovol ... SOURCE` seeds the built selfroot MicroPython byte for
  byte by default at `OID_MP_EXEC`; `NOMPEXEC=1` deliberately omits it for
  the missing-object diagnostic. The `ohello` BSS-header mutation remains
  confined to its fixture. An older image without the interpreter is not
  migrated; `oinit` reports the missing OID and exits without a fallback.
- `tools/mkrepl [OUT]` prepares a fresh ESP + O REPL disk with the normal
  kernel and `init=/boot/oinit -repl -vol PARTUUID=...`. It refuses to
  replace an existing image unless `FORCE=1`, so a persistent user image
  is never silently reformatted or reseeded. `./repl_tui.sh` is the exact
  human-facing command from the repository root.
- Retained bootstrap dependencies are explicit: `oinit` is still reached
  through the inherited internal boot interface, `kbdfs` is still the
  embedded console helper, and `devroot` plus the separate `ohandle`/
  `oexec` regression harnesses remain. MicroPython executable bytes, its
  Environment/code and persistent state come from O. This is not a claim
  that every runtime file interface has been removed.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
for gate in test-o-boot-omp test-o-boot test-o-exec-args test-o-exec \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate-default-o.log"
done
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `f5f989838226c6b8135c0b137a5f813c` (SHA-256 `0254386260027b6f3be197d17a87ab08ea554fc44761f08d370c96190e772d16`), test-only `9pc64mp` md5 `39ef7f6af90766c88095a8da11e999fe` (SHA-256 `f661e97404284355154ff5029a9e77784c63025302f34a36456b663cb1f5914f`), plus loader and userspace binaries. `build/verification/build-default-o.log` |
| selfroot | **PASS** | `build/selfroot` at HEAD `016ccff`; `gefs`, `micropython`, `oinit`, `ohello`, `oexec`, `ohandle` and `kbdfs` present. `build/verification/selfroot-default-o.log` |
| Generated default boot contents | **PASS** | `build/amd64/pc64.rootc.c` has `addbootfile("oinit"`, `addbootfile("kbdfs"`, `ohandle` and `oexec`, and no `addbootfile("mp"`. The test-only `pc64mp.rootc.c` still has `mp`. Asserted by `test-o-boot-omp.sh`. |
| Fresh O image seed | **PASS** | `mkovol` seeded the 2,191,593-byte MicroPython executable by default at `OID_MP_EXEC`, SHA-256 `1487111f358ac845db3ca2b9485a561e722675c59c0632ca105ddd02c13b7e53`, unchanged, matching the built selfroot binary. `build/amd64/ompbootvm/mkovol.log`, `build/amd64/obootvm/mkovol.log` |
| Normal O boot, three boots | **PASS** | One ESP + O disk, no FS root, normal `9pc64`: `run()` 1 -> 2 -> 3, Counter OID/alias 7/7, O object hash equal to the host binary, no root FS mount. `build/verification/test-o-boot-default-o.log`, `build/verification/test-o-boot-omp-default-o.log`, `build/amd64/obootvm/three-boots.log`, `build/amd64/ompbootvm/omp-boots.log` |
| REPL and persistence | **PASS** | The supported `tools/mkrepl` image and `oinit -repl` path reached a prompt, evaluated `OINIT-REPL 42`, committed `kept = 4242`, and after a restart of the same disk restored the graph and printed `REPL-KEPT 4242`. `build/amd64/ompbootvm/repl1.log`, `build/amd64/ompbootvm/repl2.log` |
| Missing/malformed and older image | **PASS** | Missing and malformed OIDs returned errors while preserving the O handle; a fresh image made with `NOMPEXEC=1` printed `MicroPython object 0x4f45584543000003 is missing from O` and did not use an embedded interpreter. `build/amd64/ompbootvm/check.log`, `build/amd64/ompbootvm/legacy.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`; rollback and handle assertions unchanged. `build/verification/test-o-exec-default-o.log` |
| Native argv bounds | **PASS** | `PASS: native O argv bounds, rollback and race`; argv/Tos/BSS, boundary, malformed-copy, rollback and mutation assertions unchanged. `build/verification/test-o-exec-args-default-o.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-default-o.log` |
| GE, O volume, O objects, Python/O | **PASS** | `PASS: GE volume, raw key/value, no FS`; `PASS: O volume, no FS`; `PASS: native O objects, no FS`; `PASS: Stage 4 Environment, code and Space graph from O (no FS)`. These historical harnesses use the test-only `9pc64mp` kernel where they still need `/boot/mp`. `build/verification/test-ge-default-o.log`, `test-o-volume-default-o.log`, `test-o-objects-default-o.log`, `test-o-space-default-o.log` |

Log completion times (UTC): build 20:17:29; selfroot 20:17:34; O-loaded
MicroPython boot 20:19:26; normal O boot 20:20:01; argv 20:20:26; native
exec 20:20:51; handles 20:21:14; GE 20:21:25; O volume 20:22:25; O
objects 20:22:53; Python/O 20:23:25. The documented `test-o-space`
shutdown diagnostic (`panic: boot process died: unknown`) is unchanged
and is not a gate failure. The older image in the missing-object test also
ends when its init process exits; that diagnostic is expected, not a
fallback.

**Remaining limits:** the normal path still uses a fixed experimental OID
and embedded `oinit`/`kbdfs`; there is no program catalog, architecture
selection, permissions framework, dynamic linking or general
executable-object format support. The `pc64mp` kernel is test-only and is
never a normal or fallback boot path. The on-disk format is unchanged.

## Native O byte objects by OID — 23 October 2026

**Source state:** implementation commit
`bf2117e0c6a01310d5cfc7acaaeb06534ad10eca`
(`micropython: add native O byte objects by OID`), plus this docs-only
STATUS/report follow-up. The runtime commands below ran from that
committed tree; `tools/selfroot` cloned `bf2117e`.

**Implemented**

- The built-in `space` module now has `space.oget(oid)` and
  `space.oput(oid, data)` in `sys/src/cmd/micropython/p9space.c`. They
  bind directly to the existing `ospaceget`/`ospaceput`/`ospacecommit`
  syscalls; there is no new kernel driver, storage service, pathname,
  directory, 9P adapter or on-disk v1 change.
- `oput` writes bytes-like data and calls the native commit/sync before
  returning, independently of the Python graph dirty flag and of the
  next automatic `OID_GRAPH` commit. `oget` returns exact `bytes`
  (embedded NULs and `b""` included), raises `OSError` for a missing
  OID, and retries a changed size/read pair at most three times.
- Both require an open native `-O` volume and `-S` Space; otherwise they
  raise `OSError`. Writes reject `OID_ROOTS`/`OID_FIRST`, the whole
  `OID_CODE`-and-above region (`OID_ENV`, `OID_GRAPH`, upgrade metadata)
  and the native-exec OIDs `0x4f45584543000001`-`03`. The PoC
  whole-object limit is 1 MiB.
- `space.oid()` is unchanged and still reports a Python logical graph
  OID; native byte objects and Python graph OIDs are independent even
  when numbers coincide. OIDs 42 and 44-49 are PoC identifiers, not an
  allocator.
- Added `tools/obytefile.py` and `tools/test-o-bytefile.sh`, and
  regenerated `genhdr/qstrdefs.generated.h` for the two new qstrs.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-bytefile.sh
for gate in test-o-boot test-o-boot-omp test-o-exec test-o-exec-args \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate-bytefile.log"
done
```

The host login was not in the `kvm` group; the QEMU commands ran with the
`kvm` supplementary group (still the target's normal `-accel kvm -cpu
host`). No physical disk was used.

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; normal `9pc64` md5 `e31ae9fb0aa0c1a816b5ef55062b8896`, test-only `9pc64mp` md5 `17a87e214c6016f612dfd668a10bbdc1`, UEFI loader and userspace binaries present. `build/verification/build-bytefile.log` |
| selfroot | **PASS** | `build/selfroot` at `bf2117e`; MicroPython object SHA-256 `d3f715cd111c15986de66929acfbee6ea4b52dc58720f231d50e77fe12fb75f1`, seeded unchanged at `OID_MP_EXEC`. `build/verification/selfroot-bytefile.log` |
| Native byte objects by OID | **PASS** | One ESP + O disk, normal `9pc64`, three boots and no FS root. Boot 1 stored and read `OID 42 = b"hello\n"`, empty bytes, `b"\x00\xff\x00"`, a 2048-byte value (over `Objchunk = 480`), two OIDs with identical bytes then changed one independently, and first overwrite data. Boots 2 and 3 restored `OID 42` as the same six bytes (`Obyte: PASS reboot-hello`), verified overwrite across reboot, and re-ran all error checks. Invalid/negative/overflow/non-int OIDs, missing OID, reserved writes, over-limit writes and non-bytes data failed predictably while `OID_GRAPH` restoration and seeded code stayed intact. `build/verification/test-o-bytefile.log`, `build/amd64/obytevm/three-boots.log` |
| Unsupported mode | **PASS** | `oinit -repl` (`-O` without `-S`) reached the O-loaded REPL; `space.oget(42)` and `space.oput(42, b"x")` both failed with `space: no native O Space is open` instead of a path fallback. `build/verification/test-o-bytefile.log`, `build/amd64/obytevm/repl.log` |
| Existing O boot | **PASS** | `PASS: three O-only boots, persistent Counter and run() from O (no FS)`. `build/verification/test-o-boot-bytefile.log` |
| O-loaded MicroPython/REPL | **PASS** | `PASS: MicroPython loaded from a native O object (no embedded mp)`, including REPL persistence and missing/malformed diagnostics. `build/verification/test-o-boot-omp-bytefile.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`. `build/verification/test-o-exec-bytefile.log` |
| Native argv bounds | **PASS** | `PASS: native O argv bounds, rollback and race`. `build/verification/test-o-exec-args-bytefile.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-bytefile.log` |
| GE, O volume, O objects, Python/O | **PASS** | `PASS: GE volume, raw key/value, no FS`; `PASS: O volume, no FS`; `PASS: native O objects, no FS`; `PASS: Stage 4 Environment, code and Space graph from O (no FS)`. `build/verification/test-ge-bytefile.log`, `test-o-volume-bytefile.log`, `test-o-objects-bytefile.log`, `test-o-space-bytefile.log` |

**Remaining limits:** no OID allocator, listing, deletion, permissions,
native relationships or per-Python-object native records; the 1 MiB
whole-object bound is a PoC limit; concurrent readers see a published
version, not an immutable history API. OID 43/100's `implements`
relations remain conceptual. The on-disk format is unchanged.

## Local native OID registration — 23 October 2026

**Source state:** implementation commits
`a9c3247` (`ge/o: add local OID registration in native Space
transactions`) and `077ba29` (`ge/o: serialize OID create/commit with
their sync`), plus test-fixture commit `09cb651`. The ten pre-existing
O-only gates below ran at `077ba29`; the dedicated registration gate was
rerun from a clean tree at `09cb651`.

**Implemented**

- `space.oregister([data])` allocates a fresh local OID and publishes
  its initial payload, including a real empty occurrence, through a new
  native `ospacecreate` call. It returns only after native commit and
  `gesync`.
- The allocator high-water mark is appended to the existing Space header
  `user[...]` part: legacy `env[64] | next[8]` (72 bytes) upgrades to
  `env[64] | next[8] | "OALLOC01" | next[8]` (88 bytes). It is not an
  OID, is unreachable by ordinary `oput`, and requires no v1 disk-layout
  revision or separate database.
- Candidate range is `64 <= oid < 0xffffffff00000000`, excluding the
  native-exec OIDs `0x4f45584543000001`-`03`. Candidate selection checks
  published records (including tombstones) and the current transaction,
  so explicitly written future IDs and the seeded 42-49 PoC fixtures are
  never overwritten. The high-water mark never decreases and exhaustion
  fails instead of wrapping.
- Creation and allocator advancement share one Space transaction.
  Native `oalloclk` serializes a whole create including its sync and also
  `ospacecommit`, so concurrent registrations queue rather than duplicate
  an OID. Data is bytes-like only, `str`/non-bytes are rejected, and the
  PoC whole-object limit remains 1 MiB.
- The state is local to the active O volume and `init` Space. There is no
  machine-wide allocator, global UUID, remote registration, copy-on-read
  or OID migration.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-register.sh
for gate in test-o-bytefile test-o-boot-omp test-o-boot test-o-exec-args             test-o-exec test-o-handles test-ge test-o-volume             test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate-register.log"
done
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; normal `9pc64` md5 `3ed5904573f19b223caee55b8ca3522d`, test-only `9pc64mp` md5 `35df51ff34f9acdcff296c34e71fba65`, UEFI loader present. `build/verification/build-register.log` |
| selfroot | **PASS** | `build/selfroot` at `077ba29`; `gefs`, `micropython`, `oinit`, `oregister`-capable `ohandle` present. `build/verification/selfroot-register.log` |
| Local OID registration | **PASS** | `PASS: local native OID registration, persistence and concurrency`. Four boots of one ESP + O disk covered empty, six-byte text, embedded-NUL binary, 2048-byte multi-chunk, equal bytes/distinct OIDs, `oput` revision without allocation, explicit IDs 64/70 skipped, a new OID after every reboot, and read-only calls not advancing the allocator. `build/verification/test-o-register-final.log`, `build/amd64/oregistervm/boots.log` |
| Two-process contention | **PASS** | `/boot/ohandle -reg` on a separate disposable ESP + O disk: two processes with independent native handles each registered eight payloads; all 16 returned OIDs were distinct and readable. `build/verification/test-o-register-final.log`, `build/amd64/oregistervm/concurrency.log` |
| Corrupt allocator state | **PASS** | `REGALLOC` fixture appended a malformed 16-byte extension; both registration attempts failed with `O: corrupt allocator state`, no reset-created OID 65 appeared, and the boot completed. `build/verification/test-o-register-final.log`, `build/amd64/oregistervm/corrupt.log` |
| Unsupported mode | **PASS** | `tools/mkrepl` image with `-O` but no `-S`: `space.oregister()` failed with `space: no native O Space is open`, no filesystem fallback. `build/verification/test-o-register-final.log` |
| Native byte objects by OID | **PASS** | Unmodified `tools/test-o-bytefile.sh`: `PASS: native O byte objects by OID, no FS or Python graph`. `build/verification/test-o-bytefile-register.log` |
| O-loaded MicroPython/REPL | **PASS** | `PASS: MicroPython loaded from a native O object (no embedded mp)`. `build/verification/test-o-boot-omp-register.log` |
| O init | **PASS** | `PASS: three O-only boots, persistent Counter and run() from O (no FS)`. `build/verification/test-o-boot-register.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`. `build/verification/test-o-exec-register.log` |
| Native argv bounds | **PASS** | `PASS: native O argv bounds, rollback and race`. `build/verification/test-o-exec-args-register.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-register.log` |
| GE, O volume, O objects, Python/O | **PASS** | `PASS: GE volume, raw key/value, no FS`; `PASS: O volume, no FS`; `PASS: native O objects, no FS`; `PASS: Stage 4 Environment, code and Space graph from O (no FS)`. `build/verification/test-ge-register.log`, `test-o-volume-register.log`, `test-o-objects-register.log`, `test-o-space-register.log` |

The documented `test-o-space` shutdown diagnostic
(`panic: boot process died: unknown`) remains an observation, not a gate
failure. The O-loaded MicroPython log also retains its expected
exit-path diagnostic (`panic: boot process died: fail`); its gate
assertions and exit status are **PASS**.

**Remaining limits:** registration is local to one active native O
volume/Space; it is not a machine-wide or cross-machine allocator. There
is no remote registration, OID transport, copy-on-read, global
uniqueness, deletion/GC or retention API. A malformed allocator header is
rejected rather than repaired. The 1 MiB whole-object limit is a PoC
bound. The underlying GE/O v1 disk layout is unchanged; the allocator is
an additive interpretation of the existing Space header user part.

## Pathless native O storage — 23 October 2026

**Source state:** implementation commit
`e3843009a79f762f30e70a459fffafb7c85e9a8f` (`ge/o: route native O
storage through direct SD blocks`), plus this documentation follow-up.
The dedicated gate, registration gate, byte-object gate and the nine
existing O-only gates were run with KVM on disposable QEMU images.

**Implemented (Level A only)**

- A `PARTUUID=` O volume is found by parsing GPT directly from
  enumerated `SDunit`s (`sdunititer`, `sdunitready`, `oblockgptpart`),
  with no `#S` directory read or `namec`.
- GE's block reads, writes, sync and cache flush for this O instance go
  through `sdblockrw`/`sdblockflush` and the controller's `SDifc.bio` /
  raw flush path. The legacy `#S/.../raw` flush reopen is bypassed for
  this instance. No GE/O v1 format or OID allocator change.
- `opath=1` instrumentation counts the kernel `namec`, `newchan`,
  `walk`, `devwalk`, `cmount` and path-`sysexec` entry points.
  `oblocktest=1` checks partition-relative bounds and `SDmaxio`
  clamping; `sdflushlog=1` confirms the virtio 0x35 flush reached
  `vioblkreq`.
- `tools/test-o-pathless.sh` covers three boots of one disk with
  registration/persistence, missing PARTUUID, a malformed GPT header on
  another unit, flush evidence and the zero-delta storage window.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-pathless.sh
tools/test-o-register.sh
tools/test-o-bytefile.sh
for gate in test-o-boot-omp test-o-boot test-o-exec test-o-exec-args             test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" > "build/verification/$gate-pathless.log" 2>&1
done
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; `9pc64` md5 `d9f3184e9ab545ef9a433fb220e87d0d`, test-only `9pc64mp` md5 `97ea4dbc4241ff41e84b4dd7b412e108`. `build/verification/build-pathless-final.log` |
| selfroot | **PASS** | `build/selfroot` at `2c7a244` with the `e384300` binaries. `build/verification/selfroot-pathless-final.log` |
| Pathless Level A | **PASS** | `PASS: Level A pathless native GE/O storage window, persistence and bounds`. Three boots: `opath: volopen-enter/opened/started namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1` unchanged, i.e. zero events added by O open/GE start. `oblocktest` four PASS markers and `sdvirtio: flush PASS` on every boot. `build/verification/test-o-pathless-final.log` |
| Missing/malformed partition | **PASS** | Both cases printed `no disk has that partition`; `opath: volopen-enter` and `volopen-error` were identical (`namec=34 newchan=94 walk=49 devwalk=70 mount=7 exec=1`), so failed discovery did not fall back to `namec`. The later `panic: boot process died: fail` is the expected init-exit diagnostic for these negative cases. `build/verification/test-o-pathless-final.log` |
| Local OID registration | **PASS** | Unmodified `tools/test-o-register.sh`: four boots, explicit-ID collision skips, monotonic registration, two-process distinct IDs, corrupt-state rejection and unsupported-mode error. `build/verification/test-o-register-pathless.log` |
| Native byte objects | **PASS** | Unmodified `tools/test-o-bytefile.sh`: three boots, empty/binary/multi-chunk values, equal bytes/distinct OIDs, revision without allocation and REPL unsupported mode. `build/verification/test-o-bytefile-pathless.log` |
| Existing O-only gates | **PASS** | `test-o-boot-omp`, `test-o-boot`, `test-o-exec`, `test-o-exec-args`, `test-o-handles`, `test-ge`, `test-o-volume`, `test-o-objects`, `test-o-space`. `build/verification/test-o-*-pathless.log` |
| Bootstrap pathless (Level B) | **NOT YET** | Executed chain still runs `initcode.c:startboot` `bind`/`open /dev/cons`/path-exec `/boot/oinit`; `proc0` also seeds `namec("#/")`. An attempted in-`initcode` O branch exceeded the one-page image and faulted in `proc0`'s `kmap`/`memset`; it was reverted. |
| Console pathless (Level C) | **NOT YET** | `boot.py` binds devices, spawns `/boot/kbdfs`, opens `/dev/cons`; `p9console.c` uses fd 1 and `/dev/consctl`. No direct input/REPL path was implemented or claimed. |

**Measured Level A transcript** (final gate, boot 1; boots 2 and 3 are
identical in the window):

```text
opath: volopen-enter  namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
oblocktest: PASS in-range-read
oblocktest: PASS read-at-end
oblocktest: PASS oversized-read-clamped
oblocktest: PASS write-past-end
o: O volume #S/sdF0/data@68157440, 192 MiB, opened without FS (native SD block)
opath: volopen-opened namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
opath: volopen-started namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
sdvirtio: flush PASS
```

The pre-window counts are the positive control: the legacy `/boot`
bootstrap really did allocate Chans, walk names and path-execute before
the storage window. The zero deltas are the Level A result. The complete
call-chain audit, classification and B/C blockers are in
[O-BOOT-DEPENDENCIES.md](O-BOOT-DEPENDENCIES.md).

**Remaining limits:** Level A applies to one active O volume selected by
`PARTUUID=` on an enumerated SD unit. Explicit device specs still use the
legacy `namec` path; a second simultaneous O volume, hot unplug, remote
observation and machine-wide identity are not pathless. The bootstrap and
console remain the B/C blockers. No physical disk was written or
reformatted.

## Phase C validation record

### Static audit — 21 October 2026

**Checked:** 21 October 2026 against the Phase B commit
`5413fc6a1e801f377cd3f428336b3543d7ddf83d`.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| GitHub source and document availability | **PASS (static)** | `README.md`, `AGENTS.md`, `docs/POC.md`, `docs/STATUS.md` and `docs/O-FORMAT.md` were read from the repository. |
| Documentation navigation | **PASS (static)** | 21 relative Markdown links and 32 backtick-formatted source/tool/document path references in those five Markdown files resolved to entries in the repository tree at the checked commit. This is **not** an exhaustive scan of all inherited source comments. |
| Phase B file metadata | **PASS (static)** | Git trees before/after Phase B were compared; the 22 modified executable tool files retained executable mode, and no tracked file's mode changed. |
| Build dependency review | **PASS (source inspection)** | `WHAT=all tools/build.sh` produces the root binaries used by `tools/selfroot build/selfroot`. `WHAT=kernel` alone does **not** prepare `build/selfroot/amd64/bin/gefs` or `micropython`. |

### Runtime execution — 22 October 2026

**Executed:** 22 October 2026 against
`f23d5624a153bd3645be8f8b540b3bc243ebabec` on a Debian/amd64 host with
accessible `/dev/kvm`, QEMU, OVMF and mtools. The existing prepared
9front `base.qcow2` was reused by `tools/vm-setup`.
Gate start times (UTC, recorded in `build/verification/*.timestamp`):
GE 15:11:44, O volume 15:12:23, O objects 15:13:26, Python/O 15:13:56,
O init 15:14:31.

| Check | Result | Evidence |
| --- | --- | --- |
| Host/tooling and KVM | **PASS** | `tools/vm-setup` found the prepared base image; its package, OVMF and `/dev/kvm` checks passed. The five gates ran with the target's `-accel kvm -cpu host`. `build/verification/vm-setup.log` |
| Full amd64 build | **PASS** | `WHAT=all tools/build.sh` exited 0 and printed `BUILD-DONE`; `build/amd64/9pc64`, `bootx64.efi`, `gefs` and `micropython` were present. `build/verification/build.log`, `build/amd64/session.log` |
| selfroot preparation | **PASS** | `ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot` exited 0. The generated clone's origin is `https://github.com/pereuna/Plan2001-O.git`; its HEAD is `f23d562`, and the expected `amd64/bin/gefs` and `amd64/bin/micropython` are executable. `build/verification/selfroot.log` |
| GE gate | **PASS** | `tools/test-ge.sh` exited 0: `PASS: GE volume, raw key/value, no FS`; raw value crossed reboot (0 → 1 → 2). `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile gate | **PASS** | `tools/test-o-volume.sh` exited 0: `PASS: O volume, no FS`; the O volume persisted 0 → 1 → 2 and wrong-profile opens were rejected. `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects gate | **PASS** | `tools/test-o-objects.sh` exited 0: `PASS: native O objects, no FS`; both OIDs were restored on the second boot. `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O gate | **PASS** | `tools/test-o-space.sh` exited 0: `PASS: Stage 4 Environment, code and Space graph from O (no FS)`; boot 2 restored the graph (41 → 42), same alias/OID, and committed version 2. `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init gate | **PASS** | `tools/test-o-boot.sh` exited 0: `PASS: three O-only boots, persistent Counter and run() from O (no FS)`; one disk, `run()` returned 1, 2, 3, Counter OID stayed 7, no root FS mount. `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log` |

The `test-o-space` serial log also contains
`panic: boot process died: unknown` after each
`space: O: committed init version N` line. The gate's required
assertions and exit status are **PASS**; this shutdown-path diagnostic
is recorded as an observation and was not used to change the gate or
the specification.

## Process-local O handle experiment — 22 October 2026

**Source state:** this experiment is committed as
`30e9ae16c0b7ab82fcc6404cdffddbbb246c8ebd`. The results below were
first run from its working tree before that commit; the same handle
regression was rerun in the final native-exec suite recorded below.

**Design:** each `Proc` owns an opaque eight-entry table of `Ohand`
sessions. An entry holds an `Ospace *` and a `Ref`. Table lookup takes a
temporary reference under the table lock, then releases the lock before
calling storage. Explicit close removes the entry under the lock and
drops the ownership reference; the last reference calls
`onativeclose()`/`ospaceclose()`, which aborts an unfinished transaction
and never commits. Process exit and successful `exec` detach all entries
under the lock, then release sessions outside it. Failed `exec` does not
call the cleanup hook. Children start empty, including `RFMEM` children.
The global volume instance and volume authorization are unchanged.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 114 programs; kernel and loader present. `build/verification/build-ohandles.log` |
| selfroot binaries | **PASS** | `build/selfroot/amd64/bin/{gefs,ohandle}` present and executable. `build/verification/selfroot-ohandles.log` |
| Process-local O handles | **PASS** | one ESP + O boot, no FS root; isolation, independent sessions, explicit-close and exit capacity, abort on close/exit, successful/failed `exec`, and invalid/double close. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC): process-local handles 15:35:46,
GE 15:36:19, O volume 15:36:30, O objects 15:37:31, Python/O 15:37:58,
O init 15:38:29.

## Native executable-object experiment — 22 October 2026

**Source state:** clean tree at
`4678fada0d66f83b310291320e57aba12068934d`. This commit fixes the two
review findings against `ab3a77e`: the exec stack now reserves
`sizeof(Tos)` before placing `argv` and its strings, and segment
addresses (`abss`/`ebss`) remain `uintptr` through both loader paths.
The target now asserts `argv[0]`, intact `Tos` fields and a high BSS
page; host seeding enlarges the target's BSS header to `0xffffffff` so
the BSS extent crosses 4 GiB. This STATUS update is a docs-only follow-up
commit.

**Loader:** `OEXECUTE`/`oexecute(space, oid)` resolves the handle only in
the calling process, retains its session reference for one bounded
whole-object read (`Objexecmax` = 8 MiB, a single published version),
then releases the reference before parsing. `execparse` is shared with
`sys_exec` and validates the amd64 a.out magic, header length,
text/data/bss arithmetic and bounds, object length, entry point and
user-address limits. `execo` builds ordinary text/data/BSS segments from
the object bytes, then uses the shared `execcommit` process-transition
path (segments, stack, close-on-exec handles, text/args, notes, MMU
flush). Failure before commit leaves the old image and handles intact;
there is no pathname, `Chan`, `Fid`, Qid, mount or 9P step.

The target program `ohello` exists only as an O object. `/boot/oexec`
is an embedded regression harness (test bootstrap, not the loader).
`tools/mkovol` seeds the target at `OID_EXEC_TEST` and malformed bytes
at `OID_BADEXEC_TEST` through the existing `-i` seed layout.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
NATIVEEXEC=build/selfroot/amd64/bin/ohello \
  tools/mkovol build/amd64/oexec-o.img 192 tools/odemo.py
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 116 programs; kernel and loader present. `build/verification/build-bssboundary.log` |
| selfroot binaries | **PASS** | `gefs`, `ohello`, `oexec` built; selfroot at `4678fad`. `build/verification/selfroot-bssboundary.log` |
| Native executable object | **PASS** | one ESP + O boot, no FS root; child loaded `ohello` by OID, checked `argv[0]`, intact `Tos` fields and a BSS page beyond 4 GiB, printed both target markers, exited 0, parent observed success; missing OID and a truncated valid header failed while the handle remained usable; close-on-exec handle rule held. `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| Process-local O handles | **PASS** | all isolation, lifetime, abort, exec and error checks. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC, clean tree at `4678fad`): native executable
16:50:09, process-local handles 16:50:33, GE 16:50:56, O volume
16:51:07, O objects 16:52:07, Python/O 16:52:35, O init 16:53:05. The
binary-grep false positive in `test-o-boot.sh` remains fixed; no
assertion was weakened.

## Native O MicroPython experiment — 22 October 2026

**Source state:** HEAD `122e585a172f39bdc1fb31eca79841acfe2e6d27`, with
this experiment's source changes in an **uncommitted working tree**. The
binaries and images below were built from that tree; this record is not
a claim about a clean committed revision. The previous native-executable
results above are unchanged history.

**Implemented:** `oexecute(space, oid, argv, argc)` passes a bounded,
validated argument vector, copies the strings to kernel-owned memory
before the process image is replaced, and places `Tos`, strings and argv
on the exec stack without overlap. The native loader marks its
image-less text/data/BSS/stack segments `SG_NOSWAP`, and `dupseg()`
accepts a data segment with no file image, so `rfork` and the page
reclaimer do not treat the O-loaded bytes as file-backed pages. The
small embedded `/boot/oinit` harness opens the O volume and `init` Space
and executes `OID_MP_EXEC` (`0x4f45584543000003`), passing the argv that
`sys/src/cmd/micropython/main.c` requires. The dedicated `pc64omp`
kernel configuration embeds only `oinit` and `kbdfs`; the ordinary
`pc64` configuration still embeds `/boot/mp`.

The seed builder in `sys/src/cmd/gefs/ream.c` now builds a normal
multi-level GE tree from the sorted seed records, so a large executable
is not limited to one catalog leaf. `tools/mkovol MPEXEC=FILE` seeds the
real MicroPython executable **byte for byte**; `tools/oseed.py` reads
the prepared copy back, and `/boot/oinit` prints the SHA-256 of the
object read from O. The BSS-header patch remains confined to the
`NATIVEEXEC`/`ohello` fixture.

**Object and limits:** MicroPython 2,191,593 bytes, SHA-256
`1487111f358ac845db3ca2b9485a561e722675c59c0632ca105ddd02c13b7e53`;
`oinit` 76,349 bytes, SHA-256
`70b4d0050606507fa46e3f215e6f017e2f36e096083a25154c5656d677fa3f18`.
`Objexecmax` remains 8 MiB. The test O image is 192 MiB; no disk-format
revision was added.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-boot-omp.sh
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build, both kernels | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `8df642b1daaccaa2c539005a4aaa30e0`, `build/amd64/9pc64omp` md5 `aa1a3ae158a6809bcf7254c1edbe366c`. `build/verification/build-omp.log` |
| selfroot | **PASS** | `build/selfroot` at HEAD `122e585`; `oinit`, `gefs` and `micropython` present. `build/verification/selfroot-omp.log` |
| Generated boot contents | **PASS** | `build/amd64/pc64omp.rootc.c` has no `addbootfile("mp"` and has `oinit`/`kbdfs`; `build/amd64/pc64.rootc.c` still has `mp`. Asserted by the new gate. |
| MicroPython from native O | **PASS** | one ESP + O disk, no FS root, dedicated `9pc64omp`; three boots of the same disk: `run()` 1 -> 2 -> 3, Counter OID/alias 7/7, object SHA-256 equals the host binary; REPL evaluated `OINIT-REPL 42`; missing/malformed objects returned errors with the O handle preserved. `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl.log`, `build/amd64/ompbootvm/check.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`; argv/Tos/BSS and rollback assertions. `build/verification/test-o-exec-omp.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-omp.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and embedded O init all exited 0. `build/verification/test-ge-omp.log`, `test-o-volume-omp.log`, `test-o-objects-omp.log`, `test-o-space-omp.log`, `test-o-boot-embedded.log` |

Log timestamps (UTC, completion of each log write): build and selfroot
19:10:25; O-loaded MicroPython 19:11:15; native executable 19:11:43;
handles 19:12:05; GE 19:12:16; O volume 19:13:16; O objects 19:13:44;
Python/O 19:14:15; embedded O init 19:14:49. The documented
`test-o-space` shutdown diagnostic (`panic: boot process died: unknown`)
is unchanged and is not a gate failure.

**Remaining limits:** the O-loaded path is demonstrated only by the
dedicated `pc64omp` test configuration and documented OID. The ordinary
`pc64` boot still embeds MicroPython through `devroot`; `kbdfs` and the
small `oinit` harness are still embedded. There is no program catalog,
architecture selection, dynamic linking, permissions framework, or
general executable-object format support. The on-disk format is
unchanged.

## Native O exec argv copy fix — 22 October 2026

**Source state:** HEAD `b41a102384efa81b17cdc5f923415b123341f8ca`, with
the fix in an **uncommitted working tree**:
`sys/src/9/port/sysproc.c`, `sys/src/cmd/oexec/oexec.c`,
`sys/src/cmd/ohello/ohello.c`, `docs/O-FORMAT.md`, this file and the new
`tools/test-o-exec-args.sh`. This record is not a claim about a clean
committed revision.

**Source-review conclusion (not runtime evidence):** the previous
`execo()` measured each user string with `vmemchr()`, allocated from that
total, then reread `uargv[i]` and used unbounded `strlen()` before
`memmove()`. An RFMEM peer could change a pointer, terminator or string
between passes, so the later copy was not bounded by the earlier check.
The fix:

- snapshots the bounded pointer array once into kernel storage after an
  `okaddr()` range check; later code never rereads the live array;
- copies each string with `execargcopy()` into kernel memory, checking
  each page with `okaddr()` and never writing past the remaining
  destination capacity;
- accepts a length and terminating NUL only from the copied bytes, then
  uses bounded scans on that private snapshot;
- enforces `Oargmax = 32` and `Oargbytes = 16 KiB` including every NUL,
  plus the existing `Tos`, argv-pointer, alignment and 16 MiB stack
  checks; and
- reports bad pointers as ordinary `-1` syscall errors via `okaddr()`
  rather than the note-posting `validaddr()`, so the caller can verify
  its O handle after a failed call.

Concurrent modification is explicitly not an atomic all-argument
snapshot: a bounded copied result or a clean error is accepted. Failure
before process transition still releases the object buffer, argument
allocations, session reference and any partially constructed segments.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-exec-args.sh
tools/test-o-boot-omp.sh
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build, both kernels | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `d028692a55eda1a6ae60215b51c7ffda`, `build/amd64/9pc64omp` md5 `24a8c66c27ac40f02b683326c8a77253`. `build/verification/build-args.log` |
| selfroot | **PASS** | HEAD `b41a102`; `oexec` SHA-256 `68d4fe842c254ec8125c3de361a6b97032fc5d0447c8dd2115af72fe7755b6f0`, `ohello` SHA-256 `2d1b022e29aafe95333cf6452601262c50a0777b6ec70e4b39800f46d8f16afd`. `build/verification/selfroot-args.log` |
| Focused native-exec argv gate | **PASS** | synthetic `argc == 0`, 5 valid arguments including an empty one, 32 arguments, the exact 16 KiB aggregate boundary accepted, one byte over rejected, missing NUL, negative and excessive argc, nil and misaligned argv, invalid string pointer, cross-page string, repeated failures with usable handles, and 32 shared-memory mutation attempts. `build/verification/test-o-exec-argv.log`, `build/amd64/oexecargsvm/serial.clean.log` |
| O-loaded MicroPython | **PASS** | `PASS: MicroPython loaded from a native O object (no embedded mp)`; three boots and the REPL smoke test. `build/verification/test-o-boot-omp-args.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`. `build/verification/test-o-exec-existing.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-args.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and embedded O init all exited 0. `build/verification/test-ge-args.log`, `test-o-volume-args.log`, `test-o-objects-args.log`, `test-o-space-args.log`, `test-o-boot-args.log` |

Log timestamps (UTC, completion of each log write): build 19:42:10;
selfroot 19:42:11; focused argv 19:42:34; embedded O init 19:43:32;
native executable 19:43:56; handles 19:44:19; GE 19:44:29; O volume
19:45:29; O objects 19:45:56; Python/O 19:46:27; O init 19:47:02. The documented
`test-o-space` shutdown diagnostic (`panic: boot process died: unknown`)
is unchanged and is not a gate failure. No focused-gate failure or kernel
panic occurred in the recorded run.

## Reproduction on a prepared Debian/amd64 host

Run from the repository root with a **committed, clean source tree**.
Verify `git status --short` and record `git rev-parse HEAD` first:
`tools/overlay` can include working-tree files, whereas
`tools/selfroot` clones **committed HEAD**, so testing uncommitted
sources risks mixing incompatible binaries and code.

`tools/vm-setup` checks Debian packages, OVMF, the selected VM
accelerator and a pinned 9front bootstrap image. The **O-only QEMU suite
(nine gates) currently expects KVM**: `tools/targets/amd64` supplies
`-accel kvm -cpu host` directly to those guest invocations.
`VM_ACCEL=tcg` is supported by the bootstrap `tools/vm` path, but it
does **not** automatically switch these standalone gate scripts to TCG.
Use a host with accessible `/dev/kvm` for the commands below.

```bash
set -euo pipefail
mkdir -p build/verification
git rev-parse HEAD | tee build/verification/commit.txt
git status --short

tools/vm-setup 2>&1 | tee build/verification/vm-setup.log
WHAT=all tools/build.sh 2>&1 | tee build/verification/build.log

# Work around tools/selfroot's inherited Plan2001 origin default
# until that separate functional cleanup is made.
ORIGIN=https://github.com/pereuna/Plan2001-O.git \
  tools/selfroot build/selfroot 2>&1 | tee build/verification/selfroot.log

test -s build/amd64/9pc64
test -s build/amd64/9pc64mp        # test-only historical harness kernel
test -s build/amd64/bootx64.efi
test -x build/selfroot/amd64/bin/gefs
test -x build/selfroot/amd64/bin/micropython
test -x build/selfroot/amd64/bin/ohandle
test -x build/selfroot/amd64/bin/oexec
test -x build/selfroot/amd64/bin/ohello
test -x build/selfroot/amd64/bin/oinit

for gate in test-o-boot-omp test-o-boot test-o-exec-args test-o-exec \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate.log"
done
```

The normal human REPL uses a fresh disposable image; an existing
`build/amd64/repl.img` is kept, not reseeded:

```bash
tools/mkrepl                     # refuses to replace an existing image
./repl_tui.sh                    # UEFI -> 9pc64 -> oinit -> O MicroPython
```

**Safety:** these scripts create, overwrite or reformat disposable
images under `build/`. Run them in a dedicated development checkout;
**never substitute a real disk or partition**. Do not use
`tools/selfroot -p DEV`, `dd` to block devices or `tools/mkovol`
on a real device as a regression shortcut. Build scripts may require
significant free space for the VM and disk images.

`set -euo pipefail` makes a failed build, precondition or QEMU gate
stop the sequence; `tee` saves the output and does not conceal a
nonzero exit status. **A test's name or log-file existence is not
evidence of PASS.**

## Runtime gate acceptance and logs

| Gate | Required check | Main outputs |
| --- | --- | --- |
| Build | Exit 0, `BUILD-DONE` in the build session, normal `9pc64` and test-only `9pc64mp` kernels + UEFI loader + `gefs` + MicroPython + `ohandle` + `oexec`/`ohello`/`oinit` binaries present | `build/verification/build.log`, `build/amd64/session.log`, `build/vm/serial.log` |
| GE | `tools/test-ge.sh` exits 0 and reports `PASS: GE volume, raw key/value, no FS`; same raw value survives reboot. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile | `tools/test-o-volume.sh` exits 0 with `PASS: O volume, no FS`; wrong-profile open attempts are rejected. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects | `tools/test-o-objects.sh` exits 0 with `PASS: native O objects, no FS`; two OIDs survive reboot. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O | `tools/test-o-space.sh` exits 0 with its Environment/code/Space graph PASS; same alias/OID and O code survive two boots. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init | `tools/test-o-boot.sh` exits 0 with `PASS: three O-only boots`; normal `9pc64` + `oinit`, one disk, `run()` yields 1, 2, 3, same Counter OID, no root filesystem mount, O object hash equals the host binary | `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log`, `boot1.log`–`boot3.log` |
| O handles | `tools/test-o-handles.sh` exits 0 with both its per-check markers and `PASS: process-local O handles`; isolation, independent sessions, close/exit capacity, abort, exec rules and invalid handles pass | `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| O execute | `tools/test-o-exec.sh` exits 0 with `PASS: native executable object from O, exec and rollback`; the O-only target marker appears once, the child exits successfully, missing/malformed loads preserve the caller's handle, and native exec closes handles | `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| O argv | `tools/test-o-exec-args.sh` exits 0 with `PASS: native O argv bounds, rollback and race`; valid/empty/32-argument argv, the exact aggregate boundary, over-limit and malformed copies, bad counts/pointers, repeated rollback with usable handles, and shared-memory mutation attempts pass, with the synthetic argv/Tos/BSS markers appearing exactly once | `build/verification/test-o-exec-argv.log`, `build/amd64/oexecargsvm/serial.clean.log` |
| O MicroPython | `tools/test-o-boot-omp.sh` exits 0 with `PASS: MicroPython loaded from a native O object (no embedded mp)`; the generated normal `pc64` boot contents contain `oinit`/`kbdfs` and no `mp`; three boots of one disk yield `run()` 1, 2, 3 with the same Counter OID/alias; `tools/mkrepl` + the REPL evaluate an expression and keep a value across a restart; missing/malformed objects and an older image without the interpreter return clear diagnostics and preserve the handle where the object exists | `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl1.log`, `repl2.log`, `check.log`, `legacy.log` |

Individual QEMU serial logs may be **overwritten between boots** by
their scripts. The captured `build/verification/*.log` output and
`test-o-boot.sh`'s three-boot transcript are the primary evidence.
Preserve relevant failure logs or copies before rerunning a gate.

For each execution record **UTC timestamp, commit SHA, host/VM setup,
exact command, exit status, PASS/FAIL/NOT RUN and log path**. If a gate
fails, record its first relevant diagnostic and leave its status FAIL;
do not edit the test to manufacture a PASS. Do not add historical
source-branch logs as evidence of execution at a newer commit.

## Kernel driver operation map — static inventory

**What this is:** a checked-in, deterministic source analysis of the kernel
driver surface, not a runtime change or a claim about device behaviour.
Artifacts:

- [KERNEL-OPMAP.md](KERNEL-OPMAP.md) — generated coverage report, operation
  tables, representative chains and unresolved-work list.
- [KERNEL-OPMAP.json](KERNEL-OPMAP.json) — the machine-readable operation map.
- [KERNEL-OPMAP-NOTES.md](KERNEL-OPMAP-NOTES.md) — separate source-checked
  manual annotations (not generated).

**Source state:** kernel tree `sys/src/9` at commit
`c1c4bc9bd26b5d00d5e4896ac9ba28b479ea9fdf`, clean at generation; source
fingerprint `bacd6bc3245bb33ff47472f1ee80f6816625e8e2d10305bdff63a12197a0a071`.
The generator is `tools/kernel_opmap.py` v1.

**Commands run**

```bash
python3 tools/kernel_opmap.py --write
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Regeneration | **PASS** | `--write` wrote both artifacts; deterministic output is sorted and contains no timestamps or machine-specific absolute paths. |
| Staleness check | **PASS** | `--check` reported `kernel operation map: up to date`. |
| Analyzer tests | **PASS** | 10 tests: comments/strings, multiline Qid/Cmdtab branches, if-based Qid branches, indirect callbacks, duplicate symbols, conditional compilation, deliberate parse failure, manual commands, determinism/no allowlist, and per-file accounting. |
| Coverage | **PASS (static)** | 226 files scanned (167 C, 37 headers, 7 assembly, 4 configs, 11 build helpers); 167 C files parsed; 69 registrations; 976 exposed operations; 613 shared chains; 59 native entry points. |
| Build split | **PASS (static)** | Normal amd64 `pc64`: 148 active C files, no unresolved objects; `pc64mp` test-only has the same object selection; `arm64/qemu` (planned) has 93 active C files and explicit unresolved `devbridge`/`devpci`; `riscv64` source tree is absent. |
| Representative chains | **PASS (source-checked)** | GE/O `OVOLOPEN` still reaches `Chan`/`Dev` through `gevolume` before `oopen`/`geopen`; devsd Qpart reaches `SDifc.bio` with NVMe/AHCI/virtio/loop/RAM candidates; kbd reaches `inb`; console reaches the `PhysUart.putc` interface; ethernet reaches the queue-kick `Ether.transmit`; `sdgen` exercises dynamic Qid dispatch. See the generated chain tables and NOTES. |
| Unresolved visibility | **PASS (static)** | The JSON/report keep partial and unresolved edges explicit: 45 hardware-primitive chains, 82 controller-primitive chains, 868 partial operations and 63 unresolved operations. Duplicate non-static symbols across architecture trees remain ambiguous rather than guessed. |

**Logs:** `build/verification/kernel-opmap-write.log`,
`build/verification/kernel-opmap-check.log` and
`build/verification/kernel-opmap-tests.log` (ignored build evidence).

**Scope boundary:** `kbdfs` is embedded as a `bootdir` binary but remains a
user-space 9P service; only its kernel endpoints (`devcons`, `devkbd`,
`devuart`, `screenputs`, `PhysUart` callbacks) are in this inventory.

No kernel source, syscall table, driver, libc or boot behaviour was changed.

## Known limits and follow-up work

- GE/O has no native graph edge, tag or indexed namespace relation API.
- Python logical object OIDs live inside a whole `OID_GRAPH` payload;
  native per-Python-object storage and incremental updates are absent.
- The normal `pc64` configuration embeds no MicroPython: `oinit` loads
  the real interpreter from a native O object by the fixed `OID_MP_EXEC`.
  The bounded loader still has no program catalog, architecture selection,
  permissions, dynamic linking or general object-loading contract.
  Inherited `devroot`, `oinit`, `kbdfs` and the separate `ohandle`/`oexec`
  regression harnesses remain. The `pc64mp`/`9pc64mp` kernel is test-only
  for historical embedded-MicroPython gates and is never a normal or
  fallback boot path.
- Native O Space handles are now process-local, but handle inheritance
  and cross-process transfer are not implemented; each process has at
  most eight handles. The volume instance remains global, there is no
  per-volume/per-Space authorization, and this is not a complete
  capability model.
- The process-local handle table is independent of `Fgrp`, `Chan`,
  namespaces and 9P, by design for this experiment.
- Crash/corruption recovery, incomplete transactions, concurrency,
  performance and physical hardware behavior lack production validation.
- Inherited 9front/Monolith code and legacy FS/9P tests are separate from
  the nine O-only gates. Preserve them as needed for bootstrap but do not
  treat them as native GE/O architecture.
- `tools/selfroot` still defaults its remote origin to
  `pereuna/Plan2001.git`, and the legacy `tools/test-selfroot.sh`
  still clones that repository. The 22 October run used the documented
  `ORIGIN=https://github.com/pereuna/Plan2001-O.git` override; the
  default and that legacy test still require a **separate functional
  tools fix**, which this validation intentionally does not make.
