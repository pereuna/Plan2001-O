# E9.1–E9.2: legacy host-owner ownership split and `srv`/`shr` pruning

**Scope:** amd64 `pc64` family; implementation changes only in
`sys/src/9/port/auth.c`, `sys/src/9/port/devcons.c`, the OMAP reviewed
binding file, and `sys/src/9/pc64/pc64onativedisk`. E9.3 is a separate
documentation-only stage. No E7 branch or network source was touched.

**Base:** `main` at `772d195` (assignment) / implementation before E9
`c7d5498^` = `772d195`. Evidence logs: `build/verification/e9/` (ignored
by Git).

## E9.0 baseline

- Generated `devtab[]` count: **21**.
- Registrations: `root swap arch pnp env pipe proc mnt srv shr rtc ether
  ip wg draw mouse vga uart usb kbd gefs`.
- `consdevtab`, `sddevtab`, `sdloopifc` absent.
- Baseline `ONATIVE_DISK=1 WHAT=kernel tools/build.sh`: PASS.
- Baseline `ONATIVE_DISK=1 tools/test-oboot-server.sh`: PASS, including
  the three-boot D2b image identity, Counter OID/alias 7, native SD
  flush/bounds and all negatives.
- Baseline linked symbols: `hostownerwrite`, `srvdevtab`,
  `srvrenameuser`, `shrdevtab`, `shrrenameuser`, `mntdevtab` present.

### Concrete reference audit

The repository-wide audit found these definitions and call sites:

| Symbol | Definition | Callers / references |
| --- | --- | --- |
| `hostownerwrite` | `auth.c` before E9 | only `devcons.c` `Qhostowner` write |
| `srvrenameuser` | `devsrv.c` | only `hostownerwrite` |
| `shrrenameuser` | `devshr.c` | only `hostownerwrite` |
| `hostdomainwrite` | `auth.c` | only `devcons.c` `Qhostdomain` write |
| `userwrite` | `auth.c` | only `devcons.c` `Quser` write |
| `renameuser`, `procsetuser` | `proc.c` | remain shared process-identity helpers |

No function-pointer or indirect reference to `hostownerwrite`,
`srvrenameuser` or `shrrenameuser` exists in the linked kernel sources.
The `Dev` callbacks in `devsrv.c`/`devshr.c` have no non-Dev callers;
their only externally visible symbols are the two rename helpers. The
`#s`/`#σ` namespace adapters are therefore link dependencies of the
legacy `#c` host-owner operation, not of the O D2b server path.

## E9.1 — move `hostownerwrite` to its legacy owner

The complete function body and its call sequence were moved unchanged
from `auth.c` to `devcons.c`, next to `Qhostowner`, with a comment
explaining the ownership boundary. No authorization, validation order,
copy/NUL, rename propagation, `eve` update, `procsetuser` call or return
value changed. `hostdomainwrite` and `userwrite` stayed in `auth.c`;
`renameuser`/`procsetuser` stayed in `proc.c`.

The public prototype remains in `portfns.h`; only the definition owner
changed. `devcons.c` is linked by the profiles that register the `cons`
Dev (`pc64`, `pc64mp`, `pc64native`), so `Qhostowner` still reaches
exactly one implementation there.

Verified after the move, before any `Dev` removal:

- `WHAT=kernel tools/build.sh` PASS (`9pc64`, `9pc64mp`).
- `9pc64`/`9pc64mp` link one `hostownerwrite` definition; linked symbols
  still contain `hostownerwrite`, `srvrenameuser`, `shrrenameuser`,
  `srvdevtab`, `shrdevtab`, `consdevtab` and `sddevtab`.
- `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` PASS.
- The linked `9pc64onativedisk` no longer contains `hostownerwrite`
  (the `cons` Dev and therefore `devcons.c` are absent), even though
  `auth.c` is still linked.
- `ONATIVE_DISK=1 tools/test-oboot-server.sh` PASS before pruning.

Runtime write coverage for `hostownerwrite` (authorized/unauthorized
write, size errors, namespace propagation) is **NOT RUN**: the existing
legacy tests only read `/dev/hostowner`; adding a write test would alter
the disposable kernel's host owner and was outside this bounded change.
The claim is source-equivalence plus build/link proof, not runtime
exercise of that legacy operation.

## E9.2 — prune `srv`, then `shr`

Each removal was made alone in `sys/src/9/pc64/pc64onativedisk`, then the
kernel was rebuilt, its generated `devtab[]` and linked symbols inspected,
and the complete D2b gate run on the exact new binary.

| Step | Devtab count | Generated table | Linked symbol evidence | D2b |
| --- | --- | --- | --- | --- |
| remove `srv` | 21 -> 20 | `&srvdevtab` absent; `&shrdevtab` still present | `srvdevtab`, `srvinit`, `srvattach`, `srvwalk`, `srvstat`, `srvopen`, `srvcreate`, `srvremove`, `srvwstat`, `srvclose`, `srvread`, `srvwrite`, `srvrenameuser` absent; `shr*`, `mnt*` present | PASS |
| remove `shr` | 20 -> 19 | `&shrdevtab` absent; `&srvdevtab` absent | `shrdevtab`, `shrinit`, `shrattach`, `shrwalk`, `shrstat`, `shropen`, `shrcreate`, `shrremove`, `shrwstat`, `shrclose`, `shrread`, `shrwrite`, `shrrenameuser` absent; `mntdevtab`/`mntattach` present | PASS |

