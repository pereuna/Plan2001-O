E8 VERDICT: COMPLETE
BASE / FINAL SHA / BRANCH / WORKTREE: base `1cae94f`; implementation final `1cd76c8`; branch `main`; clean worktree apart from this report/docs commit. This E8 report commit follows the six verified implementation commits; no E7 branch was touched, merged or renumbered.

BASELINE: `pc64onativedisk` (`ONATIVE_DISK=1`), generated `devtab[]` = 27 entries (not the estimated ~24), `consdevtab`/`sddevtab`/`sdloopifc` absent. Baseline `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` PASS; baseline `ONATIVE_DISK=1 tools/test-oboot-server.sh` PASS (three same-disk boots, `run() -> 1,2,3`, OID 7 identity, native bounds/flush, wrong-PARTUUID and malformed-GPT negatives).

CANDIDATES:
- `kprof` `#K`: PASS — removed; build/link/boot PASS; `kprofdevtab`/`_kproftimer` absent; `kproftimer` hook remains nil.
- `dup` `#d`: PASS — removed; build/link/boot PASS; `dupdevtab` and adapter symbols absent.
- `fs` `#k`: PASS — removed; build/link/boot PASS; `fsdevtab`/`mattach`/`mconfig` absent.
- `tls` `#a`: PASS — removed; build/link/boot PASS; `tlsdevtab`/`tlsinit`/`newtls` absent.
- `segment` `#g`: PASS — removed; build/link/boot PASS; `segmentdevtab` absent while `newseg`/`segattach`/`_globalsegattach` remain.
- `cap` `#¤`: PASS — removed; build/link/boot PASS; `capdevtab`/`cap*` absent.
- `srv` `#s`: BLOCKED — kept; config-only removal fails: `hostownerwrite: undefined: srvrenameuser in hostownerwrite`.
- `shr` `#σ`: BLOCKED — kept; config-only removal fails: `hostownerwrite: undefined: shrrenameuser in hostownerwrite`.
- `mnt` `#M`: BLOCKED — kept; config-only removal fails on `mntattach`, `mntversion`, `mntauth`, `mntrahinit`, `mntrahread`, `muxclose` in `auth.c`, `sysfile.c`, `cache.c`, `devgefs.c`, `devshr.c`.

DEPENDENCIES: `srvrenameuser`/`shrrenameuser` are unconditional calls in `hostownerwrite()` (`auth.c:143-144`). `mnt` helpers are also linked service code: `mntrahinit`/`mntrahread` (`cache.c`), `mntversion`/`mntauth` (`auth.c`), `mntattach` (`sysfile.c`, `devgefs.c`, `devshr.c`). `segmentinit` only assigns the optional `_globalsegattach` hook; `segment.c` supplies the pointer and nil fallback. `kprofinit` only sets the `kproftimer` hook; `portclock.c` null-checks it. None of the six accepted removals left an unresolved non-Dev symbol.

PRUNING: removed from `sys/src/9/pc64/pc64onativedisk`: `kprof`, `dup`, `fs`, `tls`, `cap`, `segment`. Generated `devtab[]` 27 -> 21. Surviving registrations: `root swap arch pnp env pipe proc mnt srv shr rtc ether ip wg draw mouse vga uart usb kbd gefs`. `consdevtab`, `sddevtab`, `sdloopifc` remain absent. `mnt`/`srv`/`shr` and all unlisted network/legacy drivers are retained.

LINK PROOF: after every accepted removal the newly generated `pc64onativedisk.devc.c` lacked the removed `&*devtab`, and the linked `9pc64onativedisk` lacked the removed devtab symbol. Final linked proof also retains `sdinitcontrollers`, `sdunititer`, `sdunitready`, `sdblockrw`, `sdblockflush`, `sdrio`, `sdvirtio10ifc`, `oblockopenpart`, `oblockrw`, `oblockflush`. `tools/sd_migration_check.py --profile pc64onativedisk` PASS. Evidence: `build/verification/e8/<candidate>/` and `e8/final/`.

O BOOT: baseline and every accepted candidate ran the full `ONATIVE_DISK=1 tools/test-oboot-server.sh`; all PASS. The final combined config was rebuilt and re-run (not inferred from individual passes): three boots of one disposable image, `run() -> 1,2,3`, Counter OID 7/alias 7, initial/restored/committed versions, one native SD init per boot, `sdvirtio: flush PASS`, all `oblocktest` bounds, failing-run/no-commit and missing-OID negatives, clean wrong-PARTUUID and malformed-GPT negatives, zero measured `namec/newchan/walk/devwalk/mount/exec` at the checked windows. No test marker was weakened.

LEGACY CONTROL: `WHAT=kernel tools/build.sh` PASS for `9pc64`/`9pc64mp`; both still link all nine candidate devtab symbols plus `consdevtab`/`sddevtab`. `tools/test-o-boot.sh` PASS (three same-disk boots, `run() -> 1,2,3`, Counter OID 7).

SAFETY / ABI: no source driver deleted, no `misc`/`link` change, no stub or dummy `Dev`, no OID/Space/on-disk/GPT/partition/SD-core change, no syscall or userspace ABI change, no new native TLS/9P/mount/capability subsystem. Only disposable QEMU images were used; no physical disk was written.

UNRESOLVED: `srv`, `shr`, `mnt` need a separately scoped refactor (extract or guard their non-Dev helpers) before their registrations can disappear; E8 deliberately did not do that. Physical AHCI/NVMe runtime remains NOT RUN (only QEMU VirtIO block was exercised). Generated `docs/KERNEL-OPMAP.*` was regenerated after review; the diff is the six profile removals, the profile's active-file count and the previously missing E6.3 `sdcore` arm64 record. `--check` and 29/29 tests PASS.

COMMITS / PUSH: implementation on `main`: `07437fc` (kprof), `f66c6e1` (dup), `e593480` (fs), `4a20640` (tls), `86d7dd8` (segment), `1cd76c8` (cap), followed by this reviewed docs/OMAP commit. Push status is reported by the workspace workflow; no force push and no duplicate commit/push step.
