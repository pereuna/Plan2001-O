# Boot Experiment A: kernel-only first task without the legacy user bootstrap

**Date:** 23 October 2026. **Source state:** implementation commit
`6c6e112efb201bd5d927e3276877714d56c1a92f` on `main`, plus this
documentation follow-up. The runtime evidence below was produced from
that source content with QEMU and disposable images only. This is
**Boot Experiment A**, not **Storage Level A** and not the earlier
top-down pathless-storage work recorded in
[O-BOOT-DEPENDENCIES.md](O-BOOT-DEPENDENCIES.md).

## Verdict

| Check | Result | Scope demonstrated |
| --- | --- | --- |
| **A1 — opt-in kernel boot** | **PASS** | The normal amd64 `9pc64` kernel completes hardware/scheduler initialization with `plan9.ini oboot=probe` and no root filesystem or `init=` line. |
| **A2 — scheduler and liveness** | **PASS** | `schedinit()` schedules a minimal `kproc`; it prints `OBOOT-A: KPROC-RUNNING` after scheduler entry and two later timer-driven heartbeats. It then remains asleep. |
| **A3 — legacy chain not executed** | **PASS** | `userinit`, `proc0`, `init0` and the path `exec` were not executed on the probe boot: the guarded counters are `0/0/0` and the existing path counters include `exec=0`. No `/boot/oinit` was launched. |
| **A4 — no probe namespace** | **PASS** | The probe task has `slash=nil`, `dot=nil`, and performs no `namec`, `open`, `bind`, `mount`, `exec`, root mount or user-mode entry. |
| **A5 — normal path unchanged** | **PASS** | Without `oboot=probe`, `tools/test-o-boot.sh` still performed three O-only boots and reached the O-resident MicroPython path (`run()` 1 -> 2 -> 3). No `OBOOT-A` marker appeared. |
| **Positive control** | **PASS** | `tools/test-o-pathless.sh` showed the normal boot makes real namespace calls before the O storage window: `namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1`. |

This experiment does **not** claim pathless GE/O block access, OID
persistence, pathless native executables, pathless MicroPython, or the
removal of `Chan`, `Dev`, `namec`, `devroot` or filesystem source from
the kernel. It demonstrates only the boot-boundary bypass above.

## Question and design

The question was whether the existing amd64 9front-derived kernel can
initialize its normal hardware and scheduler, then run a minimal kernel
task, without starting the inherited Plan 9 user bootstrap and its
pathname/namespace setup. The experiment starts at
`sys/src/9/pc64/main.c:main()` and changes one narrow handoff.

The only new boot option is `oboot=probe`, read with the existing
`getconf` interface after `bootargsinit()`:

```c
p = getconf("oboot");
oboot_probe = p != nil && strcmp(p, "probe") == 0;
```

At the existing handoff the branch is:

```c
if(oboot_probe){
	print("OBOOT-A: HANDOFF probe ouserinit\n");
	ouserinit();
}else
	userinit();
bootmark(BMUser);
schedinit();
```

`ouserinit()` is in `sys/src/9/port/userinit.c:140`. It mirrors the two
safe setup actions of `userinit()` (`up = nil`, `kstrdup(&eve, "")`) and
creates one `kproc("*oprobes*", oprobesched, nil)`. The task
`oprobesched()` prints its evidence, then uses the existing
`tsleep`/timer scheduler primitive to sleep for two one-second intervals
and finally sleeps forever. It never returns, so it neither unwinds into
an empty run queue nor busy-spins at interrupt-disabled priority.

The instrumentation is intentionally small:

* `oboot_legacy_userinit`, `oboot_legacy_proc0` and
  `oboot_legacy_init0` increment at `userinit` (`userinit.c:102`),
  `proc0` (`userinit.c:40`) and `init0` (`main.c:156`). These are the
  direct call-chain guards.
* The existing `opath_*` counters in `sys/src/9/port/chan.c` count
  `namec`, `newchan`, `walk`, `devwalk`, mount and path `exec` entry
  points. They predate this experiment and are reused unchanged.
* Probe markers are printed only when `oboot=probe` is set; the normal
  boot prints no new marker.

No change was made to `kproc`, `newproc`, `schedinit`, `sched`, low-level
drivers, `proc0`, `init0`, `initcode.c` or the normal `userinit` branch.
The only additions to the legacy path are the three counters.

## Actual boot call graph

### Probe branch, as executed

Power-on -> UEFI loader -> `main.c:main` -> `bootargsinit` (reads
`oboot=probe`) -> normal machine, memory, trap, clock, PCI, APIC, timer
and page initialization -> `procinit0` -> `initseg` -> `links` ->
`chandevreset` -> `preallocpages` -> `pageinit` -> `ouserinit` ->
`kproc(*oprobes*)` -> `schedinit` -> `sched` -> `oprobesched` ->
two timer heartbeats -> sleeping task.

