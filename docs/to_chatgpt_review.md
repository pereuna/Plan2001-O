**E3a PREFIX SAFETY: PASS** — committed and pushed as `70799b9`.

**BEFORE FIX:** synthetic `offset += 1;` was observed as `DIRECT-CANDIDATE`, generating a patch (`65e9c84f85738f60f9c3b96a6126a4236fdf490f0e107dcb6adb8060dcbd8b40`) whose helper omitted the mutation.

**AFTER FIX:** `offset += 1;` is `REFUSED` with `pre-dispatch compound assignment/mutation is not supported`, no candidate patch and no patch file. Covered and refused:
- all compound assignments (`+= -= *= /= %= <<= >>= &= |= ^=`)
- plain writes to `offset`, `n`, `off`, `buf`, `up`, `c` and pointer/member/array writes
- `++`/`--`, pre-switch `return`, calls and call initializers
- chained/conditional initializers, unrelated initializers, duplicate/function-pointer declarations
- source-local macro aliases, inner `#define`/`#undef`, inner `#if`, unknown statements
- supported `n == 0`/`n <= 0` guards remain accepted as positive controls.

**POSITIVE PATCHES:** unchanged and still apply cleanly on disposable exact bases:
- RTC `Qrtc`: `7b715be660380e5f75d323d38b5f0067c158508691e7e33e8c05e3102402b524`
- CONS `Qpid`: `ce6672282fead3da4f6ac49d393e05c4822f2e1fa597d9f8fa125abf188de324`
- HEAD CONS `Qppid`: `abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3`

**SOURCE SAFETY:** one classifier (`_e3_classify_prefix`) plus one policy check now drive both local resolution and prefix validation. No tracked `sys/src/9` files, build scripts or kernel behavior were modified; no proposal was applied.

**E3/E2 CLI:** `python3 tools/test_kernel_opmap.py` 27/27 PASS; OMAP `--check` PASS; native `--generate-native --check` PASS; both E3 proposal `--check` modes PASS. Determinism, tamper detection, stale-SHA, preprocessor, ALREADY-EXTRACTED and missing/ambiguous-selector tests remain.

**KERNEL/QEMU:** NOT RUN for E3a — only generator, tests and docs changed; no build-relevant kernel source changed.

**REMAINING LIMITS:** the prefix analysis is lexical/structural, not full dataflow. Unknown call chains, complex aliasing, unproposed operations and all eventual patches still require manual review, re-pinning, apply, link/boot and runtime validation. This is not proof of semantic equivalence or whole-kernel Chan independence.
