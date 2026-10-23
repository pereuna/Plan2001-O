# Plan2001-O coding/research task: pathless normal O boot (no kernel Chan/namec on executed O path)

**Repository:** pereuna/Plan2001-O. Work from current main. This replaces the previous completed registration assignment.

## Question to answer experimentally

**Can the normal amd64 Plan2001-O boot find and open its GE/O partition, execute its bootstrap and O-resident MicroPython, and perform a persistent OID operation without traversing a filesystem, opening a kernel Chan, or calling namec anywhere along that executed O boot path?**

Answer with actual source-level call chains AND instrumented QEMU runtime evidence. The objective is a useful, buildable **architecture experiment**, not a wholesale 9front rewrite. Keep legacy code and its test configuration intact until a verified replacement exists.

Terminology: an **olio** is a locally registered Space occurrence with OID; a **file** may remain an ordered byte sequence. A filesystem/directory tree and its mandatory namespace semantics are NOT part of the target O model. Relations, graphs, tags, names, and queries remain USERSPACE concerns. No #tag feature implementation or test in this assignment.

This is an experiment with a strict proof standard. If the complete path cannot be implemented safely in one bounded change, deliver a working narrower step plus an exact, evidenced "NOT YET" for the complete question. Never weaken the scope retroactively or claim a partial test proves full boot.

## 1. Read the actual implementation before touching it

Read AGENTS.md, README.md, docs/STATUS.md, docs/O-FORMAT.md, docs/GENERAL-SOFTWARE-SPECIFICATION.md, docs/OBJECT-MODEL.md and these sources:

- sys/src/9/pc64/main.c: main(), init0(), userinit() handoff, current init= handling.
- sys/src/9/port/initcode.c: startboot() currently bind()s #c/#d/#e/#p/#s/etc, open()s /dev/cons three times, then path-exec()s /boot/oinit. **This is a real O-boot dependency; do not overlook it.** It also carries a one-page/no-data limitation.
- sys/src/9/pc64/pc64: normal kernel bootdir embeds oinit, kbdfs, ohandle, oexec. sys/src/9/pc64/pc64mp is test-only.
- sys/src/cmd/oinit/oinit.c: embedded path-invoked bootstrap; it opens O and executes OID_MP_EXEC.
- sys/src/9/port/devgefs.c: sysovolopen -> gevolume -> scandisks -> namec("#S") and namec("#S/sdXX/data"); existing GPT scan and O volume handles.
- sys/src/9/gefs/kern.c: geopen/newgfd/gopen/gpread/gpwrite/rw, **gflushdev() uses namec(raw)** to issue SCSI cache flush.
- sys/src/9/gefs/load.c: loadge() still calls open(dev) and dirfstat() through GE's gopen/gdirfstat bridge.
- sys/src/9/gefs/blk.c, sys/src/9/gefs/gefs.h, sys/src/9/gefs/gdat.h: GE I/O wrapping, sync and block cache.
- sys/src/9/port/devsd.c and sys/src/9/port/sd.h: SD device discovery, sector I/O, SDifc.bio, raw command/flush path, media changes, DMA/alignment and lifetime.
- sys/src/9/port/chan.c, dev.c, sysfile.c, devroot.c, devcons.c, devpipe.c, devmnt.c, portdat.h, sysproc.c, pgrp.c: namespace and descriptor requirements.
- sys/src/cmd/micropython/main.c, p9console.c, p9space.c: O-mode initialization AND stdin/stdout/raw console paths. The standard REPL uses descriptor I/O and /dev/consctl; it is NOT pathless merely because code objects load from O.
- Relevant kernel syscall definitions and ported GE prototypes.

**Important naming distinction:** gefs.h aliases the GE-internal message channel type to Mchan and the inherited kernel Chan to Kchan. GE's own queues (wrchan/rdchan) are not filesystem kernel Chans merely because their source spelling says "Chan". Audit semantic types, not just grep counts.

## 2. Explicit definitions of three proof levels

Implement and report levels independently:

**LEVEL A — O storage I/O pathless:**
A fresh normal O volume is discovered by PARTUUID (or a clearly documented native device ID), opened and used for OID register/read/commit/sync with NO kernel Chan, namec, devwalk, 9P, or directory enumeration in the executed disk discovery / O storage I/O / flush call chain. This includes every write-cache flush and retry, not just the first sector read.

**LEVEL B — native bootstrap pathless:**
The kernel passes control to a minimal bootstrap and executes the MicroPython binary at existing OID_MP_EXEC without the legacy initcode.c bind/open/exec pathname sequence, /boot tree lookup, or filesystem Chan. An **embedded flat binary blob/table** as bootstrap is acceptable; its filename in the source tree is not a runtime filesystem. Maintain the existing stable executable bytes/OID and error/rollback semantics.

