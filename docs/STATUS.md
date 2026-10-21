# Implementation status — Plan2001-O

**Status date:** 21 October 2026. **Phase C evidence baseline:**
`main` at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`.
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
| **Implemented** | The imported source contains GE/O O-profile volumes, versioned `(SpaceID, OID)` objects, the native O syscall boundary, an O-resident Environment and `.mpy` loader, and a persistent MicroPython `init` Space. |
| **Demonstrated in the source branch** | Five reported GE/O QEMU regression gates, including three boots of one ESP + O image with counter `1 -> 2 -> 3` and preserved Counter OID/alias. See [POC.md](POC.md). |
| **Statically verified in Plan2001-O** | Documentation references and repository metadata checked at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`; details below. |
| **Runtime verified in Plan2001-O** | **NOT RUN:** no successful build or GE/O QEMU test execution from this repository has been supplied or observed in this validation. |
| **Proposed, not implemented** | Native GE/O relationship indexes/edges, per-Python-object O records, a direct native O executable loader, general persistent namespaces, object IPC and a remote protocol. |

Never promote source inspection or a successful source-branch test into
a **current-repository runtime PASS**. A missing result is **NOT RUN**,
not PASS and not FAIL.

## Phase C validation record

**Checked:** 21 October 2026 against the Phase B commit above.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| GitHub source and document availability | **PASS (static)** | `README.md`, `AGENTS.md`, `docs/POC.md`, `docs/STATUS.md` and `docs/O-FORMAT.md` were read from the repository. |
| Documentation navigation | **PASS (static)** | 21 relative Markdown links and 32 backtick-formatted source/tool/document path references in those five Markdown files resolved to entries in the repository tree at the checked commit. This is **not** an exhaustive scan of all inherited source comments. |
| Phase B file metadata | **PASS (static)** | Git trees before/after Phase B were compared; the 22 modified executable tool files retained executable mode, and no tracked file's mode changed. |
| Build dependency review | **PASS (source inspection)** | `WHAT=all tools/build.sh` produces the root binaries used by `tools/selfroot build/selfroot`. `WHAT=kernel` alone does **not** prepare `build/selfroot/amd64/bin/gefs` or `micropython`. |
| Full amd64 build | **NOT RUN (environment unavailable)** | The inspection environment lacks QEMU system tools, `qemu-img`, mtools/`mcopy`, the required OVMF firmware files and accessible `/dev/kvm`. A prepared 9front VM is also unavailable. |
| Five O-only runtime gates | **NOT RUN** | None of the QEMU scripts below was executed during this audit. Consequently, the imported PoC is not yet runtime-validated here. |

The link/path audit was performed on the repository snapshot **before**
this STATUS-only update; document paths are unchanged. This is a
GitHub-source/static audit, **not** a successful build or a boot test.
The current lack of QEMU is a validation-environment limitation, not a
claim that any O runtime test fails.

## Reproduction on a prepared Debian/amd64 host

Run from the repository root with a **committed, clean source tree**.
Verify `git status --short` and record `git rev-parse HEAD` first:
`tools/overlay` can include working-tree files, whereas
`tools/selfroot` clones **committed HEAD**, so testing uncommitted
sources risks mixing incompatible binaries and code.

`tools/vm-setup` checks Debian packages, OVMF, the selected VM
accelerator and a pinned 9front bootstrap image. With usable KVM,
run the following commands; `VM_ACCEL=tcg` is the script's documented
alternative when KVM access is unavailable, but has **not** been
validated in this audit.

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

test -x build/amd64/9pc64
test -s build/amd64/bootx64.efi
test -x build/selfroot/amd64/bin/gefs
test -x build/selfroot/amd64/bin/micropython

for gate in test-ge test-o-volume test-o-objects test-o-space test-o-boot; do
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
| Build | Exit 0, `BUILD-DONE` in the build session, kernel + UEFI loader + `gefs` + MicroPython binaries present | `build/verification/build.log`, `build/amd64/session.log`, `build/vm/serial.log` |
| GE | `tools/test-ge.sh` exits 0 and reports `PASS: GE volume, raw key/value, no FS`; same raw value survives reboot | `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile | `tools/test-o-volume.sh` exits 0 with `PASS: O volume, no FS`; wrong-profile open attempts are rejected | `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects | `tools/test-o-objects.sh` exits 0 with `PASS: native O objects, no FS`; two OIDs survive reboot | `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O | `tools/test-o-space.sh` exits 0 with its Environment/code/Space graph PASS; same alias/OID and O code survive two boots | `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init | `tools/test-o-boot.sh` exits 0 with `PASS: three O-only boots`; one disk, `run()` yields 1, 2, 3, same Counter OID, no root filesystem mount | `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log`, `boot1.log`–`boot3.log` |

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
- Native O Space handles are PoC-global rather than process-local;
  lifecycle, authority and multi-volume behavior remain unresolved.
- Crash/corruption recovery, incomplete transactions, concurrency,
  performance and physical hardware behavior lack production validation.
- Inherited 9front/Monolith code and legacy FS/9P tests are separate from
  the five O-only gates. Preserve them as needed for bootstrap but do
  not treat them as native GE/O architecture.
- `tools/selfroot` still defaults its remote origin to
  `pereuna/Plan2001.git`, and the legacy `tools/test-selfroot.sh`
  still clones that repository. They require a **separate functional
  tools fix**; this documentation validation intentionally changes
  neither script.
