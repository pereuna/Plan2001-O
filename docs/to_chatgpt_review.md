**E3 SOURCE EXTRACTION PROPOSALS: PASS** — committed and pushed as `30d0ca7`.

**PRE-E2 RTC `Qrtc`: PATCH** — source SHA `45722e4f...f1bcb` at `7b4dfac`. Patch `build/generated/e3-pre-e2/devrtc.c.patch` (`7b715be6...402b524`) inserts `rtcread_qrtc_read`, reconstructs its own `ulong offset = off`, and replaces only the `Qrtc` case. `Qnvram` and the shared original offset are untouched. Disposable-base `git apply --check` PASS.

**PRE-E2 CONS `Qpid`: PATCH** — source SHA `b6811757...1ece4`. Patch `build/generated/e3-pre-e2/devcons.c.patch` (`ce667228...188de324`) inserts `consread_qpid_read`, copies the `n <= 0` guard into the helper, and replaces only `Qpid`. The legacy pre-dispatch guard, `Qppid`, `Qkmesg`, `Qdir` and other cases remain. Apply check PASS.

**HEAD CONS `Qppid`: PATCH** — current source SHA `068dca67...0e901896`. Patch `build/generated/e3-head/devcons.c.patch` (`abb25340...f2119ee3`) inserts `consread_qppid_read`, preserves the guard, and replaces only `Qppid`. No tracked source was modified. Apply check PASS. HEAD `Qrtc`/`Qpid` correctly report `ALREADY-EXTRACTED` with no patch.

**SYNTHETIC GENERALITY: PASS** — a renamed static Dev with its own selector, local, literal value and size produces the same helper-insertion/case-replacement shape through the same rule, with no driver-name-specific emitter.

**SINGLE IMPLEMENTATION:** each proposed helper becomes the shared implementation for the selected legacy case. Applying a patch is still a review step; E2’s normal generator must be consciously re-pinned, not silently blessed.

**SOURCE SAFETY:** proposals are generated only from pinned source SHAs. Changed SHA, wrong source-ref, CRLF, in-span comments, preprocessor branches, unsupported casts/macros, unresolved `up`, parameter/local collisions, fall-through, multiple readnum results, pre-dispatch side effects/guards, overlapping spans, duplicate helper names, already-extracted branches and missing/ambiguous selectors are refused. Tracked kernel sources were not touched; tests assert this.

**E2 CLI REGRESSION: PASS** — `python3 tools/test_kernel_opmap.py` 26/26 PASS; normal OMAP `--check` PASS; native `--generate-native --check` PASS.

**RUNTIME AND KERNEL BUILDS:** E3 kernel rebuild/QEMU **NOT RUN** (proposal-only; no kernel source changed). Optional existing E2 native probe **PASS**; D2b server gate **PASS**. Isolated Plan 9 `6c` compile of both patched pre-E2 files **PASS**.

**REMAINING:** all proposals are unapplied review candidates. A separate reviewed apply, source re-pin, kernel link/boot and Chan-free runtime check are still required. Only the narrow readnum shape is proposed; RTC NVRAM/write, reset, IRQ/DMA, pipe, mount and all other driver paths remain manual.