**LEVEL C — entire demonstrated normal O boot pathless:**
After LEVEL B, MicroPython performs a real O register/read/reboot persistence or comparable existing O test, and any console/stdin/stdout needed by that path is also independent of filesystem Chans, fd-to-Chan and path lookup. No executed filesystem operations, including startup setup, output or the invoked REPL/test path, may be ignored. An OS background subsystem **not invoked by this test** may retain Chan and legacy Dev code in the compiled image; complete kernel-wide Chan removal is NOT the question.

If a level does not meet its precise contract, mark it **NOT YET** and describe the executed counterexample. Do not redefine "pathless" to mean "no filesystem mounted": the current O-only demo already demonstrates the weaker condition.

## 3. Mandatory baseline audit and evidence BEFORE changes

Create docs/O-BOOT-DEPENDENCIES.md with:

1. Concrete initial entry to GE/O transaction + direct callers, with file:line evidence; enumerate every use of namec, kernel Chan, Dev walk/stat, fs fd, path-exec and per-process fd tables along this boot.
2. Separate **core necessary mechanism** (device probe, block range, read/write/flush, interrupts, synchronization, process loading, stdout/serial I/O) from **legacy facade** (file naming, directory enumeration, 9P, qid, walk, /boot, mount).
3. Find all bootstrap and console operations from power-on through the target PASS marker, not only the O backend.
4. Record which calls happen at run time vs which are merely linked into the binary. Include the kernel-Chan vs GE-Mchan distinction.
5. Identify a smallest reversible implementation route and blockers. If a direct SD block API or console primitive already exists, reuse it instead of designing another generic framework.
6. Record HEAD commit, normal baseline build and a baseline QEMU transcript.

Do not just scan for words. Follow actual call graphs and dynamic execution.

## 4. Smallest pathless native block backend (Level A)

Prefer implementation in a compact, internal SD block interface; names below are suggestions, NOT existing APIs:

    Oblock *oblockopenpart(guid, flags);
    long oblockreadat(Oblock*, void*, long, uvlong);
    long oblockwriteat(Oblock*, const void*, long, uvlong);
    int oblockflush(Oblock*);
    uvlong oblocksize(Oblock*);
    void oblockclose(Oblock*);

It may use an existing SDunit + SDifc.bio and the existing hardware/controller drivers. It must NOT implement "direct" by opening #S/... through a hidden namec or Chan adapter.

Requirements:

- Find GPT PARTUUID directly from SD enumerated devices / real controller units; preserve partition bounds and 512/4096-byte sector awareness, little-endian GPT checks, partition type/unique GUID distinction, overflow defenses, malformed disk and missing partition behavior. Choose a sound hardware-independent SD iteration API rather than hard-coding QEMU's sdE0/sdXX.
- Respect SDunit initialization, removable/media-change locking, reference lifetime, failure cleanup, alignment/bounce-buffer/DMA and bounds as the existing sdbio does. Do NOT bypass validation to achieve a shorter call tree.
- **Correctly implement cache flush** via the underlying driver semantics with error propagation. GE's current gflushdev() reopening #S/.../raw via namec is not acceptable in Level A. If real flush cannot be implemented safely, Level A is NOT YET rather than falsely durable.
- Route native O GE reads/writes/sync through the block interface. One native O volume may be enough for this PoC. Keep GE superblocks, arenas, B-tree, existing GE/O versioning and format, OID allocator and user data unchanged. Do not repurpose OID for SD device handles.
- Be exact about error codes, read-only requests, partial transfers, out-of-range I/O, sector rounding and flush ordering. Do not silently swallow failures.
- Keep the legacy GEFS/9P path available for old regression gates and for comparison until an independently verified O path works. Avoid code duplication of the entire GE engine; limit divergence to its underlying I/O provider and volume discovery.
- No hidden Python file IO in the test or O initialization to cover up a block layer gap.

## 5. Bootstrap and console are separate, real blockers (Levels B/C)

Audit the current start of userspace:

    main.c:init0 -> initcode.c:startboot
    -> bind /dev trees -> open("/dev/cons") -> exec("/boot/oinit")
    -> oinit -> sysovolopen -> oexecute(OID_MP_EXEC)
    -> MicroPython -> p9console and O Space

A filesystem root not being mounted is INSUFFICIENT. The current embedded /boot tree remains a filesystem facade.

If Level A succeeds, implement the smallest experimental alternative for B in a **separate, explicitly selected O-native boot configuration or switch**, preserving the current working normal path as a regression control during development. Options to evaluate:

- one flat embedded bootstrap image whose entry is invoked/loaded without namec or Chan (boot image is bytes, not a directory entry);
- a kernel-native O startup path which directly loads OID_MP_EXEC after device initialization without a fake /boot name;
- another comparably small path justified by real kernel process creation and execo dependencies.

Do NOT impose a new universal O-object layer on drivers. Do NOT break the one-page initcode constraints accidentally. **Audit execo requirements:** process context, memory segments, Ureg/stack/Tos, handle lifetime, error rollback, argv copying and exit rules. Never inject executable bytes into an unsafe context merely to get rid of exec().

