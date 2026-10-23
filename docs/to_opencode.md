# Plan2001-O — Boot Experiment C: ring-3 OID executable, no pathname

**Task for the continuing OpenCode agent.** Repository: `pereuna/Plan2001-O`, current main. Continue **in the existing OpenCode session** if the actual context budget permits, using the repository as source of truth. This is a single bounded implementation-and-QEMU experiment, not a general redesign.

## Goal

Combine two **already proven, separate** paths:

- **Boot Experiment B:** `oboot=user` makes a real ring-3 process from an embedded flat probe, without `userinit/proc0/init0/startboot`; real `alarm` and `sleep` syscall round trips, zero pathname counters. Implementation `ba6b8ab` + `ddf9899`; evidence `docs/O-BOOT-EXPERIMENT-B.md`.
- **Storage Level A:** a native `PARTUUID=` GE/O volume opens and reads via SD block I/O without kernel `Chan`/`namec`; `tools/test-o-pathless.sh`, implementation `e384300`.

**Experiment C:** The Boot-B first userspace process opens a real disposable GE/O volume via `ovolopen(spec, len)`, opens `init` Space via `ospaceopen(1, "init", 4)`, and invokes `oexecute(space, oid, nil, 0)` for a **genuine binary stored on that O volume**. The existing `execo` should replace the running process image. Prove the *new O-resident program*, after the exec transition, executes ring-3 instructions and performs observable syscall round trips. The entire selected boot must require no runtime pathname lookup, `Chan`, `/boot`, `bind`, `mount`, path `exec`, or FD-backed console.

**Not** required: MicroPython, Python Environment, interactive REPL, device interface redesign or full elimination of unused legacy code. This is **Boot Experiment C**; do not rename earlier top-down Storage Levels A/B/C.

## 0. Safeguards and initial inspection

Run `git status --short`, `git log -6 --oneline`; verify prior B commits and evidence on current branch. Never overwrite concurrent local edits, force push, use destructive reset or blindly stage another agent's changes. Preserve **default normal O/MicroPython boot**, `oboot=probe`, `oboot=user`, all old regression tests and the seeded O image format. Use disposable images only.

Read `AGENTS.md`, `docs/STATUS.md`, `docs/O-BOOT-EXPERIMENT-B.md`, `docs/O-BOOT-DEPENDENCIES.md`, `docs/O-FORMAT.md` and the actual implementations:

- `sys/src/9/pc64/main.c`, `ouser.c`, `trap.c` and `sys/src/9/pc/obootuser.c`.
- `sys/src/9/port/devgefs.c`: `sysovolopen`, `sysospaceopen`, `sysoexecute`, process-local `Ohand` and `oprocexec`.
- `sys/src/9/port/sysproc.c`: `execo`, `execparse`, `execcommit`, `execregs`; `sys/src/9/pc64/trap.c` for `Ureg` provided by a real user syscall.
- `sys/src/cmd/oinit/oinit.c` for the actual call signatures and Space/volume semantics; `sys/src/cmd/oexec/oexec.c` and `ohello/ohello.c` for prior loader tests.
- `tools/mkovol`, `tools/oseed.py`, `tools/gefsdisk`, `tools/test-o-exec.sh`, `tools/test-oboot-user.sh`.

Check the syscall numbers/ABI and whether any native O syscall actually assumes `Fgrp/Egrp/Rgrp` or nonnil `slash/dot`. Do not assume because it used to be called after `/boot/oinit`. Assess GE worker start, locks, `oprocexec` handle disposal, Tos and stack/argv creation before modifications.

## 1. A separate opt-in C mode

Prefer `oboot=oid` (keeping existing `oboot=user` for B). Reuse the proven `o_user_bootstrap` ring-3 loader with the smallest safe mode selection or second tiny image; **do not copy the complete B bootstrap** and do not change the legacy default. For OID mode, the embedded first userspace program calls the existing **user** native O syscalls, not new direct kernel helper calls pretending to be userspace.

