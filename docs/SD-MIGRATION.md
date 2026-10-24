# SD storage migration: native core and the no-`#S` O-only profile (E6)

**Source base:** `1c61dd1` (E6 assignment) on `main`. **Implementation checkpoint:** `ad836d7` (`E6.1`). **Evidence:** agent-executed on 24 October 2026 with disposable QEMU images; detailed logs are under `build/verification/e6/` (ignored by Git). This document describes the implementation at `ad836d7` plus the documentation checkpoint that follows it.

**Scope:** amd64 `pc64` family only. The new opt-in profile is `pc64onativedisk` / `9pc64onativedisk`, selected by `ONATIVE_DISK=1`. It inherits E5's absent `cons` and additionally omits `sd` from the `dev` section. Default `pc64`, `pc64mp`, `pc64native` and `pc64oconsole` retain the legacy `#S` adapter.

## 1. Ownership and controller status

The split is a source-ownership split over the *same* concrete records:

| Item | Owner at E6 | Status |
| --- | --- | --- |
| `SDev`, `SDunit`, `SDifc`, `SDreq`, `SDpart`, `SDfile` | `sys/src/9/port/sd.h` (unchanged concrete structures) | existing |
| Controller registry (`sddevs[]`, `sddevletters[]`, `sddevslock`), probe entry, unit lookup/lifetime, native block I/O, shared SCSI emulation | `sys/src/9/port/sdcore.c` | new file, native core |
| Legacy `Dev #S` (`sddevtab`), `Chan`/`Qid`/`Dirtab`, `#S/sdXX/{data,ctl,raw,...}`, legacy permissions, `sdloop`-facing dispatch | `sys/src/9/port/devsd.c` | retained legacy adapter |
| AHCI | `sys/src/9/pc/sdiahci.c` (`sdiahciifc`) | compiled + linked; probed in QEMU via the AHCI controller; **not hardware-tested** |
| NVMe | `sys/src/9/port/sdnvme.c` (`sdnvmeifc`) | compiled + linked; **not probed** in the executed QEMU gates |
| VirtIO block/SCSI | `sys/src/9/port/sdvirtio10.c` (`sdvirtio10ifc`) | compiled + linked; **probed and used** for the O disk in QEMU |
| RAM disk | `sys/src/9/port/sdram.c` (`sdramifc`) | compiled + linked in the new profile; pnp returns one `SDev` with zero configured units when no `ramdisk=` is set |
| Loopback file disk | `sys/src/9/port/sdloop.c` (`sdloopifc`) | **excluded** from `pc64onativedisk`; retained in all legacy profiles |

AHCI's `iapnp()` registers its controller with `sdadddevs()` itself and returns `nil`; VirtIO, NVMe and RAM return an `SDev` chain which the core registers. `sdinitcontrollers()` still calls each `pnp` exactly once, so this controller-specific convention does not duplicate registration.

## 2. Operation matrix

Columns use the E6 task's vocabulary. `native` means callable without a `Dev`, `Chan`, `Qid`, `Dirtab` or pathname; it does not imply userspace reachability.

