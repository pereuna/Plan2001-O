# Plan2001-O object and file model — architectural definition

**Status: proposed architecture, not an implemented type system.** This document defines the intended semantics for developers and coding agents. It does not change GE/O on-disk format v1, kernel APIs, historical test results, or existing MicroPython persistence. Read [O-FORMAT.md](O-FORMAT.md) for what is implemented and [STATUS.md](STATUS.md) for evidence.

## 1. Identity, object, file, stream

An **object** (Finnish *olio*, English *object*) is an individually identifiable persistent entity. An **OID** identifies an object; it is not itself the object, a memory address, a block address, or a pathname. Two objects may contain identical bytes and still have different identities. An object may retain its identity when its content changes through committed versions.

A **file** is the byte-content abstraction of an O object: a finite ordered sequence of bytes, including the empty sequence. A file is **not** a Unix/Plan 9 directory entry, nor the bundle of data plus mandatory operating-system file metadata. It does not require a root directory, pathname, owner, mode bits, timestamps, or an inode-like record.

```text
OID 42
    content = "hello\n"      # six bytes; a file
```

The word *file* may describe an object's content or a descriptive type/category (`file`). It **does not mandate a `File` class, superclass, inheritance tree, exclusive tag, or even a stored `type=file` field**. Byte-bearing objects may have additional interpretations, such as a compiled executable or an image; those interpretations are not mutually exclusive subclasses. The exact representation of type descriptions remains open.

**Properties and relations are distinct from the file's byte content.** Creation provenance, an original creation timestamp (if actually known), executable interpretation, architecture or optional imported legacy metadata may be attached to an object or expressed as relations. Do not silently copy Unix `stat` fields into every native object or equate import/copy time with original creation time.

A **stream** is a means of accessing or transferring bytes, possibly through one or several ordered channels. It is not a file's identity or a required container. Random-access reads by offset and bounded-length byte transfers remain useful without directory traversal. A logical file need not occupy one contiguous RAM region or one physical disk block.

## 2. Relationships, not a type or directory hierarchy

Native Plan2001-O relationships are intended to form a **graph**. The graph can have many-to-many references, shared nodes, and cycles. No distinguished root directory, parent relation, canonical path, or traversal from `/` defines object identity.

```text
OID 43
    content = <6c binary>       # byte content; usable as a file

OID 100
    implements → OID 43
    purpose    → C compiler
    target     → amd64
```

Here `OID 43` is the stored 6c executable bytes. `OID 100` is a distinct semantic object describing a compiler and referring to that implementation. **`implements`, `purpose` and `target` are illustrative relation/property labels, not an implemented edge schema or a Python object hierarchy.** An implementation can be selected or replaced independently of the descriptive object; a loader eventually operates on the selected executable bytes.

Other examples of future relations: origin, generated-by, depends-on, implements-for-architecture, tag. Some objects may have no relations. Indexes and bindings are open engineering questions and **must not require reconstructing directory trees**.

An object can be read or addressed directly by identity; a graph lookup is for relationships and discovery, not a mandatory path-walk to reach the bytes.

## 3. Python is a client, never the GE/O ontology

MicroPython is an execution environment and a consumer of persistent objects. It **does not define the native object model**. Specifically:

- Python `class`, subclassing, inheritance, MRO, descriptors, metaclasses, duck typing, module imports and runtime heap objects are Python-language mechanisms; none is a mandatory GE/O classification or storage layer.
- Do not model OIDs as Python class instances in the kernel or copy Python's class/type hierarchy into GE/O. A client-side Python wrapper may exist for convenience but must not determine disk layout, native identity, or graph semantics.
- A graph of native GE/O relationships is not the same as a serialized Python object graph.
- Code and binary content can be addressed as O objects irrespective of the language used to produce them (Plan 9 C, Go, Ada, Python, etc.).

**Current implementation boundary:** GE/O v1 stores versioned opaque byte values identified by `(SpaceID, OID)` within a volume. `OID` is currently 64 bits; a single globally allocated OID across all machines is **not implemented**. Persistent Python objects in today's PoC are serialized together into the `OID_GRAPH` object, not independently stored as native GE/O graph edges. A generic `file` type field, relationship index, and the example above are **proposed**, not working APIs.

## 4. Legacy files are imported as bytes, not as namespaces

The Plan 9/9front tree and Unix trees are **inputs to migration**, not templates for Plan2001-O's native information model.

- Import concrete ordinary files and their bytes as O objects; a binary, source file or text file remains useful as a file abstraction.
- Plan 9 `bind`, `mount`, per-process directory views, `walk` and the synthetic root namespace are **not migrated** into GE/O.
- Resolve ambiguous tool names using explicit source/architecture paths during import (for example, the specific architecture build of `6c`). An original path may be retained as import provenance or in a temporary mapping, but it is not a native OID.
- Build tooling such as a prospective `mk.py` may use numeric OID lists and resolved byte locations/cached handles during migration. A physical disk address is not a durable OID; relocation must not silently change identity.
- Special dynamic Plan 9 devices, `/proc` and other generated views are not automatically imported as immutable byte files. Their behavior requires separate analysis.
- Native Plan2001-O namespaces and discovery will be designed afresh, **after** the core object and relation semantics are understood. Do not predesign them to reproduce Unix/POSIX/9P directories.

These are migration **principles**, not a claim that `mk.py`, a legacy importer, or a new namespace has already been implemented.

## 5. Non-goals and agent guardrails

1. Do not attempt to abolish files, byte blocks, byte streams, random-access reads or executable binaries.
2. Do not define an implicit hierarchical directory root, pathname-based identity, or an operating-system `stat` record as part of every object.
3. Do not insert Python class inheritance, `File` base classes or other object-oriented type hierarchies into the native storage contract.
4. Do not add an external/string OID layer or change the current 64-bit `OID` or GE/O v1 disk format for this conceptual clarification.
5. Do not invent a finished native graph, universal metadata schema, remote protocol, loader, importer or build pipeline; clearly label unimplemented ideas.
6. Do not rewrite historical PoC results when architecture changes. Preserve test evidence separately from the target model.

**Core distinction:** a file is bytes belonging to an identifiable object; a filesystem hierarchy is a separate, unnecessary organizational abstraction.
