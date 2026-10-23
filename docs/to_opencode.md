# Plan2001-O — Boot Experiment D1: O-resident MicroPython entry and first real blocker

**Task for OpenCode; repository `pereuna/Plan2001-O`, current `main`.** Continue from successful Boot Experiment C (`3374eb9`; report `docs/O-BOOT-EXPERIMENT-C.md`). The aim is a **bounded diagnostic experiment**, not a console implementation. Keep the coding agent focused on the actual first failed operation.

## Research question

Can the existing kernel start the **real, unchanged O-resident MicroPython executable** at `OID_MP_EXEC = 0x4f45584543000003` by the proven pathless first-user-process path, and **how far does MicroPython initialize before it needs any inherited Plan 9 namespace, file descriptor or console facility?**

Expected execution prefix:

```
UEFI -> kernel -> scheduler -> small embedded ring-3 O loader
     -> OVOLOPEN(PARTUUID=...) -> OSPACEOPEN(1, "init")
     -> OEXECUTE(OID_MP_EXEC, actual argc/argv) -> real MicroPython ring 3
     -> observe actual startup stages and first legacy dependency
```

**Success is not defined as a working interactive REPL, Python boot, persistence, or zero namespace operations indefinitely.** D1 must prove the OID-to-MicroPython image transition and diagnose exactly where the interpreter goes next, without disguising an expected missing-console failure as a complete system boot.

The eventual serial console / stdin / stdout / `boot.py` modernization is **D2 and NOT PART OF D1**.

## 0. Keep controls and current work safe

Before editing: `git status --short`, `git log -6 --oneline`. Make sure Boot A (`6c6e112`), B (`ba6b8ab`+`ddf9899`), C (`3374eb9`), and native storage (`e384300`) are in history. If another agent has uncommitted changes in overlapping files, do not overwrite or stage them; use a clean checkout/branch or stop with a specific conflict report. No destructive reset, forced push or blind `git add .`.

Preserve `oboot=probe`, `oboot=user`, `oboot=oid`, default legacy-compatible O/MicroPython boot, all previously passing gates, GE/O on-disk format and `OID_MP_EXEC`. Do not edit `/boot/oinit` or `boot.py` to suppress failures. No physical-disk tests.

Read `AGENTS.md`, `docs/STATUS.md`, `docs/O-BOOT-EXPERIMENT-C.md`, `docs/O-BOOT-DEPENDENCIES.md`, `docs/O-FORMAT.md` and the actual source for:
- `sys/src/9/pc64/main.c`, `ouser.c`, `trap.c`, `l.s`; `sys/src/9/pc/obootoid.c`.
- `sys/src/9/port/devgefs.c` (`OVOLOPEN`, `OSPACEOPEN`, `OEXECUTE`); `sys/src/9/port/sysproc.c` (`execo`, argv handling, `execcommit` / `execregs`).
- `sys/src/cmd/oinit/oinit.c` (`argvec` and exact existing MicroPython arguments).
- `sys/src/cmd/micropython/main.c`, `p9console.c`, `p9space.c`, `boot.py`, and the actual C/Plan9-libc startup path.
- `tools/mkovol`, `tools/oseed.py`, `tools/gefsdisk`, `tools/test-oboot-oid.sh`, `tools/test-o-boot.sh`.

**Known from source — verify on current HEAD:** `oinit.c:argvec` uses six args for the persistent init mode:

```
argv = { "micropython", "-O", "PARTUUID=<GUID>", "-S", "init", "-B", nil }
argc = 6
```

`micropython/main.c` runs `mp_init()`, then `p9_space_o(ovol)`, then **executes `boot.py` before opening/restoring `init` Space when `-S init -B` is selected**. Current `boot.py` calls `plan9.bind`, tries `/boot/kbdfs` with `spawn` and touches `/dev/cons`. Current `p9console.c` uses `fd2path(0)`, `/dev/consctl`, `readn(0)`, and `write(1)`. These are **potential expected blockers**; test which one is first rather than inferring from file order that every call executed.

