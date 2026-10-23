# Boot Experiment B: first native userspace process without a pathname

**Date:** 23 October 2026. **Source state:** implementation commits
`ba6b8ab325d5e222539b5a050bedfd1a4f636d7b` (Boot Experiment B) and
`ddf98993353c02f8ef6df59e715cf7e37aec904a` (pre-fault the `Tos` page),
plus this documentation follow-up. The runtime evidence below was
produced from that source content with QEMU and disposable images only.

**Verdict: Boot B PASS.** This is **Boot Experiment B**, not the older
top-down **Storage Level B** (MicroPython loaded from GE/O). It does not
use GE/O, `OID_MP_EXEC`, MicroPython, a console, persistent storage or a
filesystem.

## Question and scope

Can the same kernel that passed Boot Experiment A create its first
genuine amd64 ring-3 userspace process from an already available binary
image, without constructing a pathname namespace, accessing a filesystem
or invoking legacy `exec(path)`?

Experiment B answers only that. The image is a build-time embedded flat
byte image; it is not a `/boot` file, a `Chan`, a 9P object or an OID.
The source-tree filename used to build it is not a runtime pathname.

## Result and acceptance

| Check | Result | Evidence |
| --- | --- | --- |
| Normal machine initialization and scheduler entry with `oboot=user` | **PASS** | `OBOOT-B: MAIN entry`, `HANDOFF`, `KERNEL-READY`; no root or `init=` in `plan9.ini`. |
| Kernel creates the first process from bytes and validates the image | **PASS** | Flat image `image=113` bytes, `text=73`, entry `0x200028`; magic, expanded entry, alignment, text length, image length and zero data/BSS are checked before use. |
| Transfer to real ring 3, not a kernel trampoline | **PASS** | First user instruction at `0x200028`; observed user `cs=0x2b`, `ss=0x23`, `user=1`. |
| At least two user-originated syscall/trap observations | **PASS** | User `alarm` (`nr=6`) and `sleep` (`nr=17`), with entry and return records; a third `sleep` proves continuation after return. |
| User code continues after syscall return | **PASS** | `SYSCALL-RETURN nr=6` is followed by `SYSCALL-ENTRY nr=17` at a distinct user PC; later `nr=17` entries/returns continue. |
| Legacy chain and path machinery absent over the measured boot | **PASS** | `userinit=0 proc0=0 init0=0`; `namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`, both before user entry and after four user syscalls. |
| No `up->slash`/`dot`, no FD/path/console setup | **PASS** | `slash=nil dot=nil`; `fgrp/egrp/rgrp=nil`, no `/dev/cons`, no `bind`, no `open`, no `exec`. |
| No panic, user fault or unexpected exit before success | **PASS** | Gate rejects `panic`, `suicide`, `kernel fault`, `user fault`, and non-user syscall records. |
| Boot A control still passes | **PASS** | `oboot=probe`: `KPROC-RUNNING`, two heartbeats, legacy counters zero. |
| Normal O boot control still passes | **PASS** | `tools/test-o-boot.sh`: three O-only boots, `run()` 1 -> 2 -> 3. |
| Native O storage control still passes | **PASS** | `tools/test-o-pathless.sh`: `PASS: Level A pathless native GE/O storage window, persistence and bounds`. |
| Build route | **PASS** | `WHAT=all tools/build.sh`, `BUILD-DONE`. |

## Executed call graph

```text
UEFI loader
  -> main.c:main
  -> bootargsinit (reads plan9.ini oboot=user)
  -> normal machine/memory/trap/clock/PCI/APIC/timer/page initialization
  -> procinit0, initseg, links
  -> chandevreset (device reset hooks only; not chandevinit)
  -> preallocpages, pageinit
  -> o_user_bootstrap                         main.c:272-276, ouser.c:139
  -> kproc("*ouser*", ouserproc)              proc.c kproc
  -> schedinit / sched
  -> ouserproc                                ouser.c:74
       ouserimage (image validation)           ouser.c:34
       newseg text + page copy
       newseg stack + zeroed top stack page (Tos slot)
       up->kp=0, procsetup, flushmmu
  -> touser(sp)                               l.s touser, SYSRET
  -> ring 3 at 0x200028                       cs=0x2b, ss=0x23
  -> user image: alarm(0), sleep(100), sleep(100), sleep loop
  -> syscallentry / syscall / dosyscall       trap.c, sysproc.c
  -> kexit / SYSRET back to user
```

The first user-space instruction is the linked image entry at
`UTZERO+0x28`. `touser()` is the existing architecture transition: it
loads `UTZERO+0x28` into RCX, flags `0x200` into R11, the supplied user
stack into SP, zeroes the kernel scratch registers, and executes
`SYSRETQ`. The observed user selectors are `cs=0x2b` and `ss=0x23`.

`execo()` was deliberately **not** called. `execo()` ends in
`execregs()` (`sysproc.c:494`, `:670`), which writes `up->dbgreg`, the
register frame of an existing syscall/trap. A newly scheduled kernel
process has no such frame until it has entered user mode. Experiment B
therefore reuses the proven segment/page primitives and the existing
`touser()` transition, and validates the image itself.