The complete probe transcript retained in
`build/verification/test-oboot-probe-experiment-a.log` contains:

```text
Plan 9
OBOOT-A: MAIN entry oboot=probe
...
#S/sdE: ich: sata-I with 6 ports
2000M memory: 818M kernel data, 1181M user, 2431M swap
OBOOT-A: HANDOFF probe ouserinit
OBOOT-A: KPROC-RUNNING pid=1 slash=nil dot=nil
OBOOT-A: legacy-calls userinit=0 proc0=0 init0=0
OBOOT-A: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-A: HEARTBEAT 1 pid=1 ticks=103
OBOOT-A: HEARTBEAT 2 pid=1 ticks=204
```

The two heartbeat ticks are approximately one second apart and occur
after `schedinit()` has entered the scheduler, so they are liveness
evidence, not pre-scheduler prints.

### Normal branch, retained and retested

Without the option the same handoff still calls `userinit()` ->
`kproc("*init*", proc0)` -> `proc0` -> `init0` -> `touser` ->
`initcode.c:startboot` -> `bind`/`open("/dev/cons")`/path
`exec("/boot/oinit")`. That path is unchanged and is the path exercised
by the normal O boot gate.

### Linked, initialized and executed

| Category | Probe boot |
| --- | --- |
| **Present in the kernel binary** | `userinit`, `proc0`, `init0`, `initcode`, `namec`, `Chan`, `Dev`, `devroot`, `sdreset`, all existing O storage and native-exec code, and the embedded `/boot` bootdir entries (`oinit`, `kbdfs`, `ohandle`, `oexec`). Presence is not execution. |
| **Initialized before the branch** | Boot arguments, machine/memory/trap/clock/PCI/APIC/timer setup, process allocation and PIDs (`procinit0`), kernel link tables (`links`/`initseg`), `chandevreset`, then page allocators. |
| **Executed on the probe boot** | `main`, hardware/scheduler initialization, `chandevreset` and its reset hooks, `procinit0`, `pageinit`, `ouserinit`, `kproc`/`newproc`/`newpgrp`, `schedinit`/`sched`, and the probe task with `tsleep`. |
| **Not executed on the probe boot** | `userinit`, `proc0`, `init0`, `chandevinit`, `rootmount`, `touser`, `initcode.c:startboot`, `bind`, `open`, `mount`, path `sysexec`, `/boot/oinit`, the `alarm` kproc and the `closeproc` kproc. |

`chandevreset` is deliberately left in place. It runs
`devtab[i]->reset()` for every registered device. In this probe boot that
includes `devroot`'s `rootreset`, which fills `rootdir`/`bootdir`
directory metadata, and `devsd`'s `sdreset`, whose controller probe is
visible as `#S/sdE: ich: sata-I with 6 ports`. It also runs the other
device reset hooks (for example ACPI, PCI plug-and-play, Ethernet, UART,
USB, keyboard and VGA reset entry points). Therefore Experiment A does
**not** prove that no filesystem- or device-related reset code ran; it
proves that the first *user-process bootstrap* was not started and that
no `Chan`, `namec`, walk, mount or path-exec event occurred.

`chandevinit` is different: it is called only from the legacy `init0`.
The probe does not call it, so the device `init` hooks and the
`closeproc` kproc are not started. The disk controller probe above comes
from `sdreset`, not from `chandevinit`.

## Residual state, stated accurately

* **`Pgrp` is present.** `kproc()` in `sys/src/9/port/proc.c:1634`
  initializes a shared static `kpgrp = newpgrp()` and gives the new task
  that `Pgrp`. The probe has a `Pgrp`; it does not have `slash` or `dot`.
  It does not call `namec("#/")`.
* **`Proc` scheduling state is present.** The task has a PID, kernel
  stack, scheduler queue entry, process table slot and timer-based sleep.
  The probe printed `pid=1`.
* **`Dev` is linked and its reset hooks ran.** `Dev` instances and
  device reset entry points are part of the boot. This is not a claim of
  zero device code.
* **Directory metadata was initialized.** `rootreset` adds static root
  directory names to `devroot`'s tables. That is directory metadata, not
  a `Chan`, a walk, a mount or a pathname lookup.
* **No namespace was constructed by the probe task.** It has
  `slash=nil`, `dot=nil`, `exec=0`, `namec=0`, `newchan=0`, `walk=0`,
  `devwalk=0` and `mount=0` at the point of its evidence print.
* **Background activity is limited** to the scheduler, timers and the
  reset-time hardware probes. The normal `alarm` and `closeproc`
  kernel processes are not created on this path.
* **No filesystem-backed logging** was used. All evidence is console
  output and host-side logs under `build/`.

## Commands and evidence

