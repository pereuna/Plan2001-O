# E6 — OpenCode: native disk subsystem; remove #S Dev from the O-only server

**ACTIVE implementation task. Execute stages 1–6 in this ONE prompt.** Replace the completed E5 assignment, not `docs/KERNEL-API-ABI.md`. Build, run focused tests, commit and push independently verified checkpoints, and write the final OpenCode completion summary to `docs/to_chatgpt_review.md`. Do not treat passing source analysis as a substitute for linked QEMU runtime evidence.

**Baseline to verify:** `pereuna/Plan2001-O` `main` HEAD was `437f470f7170c4cc26fa622dfa72854e14924445` when this task was written (2026-10-24). E5 service split `53785d7`, E5 test report `9c41f3b`. Always check actual HEAD and working tree first. Preserve all user changes and the OpenCode JS/commit workflow.

**Read in this order:** `AGENTS.md`, `docs/KERNEL-API-ABI.md`, `docs/OBJECT-MODEL.md`, `docs/STATUS.md`, `docs/CONS-MIGRATION.md`, then the actual sources `sys/src/9/port/devsd.c` (~2142 lines), `sys/src/9/port/sd.h`, `sys/src/9/port/devgefs.c`, `sys/src/9/port/sdscsi.c`, all enabled `sd*` implementations, `sys/src/9/pc64/main.c`, `sys/src/9/pc64/pc64oconsole`, `sys/src/9/pc64/mkfile`, `sys/src/9/port/mkdevlist` and the test/build scripts. Actual current C sources are authoritative on implemented behavior.

## Goal, accepted architecture and exclusions

**Goal:** Plan2001-O must boot its *real* O-resident MicroPython D2b server, locate the GE/O volume by GPT PARTUUID, read/commit persistent O objects, and flush to disk **without registering/linking the legacy `#S` `sddevtab`**. The new profile must also retain the E5 removal of `#c` `consdevtab`.

Keep the existing physical storage controllers and their proven low-level code: SATA/AHCI `sdiahci`, NVMe `sdnvme`, VirtIO block/SCSI `sdvirtio10`, shared `sdscsi` translation where required, and existing `SDev`, `SDunit`, `SDifc`, `SDreq` structures as long as their actual semantics are appropriate. `SDifc` is a justified **controller interface**, not a new file-like `Dev`. Preserve the exact native data path already present:

```text
GE/O OID + Space
    -> O storage's PARTUUID/GPT-selected bounded Oblock
    -> devgefs.c oblockrw/oblockflush
    -> sdunititer / sdunitready / sdblockrw / sdblockflush
    -> SDunit / SDev / SDifc.bio, SDifc.rio
    -> AHCI / NVMe / VirtIO hardware
```

**Old compatibility path, retained in normal kernel:** `#S → sddevtab → Chan/Qid → sdread/sdwrite → SDifc`. It may call the same native core routines where behavior is equivalent. The new O-only path must not depend on the old path for enumeration, controller probing, initialization, read, write, flush or lifecycle.

Do **not** create a generic `NativeDevice`, `Filedev`, `ObjectDev`, object hierarchy, syscall number, new userspace Handle/Capability system, path namespace or alternative GE/O persistence model. There is NO new userspace disk ABI in E6. Keep `OID`, `Space` and `File` terminology from `KERNEL-API-ABI.md`; a live `SDunit*` is kernel state, **not** an OID, disk filepath or userspace Handle.

**Scope:** amd64 `pc64` family; opt-in QEMU O-only profile. Do not globally delete legacy `#S` support, other `Dev` devices, AHCI/NVMe/VirtIO drivers or existing legacy tests. Do not perform I/O to host physical disks; only disposable test images.

## Stage 1 — remove disk discovery's dependency on `Dev.reset`

Audit the boot call graph before changing it:

```text
pc64/main.c init sequence
    -> pci/trap/memory setup
    -> chandevreset()
        -> sddevtab.reset = sdreset()
            -> for sdifc[i]: pnp() -> sdadddevs()
    -> O-only kernel process / native OVOL / OSPACE operations
```

