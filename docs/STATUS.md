# Plan2001-O — current implementation and verification

**Last runtime verification:** 24 October 2026, OpenCode E5 on base `dd3c4f2cc3bd462a6a6f285daccb322a52e9ef9b`; implementation `53785d754cd6239d7ac3e0ce70e5792f543a07d1` on `main` (completion report: [to_chatgpt_review.md](to_chatgpt_review.md)). Earlier E4 was independently executed on base `10d9fcd...` and committed as `f60211d0...`.
**Scope:** amd64/`pc64`, opt-in `pc64native`, and opt-in no-`#c` `pc64oconsole`, disposable QEMU images. E5 results were executed by OpenCode; E4 results below were executed by Codex/Astra. Older sections retain their original agent-reported scope. E4 review: [to_astra_review.md](to_astra_review.md).
**Historical record:** `git show 62564d1dea270b9f924cc4f7eebf466bf8798074:docs/STATUS.md`. The six completed `docs/O-BOOT-EXPERIMENT-*.md` reports can be restored with `git show 62564d1dea270b9f924cc4f7eebf466bf8798074:docs/O-BOOT-EXPERIMENT-D2B.md` (substitute A, B, C, D1, D2A or D2B).

## Current proven vertical slice

`UEFI → 9Front-derived kernel → embedded minimal OID loader → OVOLOPEN(PARTUUID) → OSPACEOPEN(init) → OEXECUTE(OID_MP_EXEC) → MicroPython -O ... -S init -N → persistent Space.open('init') → run() → OSPACEPUT/OSPACECOMMIT → init: done`.

`-N` runs without the inherited `boot.py`, `kbdfs`, `/dev`-name hierarchy or interactive console input. `oboot=server` selects this path; legacy `-B` and the historical `oboot=mp` diagnostic remain available.

| Gate | Status and strictly supported observation | Source |
| --- | --- | --- |
| Pathless GE/O storage, Level A | PASS: native PARTUUID discovery, GE block I/O and flush without runtime kernel `Chan` / path walk in the observed window | `e384300`, `tools/test-o-pathless.sh` |
| Boot A, `oboot=probe` | PASS: kernel-only post-scheduler probe; no legacy init or path calls | `6c6e112` |
| Boot B, `oboot=user` | PASS: ring-3 minimal user process and syscalls | `ba6b8ab` |
| Boot C, `oboot=oid` | PASS: userloader opens O volume, executes real OID program in ring 3; negatives | `3374eb9`, `tools/test-oboot-oid.sh` |
| D1, `oboot=mp` | PASS as diagnostic ONLY: genuine O-resident MicroPython; first `PWRITE(fd=2)` exposed nil-`Fgrp` panic, later fixed | `4d1d75f` |
| D2a, native `IOWRITE` | PASS: process-granted OUT/DIAG stream to UART; nil-`Fgrp` returns error; next `boot.py`/bind problem diagnosed | `4c2ae36`, `182be33`, `tools/test-oboot-output.sh` |
| **D2b, native server** | **PASS**: same O disk booted 3 times; `run() → 1, 2, 3`; init versions 1/2/3; O versions 2/3/4; Counter OID=7, alias=7 unchanged; no observed legacy syscall attempts; separate negative `run()` failure and missing executable PASS | `3cfd4ed`, `tools/test-oboot-server.sh` |
| Legacy normal O boot | PASS in D2b controls: three-boot persistence using inherited bootstrap | `tools/test-o-boot.sh` |

**D2b image identity:** O-resident MicroPython 2,195,994 bytes; SHA-256 `cb3fe6159cf9e6ea148da15ccca71cbc8d118de42b82fd28120a44ba70723eaa`. Host seed and native `OEXECUTE` digests reportedly matched.

**D2b negative evidence:** a failing `run()` produces no successful commit/done; missing `OID_MP_EXEC` returns an error without legacy fallback. The agent's QEMU logs were under `build/verification/` and are NOT assumed committed to Git. Original report and historical STATUS remain in Git history.

