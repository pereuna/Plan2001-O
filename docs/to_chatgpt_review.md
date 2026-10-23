# Last completed agent result — E1 native generator (PARTIAL)

**E1 GENERATOR PARTIAL (agent-reported, 23 October 2026, base `c894eb5`).**
`tools/kernel_opmap.py --generate-native` extends the existing analyser rather
than adding a scanner.  It writes a 29-driver `pc64` decision manifest plus a
hash-pinned RTC pilot under `build/generated/kernel-native/` (Git-ignored).

- **RTC:** three `DIRECT` reviewed operations (`Qrtc` read, `Qnvram` read and
  write) map `Qrtc=1`/`Qnvram=2` to `rtctime`, `nvramread` and `nvramwrite`.
  `eve` permission and `Nvoff`/`Nvsize` offset rules are reproduced.  `Qrtc`
  write is `MANUAL` because `sec2rtc()`/`PUTBCD` are static.  `walk`/`stat`
  stay `LEGACY`.
- **Pipe:** `MANUAL`; dynamic `Pipe`/`qref`/`c->aux` ownership and
  open-close hangup semantics block automation.
- **Other drivers:** described, not edited; no `DIRECT` claim without a
  reviewed binding.

Evidence: `python3 tools/test_kernel_opmap.py` 18/18 PASS; default OMAP JSON/MD
hashes unchanged; generated output reproducible and
`--generate-native --check` PASS.  Generated `rtc_native.c` compiles with the
build VM's Plan 9 `6c` against repository kernel headers (log
`build/vm/serial-20261023-233225.log`), but was **not** executed in a booted kernel.  D2b was not rerun because no
executable/kernel behaviour changed.  `docs/KERNEL-OPMAP.{json,md}` remain
stale against the kernel tree from before E1 and were not silently regenerated.

**Current direction:** next iteration should add one runtime-controlled RTC
read/fault test (or a reviewed native handle contract) and then address
`devpipe` endpoint ownership.  Do not treat this as a converted driver or as
whole-kernel `Chan` independence.