The above is the *currently expected* relationship; verify every edge in current code, including generated `devtab[]` / `sdifc[]`, controller IRQ/PCI prerequisites, `chandevinit` vs `chandevreset`, `up == nil`, scheduler availability, reset vs enable vs online, and the use of `getconf`. `sdunitready` / controller `verify` / media geometry may run lazily in process context; do not force those calls into unsafe early boot.

Refactor the real probe/registration work into an explicitly named **native disk subsystem initialization function** (e.g. `sdinitcontrollers()` or an existing accurate name, not an ABI proposal). It MUST be callable without dispatching through `Dev`, `Chan` or any `#S` path. Call it at a verified correct point for the native O-only boot. Normal profiles may preserve a thin `sddevtab.reset` adapter to the same operation.

**Critical:** E6 must never enumerate/probe/add the same controller twice if both the direct boot call and `sddevtab.reset` run. Choose one clear idempotence/ownership rule, guard or profile-specific dispatch. Document the exact initialization order and why PCI, IRQ, allocation and process context are valid.

**Stage-1 acceptance:** a clean kernel build, documented native init owner/entry point, no duplicate enumeration; E5 core console remains intact. Do not yet remove `sddevtab`.

## Stage 2 — preserve `SDev`/`SDunit`/`SDifc` as concrete C storage interfaces

Make the **SD core linkable and runnable without `devsd.c`'s legacy `Dev` adapter**. This is the actual hard part: currently `sdunititer`, `sdunitready`, `sdblockrw`, `sdblockflush`, controller enumeration and `sddevtab` coexist in the same large source file. Merely removing the `sd` line from the `dev` config would drop needed native symbols and prevent boot.

Refactor into explicit source ownership (preferred: `sys/src/9/port/sdcore.c` for generic controller registry/unit/lifetime/native block I/O, `devsd.c` for legacy `Chan`/`Qid`/`Dirtab`/`sddevtab` dispatch). Reuse `sd.h` and existing controller-specific files. Other minimal packaging is acceptable **only if it actually proves `sddevtab` absent from the new linked kernel**. Do not solve by a source file full of `#ifdef O_ONLY` duplications or a fake Dev table.

Inspect and classify the entire `devsd.c` implementation:
- `sdreset`, `sdadddevs`, unit registry, `sdgetdev`, `sdgetunit`, `sdunititer`, `sdunitput`, `sdunitready`, `sdblockrw`, `sdblockflush`, shared `sdrio`, error/memory/dma code, media-change and reference lifecycle.
- Non-Dev operations referenced by controllers, `sdscsi.c` or other kernel code: `sdsetsense`, `sdfakescsi`, `sdfakescsirw`, `sdaddfile`, `sdannexctlr` and `sdconfig`-related operations. Move only the necessary implementation to a native core; when a function's real purpose is to create a `#S` virtual file (e.g. `sdaddfile`), preserve it as **legacy-only** or provide an explicitly limited no-op/unsupported policy if a controller can still call it; no silently broken linkage.
- Explicit `SDev/SDunit` reference increments/decrements and error cleanup, including `sdunititer` returning a referenced unit. Disk enumeration names `sdE...` may be transient diagnostics but are not a durable OID or required pathname.
- Controller-specific `SDifc.bio` / `rio` contract and SCSI emulation required for non-SCSI media; do not strip a working translation layer just because the word "SCSI" sounds legacy.
- Raw `SDreq` state, DMA-alignment, bounce-buffer ownership, sector alignment, partial I/O, errors, flush, removable-media state, controller enable/disable and shutdown. For `sdblockrw` retain absolute **unit byte-offset** semantics (not `#S` partition-relative offsets). Retain `devgefs.c` `Oblock` GPT partition-range guard to stop writes outside the selected partition.

**Design constraint:** sharing a concrete `SDunit` and `SDifc` between core and legacy adapter is expected; it is **not** a regression to the file abstraction. The core's exported functions must not accept `Chan*`, `Qid`, `Dirtab`, a pathname or an invented Qid selector. Keep controller-specific hardware context in appropriate concrete records.

**Stage-2 acceptance:** source/linked evidence that all GE/O native calls resolve from the core, independently of `devsd.c`; existing normal `pc64` still compiles and the legacy file adapter remains available.

## Stage 3 — retain the legacy `#S` as a compatibility adapter

