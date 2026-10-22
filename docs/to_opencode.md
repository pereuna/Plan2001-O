# Next task: load MicroPython directly from a native O object

## Goal

Extend the working native executable-loading experiment so the existing user-space MicroPython binary can be stored in GE/O and executed directly by OID.

Demonstrate:

embedded bootstrap harness -> native O executable loader -> O-resident MicroPython -> existing persistent init Space.

Keep this task limited to proving that transition. Preserve the current embedded MicroPython boot path until the alternative has been demonstrated.

## Starting point

Read AGENTS.md, README.md, docs/O-FORMAT.md, docs/STATUS.md and docs/to_chatgpt_review.md. Inspect the current code before editing.

The reviewed native executable experiment includes:
- Process-local O Space handles.
- oexecute(space, oid), currently constructing one synthetic argv[0].
- A bounded 8 MiB whole-object read.
- Shared exec parsing and process-transition machinery.
- Corrected Tos reservation and uintptr segment addresses.
- A regression probing a BSS page at 4 GiB.

The clean tested implementation is commit 4678fada0d66f83b310291320e57aba12068934d; later documentation commits record its results. Start from current main and record the actual revision.

## Implementation

1. Store the real built MicroPython executable in a disposable O volume under a documented experimental OID. Reuse the existing object representation; do not add a disk-format revision.

2. Inspect the current seeding constraints before extending them. The existing native-exec seed path patches the executable BSS header for the ohello boundary test. Keep that mutation strictly within that test fixture: MicroPython must be stored byte-for-byte unchanged. Verify the seeded content against the input binary.

   The existing small catalog/seed leaf must not become an arbitrary executable-size ceiling. Use the smallest sound change to seed a realistically sized executable, preserving existing image preparation and tests.

3. Extend native execution to pass the arguments MicroPython actually requires. Inspect main.c and the current boot configuration rather than guessing them.

   Use a bounded, validated argv interface consistent with the existing syscall ABI. Preserve existing callers or update them together. Validate user pointers, argument count, total bytes, alignment and stack bounds before replacing the process image. Copy argument data into kernel-owned state before destroying the old address space.

   Keep argv and strings below the reserved Tos area. Preserve the argv/Tos regression.

4. Add a small embedded bootstrap harness which opens the O volume and Space, then executes the MicroPython OID with the required arguments. It must not contain or load a second MicroPython copy through a file wrapper.

5. Preserve the current close-on-exec O handle rule. The new interpreter must acquire its own O session using its startup arguments. Do not silently inherit handles to make startup work.

6. Load the interpreter bytes directly through the native O engine. No temporary executable file, synthetic filesystem, pathname-based exec, Chan wrapper, Fid, Qid, mount or 9P in this loading path.

7. Check the actual MicroPython executable size against the loader's current 8 MiB limit. Retain that limit if sufficient. If a change is necessary, make it explicit and bounded, document the memory cost, and test oversized-object rejection. Preserve single-published-version reads and rollback on failure.

## Verification

Add a bounded automated QEMU regression using disposable ESP + O images without a root filesystem.

Demonstrate:
- The harness executes MicroPython from its OID.
- The tested kernel image does not embed MicroPython: absence must be established from the generated boot contents, not merely by observing a successful boot. Use a dedicated test configuration if needed; preserve the ordinary configuration.
- MicroPython loads its Environment/code and persistent init Space from O.
- Across three boots of the same disk, the existing counter advances 1 -> 2 -> 3 and retains the expected identity/alias.
- A separate interactive smoke test reaches the REPL through the O-loaded interpreter and evaluates a simple expression. Automate serial input if practical.
- Missing or malformed interpreter objects return a clear error to the harness without a kernel panic.
- Failed native execution preserves the harness image and its usable O handle.
- Existing argument/Tos/BSS and process-local handle assertions still pass.

Run the appropriate build, the new regression, and the seven existing O-only regressions, following the current STATUS instructions. Do not weaken assertions or conceal failures. Preserve diagnostic logs.

## Boundaries

Do not remove devroot globally, kbdfs, legacy drivers or the ordinary embedded MicroPython configuration in this task.

Do not implement a program catalog, architecture-selection graph, tags, package manager, permissions framework, remote protocol, watchdog or recovery supervisor.

The resulting test may still embed its small harness and console helper. Report those dependencies explicitly. This experiment proves that MicroPython no longer needs to be embedded in the tested configuration; it does not claim that all internal file interfaces have been removed.

## Technical documentation

Update docs/O-FORMAT.md and docs/STATUS.md with the actual API, boot chain, executable size/limits, commands, results, timestamps and log paths.
