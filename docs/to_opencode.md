# Task: machine-generated operation map of the entire kernel driver surface

## Goal and scope

Build a repeatable source-analysis tool that inventories the entire kernel driver surface and maps file-facing operations to the underlying C operations and hardware/service interfaces.

This is the first step toward removing file abstractions from native device access. Produce evidence for subsequent transformations; do not change drivers, system calls, libc, boot behavior or storage formats in this task.

The intended destination is ordinary kernel C functions and records, with appropriately authorized system calls. Do not design a universal object runtime or assume that reducing the number of system calls is a goal. Recover existing operations first; harmonization and parameterization come later.

Read applicable AGENTS.md instructions and current source. Treat existing documentation as context, not as proof of implementation.

## 1. Discover the complete surface

Scan all kernel source and configuration trees under sys/src/9, including architecture-specific drivers, shared port code, storage/network/controller backends, and GE/O integration. Derive the inventory from source and build configuration, not from a hand-maintained list of known drivers.

Identify:
- Dev registrations, device characters, operation callbacks and default/delegating handlers.
- Dirtab/Qid definitions, dynamic directory generation and path dispatch.
- Command tables and control-command dispatch, including handlers implemented without Cmdtab.
- Lower-level driver registrations and callback tables, including SDifc and analogous network, display, input and other subsystem interfaces.
- Native non-file entry points and calls from system-call handlers into these subsystems where present.

Separate source presence from build inclusion. Show which drivers are selected by the normal amd64 configuration, which belong to other configurations, and where conditional inclusion cannot be resolved. Do not omit inactive or architecture-specific drivers. Do not label a driver active merely because its source exists.

Account for every scanned source file with a classification or an explicit unresolved reason. An ordinary helper file need not create a fake operation, but must remain visible in coverage accounting. Report parse failures, unsupported declarations and ambiguous registrations rather than silently skipping them.

## 2. Generate an operation map

For each exposed operation, record as much as can be established statically:
- Stable source-derived ID, subsystem and driver.
- File-facing entry: device character, path/Qid, callback, command/subcommand and dispatch condition where applicable.
- Input/output shape and units when evident: byte stream, key event, block request, offset, length, configuration value, etc.
- The concrete handler and downstream function/callback chain to the first identifiable device or service primitive.
- Which steps perform path lookup, walk, open, Chan handling, offset translation, textual parsing or formatting.
- Which steps perform substantive work: access checks, bounds validation, locking, state transitions, lifetime/reference management, waiting, hardware/register/DMA/interrupt interaction.
- Return/error behavior and asynchronous completion where recognizable.
- Source path, symbol and line evidence for each material mapping.
- Analysis status: resolved, partial or unresolved, with the specific reason and unresolved edge.

Distinguish a C call observed in source from a possible indirect-call target. Resolve callback assignments where practical; otherwise retain the callback edge and known candidates. Never fabricate a complete call chain through an unresolved function pointer. Handle recursion and graph cycles without unbounded traversal.

A file callback is not necessarily a single device operation: split recognizable command and Qid branches. Conversely, read/write must not automatically be dismissed as meaningless wrappers; they can implement actual device data transfer. Preserve the distinction between framing/transport and substantive behavior.

Record local Dev/Chan dispatch separately from mounted 9P transport. Do not describe all kernel device access as 9P. Treat #x as device naming syntax, not as a process handle.

Do not claim semantic equivalence, safe removability or complete behavioral understanding merely from call-graph reachability. For responsibilities that cannot be established, record unknown rather than absent.

## 3. Implementation and outputs

Deliver:
- A checked-in analysis program under tools/, with one documented command to regenerate the inventory from the repository.
- A versioned machine-readable JSON operation map.
- A generated Markdown report under docs/ with coverage totals, per-subsystem summaries, operation tables, source references and an explicit unresolved-work list.

Choose sensible artifact names and document them. Generate both outputs from the same analysis data. Keep output deterministic, sorted and free of machine-specific absolute paths and timestamps. Include source identity/fingerprints sufficient to detect stale results.

Prefer existing repository tooling and minimal dependencies. Inspect the Plan 9 C dialect and build conventions before choosing a parser. Do not require a new compiler framework just to start this inventory. A lightweight lexical/structural scanner is acceptable if its limitations are explicit; regex matches alone must not be presented as a reliable complete semantic analysis. Ignore comments/string contents appropriately when finding declarations and calls, and preserve source locations.

Bound traversal and output size sensibly through shared graph nodes and references rather than truncating drivers or hiding unresolved paths. Do not spend this stage building a general-purpose C compiler, whole-program theorem prover or automatic rewrite engine.

Any manual annotations must be kept separate, source-linked and clearly labeled. The inventory itself must be regenerated by the program, not hand-authored to look generated.

## 4. Validate coverage and representative chains

Run the tool over the complete kernel tree. Report actual counts for scanned files, registrations, exposed operations, mapped primitives, partial mappings and unresolved cases. Define those counts so that they can be checked and are not inflated by duplicate graph paths.

Manually cross-check generated results against representative source paths:
- GE/O native entry points through the storage backend, including any remaining Chan/Dev dependency.
- Block-device partition dispatch through SDifc to NVMe and another available storage backend.
- Keyboard input, kernel console and serial/UART paths.
- At least one network driver/subsystem path.
- One dynamically generated directory or nontrivial textual control dispatcher.

Use actual current source names. If a representative subsystem does not exist, report that fact and select an available alternative.

Explain the boundary around user-space kbdfs: its binary may be embedded in the kernel image, but it is a user-space service, not a kernel-mode driver. Identify the relevant kernel endpoints; do not count its user-space 9P server as a kernel driver or expand this task into a user-space-wide audit.

Add focused analyzer tests for meaningful failure modes: comments/strings resembling declarations, multiline registrations, Qid/command branches, indirect callbacks, duplicate symbol names in separate files, conditional compilation and deliberately unsupported input that must appear as unresolved. Add a determinism check and verify that newly introduced discoverable registrations are picked up without editing an allowlist. A kernel boot regression suite is unnecessary when runtime source has not changed.

## Acceptance criteria

The command runs successfully on current source and regenerates both artifacts deterministically. Every kernel source file is accounted for; every discovered driver registration has a mapped or explicitly unresolved entry. The report shows the full discovered surface, including non-default architectures, and distinguishes it from the normal amd64 build.

Representative chains are source-checked, and gaps are visible rather than hidden behind a claim of completeness. The result must let a reviewer select a bounded next transformation and see which file-layer responsibilities must be preserved in plain C operations.

Finish the report with a short, evidence-based shortlist of promising next extraction targets and their unresolved prerequisites. Do not perform those transformations, prescribe a universal syscall ABI, or harmonize different drivers yet.
