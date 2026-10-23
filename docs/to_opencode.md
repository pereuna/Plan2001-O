# E2 — prove reusable native C extraction, link it and execute it in QEMU

**Active assignment for OpenCode.** Continue E1 from commit `65c3d541bda4d352c308bdf588fbfb06ac18ebab` (`docs/KERNEL-NATIVE-GENERATOR.md`, `docs/STATUS.md`). **D2c stays deferred.** The objective is to prove that the *same actual transformation rule* can serve **two different 9Front Dev drivers**, while retaining one source of truth for operations, and that native entries work in a **linked and booted kernel**. Not another per-driver hardcoded template, and not a 27-driver conversion.

## 0. Inspect baseline

Read `AGENTS.md`, `docs/STATUS.md`, `docs/KERNEL-NATIVE-GENERATOR.md`, `docs/CHAN-DEPENDENCIES-INDEX.md`, `tools/kernel_opmap.py`, `tools/test_kernel_opmap.py`, the real `pc64` mkfiles, and both drivers below. Verify `git status --short`, HEAD and the actual current call graph. Protect all unrelated work; no blanket resets/clean/staging, no force-push, no physical-disk tests.

E1 state: one `Analyzer.analyze()` frontend; `--generate-native` emits `kernel_native.h`, `rtc_native.c`, `native-decisions.json` in `build/generated/kernel-native/`. E1's emitter and reviewed mappings are substantially RTC-specific, generator compile tested but **not linked or called**. E1 reported 18/18 tests PASS; default `kernel_opmap.py --check` was **already stale**. Do not treat historical PASS as current execution.

## 1. Two bounded operations, different drivers

MANDATORY proof targets:

1. `sys/src/9/pc/devrtc.c`: **Qrtc READ** (visible `rtcread` selected branch, calls `readnum(offset, buf, n, (ulong)rtctime(), 12)`). This is hardware-backed via `rtctime()`; it must retain its existing RTC initialization/locking semantics. Do **not** write CMOS/NVRAM or modify time in E2.
2. `sys/src/9/port/devcons.c`: **Qpid READ** (visible `consread` selected branch, calls `readnum((ulong)offset, buf, n, up->pid, NUMSIZE)`). This is process-context-backed, **not** a hardware device, and its user-visible policy originates at `consopen`/`devopen` and `consdir[]` mode `0444`. Verify what permissions actually apply; do not assume a shared RTC authorization rule.

Optional third example: `devcons` **Qzero READ** (`memset(buf,0,n)` then return), but only after mandatory pair works; it must be a **second generic emission pattern**, not special code for `cons`.

These are just pilot endpoints; classify nonselected operations as MANUAL/LEGACY as justified. Preserve `Qid` as an internal numeric branch key if useful, but do not introduce a runtime pathname or `Chan`.

## 2. One real generalized transformation rule

Extend the existing `tools/kernel_opmap.py` frontend/IR, **not a second parser**. Implement a single **generic, narrow, fail-closed emitter** for a source-verified read operation of the shape `readnum(offset, buf, n, value_expression, size_expression)` (including E1 RTC's assign-then-return shape and console's direct return). It must derive the selected branch/body/expression/size from the actual tokenized source, `Dev` callback and Qid/Dirtab mapping, not hand-author those two C bodies in Python.

Reviewable per-operation binding DATA may explicitly provide *provenance, allowed helper symbols, type/context requirements, authorization/lifecycle policy and validation constraints*. **No** `if driver == rtc` vs `if driver == cons` native **C body** generation, duplicate `render_rtc_source`/`render_cons_source`, or copy-pasted source-body algorithms. Preserve good reviewed constraints from E1 (source SHA, literal constants and selector assertions), adapting pins when there are legitimate source edits. No silent auto-renew of a stale binding.

Source parse must conservatively refuse unsupported control flow: fallthrough, hidden macro side effects, goto, uninitialized locals, conflicting preprocessor branches, ambiguous indirect calls, or unsafe/unsupported local variables. Important differences: `consread` has a preliminary `if(n <= 0) return n` before dispatch; `rtcread` computes `offset=off`; their native functions must preserve the selected branches' actual semantics, including zero/negative n, offset casts and readnum sizing. A partial token match must **never** generate executable C. No regular-expression-only rewrite that silently changes C semantics.

