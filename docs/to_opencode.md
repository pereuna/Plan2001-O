# E3a — close unsafe pre-dispatch dataflow acceptance in extraction proposals

**OpenCode assignment; bounded E3 safety repair.** Current E3 implementation: `30d0ca73de059df5b3b6ffa1635e1f53beb0625c`, last observed HEAD `0af71e5f5f69da9c554d396438c32e1d0254fbdf`. E3 proved *proposal-only* source extraction (RTC Qrtc, CONS Qpid historical originals and HEAD CONS Qppid). **Do not move to E4, automatically apply patches or modify tracked kernel driver sources. D2c remains deferred.**

## Defect to reproduce first

The `tools/kernel_opmap.py` routine `_e3_validate_prefix()` near E3's line ~5230 accepts some statements between the handler's entry and its `switch(c->qid.path)` without analyzing their effect on values used in an extracted branch.

For example this eligible synthetic Dev handler is **unsafe to extract as currently implemented**:

```c
long handler(Chan *c, void *buf, long n, vlong off)
{
    ulong offset = off;
    offset += 1;
    switch((ulong)c->qid.path){
    case Qtest:
        return readnum(offset, buf, n, 4242, 8);
    }
    return 0;
}
```

The proposed helper reconstructs `ulong offset = off` but can omit the `offset += 1` effect; therefore the native entry can read different bytes than the legacy path. Compound assignment `+=` is tokenized but not handled by `_e3_top_level_eq()`; the `_e3_validate_prefix()` path for a statement with no simple `=` rejects calls but can let this mutation through.

**Prove this exact failure with a synthetic fixture BEFORE modifying the implementation.** Capture the observed old `DIRECT-CANDIDATE` (or actual different result) in the report without committing an intentionally failing suite. Never assert a failure not actually reproduced.

## Repair with strict, conservative prefix semantics

Maintain **one parser**: reuse `Analyzer`, existing token stream, `Function`/switch source spans, `_e3_parse_branch` and E3 patch machinery. Do not add `tree-sitter`, GCC, another C lexer or a competing tool. Minimal Python stdlib-only modification.

The safety invariant must be:

> A `DIRECT-CANDIDATE` is permitted only when every state read by the extracted helper at the selected branch entry is determined entirely by the helper's parameters, its explicitly reconstructed and immutable local initializers, permitted process context and validated helper calls; no unmodeled pre-switch modification, side effect or additional control flow may be lost.

Implement an explicit **fail-closed, token-aware pre-dispatch statement classification**. An unknown statement must not mean 'safe'. It is sufficient for E3a to *reject* constructs; no new C rewrites required.

Support just the already-reviewed harmless prefix syntax required by E3 positives:
- ordinary declarations without initializers and without side effects (including pointer locals, enums/typedef types and `extern` as already encountered in RTC/CONS);
- one reviewed initialization of a relevant scalar offset local from `off` in the actual C type (e.g. `ulong offset = off;`, `vlong offset = off;`), without later writes; preserve original scope and casts;
- known `if(n <= 0) return n;` and the existing simple directory guard, when precisely matched, with no hidden additional statements;
- unrelated declarations do **not** imply arbitrary independent assignments are safe.

Explicitly detect and refuse any pre-switch mutation or unsupported construct not proven harmless: all compound assignments `+= -= *= /= %= <<= >>= &= |= ^=`, plain reassignments `offset = ...;`, writes to `n`, `off`, `buf`, `up`, `c` or their pointed-to/members, `++/--`, dereferenced/array/member writes, function-call side effects, conditional (`?:`) operations, chained assignments, comma expressions, statement expressions, pre-switch `return` outside approved guards, and unrecognized `if`/control flow. The parser must not confuse assignment `=` with comparison `==`, nor a declaration initializer with a later assignment. Detect read/modify/write even when the RHS does not call a function.

For pre-switch operations not used by the target branch, err on the side of **REFUSED** unless the code can truly prove irrelevance; do not attempt speculative dataflow analysis in E3a. If a once-initialized offset local is mutated, never recover by copying just its initializer. The actual declaration/initialization used by the extracted case must be unique and unambiguous.

Coordinate `_e3_parse_locals()` with `_e3_validate_prefix()` so they cannot independently interpret an unsafe statement as a safe local initializer. A first-pass normalized classification/IR shared by both is ideal if small; do not create two diverging validators. Preserve original E3 exact source-span patching and existing SHA pin/refusal behavior.

**Source-specific cross-check:** pre-E2 `rtcread` contains `ulong offset = off` shared with Qnvram, pre-E2 `consread` contains `vlong offset = off` plus unrelated declarations and its approved `n<=0` guard, HEAD `consread` Qppid shares those conditions. All three must *still* be proposed correctly; the shared legacy locals and other switch cases must not change.

