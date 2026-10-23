**E1 GENERATOR PARTIAL** — committed and pushed as `65c3d54`.

**Native output / source mapping**
- `build/generated/kernel-native/kernel_native.h` — selector constants + RTC prototypes
- `build/generated/kernel-native/rtc_native.c` — reviewed RTC entry
- `build/generated/kernel-native/native-decisions.json` — 29 active `pc64` Dev registrations, 756 operations
- Source binding: `sys/src/9/pc/devrtc.c`, SHA-256 `45722e4f...f1bcb`; hash-pinned so edits fail closed.

**RTC: DIRECT (compile-validated, not runtime-executed)**
- `Qrtc` read → `rtctime()` + `readnum()`: DIRECT
- `Qnvram` read → `nvramread()` with `Nvoff`/`Nvsize`: DIRECT
- `Qnvram` write → `nvramwrite()` with offset-0 rule and bounds: DIRECT
- `Qrtc` write → **MANUAL** (`sec2rtc()`/`PUTBCD` are static; explicit error, no fake success)
- `eve` permission checks and offset rules are reproduced. Namespace `walk`/`stat` remain LEGACY.
- Generated C compiled successfully with the build VM's Plan 9 `6c` against repository kernel headers (`build/vm/serial-20261023-233225.log`, ignored). Runtime RTC call not performed.

**PIPE: MANUAL** — dynamic `Pipe`/`qref`/`ref`/`c->aux` ownership, `qhangup`/`qclose`/`qreopen`, opposite-queue read/write and `qsetlimit` block safe automation. Manifest records these blockers; no pipe code generated.

**OMAP CLI COMPATIBILITY: PASS** — default JSON/Markdown hashes are unchanged from before E1. Baseline note: `kernel_opmap.py --check` still reports the pre-existing stale `docs/KERNEL-OPMAP.{json,md}`; they were not silently regenerated.

**Tests**
- `python3 tools/test_kernel_opmap.py` — **18/18 PASS**
- Generated output reproduced byte-for-byte twice; `--generate-native --check` PASS
- `WHAT=kernel tools/build.sh` **NOT RUN** (no kernel/executable source changed)
- D2b server gate **NOT RUN** (no executable/kernel behavior change)

**Remaining kernel `Chan` dependencies:** all non-pilot drivers, pipe endpoints, RTC `walk`/`stat`/`open`/`close`/directory read, GE/O volume discovery, mount/9P transports, and the retained `Chan`/`Qid`/`Dirtab`/`Walk`/`Dev` kernel machinery. No driver has been converted to Chan-free operation.
