# Implementation status — imported O-only PoC

Source snapshot: `pereuna/Plan2001`, branch `poc-o-only`,
commit `436ed30c894c4060638341ecebe82004d457f496`
(20 October 2026). Imported as a fresh source tree, **without
upstream Git ancestry**.

## Demonstrated by source-branch test logs

- Native GE/O partition access without an FS root.
- Stable SpaceID-scoped OIDs, GE-backed versioned objects, commits.
- MicroPython Environment and verified `.mpy` code loaded from O.
- Embedded MicroPython boots persistent `init` Space from O.
- QEMU test `tools/test-o-boot.sh` ran three sequential boots
  from the same ESP + O disk: counter 1, 2, 3, with the same OID
  and alias preserved; no filesystem root was mounted.

These are test results documented in the **source repository**,
not a claim that the imported repository has been rebuilt and
re-tested after migration.

## Still experimental / not implemented

- GE/O-native relationship graph and persistent namespace bindings.
- Per-Python-object native O records; currently an entire persistent
  Python graph is committed as one `OID_GRAPH` object.
- General OID-based native executable loader (current interpreter
  is kernel-embedded via legacy `devroot`).
- General-purpose O-resident Python package management.
- Fully designed process-local object handle lifecycle, access
  control, object IPC, or remote object protocol.
- Production-grade corruption recovery, hardware validation,
  performance or concurrency guarantees.

## Regression commands

```sh
WHAT=kernel tools/build.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

These commands require the repository's existing 9front/QEMU host
build environment. Their presence is not evidence they have
passed in this new repository. The first task after migration is
to run these gates before structural source pruning.

See [README.md](../README.md) for active architecture and
[o-volume-format.md](o-volume-format.md) for the implemented
on-disk format.