## E5 #c native-service decomposition and O-only console profile

**APPROVE (agent-executed).** The `#c` aggregator is split into concrete kernel
services without a generic `NativeDev`, handle table or userspace ABI:

- `sys/src/9/port/cons.c`: console output (`consputstr`), `print`/`iprint`/
  `panic`/`putstrn`, `sysfatal`/`_assert`, log ring (`kmesgwrite`/
  `kmesgreadat`), exclusive `kprint` operations, `readnum`/`readstr`,
  `consinit`, `consactive`, `prflush`, `cpushutdown`.
- `sys/src/9/port/procobs.c`: typed current-process PID/PPID/user and six
  accounting slots (`proccputimes`). E4's `consqpidread`/
  `consread_qppid_read` remain the legacy text adapters.
- `sys/src/9/port/sysinfo.c`: system name/domain/owner/config getters,
  `sysnameset`, typed `Sysstat`, privileged clock gate, null/zero semantics.
- `tod.c`/`random.c`: pre-existing time/entropy implementations are used
  directly. `main`-time `chandevinit` was not assumed: the O path calls
  `consinit()` from `ouserproc` and the native probe after `up` exists, so
  `randomseed` is a normal kproc rather than a parentless boot process.
- `devcons.c` is now the legacy `Chan`/`Qid`/`Dirtab` adapter plus time
  text/binary encoding only. `pprint` is retained in the core because fault
  paths use it, and its legacy fd 2/`Fgrp`/`Chan` dependency is explicit.

`docs/CONS-MIGRATION.md` covers all 23 live Qid enumerators plus the core
symbols: **19 native, 2 legacy-only (`Qdir`, `Qdrivers`), 2
intentionally-unsupported (`Qconsctl`, `Qmordor`), 0 unclassified**. No
userspace ABI was added; process/log/time/config/control operations are
kernel-only. `IOWRITE` was not broadened.

The opt-in `pc64oconsole` profile removes only the `cons` line from the normal
`pc64` `dev` section. The generated `devtab[]` has no `&consdevtab`, and the
linked kernel has no `consdevtab` symbol while retaining `consinit`, `panic`,
`iprint`, `putstrn`, `kmesgreadat`, `procpid`, `sysstatget`, `todinit`,
`randominit`, `readnum` and `readstr`. `pc64`, `pc64mp` and `pc64native` keep
the `#c` registration.

Executed gates (all PASS):

```sh
python3 tools/cons_migration_check.py
python3 tools/kernel_opmap.py --write
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py
NATIVE_PROBE=1 WHAT=kernel tools/build.sh
tools/test-o-native-generator.sh
WHAT=kernel tools/build.sh
tools/test-o-boot.sh
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
OCONSOLE=1 tools/test-oboot-server.sh
```

Observed: E5 console/log marker `logmark=1`; time/random plausible and
distinct; typed PID/PPID/user/accounting and config getters; clock control
denied for an unprivileged process context; kprint acquire/busy/read/close/
reopen correct; typed sysstat, null/zero semantics; legacy adapter cputime
format `72` bytes and Qtime denial. D2b on the O-only profile booted the same
disk three times (`run() -> 1,2,3`), no panic/fault, `cons: init tod=1
random=1`, and `namec/newchan/walk/devwalk/mount/exec` all zero at the
measured `n=64` window. Legacy `tools/test-o-boot.sh` (normal `9pc64`) also
passed. Logs: `build/verification/e5/` (ignored by Git).

Limitations: this proves the O-only server profile does not register or link
`consdevtab`; it does **not** remove all legacy `#c` code from the repository,
and `Qdir`/attach/walk/stat/open/close, `Qdrivers` and `Qmordor`/`Qconsctl`
remain deliberate legacy/unsupported cases. `pprint` still uses legacy fd 2
and `Chan`. `#b`, `#i`, `#v`, `#t`, UART and screen drivers are unchanged.

## E4 independently reviewed Qppid integration

