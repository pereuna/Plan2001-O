# O-only proof of concept — demonstrated gates

**Evidence source:** `pereuna/Plan2001`, branch `poc-o-only`,
commit `436ed30c894c4060638341ecebe82004d457f496` (20 October 2026).
The source snapshot was imported into Plan2001-O without its Git ancestry.
The results below were reported by the **source-branch experiments**;
they are not evidence of a fresh run of this repository.

| Gate | What the experiment demonstrates | Regression script |
| --- | --- | --- |
| 1. GE | Open a raw GE volume, persist a key/value record across reboot, without mounting an FS root | `tools/test-ge.sh` |
| 2. O profile | Format and open a native O-profile volume, find the flat `init` catalog entry, and reject a wrong volume profile | `tools/test-o-volume.sh` |
| 3. O objects | Commit and restore two versioned native objects addressed by stable `(SpaceID, OID)` | `tools/test-o-objects.sh` |
| 4. Python on O | Load the Environment manifest and verified `.mpy` code from O; restore the Python graph and alias on a second boot | `tools/test-o-space.sh` |
| 5. O init | Boot the **same** ESP + O disk three times with no FS root and execute restored `run()`: counter `1 -> 2 -> 3`, preserving the Counter OID and alias | `tools/test-o-boot.sh` |

These five gates form a **vertical slice**, not a general-purpose operating system.
The bootstrapped user-space interpreter is still embedded in the kernel
image and reached through inherited `/boot/mp` loading.

## What the gates do not prove

- GE/O-native indexed relationships, tags or arbitrary persistent namespace bindings.
- Independent native storage for each Python object: the current graph is one `OID_GRAPH` object.
- Direct native executable-object loading from GE/O.
- General package management, process-local object capabilities, IPC or a remote object protocol.
- Production-grade recovery, concurrency, hardware compatibility or performance.

This document preserves experiment evidence. For **current verification**,
follow [STATUS.md](STATUS.md); for bytes, record layout and API see
[O-FORMAT.md](O-FORMAT.md); for the research direction see [README.md](../README.md).