## 1. A separate opt-in D1 mode

Prefer `oboot=mp`, preserving `oboot=oid` as the C test. Reuse the existing embedded OID loader (and its `otouser`/ring-3 setup), not an additional copy of the loader or an alternative kernel-side executable loader. The `PARTUUID` must still come from the **newly generated disposable GPT** using `obootvol=PARTUUID=@PARTUUID@`, not a hard-coded GUID.

In `oboot=mp` only, select `OID_MP_EXEC`, the actual MicroPython executable and appropriate argv supplied entirely from valid user memory. Be exact about the one-page initial loader image's constraints: Plan9 C literals / static state, stack argument block, pointers and lengths must be checked. `oexecute` snapshots user argument pointers and strings; ensure all six arguments are addressable in the initial user image/stack and survive until syscall copying. Validate `argc`, `argv[argc]=nil`, bounded strings and a fresh PARTUUID. Retain C's fixed test OID and original argv unchanged.

The O volume and program read must use the **existing** `PARTUUID -> direct native SD/GE/O -> onativeget -> execo` path. `execo` should replace the initial ring-3 process with the real MicroPython executable without any `/boot` lookup. Do not embed the MicroPython executable in the kernel and do not use `NATIVEEXEC` or the `RAWEXEC` fixture OID as a substitute. Use the existing default `tools/mkovol ... tools/odemo.py` seeding of `OID_MP_EXEC`, unchanged.

## 2. Diagnostic measurement, not a fake passing runtime

Build a **time-bounded and phase-aware** observation path with `OBOOT-D1:` serial markers, guarded by `oboot=mp` (including after the process image is replaced). Preserve the global `opath` counters as cumulative, not reset. At minimum record:

1. Actual first user-mode entry from the embedded loader, successful `OVOLOPEN`/`OSPACEOPEN` and the precise `OEXECUTE` call with OID `0x4f45584543000003`.
2. Binary provenance: host MicroPython executable SHA-256, unchanged O seed SHA-256, and independently verified OID read bytes / digest. Reuse the existing `oinit` hash algorithm/tool if practical; **do not use only an 8-bit sum as proof for a 2 MB interpreter**. Keep instrumentation bounded and optional.
3. Actual **post-exec `Ureg` change** (`text=micropython` or verified program name, new user PC and valid user `CS/SS`), then one or more *real* MicroPython-originated user-mode syscalls / subsequent execution. Do not claim the interpreter initialized merely because `OEXECUTE` reached `execcommit`.
4. Distinguish milestones as facts rather than guesses: program entry/libc startup; `main` reached; `mp_init` entered/completed; `p9_space_o` entered/completed; `boot.py` entered; first `bind/open/spawn/fd` request; `space.open('init')` reached; `p9_space_boot` reached; durable commit reached. Show `REACHED`, `NOT REACHED`, or `UNKNOWN` with actual source lines / traced PCs and runtime evidence. It is acceptable to leave late milestones NOT REACHED if an earlier dependency blocks.
5. **First actual inherited dependency attempted**: capture the first user-originated namespace/FD/path/console operation including attempted syscalls and return value, even if `namec` is never entered because the syscall rejects a missing `Fgrp` earlier. Identify the precise function, source file:line, syscall/arguments where safely observable, and error. Do not confuse zero `opath` counters with no attempted file operations.
6. Classify process fate: successful scheduled execution, trapped fault, returned error, unhandled MicroPython exception, idle/sleep, exit, QEMU timeout. A process that panics or hangs is a diagnostic result, not a hidden PASS. Do not suppress `panic`, swallow exceptions or inject fake FD-backed console support.

