# E5 — OpenCode: decompose ALL #c functionality into native kernel C APIs; prove a #c-free O-only profile

**ACTIVE TASK for OpenCode / DeepSeek.** Execute this assignment, not merely a design review. Source-controlled output is the implementation, focused tests, an honest audit and a single completion report. Read this file directly after \`git pull --ff-only\`; the previous Codex/Astra E4 assignment is historical, not an active competing instruction.

**Architectural authority:** \`docs/KERNEL-API-ABI.md\` (canonical concepts T01–T28), then \`AGENTS.md\`, \`docs/OBJECT-MODEL.md\`, \`docs/STATUS.md\`, \`docs/KERNEL-NATIVE-GENERATOR.md\`, \`docs/to_astra_review.md\`. Actual C source defines currently implemented behavior. E4 implementation baseline: \`f60211d0cd61886c839401262dff4a17abadd8a6\`; E5 assignment base \`6f97b492c81798252247dfa3d4b9fea8ce913372\`. Verify actual HEAD first.

## Desired final state / precise definition of "whole #c migration"

The inherited \`#c\` / \`consdevtab\` is NOT a hardware driver. It mixes independent kernel services. The objective is **complete functional decomposition**, rather than a new \`NativeDev\`, generic \`native_cons_read(Qid)\` facade or a renamed filesystem.

1. Every meaningful \`#c\` operation, initialization dependency and exported core function has a **documented, concrete, independently callable kernel C operation**, or is explicitly classified **legacy-only / unsupported** with a justified user-visible replacement policy. NO operational side effect may be silently dropped.
2. Real work/ownership lives in the appropriate kernel service/driver: Console output and log, Proc observations, Time, Random, system configuration, system control, statistics, and optional compatibility facilities. Retain \`Queue\`, \`Block\`, \`Proc\`, \`Lock\`, \`QLock\`, \`Rendez\`, etc. under their actual meanings. Do NOT create generic \`Device\`, \`Resource\`, \`Object\`, \`Channel\`, new handle class or artificial \`read/write/close\` vtable.
3. The legacy \`#c\` \`Dev\` implementation can remain as a **thin, behavior-preserving adapter** in legacy configurations while it delegates to the same native operations. Legacy \`Chan/Qid/Dirtab\` may exist in that isolated adapter; they must not leak into the native operation signatures or dynamic native call chains.
4. Deliver an **opt-in O-only amd64 kernel profile** that does not register \`consdevtab\` at all (no \`#c\` \`Dev\` registration), but retains essential \`print/iprint/panic\`, UART/screen output, time/random initialization, process/service behavior needed by O boot, and the proven D2b pathless server. **This is the primary removal proof.** Existing standard \`pc64\` and E4 \`pc64native\` must remain compatible and bootable. Do not globally delete \`#c\` before its users/boot dependencies are resolved.
5. Native **kernel C API** now; userspace **ABI** only when its complete rights/lifetime/layout contract is explicitly specified and reviewed. Reuse the already-implemented restricted \`IOWRITE\`/O syscall paths when appropriate. Do **not** invent 23 syscalls, a universal handle table or a new public ABI as a shortcut; operations without a native userspace consumer may remain kernel-only, but must not be misrepresented as userspace replacements.
6. Provide an auditable per-entry migration manifest and bounded QEMU evidence. A kernel building with \`consdevtab\` merely dormant is NOT the same as an O-only configuration without \`#c\` registration.

**This assignment is deliberately ambitious.** Complete as many stages as can be proved, committing each verified checkpoint. If an architectural/ABI decision or safety blocker cannot be resolved, report an exact **HOLD** at that gate and retain the working partial implementation. NEVER claim complete migration when only E4's three readnum operations exist.

## 0. Inventory first — all source-backed edges, not only E4 reads

Read the *whole current* \`sys/src/9/port/devcons.c\` (~1026 lines) including \`print/putstrn/iprint/panic/pprint\`, \`consinit\`, \`consdevtab\`, time encoding helpers, \`consread\`, \`conswrite\`, \`consopen/close\`, \`Qdir\`, all \`Dirtab\` modes and fall-through/defaults. Cross-reference \`portdat.h\`, \`portfns.h\`, \`qio.c\`, \`tod.c\`, \`random.c\`, \`port/print.c\`, \`sysfile.c\`, \`sysproc.c\`, build machinery and actual low-level user callers. Use \`tools/kernel_opmap.py\` / existing \`docs/KERNEL-OPMAP.json\` for structural hints; scan source for global symbols and cross-file callers too. Do not introduce a second huge general-purpose parser.

There are **23 Qid enumerators**, including \`Qdir\`, but the table is not equivalent to 23 usable data functions. Create \`docs/CONS-MIGRATION.md\`: one agent-readable table **with EVERY enumerator** plus \`consinit\`/reset/shutdown and \`print\`, \`iprint\`, \`panic\`, \`putstrn\`, \`pprint\`, \`readnum/readstr\`. Columns MUST be machine-extractable Markdown: \`Qid_or_symbol | current_read | current_write | legacy_perm | owner | native_operation | callers | security | state/lifetime | migration_status | evidence\`. Derive mode bits/behavior from actual code, including intentionally unsupported branches.

Scope map to verify, do not assume complete without checking:

| Domain / owner | Entries to audit | Non-negotiable detail |
| --- | --- | --- |
| Console and diagnostics | \`Qcons\`, \`Qconsctl\`, \`Qkmesg\`, \`Qkprint\`; \`putstrn0\`, \`putstrn\`, \`print\`, \`iprint\`, \`panic\`, \`sysfatal\`, \`_assert\`, \`pprint\`, \`prflush\`, \`consactive\`, \`cpushutdown\`, \`screenputs\`, \`serialoq\`, \`kprintoq\` | Retain log ring, ESC exception, screen/UART routing, queue wakeup/close semantics, early/panic IRQ-safe output, nil-Fgrp path. \`pprint\` currently reaches \`up->fgrp->fd[2]\` → \`Chan\`: do not conceal it in a native path. |
| Process | \`Qpid\`, \`Qppid\`, \`Qcputime\`, \`Quser\` | Exact \`up\` context, parent PID, CPU clocks, per-process username; E4 helpers are transitional text adapters, not ideal final typed API. User-write may change process credentials, NOT a trivial setter. |
| Time | \`Qtime\`, \`Qbintime\`; \`consinit\` → \`todinit\` | Native snapshots/clock controls; string and binary formats remain legacy serialization. Preserve clock set/trim/frequency privileged checks, width/endianness and old error behavior. |
| Entropy | \`Qrandom\`; \`consinit\` → \`randominit\` | Boot initialization and entropy policy; no accidental uninitialized RNG in the O-only profile. |
| System config | \`Qhostdomain\`, \`Qhostowner\`, \`Qsysname\`, \`Qconfig\`, \`Qosversion\` | Current source of truth, mutability/permissions and lifetime. E.g. \`config\` is read-only; do not grant a native writer. |
| Monitoring | \`Qsysstat\`, \`Qdrivers\` | Multi-CPU stats, reset side effects, \`devmask\` per Pgrp, real meaning of legacy Dev listing. Do not relabel legacy \`Dev\` enumerations "native driver inventory" without implementing one. |
| System control | \`Qreboot\` commands \`reboot\`, \`panic\`, \`rdb\` | These include privileged/destructive controls. Preserve \`iseve\` and stronger requirements where applicable; NOT permitted as unrestricted public ABI. Never actually run the destructive panic/debug operations in normal test jobs. |
| Synthetic data / forbidden | \`Qnull\`, \`Qzero\`, \`Qmordor\` | \`null\` discards output/EOF, \`zero\` fills requested bytes, \`mordor\` deliberately errors. These are semantic operations, not separate fake files in the new API. |
| Namespace only | \`Qdir\`, \`consattach/walk/stat/open/close\` | No new native equivalent to pathname traversal. Preserve legacy \`Qkprint\` exclusivity/ref/close semantics if the adapter stays. |

**Find all missing Qids** from actual enum/table. Explicitly trace \`consinit\`: calling \`chandevreset\` alone is not the same as \`consinit\`, and the existing O boot may defer or bypass \`chandevinit\`. Track whether \`todinit\` and \`randominit\` happen on each boot path, not by guess. Inspect \`mkdevlist\`, \`mkfilelist\`, \`portmkfile\`, \`sys/src/9/pc64/mkfile\` and configuration-generated source to understand build/link dependence on \`consdevtab\`.

**Stage 0 gate:** all 23 enumerators plus globals mapped, with concrete line/path dependencies and native/legacy classification; no claim that keyboard \`#b\`, draw \`#i\`, mouse, VGA or UART \`#t\` are part of \`#c\`. A \`#c\`-free console kernel does NOT mean screen/keyboard drivers have migrated.

## 1. Define an executable, non-generic kernel C service API

Separate **semantic data** from legacy text/binary encoding. Prefer real pre-existing functions directly rather than speculative wrapper proliferation. Add small domain-specific C declarations to the appropriate existing port header or a small domain header **only for actual newly implemented functions**; do not define an elaborate universal driver header.

Illustrative intent (NOT approved prototypes):

- Process: read current \`Proc\`'s typed PID, parentpid, accounting, identity subject to correct process and access contract. Keep E4 \`readnum\` helpers as legacy text-format adapters.
- Time: retrieve a coherent snapshot; set/trim/frequency operations enforce exactly the appropriate trusted-call/privilege policy at the public boundary. Avoid permanent shared global scratch state or returning pointers to stack buffers.
- Entropy: use existing \`randomread\`/init; avoid redundant PRNG wrappers.
- Console: preserve actual \`print\`/\`iprint\`/\`panic\` implementation and its safe early/IRQ paths; provide a direct byte-output function only if different semantics demand it. Do not force the diagnostic console into graphical \`Display\` or keyboard abstractions.
- Log: retrieve snapshot/ring data with explicit atomicity and offset policy; controlled reader subscription if actually needed. Kernel queue and streaming semantics are distinct.
- Configuration: typed get/set of real settings if already backed; restrict writes appropriately.
- Monitoring: typed system statistics; reset only under permitted caller context. Legacy formatting may stay in \`consread\` adapter.
- Control: direct, privilege-checked system shutdown/reboot actions rather than command-string \`write\`. Preserve all dangerous actions behind explicitly authorized code; unsupported functionality may be denied in O-only profile.

**Native API quality gate:** no new function takes \`Chan*\`, \`Qid\`, \`Dirtab\`, §file path§ or a synthetic Qid selector; no \`native_cons_read(any_qid)\` expanded to replace every function. Typed native functions should not return decimal text merely because \`#c\` did. Legacy serialization belongs to legacy adapter. Every operation has documented preconditions, side effects, ownership, sleep/IRQ safety and validation.

Some legacy entries are meaningless as native services (e.g. \`Qdir\`, \`Qmordor\`, \`Qdrivers\` as a Plan 9 namespace listing); **do not manufacture replacement services**. Record \`LEGACY-ONLY\` / \`INTENTIONALLY-UNSUPPORTED\` with a reason and a policy for any consumers. "Complete" means complete coverage and deliberate decisions, not a one-for-one fake API.

## 2. Refactor along real responsibility boundaries while keeping legacy behavior

Apply bounded stages (commit at each verified checkpoint):

**E5.1 Core split and lifecycle.** Move independent shared services out of \`Dev\` registration ownership (e.g. non-Dev core console code and initialized Time/Random services) while maintaining original behavior. Refactor implementation only where needed. \`print\`, \`iprint\`, \`panic\`, \`putstrn\`, \`pprint\`, \`prflush\`, \`cpushutdown\` and their globals must link and remain correct, including before scheduler/when \`up == nil\` and in a crash. Shared low-level \`readnum/readstr\` are generic formatting helpers and must not vanish when \`#c\` is absent. DO NOT change panic recovery semantics as incidental cleanup. \`pprint\` may remain a legacy-specific function if native kernel/boot paths do not call it; explicitly state where it still uses \`Chan\`.

**E5.2 Domain operations.** Implement native core operations for ALL meaningful domains in stage 0. Keep existing real data/function structures; do not expose \`Queue*\` or \`Proc*\` to userspace. For operations whose only meaningful implementation is already a Chan-free function, use it directly (with contract) and avoid duplicate wrappers. For restricted actions, require named trusted-kernel caller or preserved explicit rights check; do not silently bypass \`consopen/devopen\` permission checks.

**E5.3 Compatibility adapter.** Keep \`consdevtab\` in existing \`pc64\` and \`pc64native\` configurations for a comparison test. Rework \`consread/conswrite/consinit\` to dispatch to native services when safe, preserving byte-for-byte legacy read/formatting/offset/error, write permissions, exclusivity and lifetime. \`Chan\` may occur **only** in adapter paths. A legacy branch which cannot yet safely delegate must be marked \`LEGACY-ONLY\`; no invented equivalence. Do not forcibly route all operations through the E4 readnum generator: that rule is intentionally narrow. Keep current E4 \`NATIVE_REVIEWED_BINDINGS\` valid; if source moves, audit/repin exact source hashes only after reviewing changed helpers.

**E5.4 No-#c O-only link and runtime.** Create an opt-in config/profile (unambiguous name, e.g. \`pc64oconsole\`, selected via explicit build/test variable) that **excludes** \`consdevtab\` from the generated \`Dev\` registration list. Arrange to compile/link essential console/time/random core as non-Dev sources. Inspect generated devtab and linked symbols to prove both:
  - no \`consdevtab\` registration or runtime \`#c\` attach/walk path exists in this profile;
  - \`print/iprint/panic\` and essential native service/lifecycle symbols are present and executed.
Avoid misleading results: having the old \`Dev\` in the binary but simply not calling it is not sufficient. The linked *implementation* may still contain compat-only code only when explicitly justified by the linker/build model, but \`consdevtab\` must not be registered; prefer to omit compat code entirely in the O-only profile if straightforward.

The normal \`pc64\` and \`pc64native\` kernel behavior must remain unchanged. Keep \`#b\`, \`#i\`, \`#v\`, \`#t\` unchanged: they are separate migration targets. Do not remove other \`Dev\` or kernel-wide \`Chan\`. Do not alter GE/O v1, OIDs, kernel syscall table/ABI, or introduce a Python class-based device framework.

**E5.5 Userspace boundary and real consumer audit.** Search low-level userspace for \`#c\`, \`/dev/cons\`, \`/dev/time\`, \`/dev/reboot\`, etc.; record every reachable dependency of the new O-only boot path vs legacy-only applications. For O-only mode, if no user needs a given \`#c\` operation, native kernel-only implementation is sufficient; if user does need it, use **already approved, precisely scoped** syscalls or propose a **specific ABI contract** with rights, lifetime, validation and test before implementing it. Under no circumstances publish unrestricted time setters, reboot/debug, hostowner/identity changes, process control or kmesg queue pointers as convenience calls. If a new ABI is truly required and not specified by \`KERNEL-API-ABI.md\`, mark \`OPEN / HOLD\` rather than inventing a universal handle or new syscall numbers.

**E5.6 Evidence, cleanup.** Only remove transitional duplicated business logic and/or old adapter links from O-only build once exact native/legacy comparison and no-#c evidence are green. Legacy \`pc64\` compatibility may remain as long as legacy users need it; clearly distinguish "O-only #c unregistered" from "all legacy code removed from the repository."

## 3. Minimal, discriminating acceptance gates

No massive test campaign. Run in this order; log **actual** results, and rerun only dependent checks when fixing failures:

**Gate A — source/coverage**: enumerate 23 Qids, read/write/permissions and non-Qid exported core functions; report 100% coverage (each \`native\`, \`legacy-only\` or \`unsupported\`) and any outstanding actual users. A tiny source-check script/test under \`tools/\` may assert stable coverage, correct C labels and O-only devtab absence; do not make it a second general C analyzer.

**Gate B — functional unit probes**: focused native tests for (1) console output/log routing and early panic-safe path *without intentionally triggering panic*, (2) time/random initialization and sampled read behavior, (3) process PID/PPID/accounting, (4) read-only/denied writes, (5) log reader/close semantics if migrated, (6) one privileged operation **denied** for an unprivileged caller (never execute destructive success path). Use the repository's existing Plan 9 testing framework, not mock-only proof.

**Gate C — build**: normal \`WHAT=kernel tools/build.sh\` (pc64 and historical test control), E4 source/generator checks (update pin deliberately if appropriate), opt-in no-#c build. Prove its generated devtab/registration and linked core symbols. If \`tools/kernel_opmap.py --check\` source fingerprint changes, regenerate \`--write\` deliberately, review the diff and recheck.

**Gate D — O-only QEMU**: one disposable no-#c O-only kernel boot running **real D2b server** (or an equivalent integration test using the SAME O init, O volume, and MicroPython entry, not just a kernel print probe). Verify boot prints, 3-cycle same-disk persistence where already required by \`tools/test-oboot-server.sh\`, no panic, no missing time/random init, absence of \`#c\` registration and zero \`namec/newchan/walk/devwalk/mount/exec\` counters within explicitly described pathless measured windows. Preserve serial log. If a separate O-only test script is required, derive it from the existing D2b fixture with minimal duplication and opt-in profile selection. Never touch real disks.

**Gate E — legacy controls**: at most one focused legacy-\`#c\` test for representative formatting/permission and one native E4 QEMU regression if the E4 shared helpers/generator changed; do not run \`WHAT=all\`, GUI boot, every dev test or unrelated networking/storage battery without a concrete reason. If a gate cannot be executed, record \`NOT RUN\` with reason and **HOLD** on full acceptance.

**Adversarial checks**: programmatic/assertion-level failure for missing/forbidden \`#c\`, invalid native caller context, a non-privileged time-set or reboot request, and a disallowed userspace pointer if any new userspace-facing function exists. Tests must not actually call \`panic\`, \`rdb\`, hardware reboot or write physical disks.

A **FULL E5 APPROVE** requires coverage + source audit, functional gates, both legacy and O-only builds, a real O-only D2b QEMU run and security/lifecycle review. A **PARTIAL / HOLD** is a valid result when a specific unresolved ABI or internal refactor blocks that proof; do not fabricate completion.

## 4. Evidence and communication

- Maintain **one** source-oriented migration file: \`docs/CONS-MIGRATION.md\`. This is an operation matrix + implemented source/function relationship map + unresolved blockers, not marketing copy or a broad OS essay.
- Update \`docs/STATUS.md\` and, **only if genuinely necessary**, amend \`docs/KERNEL-API-ABI.md\` to add explicit canonical concepts *with IDs and rationale*; do not silently redefine \`Queue\`, \`Stream\`, \`Pipe\`, \`Handle\`, \`Capability\`, \`OID\`, \`Dev\` or \`Chan\`.
- Write the OpenCode completion summary to **exactly** \`docs/to_chatgpt_review.md\` (replace previous transient cleanup notice; Astra's \`docs/to_astra_review.md\` remains as historical review). No webpage, slides or ornate external artifacts. Keep generated checks/logs under ignored \`build/\`.
- Use clear committed checkpoints, e.g. \`E5.0 map\`, \`E5.1 split\`, \`E5.2 native services\`, \`E5.3 adapters\`, \`E5.4 no-cons\`, \`E5.5 evidence\`, while ensuring each commit is reviewable and avoids knowingly broken default kernel. No force-push or destructive cleanup; don't overwrite other uncommitted work. OpenCode's existing JS/git automation may handle final add/commit/push: do not duplicate it mindlessly.
- Do not create a new competing task file or reopen the completed Astra assignment. If complete scope is too large for one run, push **only verified coherent checkpoints**, identify exact next checkpoint; never turn incomplete coverage into a claim of total migration.

**Final report required literal headings**:

\`\`\`text
E5 VERDICT: APPROVE / PARTIAL-HOLD / REJECT
BASE / FINAL COMMIT(S) / BRANCH:
EXPLICIT SCOPE: O-only no #c registration / full repository legacy removal (distinguish)
23-QID COVERAGE: native N, legacy-only N, intentionally-unsupported N, unclassified N
CORE SYMBOLS: print, iprint, panic, putstrn, pprint, readnum/readstr, init, shutdown (each status)
KERNEL C API: actual functions, files and ownership; not hypothetical prototypes
USERSPACE ABI: implemented / existing reused / OPEN, rights analysis
LEGACY #c: retained, removed from O-only, or not yet removable; exact registration evidence
BUILD AND RUNTIME: exact commands, test PASS/FAIL/NOT RUN, log paths and commits
PATHLESS EVIDENCE: measured window and actual counters, avoid whole-kernel claims
SECURITY/LIFETIME: permission checks, kprint exclusivity, Queue/Stream separation, critical context
UNRESOLVED: concrete blockers with source paths and next small action
\`\`\`

**E5 goal in one line:** turn the multi-purpose Plan 9 \`#c\` namespace aggregator into real, plainly named and separately owned native C service functions; prove that the Plan2001-O O-only server can boot without registering the \`#c\` \`Dev\`, while legacy environments continue to work.
