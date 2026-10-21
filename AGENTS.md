# Plan2001-O — instructions for coding agents

Read [README.md](README.md) and [docs/STATUS.md](docs/STATUS.md)
first. They supersede the old Plan9/9front project documentation.

## Active architectural hypothesis

- GE/O is a native persistent object **and relationship graph**.
- Identity is `(SpaceID, OID)`; paths are not object identities.
- Python replaces rc/sh/awk/init and demonstrates persistent
  namespaces, code, functions, and values. GE/O is not Python-specific.
- Native executable binaries, text and other content types belong
  in GE/O; eventually the kernel loads executables by object ID.
- A native object process/IPC/remote protocol remains undecided.

## Boundaries

- Do **not** introduce a flat filesystem, 9P adapter, fake
  file-backed object store, path-based native O API, or
  compatibility namespace to bypass open design decisions.
- Useful byte offset operations and per-process resource handles
  are allowed; they do not imply a filesystem hierarchy.
- Existing Plan 9 implementation code may be retained temporarily
  to keep the proven PoC buildable. Its design is not a goal.
- Do not assume the native relationship graph or direct O-exec
  already exists. The current Python persistence still rewrites
  an entire `OID_GRAPH` object.
- Prefer small reversible experiments with precise QEMU evidence.
  Do not run destructive image-reformatting tools against real disks.
- Keep upstream `LICENSE` and provenance; source migration did
  not change code ownership or license obligations.

Preserve `tools/test-o-boot.sh` and the other O regression tests
while simplifying legacy dependencies. Report actual commands,
passes, failures and unknowns; do not infer tests from source code.
