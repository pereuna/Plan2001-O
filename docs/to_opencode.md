# Plan2001-O — Boot Experiment B: first native userspace process without a pathname

**Repository:** `pereuna/Plan2001-O`, current `main`. **Task:** implement and test the smallest bottom-up **user-mode** continuation of successful Boot Experiment A. Work on today's source, not on an older snapshot.

## Objective and terminology

Experiment A (`6c6e112`, evidence `docs/O-BOOT-EXPERIMENT-A.md`) proved that `oboot=probe` schedules a kernel task without the inherited `userinit -> proc0 -> init0 -> startboot` chain or executed pathname operations. The prior **Storage Level A** (`e384300`, `docs/O-BOOT-DEPENDENCIES.md`) independently proved direct native GE/O block access. Both must stay working.

**Boot Experiment B asks only: Can this same kernel create its first genuine amd64 ring-3 userspace process from an already available binary image, without constructing a pathname namespace, accessing a filesystem or invoking legacy `exec(path)`?**

Do not conflate **Boot Experiment B** with the older top-down **Storage Level B** goal of loading MicroPython from GE/O. **Boot Experiment B does not require GE/O, OID_MP_EXEC, MicroPython, an interactive console, or persistent storage**. A small, build-time embedded **flat byte image** is an acceptable proof artifact; a source-tree filename is not a runtime pathname. The actual kernel-to-user transition, not the storage source of the bytes, is the subject of this test.

A genuinely running userspace instruction sequence and return through a user-originated syscall/trap are required. A kernel `kproc` that merely calls a C function or prints "USERMODE" does NOT pass.

## 0. Protect completed work and other agents

Before editing, inspect `git status --short`, `git log -6 --oneline` and current HEAD. Confirm `6c6e112` (Boot A), `e384300` (native O storage), and `235ad0d` (Boot A evidence) are ancestors. If an old agent still owns uncommitted overlapping files, do not overwrite or stage them; use a clean separate checkout/branch or report the collision. Never use a destructive reset, force-push, `git clean -fd`, or blind `git add .` to resolve overlapping work.

Preserve:
- default boot (existing `/boot/oinit` -> O-resident MicroPython) and its persistence gates;
- `oboot=probe` (Boot A) and its heartbeats;
- native `PARTUUID` GE/O and `tools/test-o-pathless.sh`;
- the prior experiment reports. New results go into a **new** report.

Read `AGENTS.md`, `docs/STATUS.md`, `docs/O-BOOT-EXPERIMENT-A.md`, `docs/O-BOOT-DEPENDENCIES.md`.

## 1. Inspect the real process/loader boundary before writing code

Follow and record source-backed call chains for:

- `sys/src/9/pc64/main.c`: `oboot=probe` branch, `userinit`, `schedinit`, `init0`, `touser` and stack/argv setup.
- `sys/src/9/port/userinit.c`: existing `proc0` creates `Pgrp`, `Egrp`, `Fgrp`, `Rgrp`, `slash/dot`, text and stack segments, and invokes `init0`. Which operations are **required** to execute user code, and which only implement the legacy namespace/descriptor model?
- `sys/src/9/port/proc.c`: `kproc`/scheduler, `kp` transition, lifetime and `pexit`. Remember `kproc` already allocates a `Pgrp`; do not claim a structure-free process.
- `sys/src/9/port/sysproc.c`: `execparse`, `segload`, `execcommit`, `execo`, `newseg`/segments and rollback. **Important:** `execo` ends in `execregs()`, which uses `up->dbgreg` to modify an existing syscall/trap `Ureg`. A newly scheduled kernel process may not have such a user register frame. DO NOT directly call `execo()` from a kernel bootstrap task on the assumption that it is equivalent to `touser()`. Reuse its proven validation/memory mechanisms only where safe.
- `sys/src/9/pc64/trap.c` and `sys/src/9/pc64/l.s`: `touser`, `execregs`, `userureg`, `syscall`, privilege selectors/register handling and what actually establishes ring 3.
- `sys/src/9/port/segment.c`, `sys/src/9/pc64/mmu.c`, `sys/src/9/port/portmkfile`, `sys/src/9/pc64/pc64`: executable mapping, build-time flat image generation and user memory safety.
- Existing tiny userspace image/toolchain examples; prefer an already functioning toolchain/ABI over a new loader framework.

