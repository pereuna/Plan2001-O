Implemented the kernel driver operation-map inventory.

- Analyzer: `tools/kernel_opmap.py`; regenerate with `python3 tools/kernel_opmap.py --write`, verify with `--check`.
- Outputs: `docs/KERNEL-OPMAP.json` and `docs/KERNEL-OPMAP.md`; manual cross-checks in `docs/KERNEL-OPMAP-NOTES.md`.
- Current results: 226 files scanned, 69 registrations, 976 exposed operations (45 hardware-resolved, 82 controller, 868 partial, 63 unresolved), 613 shared chains, 59 native entry points.
- Tests: 10 passed via `python3 tools/test_kernel_opmap.py`; `--check` reports up to date. Logs: `build/verification/kernel-opmap-*.log`.
- No kernel source, syscall table, driver, libc or boot behavior was changed.
