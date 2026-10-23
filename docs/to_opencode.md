# Plan2001-O — Boot Experiment D2a: native output stream, UART backend

**Task for the current OpenCode agent.** Repository: `pereuna/Plan2001-O`, current `main`. Continue from Boot D1, implementation `4d1d75f`, report `docs/O-BOOT-EXPERIMENT-D1.md`. **One falsifiable experiment: make the first real O-resident MicroPython diagnostic output work without `Chan`, `Fgrp`, `/dev/cons`, `kbdfs`, or a filesystem path, then identify the NEXT actual bootstrap dependency.** Do not turn D2a into a full console or REPL migration.

## Architectural contract — important correction

Plan2001-O is removing **compulsory hierarchical filesystem navigation**, NOT the concepts of files, byte contents or streams.

Keep these distinct:
- **file/content**: stored or memory-resident bytes; may have OID;
- **stream**: time-ordered bytes between active participants; need not have OID or pathname;
- **device**: operation-capable resource (UART TX/RX);
- **handle**: process-owned permission to use a live endpoint; it is not necessarily an FD, `Chan`, path or persistent OID;
- **display buffer** (future): addressable screen state, not equivalent to terminal output stream;
- **keyboard events / kbmap daemon** (future): separate from UART output and MicroPython REPL.

The new **process-local output stream contract is intended to survive this experiment**. The one-UART backend, handle slot numbering, instrumentation and boot-mode binding are **experimental and replaceable**. Do not canonize an entire stream registry, terminal model or final ABI at this stage.

**Do NOT implement** `if (up->fgrp == nil && fd == 2) uartputs(...)` in `PWRITE`; do not fabricate an `Fgrp` or a fake `Chan` for a serial port. Do not open `#c/cons`/`/dev/cons` or create a miniature 9P service. Existing `fd` semantics may stay for compatibility paths.

## 0. Protect current state and find exact boundary

Run `git status --short`, `git log -6 --oneline`, check working branch and concurrent edits. Never use destructive reset, `git clean -fd`, force-push, overwrite another agent's edits or stage unrelated files. Preserve old A/B/C/D1 gates, normal O boot, existing `boot.py` and `OID_MP_EXEC` format.

Read `AGENTS.md`, `docs/STATUS.md`, `docs/O-BOOT-EXPERIMENT-D1.md`, and relevant source. The verified D1 failure is:

```
real O-resident MicroPython, mp_init completed
 -> p9_space_o -> OVOLOPEN succeeds
 -> p9space.c:366 fprint(2,"space: O volume selected...")
 -> libc write -> PWRITE(fd=2)
 -> sysfile.c:fdtochan: f=up->fgrp=nil; lock(f)
 -> kernel fault at addr 0x8 / panic
```

The first new observable goal is **the same diagnostic message arriving through native UART output with `up->fgrp=nil` and no `PWRITE(fd=2)` attempt for that message**.

Inspect:
- `sys/src/9/port/devuart.c`: `consuart`, `uartputs`/`uartputc`, queued output `serialoq`, actual device availability and locking; `sys/src/9/port/devcons.c` output and newline rules. Reuse the actual existing UART driver; do not invent a new serial driver.
- `sys/src/9/pc64/ouser.c` and process lifetime; `sys/src/9/port/portdat.h` (`Proc`), `proc.c`, `sysproc.c:execcommit`; process survives `OEXECUTE` as the same PID, with new executable. Ensure the output authorization survives this image replacement but is cleared on process exit/reuse and cannot leak to unrelated processes.
- `sys/src/libc/9syscall/sys.h`, `sys/src/9/port/systab.h`, `sys/src/libc/9syscall/mkfile`, `sys/src/9/pc64/trap.c`: exact amd64 user syscall ABI and proper wrapper-generation route. Current calls 54–61 are native O calls. Select the next genuinely free syscall number only after checking complete table; update declarations/tables/labels and libc linkage consistently, test clean rebuild.
- `sys/src/9/port/sysfile.c:fdtochan` and `syspwrite`.
- `sys/src/cmd/micropython/p9console.h`, `p9console.c`, `p9hal.c`, `main.c`, `p9space.c`, `boot.py`: MicroPython `print()` uses `mp_hal_stdout_tx_strn -> p9_console_write`; a limited number of diagnostic `fprint(2,...)` sites in `main.c` and `p9space.c` use Plan 9's FD ABI.

## 1. Small generic write API; no FD-to-UART special case

Implement one **native byte-stream write syscall** (conceptual signature):

```c
long iowrite(Iohandle stream, const void *buf, long n);
```