## What is required, what is legacy

| Category | Boot Experiment B |
| --- | --- |
| **Indispensable** | `Proc`/kernel stack, PID and scheduler state; one process `Pgrp` supplied by `kproc`; a text segment; a stack segment; a zeroed top stack page containing the `Tos` slot; the user stack pointer; `touser()`/`SYSRET`; the existing syscall entry/return path; the existing timer for `sleep`. |
| **Not used** | `userinit`, `proc0`, `init0`, `startboot`, `touser`'s argv/initcode setup, `namec`, `cclone`, `Chan`, `Dev` open/read/write, `bind`, `mount`, `exec`, `rootmount`, `chandevinit`, `/dev/cons`, `kbdfs`, `/boot` entries, O storage, MicroPython. |
| **Residual but unused** | The shared `Pgrp` created by `kproc` (`kpgrp`); the `Proc`'s `text`/`user` strings; `chandevreset` and its reset-time effects. |
| **Explicitly nil** | `up->slash`, `up->dot`, `up->fgrp`, `up->egrp`, `up->rgrp`, `up->parent`, `up->tt`, `up->trend`; `up->alarm=0`, `up->parentpid=0`. |
| **Process state** | `up->kp=0`, `up->noswap=0`, `up->privatemem=0`, normal priority, `procsetup()` and `flushmmu()` before entry. |

`kproc()` still allocates a `Pgrp`; Experiment B does not claim a
structure-free process. It does not construct `Fgrp`, `Egrp` or `Rgrp`,
and no `Chan` is created. `chandevreset` still runs before the branch:
`rootreset` initializes static directory metadata and `sdreset` probes
the disk controller (visible as `#S/sdE: ich: sata-I with 6 ports`).
`chandevinit` is not called, so the device `init` hooks and the
`closeproc` kproc are absent. The normal `alarm` kproc is also absent;
the user probe's own `alarm(0)` is a syscall on its own process.

## User image and build mechanics

The user image is an ordinary source file, `sys/src/9/pc/obootuser.c`,
compiled and linked by the repository's normal amd64 tools:

```text
sys/src/9/pc/obootuser.c
  -> obootuser.$O                    (6c, kernel build tree)
  -> obootuser.out                   (6l -l -R1 -s, linked with libc)
  -> obootuser.i                     (xd byte array, mkfile %.i rule)
  -> included in sys/src/9/pc64/ouser.c
  -> copied to the first user text page at UTZERO
```

The source is deliberately trivial:

```c
void
_main(void)
{
	alarm(0);
	sleep(100);
	sleep(100);
	for(;;)
		sleep(1000);
}
```

No C startup, console, file descriptor, environment, directory lookup or
`/boot` program is involved. The linked plan9 a.out has a 32-byte
`Exec` header, an 8-byte expanded entry, 73 bytes of text, no data and
no BSS; the total image is 113 bytes. The kernel's `ouserimage()`
(`ouser.c:34`) checks:

* the `AOUT_MAGIC` header magic;
* the expanded entry is exactly `UTZERO+0x28`;
* the entry is word-aligned;
* text is non-zero, fits one page, and the image is not truncated;
* the whole image fits the user text page;
* data and BSS are zero (the probe has no writable data outside the
  stack).

A failure panics before any user instruction. The kernel `mkfile`
targets are `obootuser.out` and the `ouser.$O: obootuser.i` dependency
(`sys/src/9/pc64/mkfile:150-153`).

## Instrumentation

* `OBOOT-B:` markers are printed only when `plan9.ini oboot=user` is
  set.
* `oboot_user`, `oboot_userpid` and `oboot_usernsys` live in
  `sys/src/9/pc64/ouser.c` and are declared in `sys/src/9/pc64/fns.h`.
* `syscall()` in `sys/src/9/pc64/trap.c` prints `SYSCALL-ENTRY` before
  `dosyscall()` and `SYSCALL-RETURN` after it, only for the intended
  probe PID, only when `userureg(ureg)` is true, and only for the first
  eight syscalls. It records user PC, SP, CS, SS, syscall number and
  return value.
* After the fourth traced syscall it prints the legacy and path counters
  again, so the zero counts cover both the pre-entry window and the
  measured user/kernel activity.
* No counter is reset. The Boot A counters and the existing `opath`
  counters are read as-is.

Measured transcript from
`build/verification/test-oboot-user-boot-experiment-b.log`:

