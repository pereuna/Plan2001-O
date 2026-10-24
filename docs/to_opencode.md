# E7 — OpenCode: evidence-driven pruning of legacy Dev registrations in the O-only server profile

**ACTIVE implementation task on `main`.** E6 has completed; this document supersedes the finished E6 assignment. Work on the existing `pc64onativedisk` profile only. Execute the bounded nine-candidate audit and incremental profile-pruning in this task, with actual builds and O boot evidence. Preserve the default and legacy profiles. Report to `docs/to_chatgpt_review.md`, document the results, and use the project's existing commit/push workflow without double-committing.

**Starting point:** `pereuna/Plan2001-O` `main`, E6 checkpoints `ad836d7`, `9901fe4`, `22399f3` and OpenCode completion `0f0a47a` (as observed when this assignment was written, 2026-10-24). At execution time, record the actual `git rev-parse HEAD`, branch, and `git status --short`. Never reset, clean or overwrite unrelated user changes. If HEAD has advanced, review the diff before acting.

**Read first:** `AGENTS.md`, `docs/KERNEL-API-ABI.md`, `docs/STATUS.md`, `docs/SD-MIGRATION.md`, `docs/CONS-MIGRATION.md`, `sys/src/9/pc64/pc64onativedisk`, `sys/src/9/pc64/pc64`, `sys/src/9/pc64/pc64oconsole`, `sys/src/9/pc64/mkfile`, `sys/src/9/pc64/main.c`, `sys/src/9/port/mkdevlist`, `tools/build.sh`, `tools/test-oboot-server.sh`, and each relevant `dev*.c` and direct consumer. The current source, config, generated `devtab[]`, linker result and actual runtime are authoritative, not a prior estimate.

## Goal and limits

E6 proved that the real D2b O-resident MicroPython server boots with neither `#c` (`consdevtab`) nor `#S` (`sddevtab`) registered or linked: `ONATIVE_DISK=1` selects `pc64onativedisk`. Roughly 15 of the remaining ~24 legacy `Dev` registrations **may** eventually be removable from this profile without implementing any replacement native service. Those counts are estimates, NOT permission to delete 15 entries. This task covers **only the nine explicitly listed candidates below**. The objective is to remove confirmed-unused legacy file/namespace-facing `Dev` registrations **from this O-only profile**, while keeping the executing kernel's actual needed functionality intact.

Do not globally delete drivers or change ordinary `pc64`, `pc64mp`, `pc64native` or `pc64oconsole` behavior. Do not remove or stub underlying functions, data structures, initialization, interrupts, or real services merely because their `Dev` wrapper was dropped from `devtab[]`. If the O boot needs a function currently owned by a candidate source, retain a linkable concrete implementation as needed; do NOT invent a generic native device hierarchy or a new userspace ABI. Unlike E5/E6, **do not undertake broad extraction/refactoring** as part of this pruning exercise. If a genuine nontrivial extraction is required, classify that candidate as BLOCKED/DEFERRED and explain the smallest separate task.

The O-only **server** is a target/use case of this opt-in profile, not a blanket architectural decision to prohibit keyboards, mice, graphical hardware or those drivers throughout Plan2001-O. Do not prune unlisted drivers (including `root`, `env`, `proc`, `ip`, `wg`, `gefs`, `ether`, `kbd`, `draw`, etc.) by assumption. Do not remove the E6 native SD core or controller support; no changes to OID/Space/on-disk format, partition bounds, or MicroPython persistence.

## Nine removal candidates (all hypotheses until verified)

| Dev label | config name | implementation | reason to investigate | special caveat |
| --- | --- | --- | --- | --- |
| `#k` | `fs` | `devfs.c` | inherited file-oriented disk combining/mirroring/partition interface | distinguish this from GE/O and the native SD block core; verify no boot or link references |
| `#a` | `tls` | `devtls.c` | inherited `Chan`-based TLS/SSL record device | WireGuard does not justify this `Dev`; inspect other live consumers rather than equating all encryption |
| `#K` | `kprof` | `devkprof.c` | file-oriented kernel profiling interface | check whether any tracing/diagnostic symbol is used independently |
| `#d` | `dup` | `devdup.c` | legacy descriptor-as-directory interface | distinguish the namespace `Dev` from actual `Fgrp`/descriptor lifecycle |
| `#M` | `mnt` | `devmnt.c` | legacy 9P mount/namespace `Dev` | shared mount/9P helpers or boot initialization may have non-Dev references; avoid treating a build error as a deletion order |
| `#s` | `srv` | `devsrv.c` | publishing `Chan` service endpoints in namespace | inspect userspace bootstrap and any indirect consumers |
| `#σ` | `shr` | `devshr.c` | shared inherited mount namespaces | inspect process, namespace and mount dependencies; preserve generic process services |
| `#g` | `segment` | `devsegment.c` | file interface for shared memory segments | do NOT confuse with `Segment` structures, executable loading, VM, or ordinary process memory |
| `#¤` | `cap` | `devcap.c` | inherited identity/capability text interface | inspect credential, permission, privilege, user identity and security call chains before change |

