# Legacy `Dev` pruning in the O-only `pc64onativedisk` profile (E8)

**Scope:** `sys/src/9/pc64/pc64onativedisk` only, selected by
`ONATIVE_DISK=1`. The other profiles remain unchanged. **Base:** `main`
`1cae94f` (after E6 checkpoints `ad836d7`, `9901fe4`, `22399f3` and
OpenCode completion `0f0a47a`); final implementation SHA `1cd76c8`.
Evidence logs are under `build/verification/e8/` (ignored by Git).

This document is the Stage 1 inventory and the Stage 2 result record. It is
not a claim about whole-kernel `Chan` independence and it does not propose a
replacement native device hierarchy, userspace ABI, native TLS/9P/mount or
capability subsystem.

## Baseline registration inventory

The generated table from the baseline build
(`build/verification/e8/baseline/pc64onativedisk.devc.c`) contains **27**
`Dev` registrations:

```text
root swap arch pnp env pipe proc mnt srv shr dup rtc tls cap kprof fs
ether ip wg draw mouse vga uart usb kbd segment gefs
```

`&consdevtab` (`#c`), `&sddevtab` (`#S`) and `sdloopifc` are **absent** in
the baseline, as E5/E6 require. The config's `dev` section also has 27
entries. `pc64onativedisk` is still the only edited profile.

Boot/initialization facts that apply to every candidate:

- `pc64/main.c` calls `chandevreset()` for every registered `Dev`, then
  calls `sdinitcontrollers()` directly. `chandevreset()` also calls
  `todinit()`.
- The D2b server path (`oboot=server`) does **not** call `chandevinit()`;
  `ouserproc()` calls `consinit()` directly. Therefore a candidate's
  devtab `init` function only runs on the legacy `userinit()`/`init0()`
  path, not in the measured O server.
- Source ownership matters: dropping an entry from the config removes its
  `dev*.c` from `DEVS`. Any symbol from that source still referenced by
  another linked object becomes an unresolved link error. A source file's
  dormant function is not a runtime dependency, but a linked reference is.

## Dependency matrix

Status is the Stage 1 classification. Stage 2 outcomes are recorded below
the matrix.

| Dev | config | devtab symbol | source | reset/init | link dependencies | reachable O-only consumers | legacy-only purpose | Stage 1 status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `#k` | `fs` | `fsdevtab` | `sys/src/9/port/devfs.c` | `devreset` (no-op), `devinit` (no-op) | none outside the file; function names are file-local consumers of `Dev`/`Chan` and `namec` for inner legacy devices | none in the measured D2b window | disk mirror/cat/inter/part/crypt configuration through `#k/fs` | `REMOVABLE` |
| `#a` | `tls` | `tlsdevtab` | `sys/src/9/port/devtls.c` | `devreset` (no-op), `tlsinit` (not called on O server) | none outside the file | none in the measured D2b window | `Chan`-based TLS record device | `REMOVABLE` |
| `#K` | `kprof` | `kprofdevtab` | `sys/src/9/port/devkprof.c` | `devreset` (no-op), `kprofinit` sets the global `kproftimer` hook (not called on O server) | no call to a devkprof symbol outside the file; `portclock.c` only tests `kproftimer != nil` and the pointer remains nil without `kprofinit` | none in the measured D2b window | file-oriented kernel profiling | `REMOVABLE` |
| `#d` | `dup` | `dupdevtab` | `sys/src/9/port/devdup.c` | `devreset`/`devinit` no-op | none outside the file | none in the measured D2b window | descriptor-as-directory view | `REMOVABLE` |
| `#M` | `mnt` | `mntdevtab` | `sys/src/9/port/devmnt.c` | `mntreset` calls `cinit()`; `devinit` no-op | **blocked:** `cache.c` references `mntrahinit`/`mntrahread`; `auth.c` references `mntversion`/`mntauth`; `sysfile.c` and `devgefs.c` reference `mntattach` | none in the measured D2b window, but the symbol owners are linked | 9P mount/namespace adapter and shared RPC/read-ahead helpers | `BLOCKED` |
| `#s` | `srv` | `srvdevtab` | `sys/src/9/port/devsrv.c` | `devreset` no-op; `srvinit` not called on O server | **blocked:** `auth.c:143` always calls `srvrenameuser` from `hostownerwrite` | none in the measured D2b window | publish `Chan` service endpoints in a namespace | `BLOCKED` |
| `#σ` | `shr` | `shrdevtab` | `sys/src/9/port/devshr.c` | `devreset` no-op; `shrinit` not called on O server | **blocked:** `auth.c:144` always calls `shrrenameuser`; the file also references `mntattach` | none in the measured D2b window | shared inherited mount namespaces | `BLOCKED` |
| `#g` | `segment` | `segmentdevtab` | `sys/src/9/port/devsegment.c` | `devreset` no-op; `segmentinit` only assigns `_globalsegattach` (not called on O server) | no link dependency: `segment.c` defines `_globalsegattach` itself and uses a nil check (`segment.c:770`); the hook simply stays nil | none in the measured D2b window | `#g` file interface for global segments; not the `Segment` VM structures or executable loader | `REMOVABLE` |
| `#¤` | `cap` | `capdevtab` | `sys/src/9/port/devcap.c` | `devreset`/`devinit` no-op | none outside the file; capability helpers are file-local consumers of the `#¤` adapter | none in the measured D2b window | inherited capability text interface | `REMOVABLE` |

