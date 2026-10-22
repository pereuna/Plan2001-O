# Next task: make O-loaded MicroPython the normal boot path

## Goal

Promote the demonstrated MicroPython-from-O path to the normal amd64 O-only system:

UEFI -> kernel -> embedded oinit -> MicroPython executable in O -> persistent init Space or interactive REPL.

Remove the embedded MicroPython binary from the normal kernel configuration. Retain the small oinit bootstrap and kbdfs console helper for now.

Prioritize working progress toward a file-free experimental OS. Keep this change focused; do not redesign mechanisms already sufficient for this experiment.

## Starting point

Read AGENTS.md, README.md, docs/O-FORMAT.md, docs/STATUS.md and the relevant build/boot tools.

The reviewed baseline is 8600401a84d812ca3d465802684c554e4f24dde0:
- pc64omp already boots O-resident MicroPython.
- oinit opens the volume/Space and invokes oexecute with validated arguments.
- OID_MP_EXEC is 0x4f45584543000003.
- MPEXEC seeds the unchanged interpreter.
- Native exec argv copying is now capacity-bounded.
- Three persistent boots, interactive REPL and missing/malformed-object checks have been demonstrated.

Work from current main and inspect actual dependencies before editing.

## 1. Make the O-loaded interpreter the default

Update the normal amd64 kernel configuration, O-only image preparation and supported launch commands so the default path starts oinit and loads MicroPython from O.

In particular, inspect repl_tui.sh and the scripts it delegates to. The existing human-facing REPL command must reach the O-loaded interpreter without requiring the user to select an experimental kernel or know its OID.

Preserve both uses:
- Run the persistent init Space, with the existing run()/commit behavior.
- Start the interactive REPL, using the argument combination already demonstrated by oinit -repl.

Keep the existing fixed experimental OID; a program catalog is not required.

Fresh runnable O images must be seeded with the real built MicroPython executable, byte-for-byte unchanged. Keep the ohello BSS-header mutation confined to its regression fixture. Never silently reformat or reseed an existing persistent user image. If an older image lacks the executable, return a clear diagnostic; automatic migration is outside this task.

## 2. Remove embedded mp from the normal kernel

Remove MicroPython from the normal kernel bootdir and any normal-path dependency on exec("/boot/mp"). Establish its absence using the generated boot contents.

MicroPython must still be built as an ordinary user-space executable: image preparation needs that binary to seed O. Removing the embedded copy must not accidentally remove the build output or host bootstrap dependencies used to prepare images.

Use one clear maintained default configuration. If pc64omp becomes identical to pc64, consolidate it or retain a documented alias only where needed by tools. Avoid duplicate configurations that can drift.

Existing test-only kernels may embed their dedicated harnesses. Historical embedded-MicroPython tests may be migrated to the new default path; preserve their behavioral assertions. Retain an embedded-MicroPython configuration only if a concrete regression still needs it, clearly marked as test-only. It must not remain a hidden fallback for normal startup.

## 3. Retain the minimal bootstrap dependencies

Keep embedded oinit and kbdfs. Do not remove devroot globally or rewrite console/keyboard drivers in this task.

Document the exact remaining dependencies:
- oinit is still reached through the inherited internal boot interface.
- kbdfs is still an embedded console helper.
- MicroPython executable bytes, Environment/code and persistent state come from O.

Do not claim that every runtime file interface has been removed.

If normal loading fails, print a useful serial/console diagnostic. Do not fall back to embedded MicroPython or add a recovery shell, watchdog, supervisor or reboot policy.

## Verification

Use disposable QEMU images and bounded waits.

Verify the actual default configuration and normal launch tooling:
- Generated default kernel boot contents contain oinit and kbdfs, with no embedded mp.
- Fresh default O images contain the expected MicroPython object; its digest matches the built binary.
- No root filesystem mount or pathname-based MicroPython exec is used.
- The same default disk boots three times: counter 1 -> 2 -> 3, stable Counter identity/alias and restored graph.
- The supported human REPL launch command reaches a prompt; evaluate a simple expression and demonstrate a persisted value across a restart using the same image.
- A missing or malformed interpreter object produces a clear diagnostic without using an embedded interpreter fallback.
- A failed load preserves the existing native-exec rollback and handle behavior.
- Build modes advertised for this path produce all required artifacts and fail clearly when prerequisites are missing.

Run the appropriate build and all nine existing O-only regressions listed in STATUS. Adapt obsolete embedded-boot assumptions to the new path while keeping persistence, identity, argv/Tos/BSS, handle and error assertions. Do not weaken tests to obtain PASS. Avoid duplicating an entire suite merely to rename a configuration.

The previous argv mutation test has imperfect synchronization: its ready signal precedes childopen(). This is not a blocker for this task; do not expand this change into another argument-copy redesign.

## Boundaries and documentation

Do not change the disk format, native argv ABI, SG_NOSWAP policy, GE/O relationship model, permissions, IPC or remote protocols. Do not implement a general program catalog or move the build system into O yet.

Update README.md, docs/O-FORMAT.md and docs/STATUS.md to describe the new normal boot chain, retained bootstrap dependencies, exact human-facing command, image prerequisites, and actual test evidence. Preserve historical test records and distinguish the new default from earlier experiments.