**APPROVE.** The actual E3 proposal from base `10d9fcd` was reviewed, applied
first in an exact-base disposable worktree, compiled with Plan 9 `6c`, then
applied unchanged to the working tree. Legacy Qppid and generated
`native_cons_qppid_read` share `consread_qppid_read`; live enum/Dirtab mapping
is 13. Qrtc/Qpid remain. This is kernel-internal-only, requires `up != nil`
and a valid caller buffer; it adds no user authorization or userspace ABI.

Audit fixes reject a mutation hidden in a directory guard, lossy UTF-8 source
round-tripping, and unmanifested stale proposal patches. All 27 existing tests
remain covered; the original Qppid proposal assertion now uses its historical
input, while current source must report ALREADY-EXTRACTED. The final 29 tests
pass. `WHAT=kernel` now exports the interpreter it already compiles, enabling
D2b to use fresh bytes without a full tree build.

Executed gates (all PASS; no unrelated regression battery):

```sh
python3 tools/test_kernel_opmap.py
python3 tools/kernel_opmap.py --check
python3 tools/kernel_opmap.py --propose-extraction --config pc64 --selectors cons:read:Qppid --out-dir build/generated/e4-applied
python3 tools/kernel_opmap.py --propose-extraction --config pc64 --selectors cons:read:Qppid --out-dir build/generated/e4-applied --check
python3 tools/kernel_opmap.py --generate-native --config pc64 --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --config pc64 --out-dir build/generated/kernel-native --check
NATIVE_PROBE=1 WHAT=kernel tools/build.sh
tools/test-o-native-generator.sh
WHAT=kernel tools/build.sh
tools/test-oboot-server.sh
```

The first OMAP check correctly failed on new source fingerprints; deliberate
`--write`, constrained diff review, and recheck passed. Only devcons/probe
source records changed. Native QEMU ran **once**, before the normal build
replaced staging/loader output. Both builds' VM inputs matched all 232 kernel
source files; staged native C/header also matched the validated generator output.
Kernel fingerprint: `3fe196b84e63da346e5783fad13478a6c10ef3ba8f62f5cbbb32b6939a58f2d6`.

QEMU observed Qppid=0 equal to `up->parentpid`, return 12, exact decimal
formatting, offset-8 partial read, clamp/zero/negative-length, out-of-range,
negative-offset and 32-bit offset-wrap behavior. Existing Qrtc/Qpid and
unsupported-selector gates passed. BEGIN/END counters: namec/newchan/walk/
devwalk/mount/exec all zero. D2b passed three same-disk boots (`1 → 2 → 3`,
Counter OID=alias=7), run-failure/no-commit and missing-executable negatives.
Logs: `build/verification/e4/` (including native serial and `d2b/` copies).
MicroPython: 2,195,994 bytes, SHA-256
`bc4156a0e44c5e8c96647eb9923e052f5eec6ec7e8e816a761a8ba8c9319c2ba`.

## E2 native generator (linked and executed)

**E2 GENERIC EXTRACTION PASS (agent-reported, 23 October 2026).**  The same
`readnum` extractor/renderer now emits and links two real `pc64` read
operations:

- `devrtc.c` `Qrtc` read → shared `rtcqread`, generated
  `native_rtc_qrtc_read`;
- `devcons.c` `Qpid` read → shared `consqpidread`, generated
  `native_cons_qpid_read`.

Both inherited `Dev` branches delegate to those same helpers, so the
algorithm is not duplicated.  The E1 RTC NVRAM `DIRECT` claims are explicitly
downgraded to `MANUAL`; `devpipe` remains `MANUAL`.

`NATIVE_PROBE=1 WHAT=kernel tools/build.sh` builds opt-in `9pc64native` by
staging generated C from `build/generated/kernel-native/`.  The normal
`pc64`/`pc64mp` builds link a stub and are unaffected.
`tools/test-o-native-generator.sh` boots that kernel with `onativeprobe=1`
and observed, in a real kernel process after `rtcinit()` (no
`chandevinit`/namespace): `Qrtc` return 12 with a plausible time, `Qpid`
return 12 with `up->pid`, correct size/offset/zero/negative behavior,
unsupported-selector refusals, zero path counters in the measured window, and
no panic/fault.  Logs: `build/verification/o-native-generator-*.log` (not
committed).  This proves native dispatch, not all legacy modes or whole-kernel
Chan independence.

