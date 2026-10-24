# E4 — Codex Astra: independent audit, real generator execution, reviewed kernel integration

**Executor: Codex / Astra.** This is the **only active coding assignment** for this iteration; `docs/to_opencode.md` has intentionally been removed. Read this document directly in the repository. Do **not** invoke OpenCode or its `/nexr` command, automate another agent, or treat old agent reports as independent evidence.

## Mandate

Act as **independent reviewer, tester, integrator and acceptance authority** for the E1–E3a native-operation toolchain made by OpenCode. Make a substantive, **real end-to-end production-of-evidence step**, not another design report: on the **current source tree**, run `tools/kernel_opmap.py` to generate a previously unapplied C extraction patch, critically inspect the resulting C, decide whether it is safe, then integrate **one** approved native operation through generation → compilation → linking → a disposable QEMU boot. Review and fix blocking flaws in the generator when needed; do not simply trust its `DIRECT-CANDIDATE` flag.

**Primary target:** `sys/src/9/port/devcons.c`, `consread` **Qppid READ** (`readnum((ulong)offset, buf, n, up->parentpid, NUMSIZE)`), which E3a currently proposes as `consread_qppid_read` but **has not applied**. This is the third distinct real operation following E2's Qrtc and Qpid. It is a process-context operation, not a hardware identity. Qppid selector value must be derived from live enum/Dirtab source (presently expected 13), not assumed.

**Stretch investigation, not required for approval:** identify one additional non-`readnum` path, e.g. `devcons` Qzero or `devpipe`, and explain from the existing OMAP why the current rules refuse it. Do **not** invent a weak generalized conversion to pass an extra example. E4 success is independently reviewed and truly executed **Qppid**, plus preserved Qrtc/Qpid and D2b; NOT a 27-driver bulk rewrite.

Project base as last observed: `22f3e0dea4505f755aa7bf1f74d26b5178c46728` (E3a `70799b92a62da61de067fc4ea2cbe081b3f199f6`). **Check actual HEAD, git status, working tree, existing user edits, and the files before relying on these SHAs.** Read `AGENTS.md`, `docs/STATUS.md`, `docs/KERNEL-NATIVE-GENERATOR.md`, `docs/to_chatgpt_review.md`, `tools/kernel_opmap.py`, `tools/test_kernel_opmap.py`, `tools/test-o-native-generator.sh`, `tools/build.sh`, `sys/src/9/port/devcons.c`, `sys/src/9/pc/devrtc.c`, `sys/src/9/pc64/onativeprobe.c`. Load large `KERNEL-OPMAP.json` only selectively. No new scanner, no third-party Python dependency.

## 1. Independent critical audit — before applying a patch

Inspect the **actual Python implementation** and its generated proposal, including:
- token span/source-byte accuracy, hash pinning, idempotence and detection of already-extracted branches; preprocessor/unknown-syntax handling; failure atomicity;
- E3a's `_e3_classify_prefix` and associated prefix policy: mutate-before-switch cases (`offset += 1`, later `offset = ...`, `n`/pointer/member writes), no false `DIRECT-CANDIDATE` when an effect is lost;
- local offset reconstruction, copied `n <= 0` guard, full `readnum` formatting/length/offset semantics, possible negative values/unsigned conversion, symbol names, extern visibility, generated helper placement, `up != nil` in the real call context;
- pathless transitive helper chain and read-only behavior; correctness of `Qid` selector mapping **without** namespace traversal;
- **authorization boundary**: inherited `consopen/devopen`/Dirtab `0444` applies to legacy requests; natively callable `consread_qppid_read` has **no independent user authorization**. This is acceptable ONLY as a strictly kernel-internal operation with an explicit caller/context contract, never publish a syscall or expose it to arbitrary userspace;
- build steps: generated `kernel_native.c` must be freshly built from validated source after the patch, not an old staged file, and checked against the same source version actually compiled.

