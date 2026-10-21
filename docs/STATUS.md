# Implementation status — Plan2001-O

**Recorded baseline:** 21 October 2026, `main` at
`f27adb071043a33ffd1efd0a6833503c710ebb15`.
Imported source: `pereuna/Plan2001` / `poc-o-only` /
`436ed30c894c4060638341ecebe82004d457f496`
(20 October 2026). The import has **no upstream Git ancestry**.

## Evidence and verification

| Category | Assessment |
| --- | --- |
| **Implemented in imported source** | Native GE/O O-profile volume, stable SpaceID/OID object records, versioned commits, O-resident Environment and `.mpy`, and persistent MicroPython `init` Space |
| **Demonstrated on source branch** | Five QEMU/GE tests, including three sequential boots of one ESP + O disk with `run()` counter `1 -> 2 -> 3` and a stable Counter OID/alias; see [POC.md](POC.md) |
| **Verified in Plan2001-O after import** | **Not yet recorded.** Do not claim these tests passed here until their logs are collected. |
| **Proposed / not implemented** | Native GE/O relationship edges and indexes, per-Python-object O persistence, native O executable loader, general namespaces, object IPC and remote protocol |

Source-branch evidence is not a substitute for an execution result from
this repository. Do not change a claim to **verified** until the tested
commit, command, run date, outcome and log location are recorded.

## Reproducible amd64 build and regression sequence

On a Debian-compatible host with QEMU/OVMF, a 9front bootstrap VM and
the prerequisites checked by `tools/vm-setup`:

```sh
# Initial host/VM preparation (idempotent when already installed).
tools/vm-setup

# WHAT=all populates build/amd64/root/amd64/{bin,lib};
# WHAT=kernel alone does NOT provide the tools needed by O tests.
WHAT=all tools/build.sh

# Build a disposable self-hosting directory (NOT a disk partition).
tools/selfroot build/selfroot

# GE baseline, O format/objects, Python/O, and persistent init.
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

The regression scripts require `build/selfroot/amd64/bin/gefs`;
the Python/O tests additionally require
`build/selfroot/amd64/bin/micropython`. The `WHAT=all` build plus
`tools/selfroot build/selfroot` provides the expected preparation path.
This **dependency sequence has been inspected in source, not executed
as part of the documentation update**. The tests create or replace
disposable images under `build/`. Never substitute a real block device.

## Record each run

For each gate, record: UTC date/time, commit SHA, exact command, exit status,
a short PASS/FAIL/NOT RUN result and relevant log path. The QEMU
three-boot test writes `build/amd64/obootvm/three-boots.log`; the
build stores `build/amd64/session.log` and VM serial output under
`build/vm/`. Logs need not be checked into Git.

## Known limitations and next questions

- O catalog is currently seeded with an `init` Space; no general persistent relation or tag index.
- MicroPython commits the full graph as one `OID_GRAPH` object, despite stable logical Python OIDs.
- No OID-based user-executable loader; the interpreter is embedded using inherited `devroot`.
- O handle bookkeeping is PoC-global; process-scoped lifetime, access control and multi-volume behavior require design.
- Recovery and failure injection, corrupt/missing-object diagnostics, concurrency and hardware validation remain incomplete.
- Build scripts still include inherited 9front/Monolith components. Those dependencies will be assessed separately; their presence does not define the target architecture.

See [README.md](../README.md) for the hypothesis,
[POC.md](POC.md) for source-branch test evidence and
[O-FORMAT.md](O-FORMAT.md) for the implemented format.