```text
Plan 9
OBOOT-B: MAIN entry oboot=user
...
OBOOT-B: HANDOFF user o_user_bootstrap
OBOOT-B: KERNEL-READY pid=1 entry=0x200028 text=73 image=113 slash=nil dot=nil
OBOOT-B: legacy-calls userinit=0 proc0=0 init0=0
OBOOT-B: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-B: KERNEL-TO-USER pid=1 pc=0x200028 sp=0x7fffffffef78
OBOOT-B: SYSCALL-ENTRY pid=1 nr=6 pc=0x200070 sp=0x7fffffffef60 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-RETURN pid=1 nr=6 ret=0x0 pc=0x200070 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-ENTRY pid=1 nr=17 pc=0x200061 sp=0x7fffffffef60 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-RETURN pid=1 nr=17 ret=0x0 pc=0x200061 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-ENTRY pid=1 nr=17 pc=0x200061 sp=0x7fffffffef60 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-RETURN pid=1 nr=17 ret=0x0 pc=0x200061 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-ENTRY pid=1 nr=17 pc=0x200061 sp=0x7fffffffef60 cs=0x2b ss=0x23 user=1
OBOOT-B: SYSCALL-RETURN pid=1 nr=17 ret=0x0 pc=0x200061 cs=0x2b ss=0x23 user=1
OBOOT-B: AFTER-SYSCALLS legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
```

The first `SYSCALL-ENTRY` is a real trap from `cs=0x2b` user code at
`0x200070`; its return is followed by another user syscall at
`0x200061`. The user PC values are distinct because the `alarm` and
`sleep` call sites differ; the repeated `sleep` entries prove continued
execution after each return.

## Commands and results

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-b.log
tools/test-oboot-user.sh 2>&1 | tee build/verification/test-oboot-user-experiment-b.log
```

Build: **PASS**, `BUILD-DONE`; normal `9pc64` md5
`f27c24cc102ed216b2deae098763a4b4`, test-only `9pc64mp` md5
`d260f7c2d934f9b268c5eb3057809d37`.

Boot B gate: **PASS**,
`PASS: Boot Experiment B ring-3 user probe, two syscall round trips`.
Serial copy:
`build/verification/test-oboot-user-boot-experiment-b.log`;
QEMU output: `build/amd64/obootuservm/`. The image was a disposable ESP
plus a 16 MiB empty data partition, built with:

```text
bootfile=/9pc64
console=0
user=glenda
oboot=user
```

There is no `root=` and no `init=` line. The guest has no O volume, no
root filesystem, no `/boot` program and no network. QEMU is stopped by
the gate after the success markers; the user task is in its sleep loop,
not crashed.

### Controls

| Control | Command | Result | Log |
| --- | --- | --- | --- |
| Boot A `oboot=probe` | disposable ESP, `oboot=probe`, 30 s QEMU run | **PASS**: `KPROC-RUNNING`, heartbeats 1/2, legacy/path counters zero | `build/verification/test-oboot-probe-experiment-b.log` |
| Normal O boot | `tools/test-o-boot.sh` | **PASS**: three O-only boots, MicroPython, `run()` 1 -> 2 -> 3 | `build/verification/test-o-boot-experiment-b.log` |
| Native O storage | `tools/test-o-pathless.sh` | **PASS**: Level A pathless native GE/O storage window, persistence and bounds | `build/verification/test-o-pathless-experiment-b.log` |

The negative `test-o-pathless` cases retain their documented expected
`panic: boot process died: fail` diagnostics for a deliberately missing
partition; the gate exits 0 and is not a Boot B failure.

## Limitations and non-claims

* The user probe is a 113-byte flat image with no console, no file
  descriptors, no environment, no shared libraries and no writable data
  outside its stack. It proves the execution boundary, not a general
  userspace runtime.
* The optional malformed/truncated image failure test is **NOT RUN**.
  The kernel has explicit pre-entry validation and panics on bad magic,
  entry, alignment, truncation, data/BSS or page overflow, but no
  injection mode was added in this experiment.
* `chandevreset` still executes before the branch, including
  `rootreset` metadata and hardware probes. Experiment B is a
  first-process/path bypass, not a device-reset bypass.
* The kernel still contains `Dev`, `Chan`, `namec`, `devroot`, O storage
  and the legacy `userinit`/`proc0`/`init0`/`initcode` code. Presence is
  not execution.
* This is not Storage Level B: no OID, GE/O volume, O-resident
  executable or MicroPython was read or executed.
* No on-disk format, storage path, default boot, `OID_MP_EXEC` or
  console service was changed.

## Concluding answer

**Boot B PASS.** The executed Boot B path has **no remaining dependence
on legacy pathname, FD or namespace machinery**: `slash`/`dot` are nil,
the process has no `Fgrp`/`Egrp`/`Rgrp`, and the measured counters are
zero for `namec`, `Chan`, walk, mount and path exec. The only residual
bookkeeping is the `Pgrp` created by `kproc` and the reset-time device
and directory metadata described above.

**Smallest proposed next step** (not implemented): keep this user
process and have it issue the existing non-file native O syscalls
`OVOLOPEN` with the already-supported `PARTUUID=` spec, `OSPACEOPEN`,
and `OEXECUTE` for an OID, using the direct `sdblockrw`/GPT/PARTUUID
provider. Because these calls originate in the ring-3 process, the
existing syscall path supplies `up->dbgreg`, so `execo()`/`execregs()`
can perform the next process transition without any pathname, `Chan`,
`bind`, `mount` or `/boot` lookup. The PARTUUID and test OID can be
embedded in the probe image or passed on its initial stack; that is the
smallest next experiment, and it is deliberately not implemented here.
