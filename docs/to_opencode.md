# Plan2001-O — Experiment A: bottom-up boot without the legacy first user process

**Task for OpenCode. Repository:** `pereuna/Plan2001-O`, current `main`.  
**Scope:** one small, reversible kernel boot experiment. This **supersedes** the previous A/B/C pathless-boot assignment in this file. Do not continue its block-storage, executable-loader or console refactors as part of this task.

## Question

Can the existing amd64 9front-derived kernel initialize its normal hardware and scheduler, then run a minimal **kernel process** without starting the inherited Plan 9 user-process bootstrap and its pathname/namespace setup?

Approach this **bottom-up**, starting from `sys/src/9/pc64/main.c:main()`, not by removing filesystem APIs from the top. The experiment must distinguish code **present in the kernel binary**, code **initialized at boot**, and code **actually executed on the chosen boot path**.

The aim is **NOT** to remove `Chan`, `Dev`, `namec`, `devroot`, the filesystem source, or any existing O interface. It is to demonstrate that the traditional user-boot chain can be bypassed at a narrow branch point while the rest of the kernel remains usable.

## 1. Source check before edits

Read `AGENTS.md`, `docs/STATUS.md`, and at least:

- `sys/src/9/pc64/main.c`: `main`, `init0`, and the `userinit(); schedinit();` transition.
- `sys/src/9/port/userinit.c`: `userinit`, `proc0`, `namec("#/")`, segment creation, `init0`.
- `sys/src/9/port/initcode.c`: `startboot` with `bind/open/exec`.
- `sys/src/9/port/proc.c`: `kproc`, `newproc`, `schedinit`, `sched` and sleep/delay facilities.
- `sys/src/9/port/chan.c`: `chandevreset`, `chandevinit` and pre-existing `opath` counters.
- `sys/src/9/port/devroot.c`: `rootreset`; `sys/src/9/port/devsd.c`: `sdreset`.
- `sys/src/9/pc64/pc64`, existing QEMU scripts and boot configuration.

Verify the actual call chain and relevant runtime preconditions. In particular, **`kproc()` is not independent of all namespace-related data structures**: in current `proc.c`, it initializes/holds a `Pgrp` (`kpgrp = newpgrp()`). When `up == nil`, it gives its new kernel process `slash=nil` and `dot=nil`. Do not claim “no Pgrp” just because the process avoids path lookup. Also note `userinit()` initializes `eve` before calling `kproc`; any replacement must safely preserve required initialization without entering the legacy `proc0` path.

## 2. Implement a small, opt-in probe path

Introduce one explicit experimental boot option, preferably `oboot=probe`, read using the existing early boot-configuration interface. The ordinary boot with no such option MUST remain unchanged.

Near the current handoff in `main()`, implement conceptually:

```c
if(/* explicit oboot=probe */)
    ouserinit();      /* experimental kernel-only first task */
else
    userinit();       /* untouched normal path */
schedinit();
```

Names and exact placement are suggestions; use the repository's actual conventions.

`ouserinit()` should create one minimal `kproc` that:

1. Runs **after** the scheduler starts, with a clear serial/kernel-console marker, e.g. `OBOOT-A: KPROC-RUNNING`.
2. Prints basic safe evidence (PID, `slash/dot` state, possibly a scheduler heartbeat using an existing scheduler-safe primitive).
3. Remains schedulable or sleeping after the marker; do not return into an uninitialized/empty run queue or busy-spin forever at interrupt-disabled priority.
4. Does not call `namec`, `open`, `bind`, `mount`, `exec`, `rootmount`, `init0`, `touser`, or construct a user-mode namespace.
5. Uses only existing kernel scheduling, logging and memory primitives. No O volume, disk I/O, MicroPython, bootstrap binary, custom syscall, 9P, REPL or filesystem operation.