For **Level C**, inspect current stdio descriptors, keyboard kbdfs, MicroPython p9console.c and normal runtime init. The target may use a small direct serial console primitive rather than fd 0/1 or /dev/consctl; keep its behavior testable in QEMU and usable for a human where required. Reusing inherited UART hardware routines is preferable to writing a new terminal subsystem. Changing print output alone does not prove the interpreter's input path.

A useful **minimal Level C test** is the normal O-resident MicroPython boot doing native GE/O writes/reads and emitting PASS over a direct serial/console mechanism; an interactive REPL is an additional check only if it, too, is proven pathless. Clearly state which level was demonstrated.

If attaining B or C requires a wide replacement of process setup, syscalls, process stdio and all kernel driver APIs, **STOP at the last working proven level**, document the concrete call-chain blocker and cost rather than starting an unbounded refactor. This experiment is intended to decide whether 9front remains viable versus Genode/L4, not to force success at any cost.

## 6. Instrumented proof and disposable-QEMU gates

Add e.g. tools/test-o-pathless.sh plus an OPTIONAL instrumented kernel build and source-visible instrumentation. Capture and classify actual runtime operations, not just build-time symbol presence.

Instrument the relevant legacy entry points and callers in the scoped O execution path (namec, newchan/Chan allocation, devwalk/path walk, bind/mount, kernel-Chan SD access, legacy path exec and console descriptors). Beware: boot may invoke some before selection of the O path, so define and report the beginning/end of the observation window **and any pre-window calls affecting bootstrap**. Never hide earlier dependency by starting counters only after disk open. Prefer counters/markers, with detailed traces only when needed. Instrumentation must be switchable and should not perturb ordering/locks or require filesystem logging; print compact serial markers.

Checkpoints:
1. Baseline old boot still functions; log at least one real legacy path invocation to prove instrumentation works (positive control).
2. Direct O GPT volume opens by PARTUUID (test wrong/missing GUID and malformed GPT) with no kernel Chan or namec in its storage path.
3. OID allocation, empty/binary byte retrieval, read-after-write, normal sync; reboot the **same disposable disk** twice and verify stable OIDs/content and monotonic registration.
4. Explicit block-range failures/oversized requests rejected; flush command really reached the driver or has positive device-level evidence, not simply that an empty wrapper returned 0.
5. A deliberately exercised injected failure / interrupted operation when practical; no falsely reported committed OID on failed sync.
6. If B implemented: execute MicroPython from O by current binary OID without runtime /boot lookup, verify source binary SHA where existing gates already do so, and clean error when executable OID missing/corrupt.
7. If C implemented: a full normal O boot to a durable GE/O + MicroPython PASS marker with a verified **zero** forbidden legacy-path event count throughout the complete selected boot path, including console. Ensure the instrumentation check is not bypassed in uninstrumented code.
8. Existing gates as appropriate: WHAT=all tools/build.sh; tools/selfroot build/selfroot; tools/test-o-register.sh; tools/test-o-boot-omp.sh; tools/test-o-boot.sh; tools/test-o-exec.sh; tools/test-o-exec-args.sh; tools/test-o-handles.sh; tools/test-o-bytefile.sh; tools/test-ge.sh; tools/test-o-volume.sh; tools/test-o-objects.sh; tools/test-o-space.sh. Report PASS/FAIL/NOT RUN with **actual** commands and logs.

The test gate must not pass just because an expected marker appears if there were forbidden calls, warnings ignored, kernel panics before success, or a timeout. An expected QEMU shutdown diagnostic may be called out separately from a runtime path proof, consistent with earlier STATUS evidence.

## 7. Deliverables and decision

- docs/O-BOOT-DEPENDENCIES.md: measured call-path analysis, LOC/source anchors, A/B/C evidence and exact remaining blockers.
- Minimal safe source/test changes for the highest proven level; preserve baseline paths. Prefer 1–3 compact, reviewable commits over a giant refactor. Build/test before committing.
- docs/STATUS.md: dated record with exact commit/working-tree status, actual QEMU commands, PASS/FAIL/NOT RUN, logs, and any observable data integrity risk.
- docs/to_chatgpt_review.md: agent-facing review with the real technical findings and comparison (native 9front path cost vs replacing platform). **Do not handcraft a different final-answer transcript into this file if the existing OpenCode idle plugin copies the exact visible final answer there.** Keep full durable evidence in O-BOOT-DEPENDENCIES.md and STATUS.md.
- Commit and push intended edits; the OpenCode final-answer automation may handle the final git add/commit/push. Avoid racing its writes.

Conclude with a concise verdict, one of:
- **A/B/C PASS** — normal O boot demonstrably free from kernel Chan/namec in the entire executed path;
- **A PASS; B/C NOT YET** — native GE/O storage no longer depends on files but bootstrap and/or console do;
- **A NOT YET** — exact unresolved call chain, limitations, risks and minimum next experiment.

Never claim that merely renaming Dev/Chan or removing mounting achieves this. Do not remove the legacy filesystem from the repository or change on-disk formats. Do not implement #tags, graph semantics, new object hierarchies, global OIDs, an IP protocol, or Genode migration. Do not use real physical disks during tests.