Retain `sddevtab` in normal `pc64` / `pc64mp` / `pc64native` and the previous `pc64oconsole`:
- `sdattach/sdwalk/sdstat/sdopen/sdclose/sdread/sdwrite/sdwstat/sdconfig` must preserve existing external behavior where still used.
- `#S/sdXX/data`, `ctl`, `raw`, `sdctl`, part names, permission checks, `devmask`/probed controller names, reference/lifetime and media-change rules remain legacy-only semantics and must not leak into the native C signatures.
- Record when legacy `sdbio` and native `sdblockrw` share implementation and when they intentionally differ (partition vs whole unit, EOF vs error, permissions, version/change semantics, raw control). Do **not** blindly equate them or replace all cases with a thin wrapper without comparing conditions.
- Preserve `sddevtab.reset` as a wrapper or agreed profile-safe lifecycle operation; ensure no second probe if `sdcore` init has already run.
- Preserve `sdscsi` and controller behavior, including their `pnp`/`enable`/`online`/`bio`/`rio` hooks. Test at least the VirtIO controller used by D2b, and compile AHCI/NVMe without claiming hardware tests.
- Track explicit limitations: `sdloop.c` currently uses `Chan*` and calls `devtab[c->c->type]->read/write`. It is **legacy-backed** and must not be misrepresented as native even if `SDifc` calls it.

**Stage-3 acceptance:** default and E5 no-`#c` kernels still build; representative legacy `#S` storage behavior survives, and old tests still have an actual route to the same storage implementation.

## Stage 4 — new opt-in profile: BOTH `#c` and `#S` absent

Add a configuration based on `sys/src/9/pc64/pc64oconsole`, e.g. `pc64onativedisk` / kernel `9pc64onativedisk`, selected with explicit `ONATIVE_DISK=1` in `tools/build.sh` and `tools/test-oboot-server.sh`. Choose ONE stable spelling across config, scripts, generated outputs, logs and documentation. This profile **inherits E5's no-`cons` setting** and further removes `sd` from the `dev` section.

Keep `sdiahci`, `sdnvme`, `sdvirtio10` and whatever `sdscsi`/PCI/DMA/IRQ functions their genuine C interfaces require under `misc` or equivalent direct link. Prefer leaving `sdram` unless justified otherwise. **Exclude `sdloop` from this new profile** because its backing file uses `Chan` and `devtab`; preserve it in legacy configs. Explicitly inspect how `mkdevlist`/`mkdevc` derive object list and `sdifc[]` registration; do not assume a source listed in `misc` is automatically initialized correctly.

Verify all of:
- generated `devtab[]` contains **neither** `&consdevtab` **nor** `&sddevtab`;
- linked `9pc64onativedisk` contains **neither** `consdevtab` **nor** `sddevtab`, but does contain direct console services (E5), SD core, `sdunititer`, `sdunitready`, `sdblockrw`, `sdblockflush`, essential controller entries and GE/O native O-block calls;
- the linked kernel does not need legacy `#S` namespace resolution at any point of the measured O boot path; `sdloop` is not linked if it still requires `Chan`;
- runtime enumeration/discovery completes even though no `sddevtab.reset` exists;
- **normal/default kernels do not silently switch** to the new profile and E5's `OCONSOLE=1` meaning remains unchanged.

Treat mixed opt-in flags (`NATIVE_PROBE=1`, `OCONSOLE=1`, `ONATIVE_DISK=1`) deterministically: define precedence or reject unsupported combinations explicitly, rather than accidentally building/testing different kernels than requested. Keep an opt-in profile; do not globally delete `#S`.

**Stage-4 acceptance:** actual generated devtab plus final linked-symbol proof and a bootable new kernel, not just an edited config.

## Stage 5 — `sdloop` policy and native userspace consumer audit

`sdloop` is a virtual disk backed by an inherited `Chan` to a file; it is **not** required by the existing tested O-only partition-backed D2b path. Keep it out of the new profile, without deleting it from normal kernels. In `docs/SD-MIGRATION.md` explain precisely why and how its future native replacement could use an O-resident byte source **only after** a separate reviewed lifetime/recursion/commit design; do not implement that speculative feature.