**Important:** labels/character encodings and the source files are hints from the current inventory. Confirm actual `devtab` code points and `dev` configuration mapping; use concrete config names and symbols, not ambiguous glyph matching. The easy/dependency distinctions are hypotheses, not pre-approved deletions.

## Stage 1 — machine-readable inventory and dependency audit (no removal yet)

1. Record the baseline `pc64onativedisk` `dev` entries and generated `devtab[]`, verify count against the claimed ~24 remaining, and report the *actual* counts. `#c` and `#S` should already be absent; verify rather than assume.
2. For each of the nine entries, use the existing `tools/kernel_opmap.py` / `docs/KERNEL-OPMAP.json` and source-level call/reference analysis to trace its `Dev` callbacks, global exported symbols, `devtab[]` registration, `misc`/`link`/implicit source references, `chandevreset`/`chandevinit`/`chandevshutdown` behavior, and any callers reachable in O-only D2b bootstrap, O loader, GE/O, MicroPython, network, process, authentication or kernel error/diagnostic paths.
3. Separate clearly: (A) `Dev` registration/namespace semantics; (B) link-time source-object ownership; (C) genuine non-Dev service dependencies; (D) reachable O-only runtime dependencies; (E) legacy-only behavior. A `namec` string or dormant function in a source file is *not by itself* proof of a runtime dependency, but an unresolved symbol, live init function or reachable call is.
4. For each candidate record a classification: `REMOVABLE` (registration can disappear while all genuine services remain), `BLOCKED` (actual required symbol/init/runtime dependency), or `UNCERTAIN` (missing evidence). Include function names/source locations and concrete reason. Do not take "not used by D2b" as evidence of safety for every server feature; scope the claim to the demonstrated profile and explicitly flag not-yet-tested services.

Create `docs/DEV-PRUNING.md` (English, agent-readable), with one matrix per candidate: `Dev | config | devtab symbol | sources | link dependencies | boot/init dependencies | reachable O-only consumers | legacy-only purpose | status | tested evidence`. Record the baseline counts and concise call-graph notes.

## Stage 2 — incremental, reversible config-only pruning

Use `pc64onativedisk` as the sole edited kernel profile. Suggested initial order: `kprof`, `dup`, `fs`, `tls`, then `srv`, `shr`, `segment`, `mnt`, `cap`; adjust order only if dependency analysis gives a reason. **Test one candidate at a time**, retaining previous accepted removals. Do not batch-delete all nine and then guess which caused the failure.

For each candidate:
1. Save the exact previous known-good config, build and test artifacts/logs; note `git diff` and the profile's registration count.
2. Remove **only its entry from the `dev` section of `sys/src/9/pc64/pc64onativedisk`**. Do not globally delete `dev*.c`. Do not silently change `link`, `misc`, shared platform builds or unrelated configuration. Source restructuring needs a separate explicit justification and scoped approval/hold.
3. Run an actual kernel build/link under `ONATIVE_DISK=1` and inspect the generated `pc64onativedisk.devc.c` and the **linked** `9pc64onativedisk`. Prove the removed `*devtab` registration and symbol are absent. Prove `consdevtab` and `sddevtab` remain absent and the native SD/O and required console symbols remain.
4. Run `ONATIVE_DISK=1 tools/test-oboot-server.sh` against **that exact newly built kernel**, with its disposable combined O disk and three boots. It must pass the real D2b persistence, identity, negative and native SD bounds/flush tests already checked by the script. Preserve the baseline's exact verification semantics (do not weaken/remove markers to force PASS).
5. If the compile, link, symbol proof, or O runtime fails, **revert just that candidate's config edit**, restore the last known-good accepted state, and log `BLOCKED` with the exact undefined symbol, initialization issue, error or observed QEMU failure. Continue to the next independently testable candidate only if safe. No fake stubs, dummy `Dev` registrations or behavior changes to make tests green.
6. If both linked proof and runtime pass, record `PASS` for that candidate with the exact build/test commands, exit codes, relevant logs and resulting `devtab[]` count. Commit coherent verified checkpoints (small commits or clear series), never mix failing attempts into a successful change. Do not treat build success alone as approval.