### Notes on the blocked cases

- `mnt` is not merely a namespace wrapper in this tree. `cache.c` directly
  declares and calls `mntrahinit`/`mntrahread`, and the mount/auth syscall
  paths call `mntattach`/`mntversion`/`mntauth`. Removing `devmnt.c` while
  keeping `cache.c`, `auth.c`, `sysfile.c` and `devgefs.c` linked causes
  unresolved symbols. Extracting those helpers is a separate, larger
  refactor, which E8 deliberately does not attempt.
- `srv` and `shr` are blocked by `hostownerwrite()` in `auth.c`, which
  unconditionally calls both rename helpers. Those helpers are also used to
  keep existing service/mount ownership consistent after a host-owner
  change. A config-only removal would break the link; a guarded no-op or
  extraction would be a behavioral change, not pruning.

## Stage 2 procedure

For each accepted candidate, only its line was removed from the `dev`
section of `sys/src/9/pc64/pc64onativedisk`. After each edit:

1. `ONATIVE_DISK=1 WHAT=kernel tools/build.sh`
2. inspect the newly generated `build/amd64/pc64onativedisk.devc.c` and
   the linked `build/amd64/9pc64onativedisk` symbol table;
3. `ONATIVE_DISK=1 tools/test-oboot-server.sh`;
4. keep the edit only if link proof and the complete three-boot D2b run
   pass. Otherwise revert only that line and record the exact failure.

Logs and binary/symbol evidence are copied to
`build/verification/e8/<candidate>/`. The final section records the
combined result and the legacy-profile control.

## Stage 2 results and final registration inventory

_Updated as the bounded removals are executed; see below._

## Stage 2 results

| Candidate | Result | Registration count | Concrete evidence |
| --- | --- | --- | --- |
| `kprof` (`#K`) | **PASS (removed, linked and runtime-verified)** | 27 -> 26 | build PASS; `kprofdevtab`/`_kproftimer` absent, `kproftimer` hook present but unassigned; D2b PASS |
| `dup` (`#d`) | **PASS (removed, linked and runtime-verified)** | 26 -> 25 | build PASS; `dupdevtab` and `dup*` adapter symbols absent; D2b PASS |
| `fs` (`#k`) | **PASS (removed, linked and runtime-verified)** | 25 -> 24 | build PASS; `fsdevtab`/`mattach`/`mconfig` absent; D2b PASS |
| `tls` (`#a`) | **PASS (removed, linked and runtime-verified)** | 24 -> 23 | build PASS; `tlsdevtab`/`tlsinit`/`newtls` absent; D2b PASS |
| `segment` (`#g`) | **PASS (removed, linked and runtime-verified)** | 23 -> 22 | build PASS; `segmentdevtab` absent while `newseg`/`segattach`/`_globalsegattach` remain; D2b PASS |
| `cap` (`#¤`) | **PASS (removed, linked and runtime-verified)** | 22 -> 21 | build PASS; `capdevtab`/`cap*` helpers absent; D2b PASS |
| `srv` (`#s`) | **BLOCKED (kept)** | 21 | config-only removal fails link: `hostownerwrite: undefined: srvrenameuser in hostownerwrite` |
| `shr` (`#σ`) | **BLOCKED (kept)** | 21 | config-only removal fails link: `hostownerwrite: undefined: shrrenameuser in hostownerwrite` |
| `mnt` (`#M`) | **BLOCKED (kept)** | 21 | config-only removal fails link: `shrwrite: undefined: mntattach`, `sysfversion: undefined: mntversion`, `sysfauth: undefined: mntauth`, `copen: undefined: mntrahinit`, `cread: undefined: mntrahread`, `chanfree: undefined: muxclose` |

