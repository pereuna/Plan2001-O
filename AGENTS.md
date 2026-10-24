# Plan2001-O — instructions for coding agents

Read the [Finnish philosophical manifesto](docs/OLIO-OBJEKTI-MANIFESTI.md) for concepts and the [English general software specification](docs/GENERAL-SOFTWARE-SPECIFICATION.md) for one proposed computer realization. The manifesto is **not an implementation mandate**. The Plan2001-O PoC **deliberately uses ordinary 8-bit bytes, 64-bit OIDs, existing Plan2001/9front code, and conventional computer hardware**. Distinguish the philosophical meaning of *olio* (uninterpreted entity) and relational *object* from the concrete byte-oriented storage chosen for this PoC. Do not redesign storage, hardware abstractions or existing working code merely to make them philosophically general.

Read [README.md](README.md) for overview, [docs/OBJECT-MODEL.md](docs/OBJECT-MODEL.md) for the object/file model and Python hierarchy prohibition, [docs/STATUS.md](docs/STATUS.md) for current verification and tests, [docs/POC.md](docs/POC.md) for demonstrated experiments, and [docs/O-FORMAT.md](docs/O-FORMAT.md) for the implemented on-disk contract. Inherited Plan 9/9front documentation is reference material, not a specification for Plan2001-O.

## Practical PoC contract

**Goal:** a small, working, byte-oriented implementation of Space, olios, relational objects, observations, and eventually named graphs on an ordinary 64-bit computer with a disk and network. Keep the philosophical manifesto independent of these contingent hardware choices.

- **Reuse before rewriting.** Begin with the working Plan2001-O code and its Plan2001/9front-derived kernel, GE/O storage, executable loader, processes, networking, console, and device drivers. Prefer a narrow modification or thin direct interface over replacing functioning subsystems. Remove an inherited abstraction only when it demonstrably obstructs the PoC and a simpler tested replacement exists.
- **Bytes are the native carrier for this PoC.** Store and transfer ordinary octet sequences. Use existing 64-bit identifiers and GE/O conventions where possible; keep application interpretation and graph relations logically distinct from raw content. No seven-bit, analogue, exotic hardware, or substrate-independent storage engine is required.
- **Hardware and access:** target a conventional 64-bit computer with persistent disk storage and networking. On a desktop, use the available display and keyboard. On a server, provide remote interaction over the network without requiring local GUI hardware. Reuse existing console/network/driver paths first. This is a target usage profile, not a claim that every mode is implemented today.
- **Keep it a proof of concept.** Demonstrate one coherent vertical slice, not a universal ontology engine, a new general-purpose desktop, a wholesale kernel rewrite, or a new network protocol for its own sake. Prefer the smallest complete behavior that can be built and tested.
- **Avoid premature generalization.** Any interpretation API or persistent graph is an incremental experiment. Do not implement speculative abstraction layers, type registries, class taxonomies, analogue representations, or cross-machine identity schemes merely because they are discussed philosophically.
- **Preserve operational evidence.** The current code stores versioned byte values and a serialized Python graph; do not claim a native relation graph or general observation API before they exist and are tested.

## Evidence and reporting

- Distinguish **implemented** (visible in source), **demonstrated** (supported by a named executed test), and **proposed** (unimplemented design).
- Read the relevant code before asserting an API or behavior. Report the commit, the exact tests actually run, their results and log paths. Never infer a successful test from a script or an older branch's logs.
- A broken gate is evidence to investigate, not permission to weaken it or silently change the specification.
- Update STATUS when verification changes; keep POC's source-branch experiment history intact.

## Production server/embedded profile

The server and embedded production profile is a **design target**, not an
implemented security model. Follow [docs/PRODUCTION-BOOT-AND-AUTHORITY.md](docs/PRODUCTION-BOOT-AND-AUTHORITY.md)
for its boot, administration and authority boundaries. There is no native
all-powerful `root`/`sudo`/universal administrator account in that target.
Inherited `eve`/`hostowner`/`iseve` behavior is **legacy and currently
present**; do not change or quietly weaken it while migration work is
incomplete. Retain USB support and the existing UEFI and GRUB boot/recovery
workflows. Do not claim secure netboot, verified boot, encrypted GE/O,
passkeys or a native administration service is implemented unless a named
test demonstrates it.

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