| symbol | defined_in | callers | native_or_legacy | inputs_outputs | ownership | permissions | initialization | errors | changed | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sdinitcontrollers` | `sdcore.c` | `pc64/main.c` (direct), `sdreset` | native | none -> probes `sdifc[]`, registers `sddevs[]` | the caller owns no returned object; registry keeps `SDev` | kernel-only | `QLock sdinits` + `sdinitialized`; one-shot | controller pnp failures are controller-local; out-of-memory prints and drops | new explicit native owner | boot marker `sd: controllers initialized (2) native-only` exactly once |
| `sdreset` | `sdcore.c` | legacy `sddevtab.reset` | legacy adapter over native core | none -> `sdinitcontrollers()` | same as above | kernel-only | guard makes a second call a no-op | same | replaced body with core call | generated `devtab[]` default retains `&sddevtab` |
| `sdadddevs` | `sdcore.c` | `sdinitcontrollers`, AHCI `iapnp`, legacy `configure` | native | `SDev*` chain -> allocates `unit`/`unitflg`, assigns `sd<letter>` | registry owns the `SDev` | kernel-only | after PCI/allocator setup, before units are opened | OOM/letter exhaustion calls `clear` and frees the chain | moved from `devsd.c` | `pc64onativedisk.devc.c` has `sdifc[]`; runtime enumerates units |
| `sdgetdev` / `sdgetunit` | `sdcore.c` | core iterator, legacy `#S` callbacks | native records, legacy-callable | device letter / subno -> referenced `SDev*` / probed `SDunit*` | caller drops `SDev` ref; unit reference is held by its `SDev` | kernel-only | `sdgetunit` lazily enables the controller and calls `SDifc.verify` once per subno | `nil` for bad id/subno, failed enable or failed verify | moved; legacy signatures unchanged | used by native O open and legacy #S |
| `sdunititer` / `sdunitput` | `sdcore.c` | `devgefs.c:oblockopenpart` | native | `Sditer*` -> referenced `SDunit*` / drop reference | returned unit keeps `SDev` reference; `sdunitput` decrefs | kernel-only | iterates registered controllers without `namec` | `nil` at end | moved; no Chan/Qid selector | `opath` window shows zero `namec`/`newchan` during discovery |
| `sdunitready` | `sdcore.c` | `devgefs.c:oblockopenpart` | native | `SDunit*` -> 1 if sectors/secsize are available | none transferred | kernel-only | calls `sdinitpart` under `unit->ctl`; online/verify in process context | returns 0 on media/geometry failure | moved | VirtIO unit becomes ready and GPT is parsed |
| `sdblockrw` | `sdcore.c` | `devgefs.c:oblockrw` | native | `(unit, write, buf, len, absolute unit byte offset)` -> bytes transferred | buffer remains caller-owned; temporary DMA bounce buffer owned by the call | kernel-only | lazy geometry/media re-init; `unit->ctl` and optional removable lock | `Ebadarg`, `Eio`; clamps at `SDmaxio` and unit end | moved from `sdblockrw`; keeps absolute unit offsets | O reads/commits on `sdF0`; `oblocktest` bounds markers |
| `sdblockflush` | `sdcore.c` | `devgefs.c:oblockflush` | native | `SDunit*` -> 0 on successful synchronize-cache | request/unit raw lock owned by the call | kernel-only | uses the driver `rio` path directly; no `/raw` open | `Ebadarg`, `Eio` | moved from `sdblockflush` | `sdvirtio: flush PASS` in every positive new-profile boot |
| `sdrio` | `sdcore.c` | `sdblockflush`, legacy raw `read`/`write` | native core | `SDreq*`, optional data -> driver `bio`/`rio` result | allocates/frees the DMA request buffer; restores driver sense state | kernel-only | called with the unit's raw lock held by the caller where required | `Etoobig`, `Enoata`, `Enoscsi`, `Eio` | moved; shared by both callers | flush and VirtIO/SCSI paths |
| `sdsetsense` / `sdfakescsi` / `sdfakescsirw` | `sdcore.c` | AHCI, NVMe, VirtIO, RAM, `sdloop` | native core (SCSI emulation is not itself a `Dev`) | `SDreq*` -> driver status/sense or translated LBA/count/direction | request/unit state | kernel-only | none | `SDcheck`/sense codes; `SDnostatus` means "continue in driver" | moved so non-SCSI controllers link without `devsd.c` | VirtIO flush and HDD path; RAM/loop in legacy profiles |
| `sdaddfile` | `sdcore.c` | AHCI (`led`), NVMe (`smart`) | native metadata helper, legacy-visible only through `#S` | `SDunit*`, name/perm/read/write callbacks -> efile slot | `SDunit` owns the registered entries | none in core; exposure permissions are legacy `#S` | controller unit verify time | `-1` for nil unit / exhausted slots | moved so controllers do not fail to link without `devsd.c`; with no `#S` the entries are never exposed | AHCI/NVMe link in the new profile |
| `sd2gen`, `efilegen`, `sdgen`, `sd1gen` | `devsd.c` | `#S` walk/stat/read | legacy | `Chan`, Qid/Dirtab, `Dir` | per-`Chan` | legacy `devdir`/`devopen` mode checks | legacy namespace only | `-1`/`Eperm`/errors | unchanged | not used by the new O path |
| `sdattach`, `sdwalk`, `sdstat`, `sdopen`, `sdclose` | `devsd.c` | `#S` namespace | legacy | spec/name/`Chan` -> `Chan*`, `Walkqid*`, `Dir` | `Chan` owns `c->aux = SDunit*` and the `SDev` reference after open | legacy `devopen`, unit/part permissions, exclusive raw | legacy namespace only | `Ebadspec`, `Enonexist`, `Einuse`, `Echange` | unchanged | `pc64native` probe attach/walk/stat/read control |
| `sdread` / `sdwrite` | `devsd.c` | `#S` namespace | legacy | `Chan`, user buffer, offset -> bytes | per-`Chan`; `sdrio`/`sdbio` inside | legacy file permissions | legacy namespace only | `Eperm`, `Echange`, `Ebadctl`, `Eio` | unchanged; calls the same core `sdrio`/`sdbio` helpers | legacy `sdctl` read in the probe |
| `sdbio` | `devsd.c` | `sdread`/`sdwrite` Qpart | legacy | `Chan`, partition-relative offset -> bytes | `Chan`/`SDunit` | legacy file permissions | legacy namespace only | `Eio`, `Echange` | unchanged; intentionally separate from absolute `sdblockrw` | not used by native O |
| `sdwstat` | `devsd.c` | `#S` namespace | legacy | `Chan`, `Dir` -> updated user/mode | `Chan`/`SDunit` | legacy owner/`iseve` checks | legacy namespace only | `Eperm`, `Enonexist` | unchanged | not used by native O |
| `sdconfig`, `configure`, `unconfigure` | `devsd.c` | `#S/sdctl`, legacy config path | legacy (controller lifecycle helpers use core registry) | spec/`DevConf` -> add/remove `SDev` | legacy controller ownership | legacy namespace/`iseve` | `#S` control path | `Ebadspec`, `Enonexist`, `Einuse` | unchanged; `sdfreedev` is now in core | default profiles only |
| `sdshutdown` | `devsd.c` | `chandevshutdown` | legacy | none -> controller `disable` | registry | kernel-only | legacy `Dev` shutdown | prints a warning when `disable` is nil | unchanged | default profiles only |
| `sdannexctlr` | `devsd.c` | no live caller in this tree (declared for inherited SDIO users) | legacy | letter/`SDifc` -> controller pointer | transfers controller out of the registry | kernel-only | legacy | `Enonexist`, `Einuse` | unchanged; frees through core `sdfreedev` | source audit |
| `SDifc.bio` | controller files | `sdblockrw`, legacy `sdbio`, controllers | controller contract | unit/LUN/write/data/sector count/LBA -> bytes | controller/unit | kernel-only | controller enable/verify | driver-defined | unchanged | VirtIO O disk path |
| `SDifc.rio` | controller files | `sdrio`, `sdblockflush`, `sdscsi` | controller contract | `SDreq*` -> status | controller/unit | kernel-only | controller enable/verify | driver sense/status | unchanged | VirtIO flush (`0x35`) and SCSI path |
| `sdscsi.c` | `sdscsi.c` | VirtIO-SCSI, AHCI/controller helpers | controller translation layer (retained) | SCSI request -> verify/online/bio | unit/controller | kernel-only | controller verify/online | SCSI sense/status | unchanged | linked in the new profile; VirtIO block does not require it but `sdvirtio10` references it |
| `sdloop` | `sdloop.c` | legacy `#S/sdctl` config only | legacy-backed, not native | path -> `namec`, backing `Chan`, file read/write | controller/`Chan` | legacy | on `#S` configuration | path/IO errors | deliberately excluded from `pc64onativedisk` | linked proof: no `sdloopifc` in `9pc64onativedisk` |
| `oblockrw`, `oblockflush`, `oblockgptpart`, `oblockopenpart` | `devgefs.c` | `sysovolopen`/`ovolopenblk`, `oblockprobe` | native O storage caller | O block + unit offset -> bytes; PARTUUID -> partition bounds | `Oblock` owns `SDunit` reference until volume close; core owns buffers | kernel-only; partition bounds checked before `sdblockrw` | after `sdunititer`/`sdunitready` in the D2b process | `Eio`, `Enomem`, `no disk has that partition` | unchanged | D2b PARTUUID boots, bounds/negatives |