Final combined profile (19 registrations):

```text
root swap arch pnp env pipe proc mnt rtc ether ip wg draw mouse vga
uart usb kbd gefs
```

`consdevtab`, `sddevtab` and `sdloopifc` remain absent. `mnt` remains as
required. `hostownerwrite`, `srvdevtab`, `srvrenameuser`, `shrdevtab` and
`shrrenameuser` are absent from the linked final O-only kernel. The
native SD/O symbols (`sdinitcontrollers`, `sdunititer`, `sdunitready`,
`sdblockrw`, `sdblockflush`, `sdrio`, `sdvirtio10ifc`,
`oblockopenpart`) remain present.

## Verification matrix

| Gate | Command | Result | Evidence |
| --- | --- | --- | --- |
| Baseline native build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `e9/baseline/build.log` |
| Baseline native D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | `e9/baseline/test-oboot-server.log` |
| E9.1 legacy build | `WHAT=kernel tools/build.sh` | PASS | `e9/e91/build-default.log` |
| E9.1 native build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `e9/e91/build-onative.log` |
| E9.1 native D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | `e9/e91/test-oboot-server.log` |
| `srv` removal build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `e9/srv/build.log` |
| `srv` removal D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | `e9/srv/test-oboot-server.log` |
| `shr` removal build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `e9/shr/build.log` |
| `shr` removal D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | `e9/shr/test-oboot-server.log` |
| Final combined native build | `ONATIVE_DISK=1 WHAT=kernel tools/build.sh` | PASS | `e9/final/build-onative.log` |
| Final combined D2b | `ONATIVE_DISK=1 tools/test-oboot-server.sh` | PASS | `e9/final/test-oboot-server.log` |
| Legacy control build | `WHAT=kernel tools/build.sh` | PASS | `e9/build-default.log` |
| Legacy O boot | `tools/test-o-boot.sh` | PASS | `e9/final/test-o-boot.log` |
| E5 console profile build | `OCONSOLE=1 WHAT=kernel tools/build.sh` | PASS | `e9/build-oconsole.log` |
| SD ownership/registration | `python3 tools/sd_migration_check.py` | PASS | `e9/sd-source-check.log` |
| SD linked proof | `python3 tools/sd_migration_check.py --profile pc64onativedisk --devtab build/verification/e9/final/pc64onativedisk.devc.c --kernel build/verification/e9/final/9pc64onativedisk` | PASS | `e9/final/sd-linked-check.log` |
| OMAP check | `python3 tools/kernel_opmap.py --check` | PASS | `e9/final/opmap-check.log` |
| OMAP tests | `python3 tools/test_kernel_opmap.py` | 29/29 PASS | `e9/opmap-tests-after-binding.log` |

Every positive D2b run booted one disposable O disk three times with
`run() -> 1,2,3`, stable Counter OID/alias 7, the expected commit
versions, native SD initialization once, `sdvirtio: flush PASS`,
`oblocktest` bounds, clean failing-`run()`/missing-executable negatives,
wrong-PARTUUID and malformed-GPT negatives, no panic/fault, and the
established zero `namec/newchan/walk/devwalk/mount/exec` counters in the
measured windows. No marker was widened or weakened.

Legacy control: `9pc64` and `9pc64mp` still link `hostownerwrite`,
`srvrenameuser`, `shrrenameuser`, `srvdevtab`, `shrdevtab`,
`mntdevtab`, `consdevtab` and `sddevtab`. `9pc64oconsole` has no
`consdevtab`/`hostownerwrite` but keeps `srv`/`shr`/`sd` registrations.

## OMAP reviewed binding

Moving the function changes the `devcons.c` source hash and the OMAP
function record. The generated `docs/KERNEL-OPMAP.*` was regenerated and
the diff reviewed: it removes `devsrv.c`/`devshr.c` from the
`pc64onativedisk` active set, updates the two registration rows, moves
the `hostownerwrite` function record from `auth.c` to `devcons.c`, and
updates the profile/source fingerprints. It does not import E7 files.

`tools/kernel_opmap.py` now carries the new reviewed `devcons.c` SHA in
`NATIVE_REVIEWED_BINDINGS` and appends it to the historical
`E3_PINNED_SHA` set; the old hashes remain for historical fixtures. All
29 OMAP tests pass after this reviewed update.

## Limitations / follow-up

- `mnt` remains out of scope; its `mntattach`/`mntversion`/`mntauth`/
  `mntrah*`/`muxclose` dependencies need a separate task.
- No runtime write test for `hostownerwrite` was added (NOT RUN).
- Only QEMU VirtIO block I/O was exercised; physical AHCI/NVMe was not.
- No userspace ABI, OID/Space/on-disk format, MicroPython persistence,
  network code, generic device abstraction or physical disk was changed.