Audit all reachable callers from:
- O-only kernel bootstrap (`pc64/main.c`, O loader and `ouser.c`, `oblockopenpart`);
- `devgefs.c` O and legacy GE paths;
- controllers `sdiahci.c`, `sdnvme.c`, `sdvirtio10.c`, `sdscsi.c`, `sdloop.c`, `sdram.c`;
- userspace O-volume and GE/O operations, and legacy `#S`/`/dev/sd*` users as evidence only.

Distinguish **native O-only reachable**, **legacy-only reachable**, and **conditionally reachable**. Legacy `devgefs.c` still has `namec("#S")` and `namec(dev)` for inherited mount/GE volume code; those references are acceptable *only if they are not invoked or required in the new O-only path*, are not pulled into the linked kernel as an accidental `sddevtab` dependency, and are explicitly reported. Note that `devgefs.c:oblockopenpart` may **format** `"#S/%s/data"` as a human-readable device label; that alone is not a pathname traversal. Prove the actual call path rather than grepping string literals and declaring failure.

No new syscall, public `Block`/`Queue`/`Handle`/`Capability` ABI or direct arbitrary raw-disk access from userspace in this stage. The GE/O O-volume syscall contract remains unchanged. Physical disk writes must stay confined to the selected **GPT O partition** and current validated kernel path.

**Stage-5 acceptance:** short precise source/audit table of each native/legacy dependency and a defensible `sdloop` exclusion, with no accidental API vocabulary drift.

## Stage 6 — bounded verification and release evidence

Run the following gates **incrementally**; stop/repair failures rather than suppressing checks. Use disposable VM/QEMU raw images only.

**A. Source and registration checks.** Add a small deterministic `tools/sd_migration_check.py` (or similarly named script, no new general C parser) that checks (i) expected native SD operation declarations and definitions, (ii) controller registry ownership and initialization, (iii) `#S` remains registered in default/E5 legacy profiles, (iv) both `#c` and `#S` missing in new profile, (v) `sdloop` absent in new profile, (vi) actual generated devtab and kernel binary when supplied as arguments. Script MUST fail closed, distinguish source proof vs linked proof, and not fake runtime verification.

**B. Builds.** Compile default `WHAT=kernel tools/build.sh`; E5 opt-in `OCONSOLE=1 WHAT=kernel tools/build.sh` if the changes affect shared console/disk init; then `ONATIVE_DISK=1 WHAT=kernel tools/build.sh`. If same `build/amd64/` paths are overwritten between builds, save or sequence the relevant artifacts/logs before subsequent commands. Preserve E4 generation checks only if changed SD source affects the operation map or generator fingerprints; run focused `python3 tools/kernel_opmap.py --check` and documented regeneration when appropriate, not uncontrolled mass artifact churn. Update relevant `docs/KERNEL-OPMAP.json` only when required and reviewed.

