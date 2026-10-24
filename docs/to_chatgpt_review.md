E6 complete and pushed: `ad836d7` (E6.1), `9901fe4` (E6.2), `22399f3` (E6.3) on `main`.

- `sdcore.c` now owns native SD init/registry/unit/block I/O; `devsd.c` remains the legacy `#S` adapter.
- `pc64onativedisk` (`ONATIVE_DISK=1`) links neither `consdevtab` nor `sddevtab`; `sdloop` excluded.
- PASS: default/E5/native-probe/new-profile builds; default O boot; legacy `#S` read control; E5 D2b; new-profile 3-boot D2b with bounds, flush, wrong-GUID and malformed-GPT negatives.
- Report: `docs/to_chatgpt_review.md`; matrix: `docs/SD-MIGRATION.md`; logs: `build/verification/e6/`.
