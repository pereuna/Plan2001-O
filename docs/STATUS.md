# Implementation status — Plan2001-O

**Status date:** 22 October 2026. **Phase C runtime evidence baseline:**
`main` at `f23d5624a153bd3645be8f8b540b3bc243ebabec`.
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
| **Implemented** | The imported source contains GE/O O-profile volumes, versioned `(SpaceID, OID)` objects, the native O syscall boundary with process-owned O Space handle tables, an O-resident Environment and `.mpy` loader, and a persistent MicroPython `init` Space. |
| **Demonstrated in the source branch** | Five reported GE/O QEMU regression gates, including three boots of one ESP + O image with counter `1 -> 2 -> 3` and preserved Counter OID/alias. See [POC.md](POC.md). |
| **Statically verified in Plan2001-O** | Documentation references and repository metadata checked at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`; details below. |
| **Runtime verified in Plan2001-O** | **PASS:** the full amd64 build and all five GE/O QEMU gates were executed from `f23d5624a153bd3645be8f8b540b3bc243ebabec` on 22 October 2026 with KVM. The process-local O handle regression also passed from a working tree based on that commit (the experiment was uncommitted at verification time). See the records below and `build/verification/*.log`. |
| **Proposed, not implemented** | Native GE/O relationship indexes/edges, per-Python-object O records, a direct native O executable loader, general persistent namespaces, object IPC and a remote protocol. |

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

**Source state:** `HEAD` is `f23d5624a153bd3645be8f8b540b3bc243ebabec`.
The experiment change set (`devgefs.c`, `portdat.h`, `portfns.h`, `proc.c`,
`sysproc.c`, `pc64`, `sys/src/cmd/ohandle/`, `tools/test-o-handles.sh`)
was **uncommitted** during this verification. `tools/selfroot` therefore
cloned `f23d562` as its source tree, while the built kernel and the
selfroot binaries came from the working-tree build. A clean committed
rerun is required before this is treated as release evidence rather than
experiment evidence.

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
test -s build/amd64/bootx64.efi
test -x build/selfroot/amd64/bin/gefs
test -x build/selfroot/amd64/bin/micropython
test -x build/selfroot/amd64/bin/ohandle

for gate in test-o-handles test-ge test-o-volume test-o-objects test-o-space test-o-boot; do
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
| Build | Exit 0, `BUILD-DONE` in the build session, kernel + UEFI loader + `gefs` + MicroPython + `ohandle` binaries present | `build/verification/build.log`, `build/amd64/session.log`, `build/vm/serial.log` |
| GE | `tools/test-ge.sh` exits 0 and reports `PASS: GE volume, raw key/value, no FS`; same raw value survives reboot | `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile | `tools/test-o-volume.sh` exits 0 with `PASS: O volume, no FS`; wrong-profile open attempts are rejected | `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects | `tools/test-o-objects.sh` exits 0 with `PASS: native O objects, no FS`; two OIDs survive reboot | `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O | `tools/test-o-space.sh` exits 0 with its Environment/code/Space graph PASS; same alias/OID and O code survive two boots | `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init | `tools/test-o-boot.sh` exits 0 with `PASS: three O-only boots`; one disk, `run()` yields 1, 2, 3, same Counter OID, no root filesystem mount | `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log`, `boot1.log`–`boot3.log` |
| O handles | `tools/test-o-handles.sh` exits 0 with both its per-check markers and `PASS: process-local O handles`; isolation, independent sessions, close/exit capacity, abort, exec rules and invalid handles pass | `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |

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
- MicroPython is still embedded via the inherited `devroot` bootstrap.
  Loading user executables directly from O remains to be demonstrated.
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
