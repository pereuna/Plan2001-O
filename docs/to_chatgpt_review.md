Implemented the normal O-loaded MicroPython boot path.

- Normal `9pc64` now embeds `oinit`, `kbdfs`, `ohandle`, `oexec`; no `/boot/mp`.
- Removed `pc64omp`; added clearly test-only `pc64mp`/`9pc64mp` for historical `/boot/mp` gates.
- `tools/mkovol` now seeds the built MicroPython executable by default; `NOMPEXEC=1` covers the older-image diagnostic.
- Added `tools/mkrepl` and updated `./repl_tui.sh` to launch the O-loaded REPL without selecting a kernel or OID.
- Updated `oinit` diagnostics, README, O-FORMAT and STATUS.

Verification on HEAD `016ccff` plus this uncommitted tree:

- Full amd64 build: PASS, `9pc64` `f5f989838226c6b8135c0b137a5f813c`.
- Generated default boot contents: no `mp`; `oinit`/`kbdfs` present.
- All nine O-only gates: PASS, including 3-boot persistence `1 -> 2 -> 3`, REPL value surviving restart (`kept = 4242`), missing/malformed/older-image diagnostics, argv/Tos/BSS, rollback and handles.
- Logs: `build/verification/*-default-o.log`.

The older `test-o-space` shutdown diagnostic (`panic: boot process died: unknown`) remains expected and is not a gate failure. No commit was made.
