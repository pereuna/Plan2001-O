# Plan2001-O — instructions for coding agents

Read [README.md](README.md) for overview, [docs/OBJECT-MODEL.md](docs/OBJECT-MODEL.md) for the object/file model and Python hierarchy prohibition, [docs/STATUS.md](docs/STATUS.md) for current verification and tests, [docs/POC.md](docs/POC.md) for demonstrated experiments, and [docs/O-FORMAT.md](docs/O-FORMAT.md) for the implemented on-disk contract. Inherited Plan 9/9front documentation is reference material, not a specification for Plan2001-O.

## Evidence and reporting

- Distinguish **implemented** (visible in source), **demonstrated** (supported by a named executed test), and **proposed** (unimplemented design).
- Read the relevant code before asserting an API or behavior. Report the commit, the exact tests actually run, their results and log paths. Never infer a successful test from a script or an older branch's logs.
- A broken gate is evidence to investigate, not permission to weaken it or silently change the specification.
- Update STATUS when verification changes; keep POC's source-branch experiment history intact.

## Architectural direction

- GE/O owns persistent object identity **and, as a goal, native persistent relationships**. Current identity is `(SpaceID, OID)` with a 64-bit OID within a GE volume, not a path or disk pointer.
- **A file is an O object's finite byte sequence**, not the combined Unix/Plan 9 metadata-plus-data record. The word `file` is a content abstraction/descriptive category, not a required `File` superclass, exclusive class, or on-disk `type=file` field.
- Files need no root directory, directory hierarchy, parent link, canonical pathname, Unix `stat` fields, or global namespace to exist. An object's optional properties and relations are separate from its file bytes.
- **Do not import Python's class system into GE/O.** Python `class`, inheritance, MRO, descriptors, modules, heap layout and runtime object types must not define the kernel's OID representation, native storage type hierarchy, or graph semantics.
- Python replaces the scripting layer and demonstrates persistent values, namespaces and code. GE/O must not depend on Python.
- Code, source and native executables may be ordinary byte-content files addressed by OID. A separate semantic program object may relate to one or more executable implementations (see OID 43/100 in OBJECT-MODEL). Those relations are **not implemented**. A bounded native O executable test path exists; general executable-object loading is **not implemented**.
- Native object-handle lifetime, indexing, permissions, IPC and remote operation remain research questions; do not invent a universal schema or protocol in advance.
- The current O path commits the Python graph as **one `OID_GRAPH` object**. Do not misrepresent this as native GE/O edges or per-object Python persistence.

## Boundaries and workflow

- Do not introduce a 9P adapter, fake directory-tree filesystem, implicit path-based O API or compatibility namespace to evade an open native-design question. Files and byte streams themselves are allowed and fundamental.
- For legacy migration, treat concrete Plan 9/Unix files as O byte objects. Do not recreate Plan 9 `bind`, `mount`, process-local hierarchical namespaces or `/bin` overlays. Explicit architecture source paths may be used to disambiguate tools at import time; a source path is not an OID.
- Do not add external/string OIDs, a new native class hierarchy, a mandatory metadata schema or a GE/O v1 format change based only on the architectural examples. The `mk.py`/numeric build-manifest concept is not yet an implemented build API.
- Byte offsets, reads, writes and resource handles are useful operations, not by themselves a filesystem hierarchy.
- **Legacy code may remain as a bootstrap dependency; its presence is not an architectural requirement. Remove it only after an alternative has been demonstrated.**
- Preserve the O-only vertical slice and its regression tests. Prefer small reversible experiments with QEMU evidence over speculative rewrites.
- Never run image-formatting or `tools/selfroot -p DEV` against a real disk as part of routine tests. Use disposable images.
- Preserve upstream copyright, license notices and provenance. Importing a source snapshot without Git ancestry does not transfer authorship.

See [docs/STATUS.md](docs/STATUS.md) for the **single maintained set of build and test commands**.