A handle denotes an endpoint **authorized in the current process**. D2a only binds an OUT/DIAGNOSTIC stream to the already initialized system console UART for the initial `oboot=mp` process. You may use two process-local slots pointing to the same UART endpoint, or the smallest equivalent typed process-local state, but **do not globally grant arbitrary processes access merely by guessing numeric handle values**. Do not conflate the number 2 with a Unix fd.

Implement and test clear semantics:
- Kernel verifies handle ownership / binding; absent, forged or revoked handles fail with a normal error. No global unconditional `uartputs` syscall.
- Validate `n`: zero-length success (may be useful for capability detection), reject negative/excessive lengths; validate/copy from user memory with the kernel's established `validaddr` + bounded-copy convention. Do not pass an unchecked user pointer to UART driver or print the input through `print("%s", userbuf)`.
- Only transfer the bytes actually copied. Return number accepted or `-1` with an error; report UART unavailable explicitly, never silently return positive while discarding output. Preserve byte order and handle short writes/errors; define whether newline CRLF transformation belongs in the temporary UART backend and avoid double CRLF. Prefer reusing existing console-output queue/serialization if suitable; avoid unbounded busy waits, disabling interrupts during long writes, and interleaving corruption. The output may need chunking.
- Binding: grant the initial native process its output stream(s) in `oboot=mp` startup, before `otouser`. Demonstrate continuity of process-local authorization across `OEXECUTE`; no duplicate grant from inside the MicroPython loader. Document who owns/revokes this right. Avoid a new generic service manager or stream router.
- No console *input* syscall, PTY, screen state, line discipline, kbmap or UART driver rewrite now.
- Scope current implementation to amd64 proof as appropriate; build should not accidentally break other targets because of unguarded declarations or missing stubs. Note platform limits.

Check initial-stream access from user mode using actual `iowrite` syscall return and UART bytes, not a kernel-only debug `print`.

## 2. MicroPython port: two output paths behind one intentional boundary

Use a port-local output function rather than globally changing Plan 9 libc's `fprint` or treating `PWRITE(fd=2)` specially.

- Under `oboot=mp`, detect/use the process-provided native output capability safely (e.g. defined stream handle + zero-length probe, or an equally small explicit mechanism). Do not discover it by a pathname, `fd2path`, env files or a user-accessible kernel pointer.
- Route `p9_console_write()` (therefore Python `print`, MicroPython exceptions and stdout) to native output **when the capability exists**. Otherwise retain the current legacy `write(1)` behavior unchanged.
- Add a small bounded port-local diagnostic formatter, e.g. `p9_dprintf(...)` using Plan9 `vsnprint` or equivalent, for existing `fprint(2,...)` diagnostics in the native `main.c`/`p9space.c` execution path. When native output is active, send its bytes through native DIAGNOSTIC endpoint; in legacy boot, preserve existing `fprint(2)` behavior (including test-visible strings). Keep formatting bounded and preserve all existing meaningful diagnostic messages. Do not make broad blanket macro overrides for libc or rewrite unrelated legacy file I/O.
- If a native write fails after native mode has been chosen, report the failure honestly and do **not silently fall back to fd 2** (which may be unavailable). Avoid recursion between error printing and `p9_console_write`.
- `p9console.c`'s existing `fd2path(0)`, `/dev/consctl`, `readn(0)` and `kbdfs` dependencies remain as they are for now; they are the subject of later steps. Do not simulate successful reads in D2a.
- Keep the user's actual `micropython -O PARTUUID=... -S init -B` invocation and `boot.py` unchanged for this experiment. The source/binary SHA changes legitimately due to port code, but `tools/mkovol` must store and `OEXECUTE` must load the **same freshly built executable bytes**, with a strong SHA-256 identity check as in D1.

## 3. Independently fix the D1 kernel panic

In `sys/src/9/port/sysfile.c:fdtochan`, check whether `up->fgrp` is `nil` **before `lock(f)`** and return the existing invalid-FD error (e.g. `Ebadfd`) rather than crashing. Keep the ordinary `Fgrp` path unchanged; do not allocate an FD table or bind a console.

Test a legacy `PWRITE` issued from a minimal process with nil `Fgrp` now returns `-1`/expected error and **does not panic**. Guard invalid `fd` carefully; do not add special UART handling to this path. If other nearby nil-`Fgrp` functions are hit, report them accurately; avoid a wholesale rewrite of sysfile operations.

## 4. Tests and acceptance

Write a bounded test `tools/test-oboot-output.sh` or equivalent with disposable QEMU GPT/ESP/O images; `oboot=mp`, generated `obootvol=PARTUUID=@PARTUUID@`, no root and no `init=/boot/oinit`. Use existing `tools/mkovol` seed, `tools/gefsdisk`, `tools/test-oboot-mp.sh` recipes. Build the updated MicroPython from current source and seed exactly that binary; verify host/seed/GE/O-read SHA-256 match. Preserve complete serial and command logs.

