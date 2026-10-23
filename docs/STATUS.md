# Plan2001-O — current implementation and verification

**Last runtime verification:** 23 October 2026, implementation commit `3cfd4ed27082c98e009030797290c6b1f84be380`, documented on `main` at `62564d1dea270b9f924cc4f7eebf466bf8798074`.
**Scope:** amd64/`pc64`, disposable QEMU images, results **reported by the coding agent**. Source review is not independent test execution.
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
- **Checks (agent-reported):** `python3 tools/test_kernel_opmap.py` 18/18 PASS;
  generated output reproduced byte-for-byte twice and
  `--generate-native --check` PASS; generated RTC C compiled with the VM's
  Plan 9 `6c` against the repository kernel headers.  `WHAT=kernel
  tools/build.sh` was NOT RUN because no kernel/executable source changed.

Known baseline: `python3 tools/kernel_opmap.py --check` currently reports the
checked-in `docs/KERNEL-OPMAP.{json,md}` stale against the kernel tree; that
predates E1 and was not silently regenerated.

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
- `docs/KERNEL-NATIVE-GENERATOR.md`: E1 generator CLI, RTC pilot evidence, refusals and remaining `Chan` dependencies.
- `docs/O-BOOT-DEPENDENCIES.md`: **historical Level A snapshot**, includes B/C NOT YET as of that earlier experiment; it does not override the newer Boot A–D2b results.
- Detailed completed boot reports are intentionally **not present at HEAD**. Read historical versions using the pinned Git commit `62564d1dea270b9f924cc4f7eebf466bf8798074`; do not re-create them merely because old links exist in past prompts.
- `docs/to_opencode.md`: **current assignment only**; a completed assignment is not an active task.
- `docs/to_chatgpt_review.md`: latest compact agent review summary.

The earlier full `docs/STATUS.md`, experiments and their source commits are retained in Git history, not deleted from history.
