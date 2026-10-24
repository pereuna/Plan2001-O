# E3 — automatically propose reviewable Chan-free C extraction patches

**OpenCode work order.** E2 is complete at implementation commit `ecd945e23706bd5e6f4eb28384121c8c76a09d31` (last observed branch HEAD `365959fb6191601c2e024244fb438f7e45a2df8d`). **D2c stays deferred.** E3 is a *source-to-source transformation proposal* experiment: use the ONE existing `tools/kernel_opmap.py` analyser to locate a supported selected `Dev`/Qid operation in its **unmodified original code**, generate a common Chan-free helper, replace that one legacy case with a helper call, and output a **reviewable unified diff**. **Do not automatically apply proposed patches to tracked kernel sources or activate them in normal builds.** No batch conversion of 27 drivers.

## Baseline and semantics

Read `AGENTS.md`, short `docs/STATUS.md`, `docs/KERNEL-NATIVE-GENERATOR.md`, `docs/CHAN-DEPENDENCIES-INDEX.md`, `tools/kernel_opmap.py`, `tools/test_kernel_opmap.py`, both drivers and E2 probe. Check HEAD and `git status --short`. Preserve unrelated edits and existing E2 native generator, native-probe integration, D2b kernel boot and all current tests.

The E2 frontend already provides `Analyzer.analyze()`, `Function`, `Switch`, `CaseLabel`, `Token` **with original source `offset`, line/column**, `Dirtab`, Qid values, source hashes, call edges, and readnum extraction validation. **Reuse this parser and token spans**. Do not create a second C scanner or use a whole-file regex substitution. Source bytes outside expressly authorized spans must remain identical (including comments, `#if` lines and unrelated branches). Treat the result as a candidate requiring review, not as a proof of semantic equivalence.

## Positive candidates: two historical originals + one new HEAD candidate

The current branch already contains the manually extracted E2 helpers, so it is **invalid** to claim to extract those same two operations from current HEAD. Use the exact Git revision `7b4dfac4903e909dc2a00f37e9320335808029ac` as the **PRE-E2 input** in a disposable staging tree or a minimal test fixture constructed from `git show`. Never checkout/reset the user's working tree. Its relevant source branches are:

- `sys/src/9/pc/devrtc.c` → `rtcread` case `Qrtc`:
  ```c
  n = readnum(offset, buf, n, (ulong)rtctime(), 12);
  return n;
  ```
  `ulong offset = off` is declared **before** the switch and **still needed by Qnvram**. The generated helper must reconstruct its own local offset; the original shared local must not be removed or broken.
- `sys/src/9/port/devcons.c` → `consread` case `Qpid`:
  ```c
  return readnum((ulong)offset, buf, n, up->pid, NUMSIZE);
  ```
  `vlong offset = off` is set before the switch and shared by many other cases. The original handler has `if(n <= 0) return n;` **before dispatch**, which a native helper must preserve for direct calls, while leaving the legacy pre-dispatch guard unchanged.

Also attempt an **additional current-HEAD candidate** `devcons.c` → `consread` case `Qppid` (currently still `return readnum((ulong)offset, buf, n, up->parentpid, NUMSIZE);`). This should produce an independent proposal *without* a new driver-specific template. Its `up` context, `0444` access policy, pre-dispatch guard and parent PID semantics must be recorded. **Do not apply the Qppid patch to HEAD.** If safe extraction cannot be established, output a precise refusal and keep E3 PARTIAL.

Use a third simple *synthetic* static-Dev fixture with renamed selector/locals/value/size to prove this is a general transformation, not a hidden RTC/CONS/Qppid allowlist. Generated function names must be deterministic and collision-checked against declared and called symbols. No E3 source modifications to NVRAM, RTC writes, device reset, IRQ, PCI, network, pipe or O-volume storage.

## Transformation rule

Extend the existing E2 narrow `readnum` recognizer so that it accepts a selected **legacy branch BEFORE a helper exists**, and emits **two related edits** from the same validated IR:

1. Insert a non-static, kernel-internal shared helper `long <generated_name>(void *buf, long n, vlong off)` into the same C translation unit, using the verified original value expression, width, offset handling, return shape and pre-dispatch `n <= 0` guard. Choose a safe insertion location outside functions, declarations and conditional compilation. Do not move `#define`s, comments or unrelated code; avoid including expression dependencies not visible there. Preserve the original expressions/casts precisely or record and justify strictly equivalent normalization.
2. Replace **only the one selected Qid case body** with `return <generated_name>(buf, n, off);`, keeping the same case label and preserving the original function's other cases, default/error handling, init, `open` permissions and lifecycle. The new helper becomes the **single executable implementation** used by the legacy case and, once accepted in a separately reviewed step, by the existing generic E2 native emitter.

The ordinary `Chan`/Qid/Dev machinery may remain in the wrapper; the *extracted helper and its bounded transitive call chain* must not need `Chan`, path walk, mount, `namec`, `Dirtab` or synthetic `Fgrp`. An internal numeric selector is allowed, but do not equate it to persistent OID. Native user access is NOT authorized by creating a helper; these remain kernel-internal until a separately designed capability boundary.

**Hard problem: data/control dependencies.** Do not copy arbitrary lexical text from a switch branch and hope it compiles. For each proposal, prove or conservatively verify:
- selected branch has no fall-through, `goto`, `break`-dependent return, hidden side effects, aliasing/captures, conflicting conditional compilation or multiple exits;
- every local referenced in the copied branch has its type/initialization and lifetime resolved; shared locals still needed by neighboring cases remain untouched;
- no `Chan` fields (`c->qid`, `c->aux`, flags, offsets, mode), member or indirect callbacks with unknown target, unsafe macros, missing `up` context, unknown helper declarations, or unreviewed hardware side effects occur in the proposed helper;
- permission evaluation still happens at the original `open`/Dirtab boundary; direct kernel calls are explicitly declared **kernel-internal-only**, not silently equivalent to an authorized userspace API;
- negative/zero lengths, offsets, numeric conversions and errors preserve the actual source behavior. In particular `consread`'s `n<=0` guard and RTC's shared `offset` have different semantics. Check symbol visibility and target Plan 9 C dialect.

If any requirement cannot be validated **fail closed** with a machine-readable reason and source evidence. Do not label a copied helper DIRECT merely because it compiles.

## Output and CLI

Add one opt-in `tools/kernel_opmap.py` mode, naming at your discretion, e.g.:

```sh
python3 tools/kernel_opmap.py --propose-extraction \
  --config pc64 --source-tree build/e3/pre-e2 \
  --selectors rtc:read:Qrtc,cons:read:Qpid \
  --out-dir build/generated/e3-pre-e2

python3 tools/kernel_opmap.py --propose-extraction \
  --config pc64 --selectors cons:read:Qppid \
  --out-dir build/generated/e3-head
```

Document the **actual working CLI** if changed. For historical input, either accept a snapshot with the normal repo build/config context or create it safely from an archive in an ignored temp/build directory. Do not require rewriting all E2 pinned hashes to analyze old input; proposal analysis is a **separate opt-in stage** with its own pinned raw input hashes and approval state. A proposal may be generated but **must not automatically become an approved DIRECT binding**. After an eventual human-reviewed patch is applied, E2's normal generator may use a consciously reviewed and re-pinned binding; never silently bless the new source hash.

Place outputs under ignored `build/generated/` only:
- `*.patch`: standard deterministic unified diff using real repo-relative paths; suitable for `git apply --check` against the **exact named base**.
- `extraction-decisions.json`: schema/version, source commit (if known), per-source full SHA-256, selected Dev/handler/Qid, line and byte spans, value/size/offset/guard, newly introduced symbols, external dependencies, permission/context/lifecycle notes, patch hash, DIRECT-CANDIDATE / REFUSED / ALREADY-EXTRACTED status, and reasons.
- optionally `*.preview.c` for review, **not** an applied source edit.

Support a check/determinism mode; no unexpected writes to tracked code or `docs/KERNEL-OPMAP.*` in dry-run. A rerun against identical sources yields byte-identical patch and manifest. A modified source hash, wrong source-ref, stale span, overlap, duplicate helper or changed case causes **explicit refusal**, never fuzzy patching. Keep existing `--write`, `--check`, `--stats`, `--generate-native`, native `--check` compatible with E2. Do not add any duplicate parser to `tools/`.