**C. Default/legacy control.** Run relevant existing QEMU storage test that exercises real `#S` behavior (e.g. `tools/test-o-boot.sh` for a normal O boot; use a focused legacy `#S` read/stat control if that script doesn't actually use `#S`). Do not claim "legacy file adapter tested" based only on native O-direct reads.

**D. Real combined O-only D2b test.** `ONATIVE_DISK=1 tools/test-oboot-server.sh` must boot its real O-partition volume with actual `9pc64onativedisk`, OID_MP_EXEC and MicroPython `-N`; same disposable disk across boot 1/2/3 with `run() -> 1,2,3`, incremental commits, preserved OID 7 identity, correct checksum and no `panic`/`fault`. Retain missing-executable and failing-`run()` negatives. Confirm boot marker and actual controller probe/registration once. Log measured `namec/newchan/walk/devwalk/mount/exec` counters and do not generalize beyond the measured window. Ensure test does not accidentally boot `9pc64oconsole` or default `9pc64`.

**E. Native block negatives and durability.** Under the new **no-`#c`/no-`#S` kernel**, verify the existing native PARTUUID/GPT rejection paths (wrong GUID, invalid/malformed GPT), out-of-bounds writes, oversized reads and the actual VirtIO flush/persistence path using minimal focused QEMU probe(s), adapting relevant `tools/test-o-pathless.sh` pieces only where needed. Its original legacy `/boot/oinit` path is NOT itself proof for the new profile. Distinguish tests actually executed on new profile from historical Level A evidence. No destructive controller commands, no host raw block devices. If a new negative is impractical, mark `NOT RUN` and explain exactly which acceptance criterion remains unproven; do not silently drop it.

**F. Review.** Audit source and logs for duplicate enumeration, init ordering, reference leaks, unwinding/locks on errors, disk-range check, missing flush, wrong write/read offset units, uninitialized `eve`/`up` and hidden `Chan` path. Preserve E5 no-`#c`. Remove unused O-profile legacy symbols only after linked + boot proof. Full regression matrix is unnecessary unless affected sources require it.

**Full E6 APPROVE** requires A–F with real new-profile QEMU boots and at least verified native disk bounds/flush and representative legacy controls. If any gate cannot be run or a serious source issue remains, report `PARTIAL-HOLD` with the exact blocker and all completed verified checkpoints; do not report a false PASS.

## Machine-oriented results and reporting

Produce one concise but complete **`docs/SD-MIGRATION.md`** with:

1. Exact source-base/commit, active `SDifc` controllers (AHCI, NVMe, VirtIO, loop, RAM) and `SDev/SDunit` ownership; distinguish compiled, linked, probed, tested.
2. A source-backed operation matrix (columns: `symbol | defined_in | callers | native_or_legacy | inputs_outputs | ownership | permissions | initialization | errors | changed | evidence`). Include `sdreset`/new core init, `sdadddevs`, `sdgetdev/unit`, `sdunititer/put/ready`, `sdblockrw`, `sdblockflush`, `sdrio`, `sddevtab` + callbacks, `SDifc.bio`/`rio`, `sdscsi`, `sdloop`, the GE/O `oblock*` callers.
3. Explicit legacy-only operations/semantics for `#S` (`attach/walk/stat/open/close/ctl/raw/part/wstat/config`), with deliberate nonreplacement reasons.
4. The exact boot initialization order and whether `chandevreset` is still used by **other** devices (it may be).
5. The exact `ONATIVE_DISK` profile/config/devtab/linked proof; O-only direct path vs legacy call graph.
6. Every executed verification command, **PASS/FAIL/NOT RUN**, logs/observations and scope limits. Do not claim physical AHCI/NVMe runtime test when only QEMU VirtIO was exercised.

Update `docs/STATUS.md` with E6 actual scope and tests. Amend `docs/KERNEL-API-ABI.md` **only** to clarify a newly established storage contract or add a genuinely missing glossary concept (with stable ID and actual implementation evidence); never overwrite canonical meaning by synonym. Write **`docs/to_chatgpt_review.md`** as an agent-readable E6 report, not an old E5 "APPROVE" line or a pointer to a nonexistent long report. Keep detailed QEMU logs in ignored `build/verification/e6/`.

**Final report exact headings:**

```text
E6 VERDICT: APPROVE / PARTIAL-HOLD / REJECT
BASE / FINAL COMMITS / BRANCH:
STAGES 1–6: PASS / PARTIAL / NOT DONE for each
INIT AND OWNER: actual symbols, sequence, exactly-once evidence
SD CORE: concrete C operations and their real source files
LEGACY #S: retained in normal profiles, registration and behavior evidence
O-ONLY PROFILE: config, flags, absence of both consdevtab and sddevtab, linked symbols
SDLOOP: excluded or blocked, reason with precise Chan edges
PARTUUID AND GE/O: live native call chain, bounds, units, flush, ownership
BUILD / QEMU: exact commands, results, logs, 3-boot O persistence and negatives
PATHLESS METRICS: observed window and actual counters
SAFETY / ABI: no new userspace raw disk access, no unauthorized host writes
UNRESOLVED: exact remaining blockers and next bounded action
```

Commit verified checkpoints as `E6.1`, `E6.2`, etc. Do not force push or overwrite unrelated changes. OpenCode's existing completion hook may handle git commit/push and the review note; coordinate with it to avoid duplicate commits. **The intended result is a real, executing O-only disk stack without `#S` or `#c` in `devtab[]`, not the deletion of working storage code.**
