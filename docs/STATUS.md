# Implementation status — Plan2001-O

**Status date:** 22 October 2026. **Current runtime evidence baseline:**
`main` at `122e585a172f39bdc1fb31eca79841acfe2e6d27` plus the uncommitted
working-tree changes of the native O MicroPython experiment below; the
previous clean-tree baseline was `4678fada0d66f83b310291320e57aba12068934d`.
Original imported source: `pereuna/Plan2001`, branch `poc-o-only`,
commit `436ed30c894c4060638341ecebe82004d457f496`
(20 October 2026); imported without its Git ancestry.

This document is the **single source of truth for current verification**.
The architecture is in [README.md](../README.md), past source-branch
experiments in [POC.md](POC.md), and the implemented on-disk contract in
[O-FORMAT.md](O-FORMAT.md).

## Evidence levels

| Level | Current evidence |
| --- | --- |
| **Implemented** | The imported source contains GE/O O-profile volumes, versioned `(SpaceID, OID)` objects, the native O syscall boundary with process-owned O Space handle tables, a bounded native executable-object path with bounded argv, an O-resident Environment and `.mpy` loader, and a persistent MicroPython `init` Space. A dedicated test configuration boots the real MicroPython executable from an O object. |
| **Demonstrated in the source branch** | Five reported GE/O QEMU regression gates, including three boots of one ESP + O image with counter `1 -> 2 -> 3` and preserved Counter OID/alias. See [POC.md](POC.md). |
| **Statically verified in Plan2001-O** | Documentation references and repository metadata checked at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`; details below. |
| **Runtime verified in Plan2001-O** | **PASS:** the full amd64 build, both kernels, selfroot, the five existing O-only gates, the process-local handle regression, the native executable-object regression and the new O-loaded MicroPython gate passed on 22 October 2026 with KVM. The earlier clean-tree run was at `4678fad`; the O-loaded MicroPython run used HEAD `122e585` plus the uncommitted working tree. See the records below and `build/verification/*.log`. |
| **Proposed, not implemented** | Native GE/O relationship indexes/edges, per-Python-object O records, general native executable-object loading (catalog, architecture selection, dynamic linking), general persistent namespaces, object IPC and a remote protocol. |

Never promote source inspection or a successful source-branch test into
a **current-repository runtime PASS**. A missing result is **NOT RUN**,
not PASS and not FAIL.

## Phase C validation record

### Static audit — 21 October 2026

**Checked:** 21 October 2026 against the Phase B commit
`5413fc6a1e801f377cd3f428336b3543d7ddf83d`.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| GitHub source and document availability | **PASS (static)** | `README.md`, `AGENTS.md`, `docs/POC.md`, `docs/STATUS.md` and `docs/O-FORMAT.md` were read from the repository. |
| Documentation navigation | **PASS (static)** | 21 relative Markdown links and 32 backtick-formatted source/tool/document path references in those five Markdown files resolved to entries in the repository tree at the checked commit. This is **not** an exhaustive scan of all inherited source comments. |
| Phase B file metadata | **PASS (static)** | Git trees before/after Phase B were compared; the 22 modified executable tool files retained executable mode, and no tracked file's mode changed. |
| Build dependency review | **PASS (source inspection)** | `WHAT=all tools/build.sh` produces the root binaries used by `tools/selfroot build/selfroot`. `WHAT=kernel` alone does **not** prepare `build/selfroot/amd64/bin/gefs` or `micropython`. |

### Runtime execution — 22 October 2026

**Executed:** 22 October 2026 against
`f23d5624a153bd3645be8f8b540b3bc243ebabec` on a Debian/amd64 host with
accessible `/dev/kvm`, QEMU, OVMF and mtools. The existing prepared
9front `base.qcow2` was reused by `tools/vm-setup`.
Gate start times (UTC, recorded in `build/verification/*.timestamp`):
GE 15:11:44, O volume 15:12:23, O objects 15:13:26, Python/O 15:13:56,
O init 15:14:31.

| Check | Result | Evidence |
| --- | --- | --- |
| Host/tooling and KVM | **PASS** | `tools/vm-setup` found the prepared base image; its package, OVMF and `/dev/kvm` checks passed. The five gates ran with the target's `-accel kvm -cpu host`. `build/verification/vm-setup.log` |
| Full amd64 build | **PASS** | `WHAT=all tools/build.sh` exited 0 and printed `BUILD-DONE`; `build/amd64/9pc64`, `bootx64.efi`, `gefs` and `micropython` were present. `build/verification/build.log`, `build/amd64/session.log` |
| selfroot preparation | **PASS** | `ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot` exited 0. The generated clone's origin is `https://github.com/pereuna/Plan2001-O.git`; its HEAD is `f23d562`, and the expected `amd64/bin/gefs` and `amd64/bin/micropython` are executable. `build/verification/selfroot.log` |
| GE gate | **PASS** | `tools/test-ge.sh` exited 0: `PASS: GE volume, raw key/value, no FS`; raw value crossed reboot (0 → 1 → 2). `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile gate | **PASS** | `tools/test-o-volume.sh` exited 0: `PASS: O volume, no FS`; the O volume persisted 0 → 1 → 2 and wrong-profile opens were rejected. `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects gate | **PASS** | `tools/test-o-objects.sh` exited 0: `PASS: native O objects, no FS`; both OIDs were restored on the second boot. `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O gate | **PASS** | `tools/test-o-space.sh` exited 0: `PASS: Stage 4 Environment, code and Space graph from O (no FS)`; boot 2 restored the graph (41 → 42), same alias/OID, and committed version 2. `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init gate | **PASS** | `tools/test-o-boot.sh` exited 0: `PASS: three O-only boots, persistent Counter and run() from O (no FS)`; one disk, `run()` returned 1, 2, 3, Counter OID stayed 7, no root FS mount. `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log` |

The `test-o-space` serial log also contains
`panic: boot process died: unknown` after each
`space: O: committed init version N` line. The gate's required
assertions and exit status are **PASS**; this shutdown-path diagnostic
is recorded as an observation and was not used to change the gate or
the specification.

## Process-local O handle experiment — 22 October 2026

**Source state:** this experiment is committed as
`30e9ae16c0b7ab82fcc6404cdffddbbb246c8ebd`. The results below were
first run from its working tree before that commit; the same handle
regression was rerun in the final native-exec suite recorded below.

**Design:** each `Proc` owns an opaque eight-entry table of `Ohand`
sessions. An entry holds an `Ospace *` and a `Ref`. Table lookup takes a
temporary reference under the table lock, then releases the lock before
calling storage. Explicit close removes the entry under the lock and
drops the ownership reference; the last reference calls
`onativeclose()`/`ospaceclose()`, which aborts an unfinished transaction
and never commits. Process exit and successful `exec` detach all entries
under the lock, then release sessions outside it. Failed `exec` does not
call the cleanup hook. Children start empty, including `RFMEM` children.
The global volume instance and volume authorization are unchanged.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 114 programs; kernel and loader present. `build/verification/build-ohandles.log` |
| selfroot binaries | **PASS** | `build/selfroot/amd64/bin/{gefs,ohandle}` present and executable. `build/verification/selfroot-ohandles.log` |
| Process-local O handles | **PASS** | one ESP + O boot, no FS root; isolation, independent sessions, explicit-close and exit capacity, abort on close/exit, successful/failed `exec`, and invalid/double close. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC): process-local handles 15:35:46,
GE 15:36:19, O volume 15:36:30, O objects 15:37:31, Python/O 15:37:58,
O init 15:38:29.

## Native executable-object experiment — 22 October 2026

**Source state:** clean tree at
`4678fada0d66f83b310291320e57aba12068934d`. This commit fixes the two
review findings against `ab3a77e`: the exec stack now reserves
`sizeof(Tos)` before placing `argv` and its strings, and segment
addresses (`abss`/`ebss`) remain `uintptr` through both loader paths.
The target now asserts `argv[0]`, intact `Tos` fields and a high BSS
page; host seeding enlarges the target's BSS header to `0xffffffff` so
the BSS extent crosses 4 GiB. This STATUS update is a docs-only follow-up
commit.

**Loader:** `OEXECUTE`/`oexecute(space, oid)` resolves the handle only in
the calling process, retains its session reference for one bounded
whole-object read (`Objexecmax` = 8 MiB, a single published version),
then releases the reference before parsing. `execparse` is shared with
`sys_exec` and validates the amd64 a.out magic, header length,
text/data/bss arithmetic and bounds, object length, entry point and
user-address limits. `execo` builds ordinary text/data/BSS segments from
the object bytes, then uses the shared `execcommit` process-transition
path (segments, stack, close-on-exec handles, text/args, notes, MMU
flush). Failure before commit leaves the old image and handles intact;
there is no pathname, `Chan`, `Fid`, Qid, mount or 9P step.

The target program `ohello` exists only as an O object. `/boot/oexec`
is an embedded regression harness (test bootstrap, not the loader).
`tools/mkovol` seeds the target at `OID_EXEC_TEST` and malformed bytes
at `OID_BADEXEC_TEST` through the existing `-i` seed layout.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
NATIVEEXEC=build/selfroot/amd64/bin/ohello \
  tools/mkovol build/amd64/oexec-o.img 192 tools/odemo.py
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 116 programs; kernel and loader present. `build/verification/build-bssboundary.log` |
| selfroot binaries | **PASS** | `gefs`, `ohello`, `oexec` built; selfroot at `4678fad`. `build/verification/selfroot-bssboundary.log` |
| Native executable object | **PASS** | one ESP + O boot, no FS root; child loaded `ohello` by OID, checked `argv[0]`, intact `Tos` fields and a BSS page beyond 4 GiB, printed both target markers, exited 0, parent observed success; missing OID and a truncated valid header failed while the handle remained usable; close-on-exec handle rule held. `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| Process-local O handles | **PASS** | all isolation, lifetime, abort, exec and error checks. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC, clean tree at `4678fad`): native executable
16:50:09, process-local handles 16:50:33, GE 16:50:56, O volume
16:51:07, O objects 16:52:07, Python/O 16:52:35, O init 16:53:05. The
binary-grep false positive in `test-o-boot.sh` remains fixed; no
assertion was weakened.

## Native O MicroPython experiment — 22 October 2026

**Source state:** HEAD `122e585a172f39bdc1fb31eca79841acfe2e6d27`, with
this experiment's source changes in an **uncommitted working tree**. The
binaries and images below were built from that tree; this record is not
a claim about a clean committed revision. The previous native-executable
results above are unchanged history.

**Implemented:** `oexecute(space, oid, argv, argc)` passes a bounded,
validated argument vector, copies the strings to kernel-owned memory
before the process image is replaced, and places `Tos`, strings and argv
on the exec stack without overlap. The native loader marks its
image-less text/data/BSS/stack segments `SG_NOSWAP`, and `dupseg()`
accepts a data segment with no file image, so `rfork` and the page
reclaimer do not treat the O-loaded bytes as file-backed pages. The
small embedded `/boot/oinit` harness opens the O volume and `init` Space
and executes `OID_MP_EXEC` (`0x4f45584543000003`), passing the argv that
`sys/src/cmd/micropython/main.c` requires. The dedicated `pc64omp`
kernel configuration embeds only `oinit` and `kbdfs`; the ordinary
`pc64` configuration still embeds `/boot/mp`.

The seed builder in `sys/src/cmd/gefs/ream.c` now builds a normal
multi-level GE tree from the sorted seed records, so a large executable
is not limited to one catalog leaf. `tools/mkovol MPEXEC=FILE` seeds the
real MicroPython executable **byte for byte**; `tools/oseed.py` reads
the prepared copy back, and `/boot/oinit` prints the SHA-256 of the
object read from O. The BSS-header patch remains confined to the
`NATIVEEXEC`/`ohello` fixture.

**Object and limits:** MicroPython 2,191,593 bytes, SHA-256
`1487111f358ac845db3ca2b9485a561e722675c59c0632ca105ddd02c13b7e53`;
`oinit` 76,349 bytes, SHA-256
`70b4d0050606507fa46e3f215e6f017e2f36e096083a25154c5656d677fa3f18`.
`Objexecmax` remains 8 MiB. The test O image is 192 MiB; no disk-format
revision was added.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-boot-omp.sh
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build, both kernels | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `8df642b1daaccaa2c539005a4aaa30e0`, `build/amd64/9pc64omp` md5 `aa1a3ae158a6809bcf7254c1edbe366c`. `build/verification/build-omp.log` |
| selfroot | **PASS** | `build/selfroot` at HEAD `122e585`; `oinit`, `gefs` and `micropython` present. `build/verification/selfroot-omp.log` |
| Generated boot contents | **PASS** | `build/amd64/pc64omp.rootc.c` has no `addbootfile("mp"` and has `oinit`/`kbdfs`; `build/amd64/pc64.rootc.c` still has `mp`. Asserted by the new gate. |
| MicroPython from native O | **PASS** | one ESP + O disk, no FS root, dedicated `9pc64omp`; three boots of the same disk: `run()` 1 -> 2 -> 3, Counter OID/alias 7/7, object SHA-256 equals the host binary; REPL evaluated `OINIT-REPL 42`; missing/malformed objects returned errors with the O handle preserved. `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl.log`, `build/amd64/ompbootvm/check.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`; argv/Tos/BSS and rollback assertions. `build/verification/test-o-exec-omp.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-omp.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and embedded O init all exited 0. `build/verification/test-ge-omp.log`, `test-o-volume-omp.log`, `test-o-objects-omp.log`, `test-o-space-omp.log`, `test-o-boot-embedded.log` |

Log timestamps (UTC, completion of each log write): build and selfroot
19:10:25; O-loaded MicroPython 19:11:15; native executable 19:11:43;
handles 19:12:05; GE 19:12:16; O volume 19:13:16; O objects 19:13:44;
Python/O 19:14:15; embedded O init 19:14:49. The documented
`test-o-space` shutdown diagnostic (`panic: boot process died: unknown`)
is unchanged and is not a gate failure.

**Remaining limits:** the O-loaded path is demonstrated only by the
dedicated `pc64omp` test configuration and documented OID. The ordinary
`pc64` boot still embeds MicroPython through `devroot`; `kbdfs` and the
small `oinit` harness are still embedded. There is no program catalog,
architecture selection, dynamic linking, permissions framework, or
general executable-object format support. The on-disk format is
unchanged.

## Reproduction on a prepared Debian/amd64 host

Run from the repository root with a **committed, clean source tree**.
Verify `git status --short` and record `git rev-parse HEAD` first:
`tools/overlay` can include working-tree files, whereas
`tools/selfroot` clones **committed HEAD**, so testing uncommitted
sources risks mixing incompatible binaries and code.

`tools/vm-setup` checks Debian packages, OVMF, the selected VM
accelerator and a pinned 9front bootstrap image. The **O-only QEMU suite
(five existing gates plus the handle regression) currently expects KVM**: `tools/targets/amd64` supplies
`-accel kvm -cpu host` directly to those guest invocations.
`VM_ACCEL=tcg` is supported by the bootstrap `tools/vm` path, but it
does **not** automatically switch these standalone gate scripts to TCG.
Use a host with accessible `/dev/kvm` for the commands below.

```bash
set -euo pipefail
mkdir -p build/verification
git rev-parse HEAD | tee build/verification/commit.txt
git status --short

tools/vm-setup 2>&1 | tee build/verification/vm-setup.log
WHAT=all tools/build.sh 2>&1 | tee build/verification/build.log

# Work around tools/selfroot's inherited Plan2001 origin default
# until that separate functional cleanup is made.
ORIGIN=https://github.com/pereuna/Plan2001-O.git \
  tools/selfroot build/selfroot 2>&1 | tee build/verification/selfroot.log

test -s build/amd64/9pc64
test -s build/amd64/9pc64omp
test -s build/amd64/bootx64.efi
test -x build/selfroot/amd64/bin/gefs
test -x build/selfroot/amd64/bin/micropython
test -x build/selfroot/amd64/bin/ohandle
test -x build/selfroot/amd64/bin/oexec
test -x build/selfroot/amd64/bin/ohello
test -x build/selfroot/amd64/bin/oinit

for gate in test-o-boot-omp test-o-exec test-o-handles test-ge test-o-volume test-o-objects test-o-space test-o-boot; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate.log"
done
```

**Safety:** these scripts create, overwrite or reformat disposable
images under `build/`. Run them in a dedicated development checkout;
**never substitute a real disk or partition**. Do not use
`tools/selfroot -p DEV`, `dd` to block devices or `tools/mkovol`
on a real device as a regression shortcut. Build scripts may require
significant free space for the VM and disk images.

`set -euo pipefail` makes a failed build, precondition or QEMU gate
stop the sequence; `tee` saves the output and does not conceal a
nonzero exit status. **A test's name or log-file existence is not
evidence of PASS.**

## Runtime gate acceptance and logs

| Gate | Required check | Main outputs |
| --- | --- | --- |
| Build | Exit 0, `BUILD-DONE` in the build session, ordinary and `pc64omp` kernels + UEFI loader + `gefs` + MicroPython + `ohandle` + `oexec`/`ohello`/`oinit` binaries present | `build/verification/build.log`, `build/amd64/session.log`, `build/vm/serial.log` |
| GE | `tools/test-ge.sh` exits 0 and reports `PASS: GE volume, raw key/value, no FS`; same raw value survives reboot | `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile | `tools/test-o-volume.sh` exits 0 with `PASS: O volume, no FS`; wrong-profile open attempts are rejected | `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects | `tools/test-o-objects.sh` exits 0 with `PASS: native O objects, no FS`; two OIDs survive reboot | `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O | `tools/test-o-space.sh` exits 0 with its Environment/code/Space graph PASS; same alias/OID and O code survive two boots | `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init | `tools/test-o-boot.sh` exits 0 with `PASS: three O-only boots`; one disk, `run()` yields 1, 2, 3, same Counter OID, no root filesystem mount | `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log`, `boot1.log`–`boot3.log` |
| O handles | `tools/test-o-handles.sh` exits 0 with both its per-check markers and `PASS: process-local O handles`; isolation, independent sessions, close/exit capacity, abort, exec rules and invalid handles pass | `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| O execute | `tools/test-o-exec.sh` exits 0 with `PASS: native executable object from O, exec and rollback`; the O-only target marker appears once, the child exits successfully, missing/malformed loads preserve the caller's handle, and native exec closes handles | `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| O MicroPython | `tools/test-o-boot-omp.sh` exits 0 with `PASS: MicroPython loaded from a native O object (no embedded mp)`; the generated `pc64omp` boot contents contain no `mp`; three boots of one disk yield `run()` 1, 2, 3 with the same Counter OID/alias; the REPL evaluates a test expression; missing/malformed objects return errors and preserve the handle | `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl.log`, `build/amd64/ompbootvm/check.log` |

Individual QEMU serial logs may be **overwritten between boots** by
their scripts. The captured `build/verification/*.log` output and
`test-o-boot.sh`'s three-boot transcript are the primary evidence.
Preserve relevant failure logs or copies before rerunning a gate.

For each execution record **UTC timestamp, commit SHA, host/VM setup,
exact command, exit status, PASS/FAIL/NOT RUN and log path**. If a gate
fails, record its first relevant diagnostic and leave its status FAIL;
do not edit the test to manufacture a PASS. Do not add historical
source-branch logs as evidence of execution at a newer commit.

## Known limits and follow-up work

- GE/O has no native graph edge, tag or indexed namespace relation API.
- Python logical object OIDs live inside a whole `OID_GRAPH` payload;
  native per-Python-object storage and incremental updates are absent.
- The ordinary configuration still embeds MicroPython via the inherited
  `devroot` bootstrap. The dedicated `pc64omp` configuration demonstrates
  the real interpreter loaded from a native O object by OID, but the
  bounded loader still has no program catalog, architecture selection,
  permissions, dynamic linking or general object-loading contract.
  `devroot`, the ordinary embedded MicroPython and `kbdfs` remain.
- Native O Space handles are now process-local, but handle inheritance
  and cross-process transfer are not implemented; each process has at
  most eight handles. The volume instance remains global, there is no
  per-volume/per-Space authorization, and this is not a complete
  capability model.
- The process-local handle table is independent of `Fgrp`, `Chan`,
  namespaces and 9P, by design for this experiment.
- Crash/corruption recovery, incomplete transactions, concurrency,
  performance and physical hardware behavior lack production validation.
- Inherited 9front/Monolith code and legacy FS/9P tests are separate from
  the existing five O-only gates. Preserve them as needed for bootstrap but do
  not treat them as native GE/O architecture.
- `tools/selfroot` still defaults its remote origin to
  `pereuna/Plan2001.git`, and the legacy `tools/test-selfroot.sh`
  still clones that repository. The 22 October run used the documented
  `ORIGIN=https://github.com/pereuna/Plan2001-O.git` override; the
  default and that legacy test still require a **separate functional
  tools fix**, which this validation intentionally does not make.