Give it the disposable image's correct `PARTUUID=` string without accessing any filesystem. **Important:** `tools/gefsdisk` generates a new GPT partition GUID per image; hard-coding a GUID in a kernel binary is not a valid repeatable gate. The kernel may read a bounded `plan9.ini` setting such as `obootvol=PARTUUID=...` with `getconf` and hand the string to the first userspace process in its initialized stack/argv, or use another equally safe and explicitly documented mechanism. The existing `INI=` support in `tools/gefsdisk` currently **does not substitute** `@PARTUUID@` in arbitrary INI fields (only the `INIT=` value gets that substitution). If adapting that tool, make a small narrowly scoped, backward-compatible substitution, and verify the final saved `plan9.ini`. Avoid exporting a kernel pointer into userspace or assuming ordinary C global variables are writable in the Boot-B image (the B one-page probe currently requires data=BSS=0).

Run:
```c
/* conceptual sequence; verify real headers/ABI */
v = ovolopen(volspec, strlen(volspec));  /* expect 1 */
h = ospaceopen(1, "init", 4);            /* expect positive handle */
oexecute(h, EXEC_OID, nil, 0);          /* success replaces process image */
```
No path operations may be used to acquire either the volume or the executable. The Space identifier here is the existing name `init` passed to a native Space API: it is **not a directory path**. Check all return values; on error, retain an observable userspace-to-kernel failure report without FD I/O, using existing opt-in instrumentation, and remain schedulable rather than crashing silently.

The O volume-open call and the actual O read must travel through the already-native `oblockopenpart -> oopenblk -> GE/O` path. Do not alter the disk engine just to make this test pass.

## 2. Choose a real O-resident target that has no FD dependency

**Critical trap:** `sys/src/cmd/ohello/ohello.c` is the existing O executable test target, but it uses `write(1,...)` and `exits`; this is *not* appropriate for a first user process whose `Fgrp` and fd 1 are deliberately absent. Make a tiny **separate** target program compiled by the existing Plan 9 amd64 toolchain which, after successful OID `oexecute`, uses only safe non-file syscalls (e.g. `alarm`, `sleep`) to demonstrate continued userspace execution. It should not return from `_main`, call file I/O, or require startup console state. Preserve the old ohello tests.

**Second critical trap:** `tools/oseed.py` unconditionally patches the BSS header of its `NATIVEEXEC` input (`x[:12] + b"\xff\xff\xff\xff" + x[16:]`) for an older targeted test. A new payload must NOT accidentally be treated as unchanged under that path. Prefer a small **test-fixture-only** opt-in raw seeding mode / new target seed input which preserves the executable bytes verbatim under a documented fixed OID, without changing the legacy `NATIVEEXEC` behavior or any on-disk GE/O format. If you can use existing seeding correctly with no change, prove it by comparing original versus O-read bytes/hash and explaining the intentional header mutation. Do not replace `OID_MP_EXEC`, alter existing ohello semantics, or corrupt the regression fixture.

A bounded extra fixture OID is fine for this experiment; use a known exact OID and document its value. Do not implement a universal program catalog.

## 3. Proof instrumentation and negative test

Use `OBOOT-C:` markers, guarded to the selected mode and PID, with existing `opath` counters unchanged. Observe and discriminate:

1. Boot-B-style **first** userspace entry, actual user mode selectors `cs=0x2b`, `ss=0x23`.
2. `OVOLOPEN` syscall return **1**, exact correct `PARTUUID`; `OSPACEOPEN` returns positive handle. Prove O engine started and the requested real OID bytes were actually fetched from the disposable image (not an embedded substitute). Record OID, exact byte length and target checksum or a comparable independently anchored identity.
3. `OEXECUTE` syscall is entered **from ring 3**, successfully performs `execo`/image commit and changes the current user instruction image. Be careful: on success the syscall handler may return through a modified `Ureg` rather than returning normally to the instruction after `oexecute`. Instrument the **actual register/stack transition**, not a fake “success” print placed before commit.
4. **After** replacement, show at least two real user-originated **target** syscalls with successful returns and continued target execution. Prefer a distinctive syscall sequence or arguments making it unambiguous that the post-exec target ran; track its program counter and user image identity. A pre-exec kernel marker or the original Boot B probe's `sleep` loop alone is insufficient.
5. Entire boot through post-exec proof: `userinit=proc0=init0=0`, `namec=newchan=walk=devwalk=mount=path_exec=0` **at both pre-exec and post-exec checkpoints**. No reset of instrumentation to conceal early events. `up->slash/dot` remain nil; report any other structs initialized or dependencies encountered.
6. `Ohand` lifecycle: inspect `oprocexec(up)` and show that the prior process-local O Space handle is not unintentionally accessible by the replaced image, or report/fix a narrowly scoped proven bug. Do not loosen isolation/rollback rules.
7. Negative case on a **separate disposable boot**: missing OID must return an error without a kernel panic or unintentional replacement; if possible, then execute the valid OID in the same process to prove rollback/handle survival. A wrong PARTUUID should fail clearly without an unexpected filesystem fallback. Keep bounded runtime and actual FAIL detection.

The target may sleep indefinitely after the verified marker. Distinguish expected host timeout from panic. Use host-visible kernel serial output; never add `/dev/cons` just to print.

## 4. Reproducible gates

Implement `tools/test-oboot-oid.sh` (or similarly named bounded test). Prepare a fresh **disposable** native O image with the target seeded, build an ESP + O GPT disk with **no root= and no init=**, and boot with `oboot=oid` plus the current generated PARTUUID safely passed to userspace. Prove the test fails if:

- GUID/volume wrong; executable OID missing/corrupt; loader syscall fails;
- post-exec user code never ran; ring-3 selectors wrong; only kernel-side marker observed;
- path counters nonzero, unexpected panic/user fault, or output ordering incorrect;
- test fixture O bytes do not match the intended target.

Run the actual baseline build and previous gates. At minimum:

```sh
WHAT=all tools/build.sh
tools/test-oboot-user.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
```

Boot A's `oboot=probe` control must also remain demonstrated; use its documented QEMU gate. Report **PASS/FAIL/NOT RUN** with exact invoked commands and logs, not an inference from earlier runs. If feasible, rerun the specific O-handle rollback regression. If any mandatory baseline fails, do not declare C PASS.

## 5. Stop line and deliverables

**C PASS** means the complete observed chain is `UEFI -> native kernel/scheduler -> embedded minimal user loader -> OVOLOPEN -> OSPACEOPEN -> OEXECUTE(OID) -> new ring-3 binary from O`, with proven post-exec code execution and zero forbidden pathname activity. Both the initial kernel-embedded probe and the true O-resident target must be identified distinctly.

If `execo` fails because it assumes a valid `Fgrp`/Egrp/process parent or a particular `Ureg` shape, isolate the **smallest actual failing dependency**; fix only if small and safe. If a more general console/runtime/process model is necessary, **STOP at C NOT YET** with a precise trace; do not reconstruct Plan 9's namespace merely to pass the gate.

Update:
- `docs/O-BOOT-EXPERIMENT-C.md`: call chains, byte provenance, OID and GUID handoff, image/stack/exec evidence, counters, negative cases, exact logs/commands, remaining limits.
- `docs/STATUS.md`: current evidence without overwriting earlier PASS records.
- `docs/to_chatgpt_review.md`: concise factual summary; respect existing OpenCode final-output automation.
- Minimal source/build/test changes. Commit and push intended files via existing automation, without racing it or staging unrelated files.

**Conclusion required:** **Boot C PASS** or **Boot C NOT YET**; which inherited Plan 9 structures **must actually execute** on this path versus simply remaining linked/initialized; and one sentence on the smallest next experiment toward O-resident MicroPython (do not implement it in C).