### Shared implementation, deliberate differences

- Native `sdblockrw` and legacy `sdbio` share the controller `bio` contract, DMA allocation, alignment, and clamps, but **not** the address space: `sdblockrw` takes an absolute unit byte offset; `sdbio` adds `SDpart.start` and enforces the legacy partition qid/version and file permissions. `devgefs.c:oblockrw` enforces the selected GPT partition range before calling the core.
- Native `sdblockflush` and legacy raw `#S/.../raw` both reach `sdrio`, but the native call constructs the `0x35` request directly; the legacy path also exposes raw ATA/SCSI command framing, ownership and permission state.
- `sdunitready` performs the same `online`/partition initialization as opening `#S/.../data`, but returns geometry instead of creating a `Chan`.
- `sdaddfile` keeps controller registration working without `devsd.c`; its `efile[]` entries have no consumer when `#S` is absent.

## 3. Legacy-only `#S` semantics

The following remain deliberately in `devsd.c` and are not replaced by native APIs:

| Legacy operation | Why it stays legacy-only |
| --- | --- |
| `#S` attach/walk/stat | Plan 9 namespace/Qid/Dirtab tree; the O path must not require it |
| `#S/sdXX/open/close` | `Chan` lifetime, `c->aux` unit reference, exclusive raw state |
| `#S/sdXX/data` | Partition-relative `sdbio`, version/change semantics, EOF-vs-error and permissions |
| `#S/sdXX/ctl` | Text control syntax, `part`/`delpart`, `SDifc.rctl/wctl` |
| `#S/sdXX/raw` | Raw ATA/SCSI framing and exclusive open |
| `#S/sdctl` | Top-level controller configuration, `config`/`unconfigure` |
| `#S/sdXX/wstat` | Legacy owner/mode mutation and `iseve` policy |
| `sdloop` | Backed by an inherited `Chan` and `devtab[...]->read/write`; not native |