**Build prerequisite:** `WHAT=kernel` may not rebuild userspace MicroPython or the host seeder needed by `tools/test-oboot-server.sh`. Reuse only artifacts proven to match the baseline/current source or run the documented full prerequisites first; never claim a boot test if it did not run. `tools/build.sh` reuses/overwrites build outputs, so preserve candidate-specific logs and binary/symbol evidence under `build/verification/e7/<candidate>/` (ignored by Git), and take care not to mix default-profile artifacts with native-profile tests.

## Stage 3 — cross-profile regression and evidence

After all nine attempted removals:
- Re-run the final `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` followed by `ONATIVE_DISK=1 tools/test-oboot-server.sh` on the **final combined config**; do not infer combined safety only from individual earlier passes.
- Run a normal kernel build (`WHAT=kernel tools/build.sh`), plus the relevant normal/legacy smoke/QEMU O boot test as practical (`tools/test-o-boot.sh` if its prerequisites are present). Confirm legacy/default `Dev` registrations still exist. Use testable generated/linked evidence, not only a source diff. If shared code was changed at all, run focused `kernel_opmap` checks and any additionally affected tests.
- Verify that `ONATIVE_DISK=1` still selects only the intended opt-in kernel; other opt-in modes and invalid flag combinations retain E6 behavior.
- Capture `devtab[]` **before/after exact counts**, and the explicit list of registrations that remain. Do not label all ~15 estimated candidates removed when only nine were investigated.
- Preserve the O server's genuine `OID_MP_EXEC`, `OVOLOPEN(PARTUUID)`, three-boot `run() -> 1, 2, 3`, OID 7 alias identity, flush and GPT/bounds negatives, and measured zero `namec/newchan/walk/devwalk/mount/exec` counts in the scope of the test windows.

Do not introduce syscall/ABI changes, a native TLS/9P/mount/capability subsystem or new replacement abstractions. Never run destructive tools against host physical disks. Preserve all license/provenance information.

## Acceptance and reporting

Use the three distinct findings `PASS (removed, linked and runtime-verified)`, `BLOCKED (kept; concrete dependency or failure)`, and `NOT VERIFIED (kept; test unavailable/inconclusive)` for **each** of the nine. An E7 overall `COMPLETE` means all nine have been evaluated and the final remaining configuration is build- and QEMU-verified; it does *not* require all nine to be removable. If prerequisites or final runtime gates fail, report `PARTIAL-HOLD`, never claim success.

Update `docs/DEV-PRUNING.md` with baseline/final registry lists and the outcome per candidate, `docs/STATUS.md` with bounded executed evidence, and `docs/to_chatgpt_review.md` with a self-contained concise review. Do not overwrite the historical E6 evidence in `docs/SD-MIGRATION.md`. Regenerate `docs/KERNEL-OPMAP.*` only if actual source/config changes demand it, with explicit diff review. Do not churn unrelated docs.

**Final review headings:**

```text
E7 VERDICT: COMPLETE / PARTIAL-HOLD / REJECT
BASE / FINAL SHA / BRANCH / WORKTREE:
BASELINE: profile, devtab count, kernel, boot result
CANDIDATES: one line per nine, PASS/BLOCKED/NOT VERIFIED + precise reason
DEPENDENCIES: actual non-Dev symbols and init call chains
PRUNING: exact removed dev registrations and surviving devtab list/count
LINK PROOF: generated devtab and linked symbol evidence
O BOOT: each successful/failed three-boot test, logs and negative checks
LEGACY CONTROL: normal build and surviving legacy Dev proof
SAFETY / ABI: unchanged O/SD semantics, no dummy services, disposable images
UNRESOLVED: blocked cases, reasons, separately scoped next action
COMMITS / PUSH: what was written and where
```

Preserve the OpenCode JS auto-summary/git hook if active; do not duplicate its commit/push step or race its output. Do not force push. **Expected outcome is a measured reduction of unnecessary legacy `Dev` registrations in the opt-in O-only server kernel, not arbitrary deletion of nine drivers or replacement of useful C services.**