The tree used for the measurement is the content of
`6c6e112efb201bd5d927e3276877714d56c1a92f`. The build was run from that
working-tree content before the commit was created; the commit contains
the same source.

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-a.log
```

Result: **PASS**, `BUILD-DONE`; normal `9pc64` md5
`0fcf61f2bd1e8c6dd700fce08e2be30b`, test-only `9pc64mp` md5
`845997f60d9fde2d987923b4ec5a017e`. Log:
`build/verification/build-experiment-a.log`.

The probe image was made on a disposable host image with no root
filesystem and no `init=` line:

```bash
NOROOTFS=1 CONSOLE=0 ROOTIMG=build/amd64/ohand-root.gefs KERNEL=9pc64 \
  INI='oboot=probe' tools/gefsdisk build/amd64/obootprobe.img
```

Its `plan9.ini` is:

```text
bootfile=/9pc64
console=0
user=glenda
oboot=probe
```

The guest was booted once with the normal amd64 QEMU target setup
(OVMF, one disposable virtio disk, no network, serial to a file) and
the command was intentionally stopped after 30 seconds:

```bash
timeout 30s qemu-system-x86_64 -name plan2001-obootprobe -nodefaults \
  -accel kvm -cpu host -machine q35 -vga std -m 2048 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=build/amd64/obootprobevm/vars.fd \
  -drive file=build/amd64/obootprobe.img,format=raw,if=none,id=d0 \
  -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
  -nic none -display none -serial file:build/amd64/obootprobevm/serial.log
```

`timeout` returned 124 because the probe remains alive and sleeping, as
designed; the required ordered markers and two heartbeats were already
present. Full serial log:
`build/amd64/obootprobevm/serial.log`; cleaned copy:
`build/verification/test-oboot-probe-experiment-a.log`.

Normal O boot gate:

```bash
tools/test-o-boot.sh 2>&1 | tee build/verification/test-o-boot-experiment-a.log
```

Result: **PASS**, `PASS: three O-only boots, persistent Counter and
run() from O (no FS)`. The three boots reached MicroPython from O and
printed `run() -> 1`, `run() -> 2`, `run() -> 3`. No `OBOOT-A` marker
appears in the normal boot transcript.

Positive control and unchanged storage gate:

```bash
tools/test-o-pathless.sh 2>&1 | tee build/verification/test-o-pathless-experiment-a.log
```

Result: **PASS**, `PASS: Level A pathless native GE/O storage window,
persistence and bounds`. The normal boot really does execute namespace
operations (`namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1`),
so the zero counts on the probe boot are meaningful, not a dead
instrumentation counter.

## Acceptance check

1. Normal kernel initialization completed in QEMU under the opt-in
   path: **PASS**.
2. `schedinit()` scheduled the probe and liveness was verified after
   scheduler entry: **PASS** (`KPROC-RUNNING`, `HEARTBEAT 1`,
   `HEARTBEAT 2`).
3. `userinit`/`proc0`/`init0`/`startboot` was not executed on the probe
   path: **PASS** (`userinit=0 proc0=0 init0=0`, `exec=0`; no
   `/boot/oinit` marker).
4. The probe did not instantiate `slash`/`dot` or perform a path lookup,
   mount or user path-exec: **PASS** (`slash=nil dot=nil`,
   `namec/walk/.../exec=0`).
5. Default normal O boot remains functional: **PASS**
   (`tools/test-o-boot.sh`).
6. Residual `Pgrp`, `Dev`, `Chan`, reset-time directory metadata and
   background activity are stated above rather than summarized as
   "zero filesystem code running anywhere": **PASS (reporting)**.

## Limits

* Only one probe boot and the normal regression gates were run. There is
  no long-duration scheduler, load, CPU-hotplug or hardware-diversity
  test.
* `chandevreset` still runs `rootreset` and hardware reset hooks before
  the branch. The probe is a first-process bypass, not a
  device-initialization bypass.
* The probe task has no console namespace, no file descriptor table
  initialized by `proc0`, no user image and no user-mode entry.
* The embedded `/boot` entries remain linked in the kernel; they are not
  executed on this path.
* The ordinary boot still uses the legacy `userinit`/`proc0`/`init0`/
  `initcode` chain. It was deliberately not removed or refactored.

## Smallest next boot-boundary change (answer only, Experiment B not implemented)

Reuse this branch point but make the first task a **user** process whose
image is supplied by bytes already available to the kernel, rather than
by a pathname. Concretely, split the essential part of `proc0` from its
namespace seeding: create the `Proc`, build text/stack segments directly
from an embedded or native-O byte image (the existing `execo`/`oexecute`
segment and stack construction is the natural reusable piece), set
`kp=0`, and enter user mode with the existing `touser` machinery. Do not
call `namec("#/")`, `cclone`, `bind`, `mount`, `open`, `exec`,
`rootmount`, `init0` or `startboot`. That is smaller than changing
`initcode.c`: it leaves the one-page initcode image and the entire
pathname bootstrap untouched while demonstrating a pathname-free
userspace entry. A console/stdin path is a separate later boundary and
is not required merely to enter user mode.