`sddevtab` is retained in `pc64`, `pc64mp`, `pc64native` and `pc64oconsole`. The generated `devtab[]` for those profiles still contains `&sddevtab`; `pc64oconsole` still contains `&sddevtab` and lacks `&consdevtab`.

## 4. Boot initialization order

The executed order in `sys/src/9/pc64/main.c` is:

```text
machinit/bootinfo/trapinit/ioinit/i8250console
cpuidentify/meminit0/archinit/meminit0/ramdiskinit/confinit/xinit
trapinit/mathinit/i8237alloc/bootfbinit
pcicfginit
bootscreeninit/printinit/cpuidprint/mmuinit/arch->intrinit
bootinforandinit/timersinit/arch->clockenable/bootinfoclock
procinit0/initseg/links
chandevreset()                 <-- all registered Dev reset calls
    sddevtab.reset -> sdreset -> sdinitcontrollers (legacy profiles)
sdinitcontrollers()            <-- direct native owner, guard makes it a no-op
                                 if sdreset already ran
bootmark(BMDevs)
preallocpages/pageinit
onativeprobe_start() / o_user_bootstrap() / userinit()
schedinit()
```

`chandevreset()` is still used by other devices and by the legacy profiles. It is not the native disk owner: `sdinitcontrollers()` is. `pc64onativedisk` has no `sddevtab`, so `chandevreset()` does no disk work there; the direct call performs PCI controller pnp and registry insertion after `pcicfginit`, `xinit` and `arch->intrinit`. These probes allocate with `malloc`/`smalloc` and use `QLock`/`Ref` exactly as the legacy boot did with `up == nil`. `SDifc.verify`/`enable`/`online` are not forced into early boot; `sdunitready` and `sdblockrw` perform those lazily in the D2b process context.

Exactly-once evidence: `sdcore.c` holds `sdinits`/`sdinitialized`; each boot log contains exactly one `sd: controllers initialized (...) native-only` line in the new profile and one `native+legacy` line in legacy profiles.

