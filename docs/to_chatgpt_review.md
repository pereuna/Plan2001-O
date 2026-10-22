Implemented the native O exec argv copy fix.

Summary:
- `execo()` now snapshots the bounded user argv pointer array once.
- New `execargcopy()` copies each string with a hard destination cap, checks each page with `okaddr()`, and derives the NUL/length only from copied bytes.
- Enforced `Oargmax = 32`, `Oargbytes = 16 KiB` including terminators, plus existing `Tos`/stack/alignment checks.
- Bad pointers return clean `-1` errors via `okaddr()` rather than note-posting `validaddr()`, preserving the caller and O handle.
- No unbounded user `strlen()`/`memcpy()` remains.
- Added `tools/test-o-exec-args.sh` covering valid/empty/32 args, argc 0, aggregate boundary, missing NUL, bad counts/pointers, cross-page strings, repeated rollback, and RFMEM mutation.
- Extended `ohello` to validate explicit argv content and `argv[argc] == nil`.
- Updated `docs/O-FORMAT.md` and `docs/STATUS.md`.

Verification, on HEAD `b41a102` plus uncommitted changes:
- Focused argv gate: PASS
- `test-o-boot-omp`: PASS
- All seven other O-only gates: PASS
- Build and selfroot: PASS
- Logs: `build/verification/build-args.log`, `selfroot-args.log`, `test-o-exec-argv.log`, and `build/verification/*-args.log`

Changes are not committed.
