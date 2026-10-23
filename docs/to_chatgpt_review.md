# Last completed agent result — E2 native generator (PASS)

**E2 GENERIC EXTRACTION PASS (agent-reported, 23 October 2026, base
`7b4dfac`).**  One `readnum` extractor/renderer in the existing
`tools/kernel_opmap.py` now drives two real `pc64` read operations:

- `devrtc.c` `Qrtc` read → shared `rtcqread` → generated
  `native_rtc_qrtc_read`;
- `devcons.c` `Qpid` read → shared `consqpidread` → generated
  `native_cons_qpid_read`.

Both inherited Dev branches delegate to those same helpers; the generated C is
a thin binding and per-driver selector dispatch.  E1's RTC NVRAM DIRECT
claims are explicitly downgraded to MANUAL.  `devpipe` remains MANUAL.

`NATIVE_PROBE=1 WHAT=kernel tools/build.sh` staged generated files under
`build/` and linked `9pc64native`.  `tools/test-o-native-generator.sh` booted
it with `onativeprobe=1` and observed in a real kernel process after
`rtcinit()` (no `chandevinit`/namespace): RTC return 12 with a plausible time,
PID return 12 matching `up->pid`, correct size/offset/zero/negative behavior,
unsupported-selector refusals, zero path counters in the measured window, and
no panic.  Logs are under `build/verification/` (not committed).

Evidence: generator tests 21/21 PASS; native `--check` PASS; normal
`--check` PASS after a deliberate OMAP `--write` caused by the reviewed source
edits/new probe files; normal `WHAT=kernel` build PASS; D2b server, D2a output,
normal O boot and pathless tests PASS.  The `what=kernel` build list now also
builds `ohandle`/`oexec`, removing a clean-build dependency on `WHAT=all`.

**Remaining:** this proves two bounded reads, not general driver conversion,
full legacy permission/lifecycle equivalence or whole-kernel Chan independence.
`Chan`, `Qid`, `Dirtab`, `Walk`, `Dev`, namespace/9P, pipe endpoints, GE/O
volume discovery and non-pilot driver paths remain.  Generated entries are
kernel-internal-only, not a userspace ABI.  Next work should either add a
third generic operation shape or a reviewed native handle contract; do not
describe the 27 drivers as converted.