## 5. `ONATIVE_DISK` profile and linked proof

- Config: `sys/src/9/pc64/pc64onativedisk`; kernel `9pc64onativedisk`.
- Selection: `ONATIVE_DISK=1 tools/build.sh`, `ONATIVE_DISK=1 tools/test-oboot-server.sh`.
- `tools/build.sh` rejects `ONATIVE_DISK=1` combined with `NATIVE_PROBE=1` or `OCONSOLE=1`; `NATIVE_PROBE=1` and `OCONSOLE=1` are already mutually exclusive.
- `dev` section: no `cons`, no `sd`.
- `misc`: `sdiahci`, `sdvirtio10`, `sdnvme`, `sdram`; **no `sdloop`**.
- `tools/port/mkdevc` now emits `sdifc[]` when `nsdifc` is non-zero even if the `sd` Dev is absent. This is required: a controller listed in `misc` is linked, but the generated registry is what makes it probeable.
- `sdcore.$O` is in the unconditional `PORT` list of `sys/src/9/pc64/mkfile`, so it is linked in every `pc64` family profile.

Generated and linked checks (PASS, executed):

```text
docs/KERNEL-OPMAP.json/.md regenerated for the new source split; --check PASS; 29/29 tests PASS
pc64/9pc64:             &consdevtab present, &sddevtab present
pc64oconsole:           &consdevtab absent,  &sddevtab present
pc64onativedisk:        &consdevtab absent,  &sddevtab absent
9pc64onativedisk symbols: sddevtab absent, consdevtab absent, sdloopifc absent;
                          sdinitcontrollers, sdunititer, sdunitready,
                          sdblockrw, sdblockflush, sdrio, sdvirtio10ifc present
```

`tools/sd_migration_check.py` performs the source checks by default and the generated-devtab/Plan-9-symbol checks when given `--profile`, `--devtab` and `--kernel`. It distinguishes `SOURCE`, `DEVTAB` and `KERNEL` lines and fails closed on missing artifacts or malformed Plan 9 a.out files.

Native O call chain (measured D2b):

```text
OVOLOPEN(PARTUUID=...)
  -> devgefs.c:ovolopenblk -> oblockopenpart
  -> sdunititer -> sdunitready -> oblockgptpart
  -> oblockrw/oblockflush -> sdblockrw/sdblockflush
  -> sdrio / SDifc.bio
  -> sdvirtio10 -> QEMU virtio-blk
```

The legacy path still exists in normal kernels:

```text
#S -> sddevtab (sdattach/sdwalk/sdstat/sdopen) -> Chan/Qid
   -> sdread/sdwrite -> sdbio/sdrio -> SDifc
```

The new profile does not resolve `#S` anywhere on the measured O path. `devgefs.c` still contains `namec("#S")`/`namec(dev)` in `scandisks`/`gevolume` for the inherited non-`PARTUUID` GE volume path; D2b passes `PARTUUID=`, so `ovolopenblk` takes the native branch. The `#S/sdF0/data@...` text printed when the volume opens is a human-readable device label built from `unit->name`; it is not a pathname traversal.

## 6. `sdloop` policy

`sdloop` is a virtual disk whose `Ctlr` stores a `Chan *c` opened with `namec(path, ...)` and whose I/O calls the backing file through the inherited `Dev` table. It is not needed by the tested O-partition path and is excluded from `pc64onativedisk`. It remains compiled and registered in `pc64`, `pc64mp`, `pc64native` and `pc64oconsole`.

A future native replacement would need a separately reviewed design for an O-resident byte source: ownership/lifetime of the source, recursion (an O-backed loop disk inside an O volume), commit/version semantics, failure and media-change behavior. E6 does not implement that speculative device.

## 7. Verification record

All commands were run on the E6 working tree and are **agent-executed** unless marked NOT RUN. Logs are copied under `build/verification/e6/` (ignored by Git).