**Measurement methods:** first prefer existing `OBOOT-C` syscall/exec instrumentation extended *only* for the D1 PID and boot mode. Existing 8-syscall cap is too short for a real interpreter: use a **bounded** trace budget, with phase/checkpoint filtering to prevent massive logs. If needed, add the smallest opt-in diagnostic check in interpreter startup (e.g., calls to an **existing non-file syscall** producing kernel-side observed markers, with a `-T` test-only option), but avoid modifying normal interpreter behavior, creating a debug syscall, or treating injected markers as proof of unmodified startup. Keep any required extra interpreter instrumentation localized and explain what it does. Do not add new global console dependencies. If `main` cannot be reached, demonstrate that honestly from traces.

**Mandatory scope distinction:** During the *prefix up to OID exec*, path counters should remain zero as in Boot C. After MicroPython starts, D1 must measure and report any forbidden operations **rather than requiring zero**; they are the subject of D2. Report cumulative counts at both points, not a fabricated whole-boot "pathless PASS".

## 3. Reproducible positive and negative tests

Implement `tools/test-oboot-mp.sh` or equivalent:

- Build `WHAT=all tools/build.sh`, `tools/selfroot` as required by the existing tree; use a fresh disposable O image with the existing `init` Space, MicroPython binary and odemo code, `NOROOTFS=1`, **no `root=`, no `init=/boot/oinit`**. Use `INI='oboot=mp;obootvol=PARTUUID=@PARTUUID@'`.
- Verify the generated `plan9.ini`, OID image hash and exact argv supplied to `OEXECUTE`. Log all QEMU serial output and stop at a precise observation milestone or bounded timeout. Never rely on a VM continuing forever as evidence of success.
- One additional **negative test** using `NOMPEXEC=1` so `OID_MP_EXEC` is absent: `OEXECUTE` must return an error without launching `micropython`, must not fall back to `/boot`, and must preserve the existing O handle (as in C). Document this as a separate negative, not as a crash.
- Distinguish `D1 EXEC PASS` (real target image replacement + at least one real post-exec syscall) from `D1 STARTUP REACHED: <verified highest milestone>`. An observed missing-console failure is compatible with **D1 diagnostic success** but must NOT be called a working O-resident MicroPython boot.
- Do not change Python code, `boot.py`, the default O executable bytes or a format just to make an early startup marker pass. If a userlib/libc assumption blocks MP entry, document exactly and stop unless the fix is a genuinely tiny, safe compatibility repair independent of D2.

For controls, *run* and report PASS/FAIL/NOT RUN with actual logs:
```sh
WHAT=all tools/build.sh
tools/test-oboot-user.sh
tools/test-oboot-oid.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
```
Plus Boot A `oboot=probe` from its documented QEMU recipe. All work in throwaway images. If an existing regression fails, do not mark D1 clean or alter an unrelated test's acceptance criteria.

## 4. Stop conditions and documentation

**STOP before D2.** Specifically do NOT implement direct UART read/write, FD emulation, `/dev/cons` replacement, kbdfs alternatives, Python `plan9` API redesign, fake tree mounts, `namec`/Chan removal, new O graph semantics, or unrelated user-process semantics. Do not broadly refactor `boot.py` to "skip" its dependency. Prioritize the observed first blocker over speculative changes.

Deliver:

- `docs/O-BOOT-EXPERIMENT-D1.md`: actual boot call graph; full six-argument contract; exact OID/host/O digest evidence; phase-by-phase startup table; first missing dependency with source:line, trace, syscall results and limits; why this is **not D2**.
- `docs/STATUS.md`: dated factual D1 results and executed commands/logs, preserving all A/B/C and Storage Level A histories.
- `docs/to_chatgpt_review.md`: concise evidence and the single concrete D2 boundary supported by D1; respect the OpenCode final summary automation.
- Small opt-in source/test edits only; commit and push with the project's established workflow, avoiding duplicate commits or concurrent writes.

**Final verdict format:** `D1 EXEC PASS / NOT YET`; `D1 STARTUP highest proven milestone = ...`; `FIRST LEGACY DEPENDENCY = <actual function/path/FD requirement and failure>`; `NEXT D2 EXPERIMENT = <one minimal evidence-driven objective>`. Never claim full pathless MicroPython boot solely because `OEXECUTE` succeeds.