The three blocked candidates were tried one at a time against the then
known-good combined config and reverted immediately after the recorded
link failure. They were never combined with a failing tree, and no source
file, `misc`/`link` section or other profile was changed to force them.

## Final combined profile

After the six accepted removals, a fresh `ONATIVE_DISK=1 WHAT=kernel
tools/build.sh` and a fresh `ONATIVE_DISK=1 tools/test-oboot-server.sh`
were run on the combined configuration (not inferred from the individual
runs). Both passed.

Final generated `devtab[]` count: **21**.

```text
root swap arch pnp env pipe proc mnt srv shr rtc ether ip wg draw mouse
vga uart usb kbd gefs
```

Removed from this profile: `kprof dup fs tls segment cap`.
Still registered: `mnt srv shr` (the blocked cases) and all unlisted
legacy and native/GE/O drivers. `consdevtab`, `sddevtab` and `sdloopifc`
remain absent. The native SD/O symbols remain linked:
`sdinitcontrollers`, `sdunititer`, `sdunitready`, `sdblockrw`,
`sdblockflush`, `sdrio`, `sdvirtio10ifc`, `oblockopenpart`, `oblockrw`,
`oblockflush`.

### Executed commands

```sh
ONATIVE_DISK=1 WHAT=kernel tools/build.sh          # baseline and every candidate
ONATIVE_DISK=1 tools/test-oboot-server.sh          # baseline, every accepted candidate, final
WHAT=kernel tools/build.sh                         # legacy control
tools/test-o-boot.sh                               # legacy/default O boot control
python3 tools/sd_migration_check.py
python3 tools/sd_migration_check.py --profile pc64onativedisk \
  --devtab build/verification/e8/final/pc64onativedisk.devc.c \
  --kernel build/verification/e8/final/9pc64onativedisk
python3 tools/kernel_opmap.py --write              # reviewed: E8 config + E6.3 sdcore record
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py                 # 29/29
```

The D2b runs preserved the existing gates without weakening markers:
three boots on one disposable image, `run() -> 1,2,3`, the OID 7
Counter/alias identity, flush, native bounds, wrong-PARTUUID and
malformed-GPT negatives, and the measured
`namec=newchan=walk=devwalk=mount=exec=0` windows.

## Legacy profile control

`WHAT=kernel tools/build.sh` passed for `pc64` and `pc64mp`.
`tools/test-o-boot.sh` passed (three same-disk O boots, `run() -> 1,2,3`,
Counter OID 7). The linked default `9pc64` and `9pc64mp` still contain
`fsdevtab`, `tlsdevtab`, `kprofdevtab`, `dupdevtab`, `mntdevtab`,
`srvdevtab`, `shrdevtab`, `segmentdevtab` and `capdevtab`; they also
retain `consdevtab` and `sddevtab`.

## Generated operation map

`python3 tools/kernel_opmap.py --check` was stale at the end because the
generated `docs/KERNEL-OPMAP.*` did not yet include this profile's
accepted removals (and still lacked the E6.3 `sdcore.c` arm64 record).
The regenerated diff was reviewed: the only changes are the six removed
`pc64onativedisk` registration references, that profile's active-file
count, the missing `sdcore` arm64 record, and the source fingerprint.
The subsequent `--check` passes and `tools/test_kernel_opmap.py` is
29/29.

## Evidence and limits

Per-candidate logs, generated `devc.c`, linked kernels and D2b boot logs
are under `build/verification/e8/<candidate>/`; baseline and final
combined evidence are under `build/verification/e8/baseline/` and
`build/verification/e8/final/`. These are ignored by Git.

Only QEMU VirtIO was used for runtime I/O. No physical AHCI/NVMe test was
run. The blocked candidates were not converted to native services, and no
new userspace ABI, generic native device hierarchy, TLS/9P/mount or
capability subsystem was introduced. The claim is limited to this opt-in
server profile and the measured boot windows; the default/legacy
profiles keep the full legacy `Dev` set.