Avoid modifications to generic `kproc`, `schedinit`, low-level driver code or the standard `userinit/proc0` implementation unless the exact measured blocker makes a tiny change unavoidable. No new abstraction framework.

**Critical distinction:** `main()` still executes `links()` and `chandevreset()` before this branch. The latter calls `devtab[i]->reset()` and currently includes both hardware probing (e.g. SD) and `devroot`'s directory-list initialization. Experiment A does **not** prove there was no filesystem-related initialization whatsoever. Leave the device reset sequence intact; inventory these effects rather than claiming that removing the first user process removed the whole filesystem.

## 3. Verification and instrumentation

- Record the `main` HEAD commit and relevant source line anchors. Find and use the repository's **actual** amd64 build and QEMU invocation; run only in a disposable VM. If a kernel configuration requires an ESP or image, use a throwaway image; **no physical disk writes**.
- Build the experimental kernel and boot once with `oboot=probe`. Save complete serial output. Assert ordered markers for `main` entry, pre-scheduler handoff, probe `kproc` execution after scheduling, and a second heartbeat or similarly observable liveness event. A mere successful compilation or pre-scheduler print is **not PASS**.
- Demonstrate that the selected branch did NOT call `userinit -> proc0 -> init0 -> startboot` or launch `/boot/oinit`. Use guarded markers/counters or another equally direct test; do not mistake absence of output for proof.
- Measure `namec`, `newchan`, `devwalk`, `mount/bind` and path-based `exec` using existing `opath` instrumentation where suitable, with enough extra **gated** instrumentation to characterize the selected boot. Clearly separate **whole-boot counts before the handoff** from **counts during the experimental task**. Do not silently discard early calls. A positive-control normal boot should establish that the instrumentation detects a real legacy call. No filesystem-backed logging.
- Demonstrate the **unchanged normal boot** without `oboot=probe` still reaches the existing O-resident MicroPython path; run the relevant existing regression gate(s), especially the normal O boot gate. Run the build/test commands actually present in the repo. Report PASS/FAIL/NOT RUN honestly, with logs and any timeout diagnostics.
- If the probe cannot safely pass scheduling or encounters an early dependency, STOP, retain the normal working path, and document the exact blocking function and a minimal next experiment. Do not expand scope into filesystem removal.

## 4. Acceptance criteria

**Experiment A PASS** only if:

1. Normal kernel initialization completes in QEMU using the opt-in path.
2. `schedinit()` schedules the experimental kernel process, and liveness is verified after scheduler entry.
3. Legacy `userinit/proc0/init0/startboot` is not executed on the probe path.
4. Probe itself does not instantiate `slash/dot` or perform a path lookup / mount / user path-exec operation.
5. Default normal O boot remains functional, and output includes real tests and logs.
6. All residual `Pgrp`, `Dev`, `Chan`, reset-time directory metadata and background activity are stated accurately. In particular, **do not assert “zero filesystem code running anywhere in kernel” without instrumented evidence**.

This is explicitly **not** a PASS for GE/O native block access, OID persistence, pathless O executables, pathless MicroPython, or full kernel removal of `Chan`/`namec`.

## 5. Deliverables

- A minimal, reviewable source diff with the opt-in boot option and experimental kernel process.
- `docs/O-BOOT-EXPERIMENT-A.md`: accurate actual boot call graph, test design, collected serial markers/counters, detailed observations and the key distinction between linked, initialized and executed code.
- `docs/STATUS.md`: dated status and PASS/FAIL/NOT RUN with exact commit and commands.
- `docs/to_chatgpt_review.md`: concise findings for architectural review, without overclaiming the scope. Respect any existing OpenCode automation that writes the final summary to this file.
- Commit and push the intended work through the project's normal completion automation, avoiding duplicate/racing commits.

**Final question for the review:** Given what Experiment A executes, what is the smallest *next* boot-boundary change that would permit a userspace process without pathname initialization? **Answer only; do not implement Experiment B yet.**