If any audit finding is potentially unsafe, document it with an exact source location, minimal reproducer and fix or **HOLD**. A green test suite never overrides a demonstrated semantic flaw. Do not weaken fail-closed checks, auto-renew all pinned hashes, or copy handwritten Qppid native code to fake generation. Investigate what the generator can *actually* prove.

## 2. Execute original generator and REVIEW its actual output

From repo root, generate the E3a proposal **without touching tracked sources**:

```sh
python3 tools/kernel_opmap.py --propose-extraction --config pc64 \
  --selectors cons:read:Qppid --out-dir build/generated/e4-astra
python3 tools/kernel_opmap.py --propose-extraction --config pc64 \
  --selectors cons:read:Qppid --out-dir build/generated/e4-astra --check
```

Check `extraction-decisions.json`, selected source SHA/operation/status, **open and read the full generated `devcons.c.patch`**, its source and destination hunks, byte spans, and hash. Earlier E3 report expected `abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3`; compare but don't treat a known digest as proof of safety.

Run `git apply --check` then `git apply` **first in a disposable exact-base worktree/copy only**. Compare to original C branch and examine that unrelated Qpid, Qkmesg, Qdir, read guards and offset locals are unchanged. Verify helper compilation against real Plan 9 headers with the existing VM/6c mechanism when reasonable. Preserve the repo's own current test code and tool; no vendor tool installs unless truly needed.

**Approval boundary:** Only after explicit source review and successful isolated application should Astra apply the **same patch** to the actual checked-in `devcons.c`. Do not manually implement the proposed C body instead. If the proposal is wrong, fix its generic generator rule, regenerate, re-review, repeat. A failing unsafe candidate means **HOLD**, not an invented success.

## 3. Prove current E2 native generation consumes the applied result

Once reviewed Qppid patch is applied:
- Extend only the **reviewed operation data** in `NATIVE_REVIEWED_BINDINGS`: add `read:Qppid` and its `consread_qppid_read` helper with precise allowed expression `up->parentpid`, `NUMSIZE`, context `up != nil`, read-only, kernel-internal-only. Keep Qrtc and Qpid. Review/repin `devcons.c` SHA **only after** examining the patch; reconcile `E3_PINNED_SHA` deliberately for this new source, retaining old historical hashes as appropriate. No automatic blanket pin updates. If E3 proposal on the new HEAD says `ALREADY-EXTRACTED`, that is correct.
- Use the SAME existing readnum native renderer, producing a `native_cons_qppid_read` symbol and `native_cons_read(selector,...)` dispatch alongside `native_cons_qpid_read`. No per-driver C renderer branches, no duplicate readnum algorithm.
- Confirm the tracked legacy `consread` calls precisely the same helper, and all native calls stay inside the kernel without `Chan`, `namec`, `walk`, `Dirtab` or Qid-path semantics in the call chain.
- Keep E2's opt-in `NATIVE_PROBE=1` build. Integrate Qppid into the **existing** `onativeprobe.c` and **existing** `tools/test-o-native-generator.sh` rather than creating a second probe framework. For the real probe process, output a short marker proving the native Qppid value equals `up->parentpid` (possibly 0), verify formatting/length, a nonzero offset partial read, zero-length and out-of-range behavior. Existing RTC Qrtc and CONS Qpid markers and unsupported selectors must remain valid. Instrument/cross-check the same BEGIN–END path counters for no introduced pathname operations. Avoid relying on a constant PID/PPID or current wall clock.

## 4. Minimal, discriminating verification — not a large test campaign

Use only the following *necessary* gates, in this order; avoid blanket `WHAT=all`, unrelated boot/exec/storage/network batteries and expensive fuzzing:

1. **Source-level gate:** `python3 tools/test_kernel_opmap.py` and add only **targeted** tests for Qppid binding, generator reproducibility, and any discovered defect. Include one E3a unsafe mutation negative case as independent sanity check, not dozens of redundant tests. All current E3a tests must continue to pass.
2. **Inventory/generation gate:** `python3 tools/kernel_opmap.py --check`, E3 proposal check and E2 `--generate-native` plus native `--check`. After the source edit, expected source fingerprints **will** change: if OMAP `--check` fails for a real new source fingerprint, deliberately run `--write`, inspect and constrain the generated diff; do not suppress check failures or commit unrelated noise.
3. **Compile/link gate:** `NATIVE_PROBE=1 WHAT=kernel tools/build.sh` and verify generated symbols in `9pc64native` (including Qppid); **also** `WHAT=kernel tools/build.sh` for the normal kernel. Consider build artifact cleanup/order: normal build may replace staging/loader; run the native QEMU probe while its native image is known fresh.
4. **Single native QEMU gate:** `tools/test-o-native-generator.sh` run **once** on disposable firmware/disk images using freshly built `9pc64native`. Require real kernel execution, correct Qrtc/Qpid/Qppid invariants, no panic/hang, timeout bounded, new call chain path counters zero. Store serial evidence under `build/verification/`.
5. **One service continuity gate**: `tools/test-oboot-server.sh` if test prerequisites exist; this verifies D2b survived. If this gate is impractical, clearly mark **NOT RUN** and **HOLD** on final integration approval rather than reporting PASS. Do not execute the unrelated full regression suite.

A PASS requires source audit AND fresh generator execution AND successful compile/link AND fresh QEMU proof AND D2b continuity. If a gate fails, fix a narrowly identified defect, rerun only its necessary dependent gates, and explain the rerun. Do not change tests merely to match incorrect output. Never run tests against physical disks or non-disposable images.

## 5. Change control, independent verdict, and report

Astra has authority to *accept or reject* the reviewed generated change, not to silently redefine acceptance criteria. Respect existing uncommitted user work; if the workspace is dirty/conflicted, use an isolated branch/worktree rather than reset/clean or overwrite. Make the smallest bounded functional edits necessary to deliver the E4 Qppid vertical slice. No new userspace ABI, OID model, driver mass migration, unrelated refactors or OpenCode configuration work.

Keep documentation compact: update existing `docs/KERNEL-NATIVE-GENERATOR.md` and `docs/STATUS.md` with actual E4 result. **Write Astra's independent review** to the single file `docs/to_astra_review.md` (do not overwrite OpenCode's historical `docs/to_chatgpt_review.md`). Include the source commit and source hashes, generated patch digest, reviewed code lines, findings/actions, each gate's exact command, observed PASS/FAIL/NOT RUN, serial log path and evidence markers, and residual risks. Do not create additional large artifacts in `docs/`.

Decision:
- **APPROVE** only when all required gates pass and the generated C passes Astra's independent semantic and safety review. Commit/push approved code + compact documentation to the intended working branch (use repository's established branch policy; state branch and commit). Do not create a PR merely for ceremony, but preserve a reviewable commit history.
- **HOLD** if an essential test or semantic proof is missing, with a precise blocker. Preserve candidate patch and test logs under ignored `build/`; do NOT commit unreviewed kernel edits as approved.
- **REJECT** when the proposal is demonstrably unsafe and cannot be repaired within this bounded task. Give a minimal source-based counterexample; do not force the kernel change through.

Use this final structure in `docs/to_astra_review.md` and the user-facing summary:

```text
ASTRA E4 VERDICT: APPROVE / HOLD / REJECT
BASE HEAD / FINAL COMMIT / BRANCH:
GENERATED PATCH: source SHA, patch SHA, source lines reviewed
INDEPENDENT AUDIT: concrete findings + fixes; authorization and process-context boundary
NATIVE C: helper, E2 binding, generated dispatcher, legacy single implementation
VERIFICATION: generator tests; OMAP/native checks; normal/native builds; QEMU Qrtc/Qpid/Qppid; D2b
PATHLESS WINDOW: actual counters, precise scope
UNRESOLVED RISKS: not full driver conversion or whole-kernel Chan removal
```

**This is a real acceptance experiment, not a request to rubber-stamp OpenCode. Be critical: inspect generated output before executing it, report limits exactly, stop safely on failed gates, and approve only if the evidence warrants it.**