## Test gates (must genuinely run)

Expand `tools/test_kernel_opmap.py` with tests for:
1. pre-E2 Qrtc and Qpid generate the two expected reviewable patches using ONE transform rule; new HEAD Qppid candidate or an honest refusal;
2. synthetic driver produces same patch shape without any driver-name-specific C emitter;
3. valid `git apply --check` on a **disposable copy of the exact matching base** (not checkout/reset on main); applying to this isolated copy changes exactly approved lines, leaves neighboring `Qnvram`, `Qppid`, `Qkmesg`, `Qdir` and pre-dispatch guards correct;
4. optional isolated Plan 9 `6c` compile of patched files, plus compare their semantics and expected helper calls with E2's manually reviewed source. A generated patch is NOT a working Chan-free native kernel until compiled/linked/called;
5. fail-closed cases: changed SHA; offsets, comments/strings and line endings; incompatible casts; parameter/local name collision; `#if` branch; `case` fall-through; multiple assignments; unreviewed macro/callback; unresolved `up`; pre-dispatch side-effect or missing guard; overlapping patch spans; already-extracted branch; missing/ambiguous Qid;
6. a second run yields identical output, checking mode detects tampering and **generator never modifies tracked files**.

Required commands (adapt script names to chosen CLI, report exact executions):
```sh
python3 tools/test_kernel_opmap.py
python3 tools/kernel_opmap.py --check
python3 tools/kernel_opmap.py --generate-native --config pc64 --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --check --config pc64 --out-dir build/generated/kernel-native
# E3 proposal creation and E3 proposal verification for both source sets
# git apply --check, and apply ONLY to disposable copy for test
```

Because the task is **proposal-only**, do not modify tracked kernel C files, build configs or execute a new user-facing native ABI. If generator source/tests alone change, normal kernel rebuild and QEMU may be reported **NOT RUN** with rationale; optionally rerun `tools/test-o-native-generator.sh` and `tools/test-oboot-server.sh` if built artifacts are available, reporting their actual status, never assumed success. If you intentionally perform a separate isolated trial compile, label it as such, not as regression verification of main.

## Documentation and finish

Keep the repo's default agent context small. Update `docs/KERNEL-NATIVE-GENERATOR.md` **briefly** with E3 CLI, candidate source hashes, exact patch/refusal outcomes, unhandled syntax and proof scope. Update the concise E3 section of `docs/STATUS.md` and write final factual summary to `docs/to_chatgpt_review.md`. Do not regenerate large OMAP files unless actual scanned source changed, and never restore `O-BOOT-EXPERIMENT-*.md`. Existing `docs/to_opencode.md` is the active assignment; the completion automation can preserve it as history or replace it only per existing agent workflow. Commit/push only intended generator, tests and compact documentation using existing OpenCode completion automation.

**Final result format (evidence, not optimism):**
```
E3 SOURCE EXTRACTION PROPOSALS: PASS / PARTIAL / NOT YET
PRE-E2 RTC Qrtc: PATCH / REFUSED — source SHA, exact edits, apply --check
PRE-E2 CONS Qpid: PATCH / REFUSED — preserved guard, exact edits
HEAD CONS Qppid: PATCH / REFUSED — no source mutation
SYNTHETIC GENERALITY: PASS/FAIL
SINGLE IMPLEMENTATION: original case -> proposed shared helper -> native generator compatibility
SOURCE SAFETY: no tracked source touched; stale/unsafe cases rejected
E2 CLI REGRESSION: PASS/FAIL
RUNTIME AND KERNEL BUILDS: actual PASS/FAIL/NOT RUN
REMAINING: what must still be reviewed manually and what cannot be auto-converted
```

**E3 PASS** means two independent real historical branches plus a synthetic new-driver case yield correct, deterministic, reviewable source patches from the existing analyser, the patch applies cleanly to the exact disposable base, source semantics and adjacent branches are convincingly preserved, and all old generator tests remain intact. A runtime kernel-wide Chan-free claim is categorically out of scope. If the HEAD Qppid candidate is refused for a documented safety reason, that does **not** force a false PASS; record it transparently.
