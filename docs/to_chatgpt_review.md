E6 VERDICT: APPROVE

BASE / FINAL COMMITS / BRANCH:
Base `1c61dd175c0757e5eaed016c1a7305f7ccad5c91` on `main`; code checkpoint `ad836d7` (`E6.1`); evidence/report checkpoint `9901fe4` (`E6.2`); `E6.3` adds `sdcore.$O` to the arm64 source list for the shared port file (no amd64 behavior change). No force push; no unrelated tracked files were changed.

STAGES 1–6: PASS / PASS / PASS / PASS / PASS / PASS
- Stage 1 PASS: native owner `sdinitcontrollers()` in `sdcore.c`; called directly from `pc64/main.c` after `chandevreset()`; one-shot `QLock`/flag guard prevents duplicate enumeration.
- Stage 2 PASS: `sdcore.c` owns the registry, unit lifetime, `sdunititer/put/ready`, `sdblockrw`, `sdblockflush`, `sdrio` and shared SCSI emulation without `Chan`/`Qid`/`Dirtab`; `devsd.c` remains the legacy adapter.
- Stage 3 PASS: `sddevtab` and all legacy callbacks remain in `pc64`, `pc64mp`, `pc64native`, `pc64oconsole`; real legacy `#S` attach/walk/stat/read control PASS.
- Stage 4 PASS: `pc64onativedisk` / `9pc64onativedisk` chosen by `ONATIVE_DISK=1`; generated devtab and linked kernel contain neither `&consdevtab` nor `&sddevtab`.
- Stage 5 PASS: `sdloop` excluded and unlinked; audit recorded in `docs/SD-MIGRATION.md`.
- Stage 6 PASS: source/linked checks, four builds, default O boot, E5 D2b, legacy `#S` control, new-profile three-boot D2b, bounds/flush and wrong-GUID/malformed-GPT negatives.

INIT AND OWNER: actual symbols, sequence, exactly-once evidence
`pc64/main.c` does `pcicfginit()` → … → `chandevreset()` → `sdinitcontrollers()` → `bootmark(BMDevs)` → `pageinit()` → `o_user_bootstrap()`. In legacy profiles `chandevreset()` invokes `sddevtab.reset` → `sdreset()` → `sdinitcontrollers()`; the direct call then returns immediately. The core holds `sdinits`/`sdinitialized`. AHCI keeps its existing `iapnp()` self-registration convention; the core still invokes each `pnp` exactly once. Every new-profile boot contained exactly one `sd: controllers initialized (2) native-only` line; legacy profiles contained one `native+legacy` line. Unit `verify`/`online` are lazy in the D2b process through `sdunitready`, not forced into early boot.

SD CORE: concrete C operations and their real source files
`sys/src/9/port/sdcore.c`: `sdinitcontrollers`, `sdreset`, `sdadddevs`, `sdindex`, `sdgetdev`, `sdgetunit`, `sdunititer`, `sdunitput`, `sdunitready`, `sdblockrw`, `sdblockflush`, `sdrio`, `sdsetsense`, `sdfakescsi`, `sdfakescsirw`, `sdaddfile`, `sdinitpart`, `sdaddpart`, `sddelpart`, `sdfreedev`. `sd.h` keeps the concrete `SDev`/`SDunit`/`SDifc`/`SDreq` structures. `sdblockrw` uses absolute unit byte offsets; `devgefs.c:oblockrw` enforces GPT partition bounds before the call; `sdblockflush` issues synchronize-cache through `SDifc.rio`. Native symbols are linked in `9pc64onativedisk`; the source checker also verifies `sdcore.c` has no `Chan`, `Qid`, `Dirtab`, `namec` or `Dev sddevtab`.

LEGACY #S: retained in normal profiles, registration and behavior evidence
`pc64`, `pc64mp`, `pc64native` and `pc64oconsole` generated devtabs contain `&sddevtab`. `pc64oconsole` still lacks `&consdevtab`. `tools/test-o-native-generator.sh` boots `9pc64native` with a disposable virtio disk and prints `ONATIVEPROBE: E6 LEGACY #S attach=1 walk=1 stat=52 read=48 inquiry=1` from a real `#S` attach → walk `ctl` → open → stat → read path. `#S` write/control mutation, removability and legacy shutdown were **NOT RUN**.

