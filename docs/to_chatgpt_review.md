E8 COMPLETE.

- Removed from `pc64onativedisk`: `kprof`, `dup`, `fs`, `tls`, `segment`, `cap` → `devtab[]` 27 → 21.
- Kept as BLOCKED: `srv`, `shr` (`srvrenameuser`/`shrrenameuser` from `hostownerwrite`) and `mnt` (`mntattach`/`mntversion`/`mntauth`/`mntrah*`/`muxclose`).
- Verified: per-candidate kernel builds, generated devtab/linked symbol absence, full `ONATIVE_DISK=1 tools/test-oboot-server.sh` D2b runs, final combined rebuild+3-boot test, default `pc64`/`pc64mp` build and `tools/test-o-boot.sh`, OMAP check/tests.
- Docs: `docs/DEV-PRUNING.md`, `docs/STATUS.md`, `docs/to_chatgpt_review.md`; OMAP regenerated after diff review.
- Commits pushed: `1cae94f..208c385` on `main`. No E7 branch changes.