## Regression tests are the principal acceptance evidence

Expand `tools/test_kernel_opmap.py` using the existing `e3_synthetic_spec()`, historical `e3_pre_fixture()` and disposable patch-copy helpers. At minimum:

1. **Reproduction + regression:** prefix `offset += 1;` is **REFUSED**, with a reason naming the unreviewed mutation and **no patch**.
2. Reject `offset -= 1`, `offset <<= 1`, `offset |= 1`; and other compound assignment token kinds (prefer parameterized coverage).
3. Reject `offset = off + 1;` or `offset = 4;` after a previously accepted initializer, including duplicate plain `=` and aliases as appropriate.
4. Reject `n = n / 2;`, `n += 1;`, `off += 1;`, `buf = ...;`, `*buf = ...;`, `c->offset = ...;`, `up->pid = ...;` and `buf[0] = ...;` in pre-dispatch context. No false `DIRECT-CANDIDATE`.
5. Reject pre-switch `return n;`, unsupported conditional and call, initializer with side-effect call, chained assignment, and unknown statements. Include innocuous comparisons *inside existing supported guards* as positive controls; do not suddenly reject all `==` tokens.
6. Keep historical `7b4dfac` RTC Qrtc and CONS Qpid patches **byte-identical** (previous SHA-256 values `7b715be660380e5f75d323d38b5f0067c158508691e7e33e8c05e3102402b524` and `ce6672282fead3da4f6ac49d393e05c4822f2e1fa597d9f8fa125abf188de324`) and HEAD CONS Qppid patch `abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3`, unless genuinely necessary and documented. All must pass `git apply --check` on corresponding disposable sources.
7. `ALREADY-EXTRACTED`, stale source SHA, preprocessor/macro/ambiguous Qid refusals must remain correct. The candidate/patch output must stay deterministic; `--check` must detect tampering; test that tracked C sources are unchanged.

Use parameterized cases or table-driven fixtures rather than repeating verbose tests. For *each* unsafe fixture assert `candidate.status == REFUSED`, an actionable reason in `extraction-decisions.json`, and **no patch generated**, not just that Python raises an exception or a compile would fail. A negative case that accidentally yields `DIRECT-CANDIDATE` is a regression failure.

## Execution and acceptance

Run and report actual results (PASS/FAIL/NOT RUN):

```sh
python3 tools/test_kernel_opmap.py
python3 tools/kernel_opmap.py --check
python3 tools/kernel_opmap.py --generate-native --config pc64 \
    --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --check --config pc64 \
    --out-dir build/generated/kernel-native
# Recreate/check E3 patches against pinned pre-E2 fixture and HEAD Qppid;
# use the actual documented --propose-extraction command and --check.
# git apply --check on disposable exact-base source snapshots only
```

This is a **generator safety repair only**. Do NOT modify tracked `sys/src/9/*` files, build scripts or kernel behavior. Kernel rebuild or QEMU re-run is **not mandatory** if no build-relevant source changed; if run, state which existing artifacts were used, and avoid calling historical logs new tests. Do not run `--write` for giant OMAP output unless a genuine fingerprint difference requires it; do not mask a failing `--check`.

Document concisely in `docs/KERNEL-NATIVE-GENERATOR.md` (short E3a subsection) and `docs/to_chatgpt_review.md`; update `docs/STATUS.md` only if it clarifies the active status. No new large reports or resurrected `O-BOOT-EXPERIMENT` files. Commit/push intended code, tests and compact docs with existing OpenCode completion automation; preserve unrelated work.

**Required final report:**

```text
E3a PREFIX SAFETY: PASS / PARTIAL / NOT YET
BEFORE FIX: offset += 1 observed status = ...
AFTER FIX: offset += 1 status/refusal reason; other mutations covered = ...
POSITIVE PATCHES: RTC Qrtc / CONS Qpid / CONS Qppid; exact hashes & apply checks
SOURCE SAFETY: tracked C unchanged, no automatic apply
E3/E2 CLI: tests, OMAP --check, native --check, proposal --check
KERNEL/QEMU: PASS/FAIL/NOT RUN (truthful scope)
REMAINING LIMITS: lexical analysis / unknown call chains / required review
```

**E3a PASS** means the demonstrated unsafe prefix mutation is reliably refused, the regression suite covers the mutation classes above, all three prior valid patch proposals remain viable, and default E3/E2 analysis and OMAP compatibility are preserved. Do not call this proof of full semantic equivalence or whole-kernel `Chan` independence.