## E1 native-operation generator (static, not a boot change)

`tools/kernel_opmap.py --generate-native` now consumes the existing
`Analyzer.analyze()` IR and writes an opt-in operation manifest plus a reviewed
RTC pilot under `build/generated/kernel-native/` (ignored by Git).  The default
OMAP `--write`/`--check`/`--stats` behaviour is unchanged.

- **E1 status: PARTIAL.** 29 active `pc64` Dev registrations are described;
  3 RTC operations are `DIRECT` (Qrtc read, Qnvram read/write), 1 RTC operation
  is `MANUAL` (Qrtc write), and `devpipe` is `MANUAL` with dynamic endpoint
  blockers.  The generated `rtc_native.c` was compiled with the build VM's
  Plan 9 `6c`; it was **not** executed in a booted kernel.
- **RTC:** `DIRECT` is claimed only for the hash-pinned reviewed branches;
  namespace `walk`/`stat` stay `LEGACY`.  `eve` permission checks and
  `Nvoff`/`Nvsize` offset rules are reproduced; Qrtc write fails explicitly
  because `sec2rtc()`/`PUTBCD` are static.
- **Boundary:** this does not convert a driver or remove `Chan`; see
  `docs/KERNEL-NATIVE-GENERATOR.md` for the exact claims and remaining
  dependencies.  No executable/kernel behaviour changed, so the D2b server
  gate was not rerun for E1.
- **Checks (E1 only, historical):** `python3 tools/test_kernel_opmap.py`
  18/18 PASS; generated output reproduced byte-for-byte twice and
  `--generate-native --check` PASS; generated RTC C compiled with the VM's
  Plan 9 `6c` against the repository kernel headers.  E1 was not linked or
  booted.

**E2 checks (historical):** `python3 tools/test_kernel_opmap.py` 21/21 PASS;
native `--generate-native --check` PASS; normal `--check` PASS after a
deliberate `--write`; `NATIVE_PROBE=1 WHAT=kernel tools/build.sh` PASS;
`tools/test-o-native-generator.sh` PASS; `WHAT=kernel tools/build.sh` PASS;
`tools/test-oboot-server.sh`, `tools/test-oboot-output.sh`,
`tools/test-o-boot.sh` and `tools/test-o-pathless.sh` PASS.  The unrelated
`what=kernel` list now builds `ohandle`/`oexec` so a clean kernel build does
not depend on a previous `WHAT=all`.

## E3 extraction proposals (source-to-source, not applied)

`tools/kernel_opmap.py --propose-extraction` uses the same `Analyzer` token
spans to propose a helper insertion plus one selected-case replacement, emitted
as a reviewable unified diff under `build/generated/`.  It never writes tracked
kernel sources or activates a patch.

- **Pre-E2 input** `7b4dfac`: RTC `Qrtc` and cons `Qpid` both `DIRECT-CANDIDATE`,
  two patches; source SHAs `45722e4f...` and `b6811757...`.
- **E3 input (through `10d9fcd`)**: cons `Qppid` `DIRECT-CANDIDATE` (no source mutation);
  RTC `Qrtc` and cons `Qpid` correctly reported `ALREADY-EXTRACTED`.
- **Synthetic** renamed static Dev also produces a patch through the same rule.
- **Apply/compile evidence:** `git apply --check` PASS against disposable exact
  bases; an isolated Plan 9 `6c` trial compiled both patched pre-E2 files.
- **Checks:** `python3 tools/test_kernel_opmap.py` 26/26 PASS; E2 native
  generation/check PASS; normal OMAP `--check` PASS.  No E3 kernel rebuild was
  needed because no kernel source changed; optional reruns of the existing E2
  native probe and D2b server gates PASS against the unchanged kernel.