Produce a short dependency table: indispensable kernel processes, segments and user stack; old pathname/Chan/FD setup; any residual `Pgrp`/`Fgrp` fields. Be explicit about the moment user mode begins.

## 2. Implement one new opt-in mode while retaining both old modes

Add `oboot=user` (or similarly unambiguous value) alongside existing `oboot=probe` and normal default in the same `main()` boundary:

```c
/* illustrative dispatch, not drop-in code */
if(oboot_is_user_probe)
    o_user_bootstrap();
else if(oboot_probe)
    ouserinit();             /* Experiment A */
else
    userinit();              /* normal legacy-compatible O boot */
schedinit();
```

Keep all earlier device/hardware reset calls untouched. Do not route the new image through `devroot`, `/boot`, `namec`, `Chan`, 9P, `bind`, `mount`, `open`, path `exec` or a fake in-memory filesystem.

Create one very small userspace probe image, compiled by the repo's ordinary build tools and included as raw kernel bytes (or an equivalently direct static image). This probe should need **no stdin/stdout/stderr, C runtime file initialization, file descriptor 0/1/2, directory lookup, environment, console server or `/boot` program**. Its job is to exercise the user execution boundary. Keep any new build recipe narrow; do not pull MicroPython or GE/O into this step.

The kernel startup code must:
1. Allocate and initialize a safe first `Proc`, with correct user/process IDs, ownership and scheduler state.
2. Establish user address space and valid text/data/BSS/stack/Tos from that byte image. Validate binary bounds/entry/alignment; avoid simply jumping to a kernel virtual address.
3. Set up the correct amd64 privilege boundary, register state and stack according to the existing kernel ABI, and enter ring 3 via the established architecture mechanism. Avoid fabricating a `Ureg` solely to placate `execo` unless it is proved consistent with the trap/return ABI.
4. Avoid `proc0`'s `namec("#/")`/`cclone` and the entire `init0`/initcode `bind/open/exec` chain. Prefer `slash=nil` and `dot=nil`. If an unrelated process bookkeeping structure must remain (e.g. `Pgrp`, `Fgrp`, `Egrp`, `Rgrp`), document the minimum and prove it does not allocate a `Chan`.
5. Arrange for the user probe to make at least **two successful, non-file syscalls or an equivalently observable user-originated trap sequence** (e.g. getpid and timer sleep/yield, after verifying actual ABI/support). Keep it alive long enough to observe scheduling and user/kernel/user transitions; do not leave a CPU-burning infinite busy loop. Do not change generic error handling just to mask pid-1 exit/panic.

For the user-mode PASS marker, instrument the existing syscall/trap boundary **only when `oboot=user` and for the intended probe PID**, verifying that `userureg(ureg)` is true and recording its user PC/CS, syscall number and return value as applicable. Produce a host-visible serial log from kernel `print` (not from `/dev/cons` and not by introducing a debug syscall that hides the intended proof). A user program writing to memory without an observed user-mode syscall/trap is NOT sufficient evidence.

Keep code changes small and reversible. No new generic executable/object/device abstraction, no rewritten scheduler, no syscall redesign. If the safest solution differs from this sketch, document why and preserve the same verifiable behavior.

## 3. Instrumented QEMU acceptance gate

Prefer a repeatable `tools/test-oboot-user.sh` rather than only a one-off manual QEMU command. Use an **isolated disposable ESP/QEMU image**, `oboot=user`, no `root=` and no `init=`; never test on a physical disk. Adapt the actual working Boot A QEMU recipe (`docs/O-BOOT-EXPERIMENT-A.md`), including bounded timeout and full serial capture.

