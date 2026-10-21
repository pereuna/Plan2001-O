# O-only proof of concept — five achieved gates

This file records the **implemented minimal demonstration** from
`pereuna/Plan2001` at `436ed30`, not the complete object-native
architecture of the new repository. Details of the native on-disk
representation are in [o-volume-format.md](o-volume-format.md).

1. GE opens the raw volume without a filesystem root or 9P service.
   Test: `tools/test-ge.sh`.
2. A native O-profile volume carries a flat `init` Space catalog.
   Test: `tools/test-o-volume.sh`.
3. O objects are addressed by `(SpaceID, OID)` and versioned.
   Test: `tools/test-o-objects.sh`.
4. MicroPython loads its Environment, compiled code and persistent
   state from O rather than filesystem paths.
   Test: `tools/test-o-space.sh`.
5. The same ESP + O QEMU disk boots three times, invoking a
   persistent `run()` with counter 1 -> 2 -> 3 and a stable alias.
   Test: `tools/test-o-boot.sh`.

**Important limitation:** Stage 5 persists the Python graph as
one native O object (`OID_GRAPH`). Native GE/O graph relations,
incremental individual Python-object storage, and loading
executable programs directly from O are **new research tasks**.

Development rule: preserve the proven vertical slice, experiment
with new native GE/O semantics, and never solve a missing object
operation by constructing a filesystem or 9P compatibility layer.

Current direction: [README.md](../README.md).