| Gate | Command | Result | Evidence / limits |
| --- | --- | --- | --- |
| A source/registration | `python3 tools/sd_migration_check.py` | PASS | source ownership, configs, `mkdevc` |
| A generated + linked, default | `python3 tools/sd_migration_check.py --profile pc64 --devtab build/verification/e6/default-pc64.devc.c --kernel build/verification/e6/9pc64.default` | PASS | `&sddevtab` registered/linked |
| A generated + linked, E5 | `... --profile pc64oconsole --devtab build/verification/e6/pc64oconsole.devc.c --kernel build/verification/e6/9pc64oconsole` | PASS | no `consdevtab`; `sddevtab` retained |
| A generated + linked, new profile | `... --profile pc64onativedisk --devtab build/verification/e6/pc64onativedisk.devc.c --kernel build/verification/e6/9pc64onativedisk` | PASS | neither `consdevtab` nor `sddevtab`; no `sdloopifc` |
| B operation map | `python3 tools/kernel_opmap.py --write` (reviewed: only source-split changes), `--check`, `python3 tools/test_kernel_opmap.py` | PASS | 29/29 tests; counts in `build/verification/e6/opmap-*.log` |
| B default build | `WHAT=kernel tools/build.sh` | PASS | `9pc64`, `9pc64mp`, loader |
| B E5 build | `OCONSOLE=1 WHAT=kernel tools/build.sh` | PASS | `9pc64oconsole` |
| B native probe build | `NATIVE_PROBE=1 WHAT=kernel tools/build.sh` | PASS | `9pc64native` |
| B new profile build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `9pc64onativedisk` |
| C default O boot | `tools/test-o-boot.sh` | PASS | three same-disk boots, `run() -> 1,2,3`, OID 7, no FS |
| C legacy `#S` control | `tools/test-o-native-generator.sh` (after adding a disposable virtio disk) | PASS | `ONATIVEPROBE: E6 LEGACY #S attach=1 walk=1 stat=52 read=48 inquiry=1`; real `sddevtab` attach/walk/stat/read on `sdF0/ctl` |
| C E5 D2b regression | `OCONSOLE=1 tools/test-oboot-server.sh` | PASS | no-`#c` three-boot persistence and negatives |
| D new-profile D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | three same-disk boots; `run() -> 1,2,3`; OID 7; no panic/fault; missing executable and failing `run()` negatives |
| E native bounds/flush | included in the D2b run with `oblocktest=1;sdflushlog=1;opath=1` | PASS | `in-range-read`, `read-at-end`, `oversized-read-clamped`, `write-past-end`, `sdvirtio: flush PASS` |
| E wrong PARTUUID | included in the D2b run on a same-seed disk with `PARTUUID=000...0000` | PASS | `no disk has that partition`; no volume, no flush, no panic |
| E malformed GPT | included in the D2b run with a second unit whose GPT header has out-of-range entry fields | PASS | `no disk has that partition`; no volume, no panic |
| F review | source + logs | PASS | duplicate-init marker count 1; no reference/lock regression observed in the executed paths |
| Physical AHCI/NVMe | none | **NOT RUN** | only QEMU VirtIO block was exercised; AHCI enumerated the QEMU SATA/IDE disk, NVMe was not probed |
| Legacy `#S` write/control mutation | none | **NOT RUN** | the legacy control is deliberately read-only (`ctl` stat/read); no destructive raw command was issued |
| Whole-kernel Chan independence | none | **NOT RUN** | only the measured O window is claimed |

### Measured path counters

In every positive `pc64onativedisk` D2b boot the instrumented window was:

```text
opath: volopen-enter namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
opath: volopen-opened namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
opath: volopen-started namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-D2B: AFTER-SYSCALLS n=64 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
```

This is a statement about the measured O-volume open/GE-start/64-syscall window only. It does not claim that the linked kernel contains no `Chan` code (`devgefs.c` still contains the inherited non-`PARTUUID` path, and the default profiles retain the complete `#S` adapter).

### Scope limits

- QEMU used disposable raw images only. No host physical disk was written.
- `sdiahci` was compiled/linked and its QEMU controller was enumerated, but no physical AHCI/NVMe hardware test was run.
- The legacy `#S` control is read-only; `#S` write/control mutation, removability, and media-change paths were not exercised after the split.
- The new profile has no legacy shutdown path through `Dev`; controller shutdown was not separately tested.
- `sdram` is linked but has no configured units in these boots.
