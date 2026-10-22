# Plan2001-O — instructions for coding agents

Read [README.md](README.md) for direction, [docs/STATUS.md](docs/STATUS.md) for current verification and tests, [docs/POC.md](docs/POC.md) for demonstrated experiments, and [docs/O-FORMAT.md](docs/O-FORMAT.md) for the implemented on-disk contract. Inherited Plan 9/9front documentation is reference material, not a specification for Plan2001-O.

## Evidence and reporting

- Distinguish **implemented** (visible in source), **demonstrated** (supported by a named executed test), and **proposed** (unimplemented design).
- Read the relevant code before asserting an API or behavior. Report the commit, the exact tests actually run, their results and log paths. Never infer a successful test from a script or an older branch's logs.
- A broken gate is evidence to investigate, not permission to weaken it or silently change the specification.
- Update STATUS when verification changes; keep POC's source-branch experiment history intact.

## Architectural direction

- GE/O owns persistent object identity **and, as a goal, native persistent relationships**. The implemented identity is `(SpaceID, OID)`, not a path.
- Python replaces the scripting layer and demonstrates persistent values, namespaces and code. GE/O must not depend on Python.
- Code, native executables and other byte-addressable or structured content are objects. A bounded native O executable test path exists; general executable-object loading (catalog, architecture selection, dynamic linking) is **not implemented**.
- Native object-handle lifetime, indexing, permissions, IPC and remote operation remain research questions; do not invent a universal schema or protocol in advance.
- The current O path commits the Python graph as **one `OID_GRAPH` object**. Do not misrepresent this as native GE/O edges or per-object Python persistence.

## Boundaries and workflow

- Do not introduce a 9P adapter, fake object filesystem, implicit path-based O API or compatibility namespace to evade an open native-design question.
- Byte offsets, reads, writes and resource handles are useful operations, not by themselves a filesystem hierarchy.
- **Legacy code may remain as a bootstrap dependency; its presence is not an architectural requirement. Remove it only after an alternative has been demonstrated.**
- Preserve the O-only vertical slice and its regression tests. Prefer small reversible experiments with QEMU evidence over speculative rewrites.
- Never run image-formatting or `tools/selfroot -p DEV` against a real disk as part of routine tests. Use disposable images.
- Preserve upstream copyright, license notices and provenance. Importing a source snapshot without Git ancestry does not transfer authorship.

See [docs/STATUS.md](docs/STATUS.md) for the **single maintained set of build and test commands**.