**Single source of functionality:** both the inherited `Dev` read branch and its generated native entry should use the same underlying executable implementation rather than maintain two diverging copies of the algorithm. Prefer a small, reviewed shared helper extraction where necessary, with `Dev` branch delegating to the helper and the generator emitting a thin direct binding; or a verified generated shared helper consumed by both paths. Pick the smallest scheme that actually builds in Plan 9 C and preserves upstream legacy logic. Document exactly which part of the transformation is generated and which part required a one-off manual review; do not claim a fully automatic C-to-C refactoring if manual source editing was needed.

The C emitted for both operations must have **no `Chan*`, `qid.path`, `Dirtab`, `walk`, `namec` or namespace traversal** in its executed helper chain. Kernel `up` may still be used for Qpid, but its context and authorization must be explicit; native helper availability is NOT a permission to expose the API indiscriminately to userspace. No new general syscall, `/dev` adapter, fake `Fgrp`, or new OID kind.

Keep generating a manifest for active `pc64` devices, with correct DIRECT/BRIDGE/MANUAL/LEGACY reasons. Mark DIRECT only for truly backed and validated operations. Other E1 claims (e.g. RTC NVRAM read/write) must remain accurate or be downgraded explicitly rather than discarded silently.

## 3. Test true generality, not merely a second hardcoded recipe

Use `tools/test_kernel_opmap.py` with fixtures that demonstrate:
- RTC Qrtc and console Qpid use **the very same renderer/extractor** with distinct input expressions and initialization/proc-context contracts.
- An **additional synthetic static Dev fixture** (different names, selector and size) works without adding a new C emitter branch or driver name to Python.
- `readnum` assign/return vs direct-return shapes, source line mapping, byte-offset behavior, length `n<=0`, and permission provenance.
- Deliberate unsupported syntax, altered permission rule, modified source hash, unresolved helper, macro alias, indirect callback, preprocessor branch or unsafe local variable cause a deterministic explicit refusal — never guessed C.
- Output is byte-for-byte reproducible; `--generate-native --check` catches stale or modified output.
- No per-driver duplicate algorithm in emitted C or the driver source; inspect source changes to substantiate this.

Be cautious about a semantic trap: matching the `readnum` call is not sufficient proof that the wrapper has the original `devopen` permission behavior or that every inherited pre-dispatch check was preserved. Include an operation-level authorization contract or explicitly label a helper **kernel-internal-only**, never silently public.

## 4. Link and boot a real native probe, without disrupting D2b

Produce real generated `.c/.h` files in `build/generated/kernel-native/` and arrange **opt-in integration** into the `pc64` Plan 9 kernel build from that directory (or copy generated files to an ignored build staging directory under `build/` through a reproducible mk step). Provide a coherent dependency graph so regeneration precedes compilation; a manually copied static generated file is not acceptable. Do not add generated multi-megabyte artifacts to Git. The normal kernel build must continue to work without the opt-in probe mode.

Create one narrowly scoped **opt-in boot test switch** (name `onativeprobe=1` or equivalent, distinct from `oboot=server` selector) and a disposable-QEMU test `tools/test-o-native-generator.sh` (name indicative) that verifies:
- both generated symbols **actually link** into the kernel (no undefined or discarded references), and both are invoked in a genuine kernel process after valid initialization, not simulated with host Python or serial text;
- Qrtc reads a plausible numeric time with bounded read and correct size; Qpid reads the current probe process's PID with correct formatting and offset; capture exact return count, source symbol ID, and value on UART;
- the probe has a legitimate `up` process context and the RTC is initialized appropriately. Audit `chandevreset()` vs `chandevinit()` in native `oboot=server` (the latter may not have run); **do not silently call hardware before device readiness**. Avoid duplicate init or unsafe PCI/clock startup. Prefer a separate one-time disposable test boot if it isolates those concerns; preserve D2b's existing pathless boot.
- errors (unsupported selector, bounds, invalid input length, absent permission) are tested when safe and can be triggered without dangerous privileged writes. RTC and Qpid are **read-only** in this experiment. If normal read outputs vary (time/PID), assert invariant formats and ranges, not exact fixed timestamps.
- trace native calls and a short list of legacy-path/Chan counters during the measured probe. **No namec/walk or synthetic Chan** may be introduced by the **new native call chain**. State exactly the trace window; do not conflate unused legacy kernel code or the separate setup phase with execution of a native operation.
- no kernel panic, no QEMU hang, hard timeout with saved serial logs. Keep verification logs in `build/verification/`. Test on disposable images only.

