E9 complete and pushed to `origin/main` (`772d195..e7bc196`).

- E9.1: moved `hostownerwrite` unchanged to `devcons.c`; `9pc64`/`9pc64mp` retain one implementation, `9pc64onativedisk` drops it.
- E9.2: removed `srv` then `shr` separately; final `devtab[]` 21 → 19, `mnt` retained.
- Verified per-step and final combined: native builds, linked-symbol absence, full D2b three-boot runs, negatives, legacy build/`test-o-boot.sh`, OCONSOLE build, SD checks, OMAP check and 29/29 tests.
- OMAP regenerated with reviewed `devcons.c` binding hashes; E3 historical hashes retained.
- E9.3: added `docs/PRODUCTION-BOOT-AND-AUTHORITY.md` and aligned AGENTS/README/spec/STATUS/review; docs-only diff, no executable changes.
- Limits: `hostownerwrite` runtime write test `NOT RUN`; physical AHCI/NVMe `NOT RUN`; `mnt` remains a separate task.
