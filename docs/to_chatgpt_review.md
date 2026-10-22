Implemented the MicroPython-from-O experiment.

Key changes:
- `oexecute(space, oid, argv, argc)` with bounded/validated argv, kernel-side copy, non-overlapping `Tos`/argv stack layout.
- Native allocator handles image-less persistent segments: `SG_NOSWAP` and nil-image `dupseg()`.
- New `/boot/oinit` harness executes `OID_MP_EXEC = 0x4f45584543000003`.
- New `pc64omp` kernel config embeds only `oinit` + `kbdfs`; ordinary `pc64` unchanged.
- Multi-level GE seed tree for large objects; `MPEXEC=` seeds MicroPython byte-for-byte.
- New QEMU gate `tools/test-o-boot-omp.sh`.

Verification (working tree on HEAD `122e585`, uncommitted):
- New gate PASS: 3 boots `1 -> 2 -> 3`, same Counter OID/alias 7, object SHA-256 matches host binary, REPL evaluated `OINIT-REPL 42`, missing/malformed objects returned errors with the handle preserved.
- Existing gates PASS: `test-o-exec`, `test-o-handles`, `test-ge`, `test-o-volume`, `test-o-objects`, `test-o-space`, `test-o-boot`.
- Logs: `build/verification/*-omp.log`, `build/verification/test-o-boot-from-o.log`.

Docs updated: `docs/O-FORMAT.md`, `docs/STATUS.md`. Changes are not committed.