A **Boot Experiment B PASS** requires *all* of:

- Normal machine initialization and scheduler entry with `oboot=user`.
- Kernel creates the first process from a byte image without runtime filesystem access, verifies image format/entry/stack/segment bounds, and successfully transfers to **ring 3**, not just a kernel trampoline.
- At least two user-originated syscall/trap observations from that process with valid user selectors/state; where syscalls return, prove user code continued after the return (not merely that syscall entry happened).
- `userinit=0`, `proc0=0`, `init0=0` plus `namec=newchan=walk=devwalk=mount=path_exec=0` over the full measured **selected boot**. Keep baseline whole-boot versus phase counts distinct; do not reset counters to manufacture zero.
- No `up->slash` or `up->dot`, and no hidden reliance on `fd`/path/console setup. List residual initialized-but-not-used directory metadata and the `kproc` `Pgrp` accurately.
- No panics, user faults, invalid memory permission jumps or unexpected process exits **before** the success marker. A host timeout *after* proven liveness is acceptable if explicitly explained.
- Three controls still PASS or are clearly marked NOT RUN/FAIL with reasons: `oboot=probe` Boot A, normal `tools/test-o-boot.sh` (MicroPython/three persistent boots), and `tools/test-o-pathless.sh` (native O storage).
- Build works with the repository's known `WHAT=all tools/build.sh` route. Earlier `WHAT=kernel` by itself is not a valid assumed build in this tree; it lacked `ohandle/oexec` bootdir prerequisites.

Use stable `OBOOT-B:` markers. Assert order and fail the gate if an unexpected panic occurs. Do not equate log markers printed before `touser` with successful entry into user mode.

If practical, include one malformed/truncated user image failure check that stops before executing an invalid address, without altering default boot. Do not inflate scope to satisfy this optional check.

## 4. Stop conditions and evidence discipline

If safe ring-3 entry requires redesigning generic `Proc`, global syscall ABI, full file descriptor semantics or replacing `execo` wholesale, **STOP at the last verified working step** and report exact function, reason and minimal alternative. Do not weaken the acceptance test. A compile-only attempt or kernel-only simulation is **B NOT YET**, not PASS.

Do not yet:
- execute O-resident MicroPython, change `OID_MP_EXEC`, implement a Python console or native imports;
- remove `Dev/Chan/namec` from the source or build, change GE/O on-disk format or storage path;
- implement graph/tag semantics, new IPC/network protocols, or migrate to another base kernel.

The goal is one precisely bounded proof: **first user-process entry from bytes, without inherited path semantics**. The later possibility of supplying those bytes from the already pathless GE/O provider is a **next experiment**, not part of B.

## 5. Deliverables

1. Small source/build/test patch with the new opt-in mode, preserving `oboot=probe` and default boot.
2. `docs/O-BOOT-EXPERIMENT-B.md`: current HEAD, minimal executed call graph, exact code:line dependencies, binary source/build mechanics, privilege-boundary evidence, counters, actual QEMU transcript, limitations, and distinct labels **Boot Experiment B** vs previous **Storage Level B**.
3. `docs/STATUS.md`: dated PASS / FAIL / NOT RUN and exact commands, results and log paths; do not rewrite previous history.
4. `docs/to_chatgpt_review.md`: compact factual technical summary. Respect the OpenCode final-summary/commit automation and do not race its writes.
5. Commit and push only intended edits via existing completion automation; no duplicate concurrent git actions.

**Conclude with:** `Boot B PASS` or `Boot B NOT YET`; the exact earliest remaining dependence on legacy pathname/FD/namespace machinery; and the **smallest proposed next step** to load a real OID-resident executable through the already-native SD/GE/O path **without implementing that next step**.
