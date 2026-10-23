**`D2b SERVER BOOT PASS`**

- **`RUN 1/2/3 = run() -> 1 / 2 / 3`**, each followed by a durable commit and `init: done`.
- **`SAME DISK = verified`**: one combined ESP+O image booted three times unchanged; no host reseed, copy or O-volume restore between boots.
- **`PERSISTENCE = init versions 1/2/3 (O versions 2/3/4); Counter OID 7 / alias 7 unchanged, n=1/2/3`**. Boot 1 fresh one-time `odemo` init; boots 2/3 restored with no module top-level reinitialization.
- **`NATIVE ONLY`**: zero `LEGACY-ATTEMPT` records; all `namec/newchan/walk/devwalk/mount/exec` counters zero at n=4/16/32/64. No post-MP `BIND/OPEN/PWRITE/FD2PATH`; native `IOWRITE` delivered the `run()`, commit and `init: done` messages.
- New `-N` mode skips `boot.py`, uses native `space.open('init')`, `p9_space_boot`, `p9_space_commit(1)` and `p9_space_report`, then sleeps without console input. `oboot=server` reuses the existing loader/`otouser`/`OEXECUTE` path. D2a and `-B` remain unchanged.
- Hidden legacy dependencies fixed only on `-N`: `p9_spacetime`/`getenv`, libc `nsec()` (`/dev/bintime`) replaced by `p9_now()`/`_NSEC`, and native `loadmod` avoiding `libpath`/`getuser` (`STAT /proc/...`).
- Negatives PASS: `run()`-raises image produces `init: run failed` / `init: failed, no commit` with no version/COMMIT/done; missing `OID_MP_EXEC` returns `-1`, preserves the handle and does not run MicroPython.
- **`LEGACY CONTROLS = PASS`**: D2a output diagnostic, Boot A/B/C, normal O three-boot, pathless storage, native exec/argv/handles.
- Commits `3cfd4ed` + docs `427adb3` pushed. Evidence: `docs/O-BOOT-EXPERIMENT-D2B.md`, `build/verification/test-oboot-server-{experiment,boot1,boot2,boot3,fail,missing}-experiment-d2b.log`. MicroPython SHA-256 `cb3fe615...723eaa`, size 2,195,994.

**`NEXT = smallest D2c input/REPL experiment`**: add a pathless serial input/line-discipline stream (or equivalent native stdin) to `p9_console_read`, then demonstrate a real REPL interaction without `/dev/cons` or `kbdfs`. Not implemented here.