Compare to legacy results / source policy where defensible. A probe reading two values proves actual native dispatch but **not** complete equivalence of all legacy modes, offset/permissions/lifecycle or whole-kernel Chan independence. Do not claim more.

**If the selected probe context cannot guarantee RTC initialization or process readiness without substantial new boot machinery**, prefer fail-safe `E2 NOT YET` with the exact blocker, rather than fabricating a test hook that bypasses hardware safety. Finish static generic-generation tests even if runtime is blocked.

## 5. Preserve regression and correct the stale OMAP signal

Run and explicitly report actual outcomes:

```sh
python3 tools/test_kernel_opmap.py
python3 tools/kernel_opmap.py --generate-native --config pc64 --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --check --config pc64 --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --check
WHAT=kernel tools/build.sh
tools/test-o-native-generator.sh  # use actual chosen script name
tools/test-oboot-server.sh
tools/test-oboot-output.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
```

Run other Boot A/B/C/exec/handles regressions if shared boot or driver code changed. `test-oboot-server.sh` requires built host tools/selfroot; follow existing build instructions. Record PASS/FAIL/NOT RUN without inventing results.

If normal OMAP `--check` is still stale, establish **why** (real source fingerprint vs tracked artifacts). If current source changed and regenerating `docs/KERNEL-OPMAP.{json,md}` is legitimate, run `--write` *deliberately*, inspect the large diff and document its cause. Do not weaken `--check`, automatically mask failure, or stage unrelated churn just to produce a green check. This housekeeping must not block or obscure the substantive E2 gate if reconciliation turns out extensive.

## 6. Scope, documents and completion

- No 27-driver batch conversion, userland keyboard/REPL (D2c), `kbdfs`, new native filesystem, general resource registry, 9P proxy, OID ontology work, or wholesale Plan9 kernel rewrite.
- Keep ONE scanner `tools/kernel_opmap.py` and its test file; no obsolete new tools except the meaningful runtime regression test.
- Keep docs compact: extend `docs/KERNEL-NATIVE-GENERATOR.md` with E2 source-to-output mapping, generic rule and refusal cases, manual-reviewed changes, link/probe evidence and limitations; update `docs/STATUS.md` and `docs/to_chatgpt_review.md`. No resurrection of old `O-BOOT-EXPERIMENT-*.md`.
- Commit and push intended changes via existing completion automation.

**Required final verdict:**
```
E2 GENERIC EXTRACTION PASS / PARTIAL / NOT YET
EXTRACTION: RTC Qrtc READ + CONS Qpid READ, same renderer = ...
SINGLE IMPLEMENTATION: legacy/native share actual underlying operation = ...
BUILT AND LINKED: Plan 9 6c/6l evidence ...
QEMU EXECUTED: real RTC and PID, exact probe markers ...
SAFETY: process context, init, permissions, rejected cases ...
OMAP: old --check and native --check outcomes ...
D2b REGRESSION: PASS / FAIL / NOT RUN
REMAINING: precisely what still uses Chan/Walk/Qid or needs manual review
```

**E2 PASS requires: two distinct real drivers using the same extraction mechanism, generated C actually linked and executed from a booted kernel, safe behavior and preserved D2b.** Generating two handwritten per-driver wrappers is **not** a PASS. If only static generation or linking succeeds, report PARTIAL honestly.
