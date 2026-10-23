**E2 GENERIC EXTRACTION PASS** — committed and pushed as `ecd945e`.

**EXTRACTION:** `RTC Qrtc READ` + `CONS Qpid READ` use the same generic `readnum` extractor/renderer. The extractor derives helper, value expression, size, offset, guard, return shape and source lines from the tokenized source. RTC uses `(ulong) rtctime()` / size `12` / assign-return; console uses `up->pid` / `NUMSIZE`=12 / direct-return with `n <= 0` guard. A synthetic third Dev fixture also generates through the same renderer without new Python driver branches.

**SINGLE IMPLEMENTATION:** Legacy branches now delegate to the same shared helpers the generated entries call:
- `rtcread` Qrtc → `rtcqread`
- `consread` Qpid → `consqpidread`

The generated C is a thin binding plus per-driver selector dispatch; no duplicated readnum algorithm. E1 RTC NVRAM `DIRECT` claims are explicitly downgraded to `MANUAL`.

**BUILT AND LINKED:** `NATIVE_PROBE=1 WHAT=kernel tools/build.sh` built `9pc64native`; `native_rtc_qrtc_read`, `native_cons_qpid_read`, `rtcqread` and `consqpidread` are present in the linked kernel. Generated files were produced by the generator and staged from `build/generated/kernel-native/`.

**QEMU EXECUTED:** `tools/test-o-native-generator.sh` PASS. Final probe markers included:
- RTC: `selector=1 n=32 off=0 ret=12 value=1792789937`, `plausible=1`, offset match, size clamp, zero/bounds checks.
- PID: `selector=12 n=32 off=0 ret=12 value=1 pid=1 match=1`, correct text/offset, zero/negative/bounds checks.
- Unsupported selectors: `rtc selector=101 caught=1`, `cons selector=112 caught=1`.
- `BEGIN`/`END` path counters all zero in the measured window; no panic/fault.

**SAFETY:** Probe runs in a real kernel process with `up`. `rtcinit()` is called exactly once; `chandevinit()` is not run on this path. Both entries are kernel-internal-only; legacy Dirtab/devopen policy remains the user-facing policy. Only read-only operations are used; no NVRAM/CMOS writes or time changes.

**OMAP:** The old `--check` was stale due a genuinely changed source fingerprint. A deliberate `--write` was run, inspected and documented; current `kernel_opmap.py --check` PASS. Native `--generate-native --check` PASS.

**D2b REGRESSION:** PASS. `test-oboot-server.sh`, `test-oboot-output.sh`, `test-o-boot.sh` and `test-o-pathless.sh` all PASS. Normal `WHAT=kernel tools/build.sh` PASS; generator tests 21/21 PASS.

**REMAINING:** Only two bounded reads are converted. `Chan`, `Qid`, `Dirtab`, `Walk`, `Dev`, namespace/9P, pipe endpoints, GE/O volume discovery, RTC/console other branches, RTC NVRAM and Qrtc write, and all non-pilot driver paths still need manual review. No userspace native ABI was added, and the 27 drivers are not converted.
