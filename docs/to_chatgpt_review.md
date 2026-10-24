# Last completed agent result — E3a prefix safety repair (PASS)

**E3a PREFIX SAFETY PASS (agent-reported, 24 October 2026, base `e0db7ee`).**
The E3 proposal prefix validator has been replaced by one token-aware
classifier plus a shared policy check.  It no longer accepts unmodeled
pre-switch mutations.

- **Before fix:** synthetic `offset += 1;` produced `DIRECT-CANDIDATE` and a
  patch (`65e9c84f...bd8b40`) whose helper omitted the mutation.
- **After fix:** that case is `REFUSED` with `pre-dispatch compound
  assignment/mutation is not supported` and no patch.  Compound assignments,
  plain writes to `offset`/`n`/`off`/`buf`/`up`/`c`, pointer/member/array
  writes, `++/--`, calls, chained/conditional initializers, unrelated
  initializers, pre-switch `return`, unknown statements and inner
  preprocessor-conditionals are refused.
- **Positive E3 proposals unchanged:** RTC `Qrtc`
  `7b715be6...402b524`, CONS `Qpid` `ce667228...188de324`, HEAD CONS `Qppid`
  `abb25340...f2119ee3`; all still pass disposable `git apply --check`.
- **Checks:** `python3 tools/test_kernel_opmap.py` 27/27 PASS; OMAP `--check`
  PASS; E2 native generate/check PASS; both E3 proposal `--check` modes PASS.
  No tracked kernel source was modified.
- **Kernel/QEMU:** not rerun for E3a because only generator/tests/docs changed;
  no build-relevant kernel source changed.

Remaining limits: the classifier is lexical/structural and deliberately
rejects unproven constructs rather than performing full dataflow.  Unknown
call chains, aliasing beyond simple locals, and all unproposed operations
still require manual review.  Proposals remain unapplied candidates, not
approved native bindings or runtime proof.