**D2a OUTPUT PASS requires all of:**

1. D1's native startup prefix remains valid: actual user-space loader -> `OVOLOPEN` -> `OSPACEOPEN` -> `OEXECUTE(OID_MP_EXEC)` -> `micropython` executes at ring 3.
2. First post-MP `OVOLOPEN` returns successfully and the literal message beginning `space: O volume selected:` arrives on host UART **from the new output syscall**, verified by guarded syscall instrumentation of the user's `iowrite` and its return value. No special kernel-generated replica of that message; no `PWRITE(fd=2)` for that diagnostic.
3. One or more **subsequent** real user-originated operations occur after that message, demonstrating interpreter execution continued beyond D1's exact failure. Identify the next first attempted legacy namespace/FD/console operation and whether it returned an error, raised a Python exception, faulted, or blocked. Record the highest verified startup phase (`p9_space_o` returned, `boot.py` entered, Space open, etc.) instead of assuming success.
4. Through the output milestone, no `userinit/proc0/init0`, no `namec/newchan/walk/devwalk/mount/path-exec` operations; counters must be cumulative and never reset. **After this milestone**, record any operations, do not suppress them to claim full pathlessness.
5. Invalid/unbound native handle, negative or oversize length, invalid user pointer, and nil-`Fgrp` legacy `PWRITE` do not crash the kernel. Check meaningful errors and that invalid buffers produce no partial arbitrary UART output. At least one user-originated native-output negative test, not only kernel mock.
6. Default boot's existing output and O persistence gates still work unmodified.

**Not a D2a failure by itself:** the **next** observed `boot.py`, FD, `kbdfs` or pathname dependency prevents a complete MicroPython boot after the output milestone. Report it precisely. Do not use a panic after the milestone as evidence of a successful console migration; it remains a diagnosed downstream failure, and fix it only in a separate later task.

Run and report actual PASS/FAIL/NOT RUN, including:
```sh
WHAT=all tools/build.sh
# rebuild clean selfroot if required; document exact command
tools/test-oboot-output.sh
tools/test-oboot-user.sh
tools/test-oboot-oid.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
```
Also Boot A `oboot=probe` per its documented disposable QEMU gate. The original **D1 panic-expectation test is now obsolete for this new kernel**: preserve the historical D1 report and update/replace the relevant harness expectation with a newly named D2a outcome. Do not falsely report old D1's exact panic as a regression that should still pass.

Keep stdout/diagnostic messages and existing three-boot persistence tests intact in normal boot. No physical-disk tests.

## 5. Stop conditions

If the minimal output stream demands a large refactor of `Proc`, `Fgrp`, all Unix/Plan9 syscall semantics, the scheduler, `execo`, UART driver or MP filesystem interfaces, **stop at D2a NOT YET** with exact obstructing function/line and smallest alternative. Do not disguise a large change as the required small diagnostic repair.

Do NOT in D2a:
- introduce `/dev/cons` replacement, `kbdfs`, 9P server, mount/tree, PTY or file hierarchy;
- implement RX/input, keyboard interrupts, keymaps, REPL editing, screen-memory object;
- rewrite `boot.py`, automatically skip it, change persisted Python object semantics, load code from the filesystem;
- permanently freeze experimental stream-handle numbering or design a general-purpose device/object framework.

## 6. Deliverables

1. Minimal kernel syscall + process-local stream grant/lifetime + UART backend + userspace libc binding; MicroPython-port diagnostics/stdout routing; independent `fdtochan` nil guard; bounded tests.
2. `docs/O-BOOT-EXPERIMENT-D2A.md`: source-backed architecture/ownership, temporary vs durable API guarantees, exact user/kernel call chain, UART transfer evidence, security/bounds/negative tests, D1 comparison and next observed blocker, complete QEMU log references.
3. `docs/STATUS.md` preserve prior A/B/C/D1 and Storage Level A evidence, annotate current D2a outcome.
4. `docs/to_chatgpt_review.md` compact factual review summary for ChatGPT. Respect existing OpenCode finishing and git automation, do not race it.
5. Commit and push only intended changes with the current repository workflow.

**Final verdict:** `D2a OUTPUT PASS` or `D2a OUTPUT NOT YET`; `NEXT BLOCKER = <actual observed dependency>`; `LEGACY COMPATIBILITY = PASS/FAIL/NOT RUN`; `STREAM API LIMITS = <what is intentionally provisional>`. Do not claim D2b (functional server boot) or D2c (interactive REPL).
