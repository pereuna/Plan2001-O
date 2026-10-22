# Next task: fix native O exec argument copying

## Goal and scope

Fix the user-memory validation/copy race in execo() in sys/src/9/port/sysproc.c. Preserve the current oexecute(space, oid, argv, argc) ABI, MicroPython-from-O boot, synthetic argv[0] for argc == 0, Tos layout and close-on-exec semantics.

Read AGENTS.md, docs/O-FORMAT.md and docs/STATUS.md, then inspect the latest code and the kernel's existing user-memory access/error mechanisms. The reviewed implementation is in commit 07088d60a04da97b517b691d6bd4abcbcd5f3116; work from current main.

## Defect

The current code measures user strings with vmemchr(), allocates kargs from that total, then rereads uargv[i] and uses unbounded strlen() before memmove().

An RFMEM peer can change a pointer, terminator or string between those passes. The earlier validation no longer bounds the later copy. This can overrun kernel-owned memory or access an unchecked address.

Fix the mechanism, not just the observed input. Repeating validation before an unbounded copy does not solve the race.

## Required implementation

- Snapshot the bounded user pointer array into kernel-owned storage using appropriate checked access. Never reread the live user argv array during subsequent string copying.
- Copy each string with a hard destination-capacity bound, using the kernel's supported fault-safe user-memory access conventions. Check user address ranges, arithmetic, and mapped spans as needed.
- Do not measure user data and then perform an unbounded copy. No strlen(), strcpy(), or equivalent unbounded operation on user-owned strings.
- Determine each argument's accepted length and terminating NUL from bytes actually copied into kernel-owned memory. If scanning and copying are separate, validate the copied result and never use the source's earlier length as proof of termination.
- Enforce argument-count and aggregate-byte limits during copying. Reserve space for terminators, argv pointers, Tos, stack alignment and architecture-specific entry setup. Guard address/size arithmetic against overflow.
- Build the final exec stack exclusively from the validated kernel-owned argument snapshot. Bounded scans or strlen() on that proven, private, NUL-terminated snapshot are acceptable.
- Concurrent modification need not produce an atomic snapshot of all arguments. A bounded copied result or a clean syscall error is acceptable; unchecked access, unterminated accepted arguments and kernel buffer overruns are not.
- Use a small, understandable helper if useful. Avoid a large new user-copy framework or unrelated changes to ordinary exec.
- Preserve rollback: failure before process transition leaves the caller image and O handles usable. Release the object buffer, argument allocations, session references and partially constructed segments on every error path. Use existing kernel error handling.
- Retain the existing limit of 32 arguments. Document an explicit aggregate-byte limit and ensure currently used MicroPython arguments remain supported. Avoid large temporary allocations when a smaller bounded strategy suffices.

Do not change SG_NOSWAP policy, program loading architecture, seed tree format, bootstrap configuration or persistent storage semantics in this task.

## Focused regressions

Extend the existing native-exec tests or add a bounded regression with explicit assertions.

Cover:
1. Multiple valid arguments, empty argument strings, argc == 0, and the maximum supported argument count. The loaded target checks exact content and argv[argc] == nil.
2. Negative/excessive argc, nil or misaligned argv when argc > 0, invalid string pointers, a string crossing into an unmapped page, missing NUL within the allowed span, and the aggregate-byte boundary including terminators and stack overhead.
3. Failed calls preserve the caller and its usable O handle. Repeat failures enough to expose obvious cleanup/capacity regressions.
4. An RFMEM peer changes source pointers and string contents/terminators during bounded attempts. Use controlled buffers and synchronization, not arbitrary memory corruption. Keep a parent supervisor outside the executing child so successful exec cannot remove the test controller. Permit either successful execution of a valid bounded snapshot or a clean error; do not require concurrent mutation to be rejected.
5. Existing argv/Tos/BSS assertions and O-loaded MicroPython startup still pass.

A probabilistic stress test alone is insufficient evidence. Also verify the copy helper's bounds and fault paths with deterministic cases. Use bounded waits, clear FAIL diagnostics and disposable QEMU images.

Run the appropriate build, the focused regression, and the eight existing O-only gates listed in STATUS (including test-o-boot-omp). Preserve assertions and failure logs.

## Technical documentation

Update docs/O-FORMAT.md with the actual argument limits and concurrent-modification semantics. Update docs/STATUS.md with the commands, tested source state, results and log paths. Distinguish source-review conclusions from executed test evidence.