At E3 completion the proposals were unapplied, not approved native bindings.
E4 above applies and verifies Qppid. The helper is
kernel-internal-only; runtime/Chan-free claims require a separate reviewed
apply, link and boot step.

E3a safety repair: pre-switch mutations such as `offset += 1;`, plain writes,
pointer/member/array writes, calls and unknown statements are now `REFUSED`
with no patch.  The three positive E3 patches remain byte-identical.  Tests are
27/27 PASS; no tracked kernel source was modified.

## Boundaries and limitations

- **Pathless measured execution is not whole-kernel Chan independence.** The full kernel retains many 9Front `Chan`, `Qid`, `Dirtab`, `Walk`, `Dev`, namespace and 9P implementations. Their *mere presence* is not a runtime path-use claim; their removal is not demonstrated. Read `docs/KERNEL-OPMAP-NOTES.md` and `docs/CHAN-DEPENDENCIES-INDEX.md` for analysis scope.
- Current GE/O persists a serialized Python graph as **one OID_GRAPH record**, not native per-object relation edges. The semantic olio/objekti model and deterministic relation scheme remain design work; see `docs/OBJECT-MODEL.md` and `docs/OLIO-OBJEKTI-MANIFESTI.md`.
- A file is finite byte content, **not** inherently a directory entry; streams are separate transfers; live resource handles need not be persistent OIDs. Removing mandatory hierarchical name traversal does **not** require removing files, streams, I/O or all FDs.
- The D2a `iomask` and fixed UART stream handles are experimental mechanisms, not a stable generic capability/IO ABI. `-N` currently proves the fixed `init`/`odemo` server, not a general daemon runtime.
- D2c native serial input/REPL is deliberately deferred. Priority is a machine-auditable driver/kernel operation extraction, not serial input. The experimental D2b trace audits selected syscall attempts and path counters, not all possible future kernel call paths.

## Build and regression checks

Use the existing repo scripts and **report PASS/FAIL/NOT RUN based on actual latest execution**, not historical status.

```sh
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-oboot-server.sh
tools/test-oboot-output.sh
tools/test-oboot-oid.sh
tools/test-oboot-user.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A / oboot=probe: see historical report and gate.
python3 tools/kernel_opmap.py --check
```

Use **disposable** QEMU disk images only; never write to physical disks in routine tests.

## Documentation boundaries

- `README.md`: current overview.
- `AGENTS.md`: coding agent rules.
- `docs/GENERAL-SOFTWARE-SPECIFICATION.md`, `docs/OLIO-OBJEKTI-MANIFESTI.md`, `docs/OBJECT-MODEL.md`: proposal and semantic distinctions, not claims that every concept is implemented.
- `docs/O-FORMAT.md`: implemented O disk format.
- `docs/KERNEL-OPMAP.md` and `.json`: **generated**, large structural inventory from `tools/kernel_opmap.py`; do not load wholesale into agent context unless specifically required. `docs/KERNEL-OPMAP-NOTES.md` is a human-readable review.
- `docs/KERNEL-NATIVE-GENERATOR.md`: E2 generator CLI, generic readnum rule, RTC/console probe evidence, refusals and remaining `Chan` dependencies.
- `docs/O-BOOT-DEPENDENCIES.md`: **historical Level A snapshot**, includes B/C NOT YET as of that earlier experiment; it does not override the newer Boot A–D2b results.
- Detailed completed boot reports are intentionally **not present at HEAD**. Read historical versions using the pinned Git commit `62564d1dea270b9f924cc4f7eebf466bf8798074`; do not re-create them merely because old links exist in past prompts.
- `docs/to_astra.md`: E4 assignment and acceptance criteria.
- `docs/to_astra_review.md`: independent E4 verdict and executed evidence.
- `docs/to_chatgpt_review.md`: latest compact agent review summary.

The earlier full `docs/STATUS.md`, experiments and their source commits are retained in Git history, not deleted from history.