O-ONLY PROFILE: config, flags, absence of both consdevtab and sddevtab, linked symbols
`sys/src/9/pc64/pc64onativedisk` has no `cons` and no `sd` in `dev`; `misc` keeps `sdiahci`, `sdvirtio10`, `sdnvme`, `sdram` and omits `sdloop`. `mkdevc` emits `sdifc[]` from `nsdifc` even without the `sd` Dev, and `sdcore.$O` is unconditional in the `pc64` `PORT` list. `ONATIVE_DISK=1` is rejected with `NATIVE_PROBE=1` or `OCONSOLE=1`. Generated `pc64onativedisk.devc.c` has neither `&consdevtab` nor `&sddevtab`. Plan 9 symbol check of `9pc64onativedisk`: `sddevtab` ABSENT, `consdevtab` ABSENT, `sdloopifc` ABSENT; `sdinitcontrollers`, `sdunititer`, `sdunitready`, `sdblockrw`, `sdblockflush`, `sdrio`, `sdvirtio10ifc`, `oblockopenpart`, `oblockrw`, `oblockflush` PRESENT.

SDLOOP: excluded or blocked, reason with precise Chan edges
Excluded from `pc64onativedisk` and proven absent by `sdloopifc` in the linked binary. `sdloop.c` stores `Chan *c`, opens it with `namec(path, ...)`, and performs backing I/O through the inherited `Dev`/`devtab` read/write path. It remains linked in the legacy profiles. A native O-backed replacement needs a separate reviewed lifetime/recursion/commit design and was not implemented.

PARTUUID AND GE/O: live native call chain, bounds, units, flush, ownership
`OVOLOPEN(PARTUUID=…)` → `devgefs.c:ovolopenblk` → `oblockopenpart` → `sdunititer`/`sdunitready`/`oblockgptpart` → `oblockrw`/`oblockflush` → `sdblockrw`/`sdblockflush` → `SDifc.bio`/`rio` → `sdvirtio10` → QEMU virtio-blk. `oblockrw` rejects writes/reads outside the selected GPT partition before the core; the core clamps at `SDmaxio` and unit end and keeps `Oblock` ownership of the `SDunit` reference. `sdblockflush` completed in every positive new-profile boot. The `#S/sdF0/data@...` text is a human-readable label from `unit->name`, not a path traversal. Non-`PARTUUID` `devgefs.c` still contains the inherited `namec("#S")`/`namec(dev)` path; it is not invoked by the measured D2b path.

BUILD / QEMU: exact commands, results, logs, 3-boot O persistence and negatives
PASS: `python3 tools/sd_migration_check.py`; `python3 tools/kernel_opmap.py --write` (reviewed source-split changes only), `--check`, and `python3 tools/test_kernel_opmap.py` (29/29). PASS builds: `WHAT=kernel`, `NATIVE_PROBE=1 WHAT=kernel`, `OCONSOLE=1 WHAT=kernel`, `ONATIVE_DISK=1 WHAT=kernel`. PASS QEMU: `tools/test-o-boot.sh` (default O boot, three boots, `run() -> 1,2,3`, OID 7, no FS); `tools/test-o-native-generator.sh` (legacy `#S` control); `OCONSOLE=1 tools/test-oboot-server.sh`; `ONATIVE_DISK=1 tools/test-oboot-server.sh`. The new-profile D2b run used one disposable O disk across three boots with incremental commits, preserved OID 7, no panic/fault, `sdvirtio: flush PASS`, `oblocktest: PASS in-range-read`, `read-at-end`, `oversized-read-clamped`, `write-past-end`, plus wrong-PARTUUID and malformed-GPT negatives and the existing missing-executable/failing-`run()` negatives. Logs: `build/verification/e6/` (ignored by Git).

PATHLESS METRICS: observed window and actual counters
Measured only from `ovolopen` enter through GE start and the first 64 D2b syscalls:
`opath: volopen-enter namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`,
`opath: volopen-opened` the same, `opath: volopen-started` the same, and
`OBOOT-D2B: AFTER-SYSCALLS n=64 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0`.
This is not a whole-kernel Chan-independence claim.

SAFETY / ABI: no new userspace raw disk access, no unauthorized host writes
No new syscall, userspace `Handle`/`Capability`/`Block`/`Queue` ABI, path namespace or raw-disk access was added. Native block operations are kernel-only and the GE/O syscall contract is unchanged. All QEMU runs used disposable images; no host physical disk was written. AHCI was enumerated in QEMU but physical AHCI/NVMe was **NOT RUN**; the legacy `#S` control was read-only.

UNRESOLVED: exact remaining blockers and next bounded action
- Physical AHCI/NVMe runtime I/O, removability/media-change and legacy `#S` write/control mutation were not executed; next bounded action is a disposable-hardware or QEMU-hotplug test that keeps the same native core path.
- The native `sdloop` replacement remains deliberately unbuilt; next action is a separate reviewed O-byte-source lifetime/recursion/commit design, not an E6 patch.
- Whole-kernel `Chan` removal is not claimed; `devgefs.c` still contains the inherited non-`PARTUUID` GE-volume path, and default profiles retain the complete `#S` adapter.
