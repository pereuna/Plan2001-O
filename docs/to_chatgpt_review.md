# Last completed agent result — E3 extraction proposals (PASS)

**E3 SOURCE EXTRACTION PROPOSALS PASS (agent-reported, 24 October 2026, base
`f5ad884`).**  The existing `tools/kernel_opmap.py` analyser now has an opt-in
`--propose-extraction` mode.  It derives a validated helper insertion and a
single selected-Qid replacement from token spans, then emits a deterministic
unified diff plus `extraction-decisions.json` under `build/generated/`.  It
never writes tracked kernel sources and never activates a patch.

- **Pre-E2 `7b4dfac`:** RTC `Qrtc` and cons `Qpid` both `DIRECT-CANDIDATE`;
  patches `devrtc.c.patch` (`7b715be6...`) and `devcons.c.patch`
  (`ce667228...`).  RTC reconstructs its own `ulong offset`; console preserves
  the `n <= 0` guard and leaves the legacy pre-dispatch guard.
- **HEAD:** cons `Qppid` `DIRECT-CANDIDATE` (`consread_qppid_read`, patch
  `abb25340...`), no source mutation.  HEAD RTC `Qrtc`/cons `Qpid` correctly
  report `ALREADY-EXTRACTED`.
- **Synthetic:** a renamed static Dev produces the same patch shape through
  the same rule; no driver-name-specific C emitter.
- **Safety:** `git apply --check` PASS on disposable copies of the exact bases;
  applied copies changed only approved lines and left Qnvram/Qppid/Qkmesg/Qdir
  and guards intact.  Changed SHA, CRLF, comments, preprocessor branches,
  unsupported casts/macros, unresolved `up`, local collisions, fall-through,
  multiple readnum results, pre-dispatch side effects, overlapping spans and
  missing/ambiguous selectors are refused.
- **Checks:** generator tests 26/26 PASS; E2 `--generate-native` and `--check`
  PASS; normal OMAP `--check` PASS.  An isolated Plan 9 `6c` trial compiled both
  patched pre-E2 files.  No E3 kernel rebuild was needed; optional reruns of the
  existing E2 native probe and D2b server gates PASS against the unchanged
  kernel.

**Remaining:** proposals are unapplied review candidates, not approved native
bindings or runtime proof.  A separate reviewed apply, re-pin, kernel link/boot
and Chan-free runtime check is still required.  Only the narrow readnum shape is
proposed; NVRAM/write/reset/IRQ/DMA/pipe/mount paths remain manual.
