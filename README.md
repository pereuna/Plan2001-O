# Plan2001-O

> **New conceptual direction (proposal, 23 October 2026):** [Olio and object — epistemological manifesto](docs/OLIO-OBJEKTI-MANIFESTI.md) (Finnish) and [A computer implementation of the manifesto](docs/GENERAL-SOFTWARE-SPECIFICATION.md) (English). An *olio* is an uninterpreted registered occurrence; an *object* is its role in a relation or observation. Octets and files are implementation/interpretation choices, not a universal ontology. The byte-centered model below documents the earlier proposal and the working PoC; [O-FORMAT](docs/O-FORMAT.md) and [STATUS](docs/STATUS.md) remain authoritative for implemented behavior.

**An experimental object-native operating system: a file is an OID-addressable object's byte content, without a mandatory root directory or filesystem hierarchy. Native relationships remain a research goal.**

Plan2001-O explores an operating system in which **objects are fundamental persistent entities, and a file is the byte-content abstraction of an object**. The architecture removes the obligatory hierarchical *filesystem*, not files. An object's identity is independent of paths and locations; its bytes may be read, written, executed when meaningful, or transferred by streams. **Today's PoC stores versioned native O byte objects, but its Python graph is still serialized into one `OID_GRAPH` object.**

The project is derived from Plan 9 / 9front, but it is **not an effort to reproduce Plan 9, Unix, POSIX, or their file-based interfaces**. Existing code is a starting point, not an architectural constraint. The goal is to discover a smaller, coherent object-native system through working experiments.

> **Core principle:** GE/O owns object identity and byte storage, and is intended to own native relationships. A file is bytes, not a mandatory metadata-plus-directory-entry structure. Python is a client of this model, **not its type system or ontology**.

## Current implementation versus target

This README describes the **architectural hypothesis**. The following table distinguishes it from the imported, working O-only proof of concept. A feature present in source is not automatically a test result from this repository.

| Concern | Imported O-only PoC | Target / open experiment |
| --- | --- | --- |
| Persistent identity | Versioned GE/O records addressed by `(SpaceID, OID)` | Identity independent of pathname and physical address; retain the 64-bit native OID |
| File content | Versioned opaque byte values | File = a finite ordered byte sequence belonging to an object; not a mandatory `File` subclass or Unix `stat` structure |
| Relationships | Python graph serialized as one `OID_GRAPH` object | Native, indexed GE/O bindings and relations |
| Namespaces | Seeded `init` Space and flat catalog | Design native name/discovery relationships later; do not migrate Plan 9 directory namespaces |
| Python | MicroPython executable stored in O and loaded by the normal amd64 `oinit` path; code and state from O | Ordinary executable object loaded from O |
| Native executables | Bounded native loader used by `oinit` for the fixed MicroPython OID plus a test loader for one target OID | General native object-ID-based loader |
| Process/remote interfaces | Inherited Plan 9 mechanisms for the PoC | Object handles, IPC and remote protocol to be explored |

**Document roles:** [README](README.md) gives the overview; [OBJECT-MODEL](docs/OBJECT-MODEL.md) defines the proposed architecture and Python/type-system boundaries; [POC](docs/POC.md) records source-branch experiments; [STATUS](docs/STATUS.md) reports verification and test instructions; [O-FORMAT](docs/O-FORMAT.md) specifies the *implemented* format. [AGENTS](AGENTS.md) is the coding-agent contract. Neither the README nor its example diagrams establish an implemented API.

## 1. Objects, files, and bytes

An **object** is an individual persistent entity, addressed in the current GE/O implementation by `(SpaceID, OID)`. An OID is an identity, not a pointer, physical block address or canonical pathname. Identical bytes may belong to distinct objects; object identity can remain stable across committed content versions.

A **file** is an object's finite ordered **byte content**. This includes text, source code, images and executable machine code. `file` names a byte-content abstraction or a descriptive category, **not a mandatory superclass, exclusive object type, or a required `type=file` field**.

```text
OID 42
    content = "hello\n"        # six bytes; a file
```

The file's data does **not** require a Unix/Plan 9 owner, mode, timestamps, pathname, inode or parent directory. Objects may separately have properties and relations, including provenance or original creation time when genuinely known. Those are not bytes in the file or universal filesystem metadata.

**Stream** denotes a way to read or transfer bytes; it is not a file's identity. Random access by offset, handles, sequential streams and multiple parallel streams remain useful, while disk blocks and memory allocation stay implementation details. A file is not required to occupy one contiguous RAM or disk block.

Current GE/O uses an 8-byte OID within a Space and stores versioned opaque byte values; it does not yet implement a generic `file` type field or indexed native object graph. See [the object/file model](docs/OBJECT-MODEL.md) for definitions and [O-FORMAT](docs/O-FORMAT.md) for actual disk layout.

## 2. The relationship graph belongs to GE/O

**Target architecture:** objects may have native persistent properties and graph relationships, independently of the file's bytes and independently of Python. Relationships can be shared, cyclic, many-to-many, and indexed without a root directory or path traversal.

```text
OID 43
    content = <6c binary>

OID 100
    implements → OID 43
    purpose    → C compiler
    target     → amd64
```

`OID 43` is a file: the 6c program's binary bytes. `OID 100` describes a compiler and relates it to one implementation. The relationship labels here are **conceptual**, not an implemented edge record, runtime API or Python class diagram. A compiler can have source objects, multiple architecture-specific implementations, or other relations without being a subclass of `File`.

The graph is not a renamed directory tree. A *namespace*, name binding or tag index might eventually be built **from relations**, but no root, parent directory, or Unix/Plan 9 `bind`/`mount` semantics are required. An OID already addresses an object; a graph traversal is not needed merely to read its bytes.

**Current limitation:** MicroPython's persistent graph is committed as the single serialized `OID_GRAPH` byte object. Independently indexed native GE/O edges and general-purpose binding/tag indexes are not implemented. A Kahn process-network FIFO or other stream-based IPC, if added, concerns runtime transfer and is separate from persistent relationships.

See [OBJECT-MODEL](docs/OBJECT-MODEL.md) for normative conceptual boundaries and [O-FORMAT](docs/O-FORMAT.md) for the current storage contract.

## 3. Python is the first object-native programming environment

Python is intended to replace the traditional OS scripting layer: `rc`, `sh`, `awk`, and filesystem-based `init` scripts. It provides a familiar language for boot configuration, administration and applications. **Python classes, inheritance, MRO, descriptors and Python object types do not define native GE/O object types or relationships.**

The intended integration extends from distributions and modules down to individual values, functions, and bindings:

```text
packages / environments
          |
modules / code definitions
          |
imports and namespace bindings
          |
functions, values, object references
          |
      GE/O objects + relationships
```

Consider:

```python
import foo
import bar

counter = 123

def run():
    return foo.process(counter)
```

A future persistent binding mechanism may associate `foo`, `bar`, `counter` and `run` with persistent objects. This is not a requirement to preserve Plan 9 directory namespaces. Imports can resolve code without `.py` files in directories; language-level imports and attributes remain Python's concerns.

**Python semantics remain Python semantics.** `import foo` includes module resolution, loading, and initialization. `a.foo` is attribute access, which may involve descriptors, inheritance, or custom methods. GE/O provides durable identity and bindings; it does not need to implement Python's language-specific attribute rules in the kernel.

Not every Python value needs a separately allocated GE/O record, and not every runtime resource can or should survive a reboot. The persistence boundary, primitive-value representation, code identity, interpreter compatibility, and object lifecycle must be tested explicitly.

`pip`-style package installation, arbitrary third-party Python compatibility, and fine-grained persistence for every Python object are **not implemented**. Source archives may be used by host-side preparation tools without making a filesystem the native runtime storage model.

## 4. Programs can be files and semantic objects

A native compiler binary is useful first as a **file**: an OID-addressable byte sequence. It may also be the implementation referred to by a different, semantic program object. This does not create a class hierarchy:

```text
OID 43
    content = <6c binary>       # file content

OID 100
    implements → OID 43
    purpose    → C compiler
    target     → amd64
```

A future loader can execute the bytes of `OID 43`; a future program/discovery layer can use `OID 100` to choose a suitable implementation. This graph representation is **a design example**, not a native relation implementation. Different languages and architectures may be represented without changing what a file is.

**Legacy migration boundary:** import concrete 9front/Plan 9 source and binary files as O byte objects. During import distinguish architecture-specific `6c` programs by their explicit source paths; do not reproduce `/bin`, process-local directory views, `bind` or `mount` in O. Source paths may be kept as provenance or in a temporary migration manifest, but are not native object identities. Prospective build tooling may use numeric OID lists; no `mk.py` migration or object-native build system is claimed to work today.

MicroPython is one executable program, not a kernel dependency or the native object ontology. The current bounded O executable-object loader exists; a general loader, program catalog and architecture selection are still experiments.

## 5. Boot without a root filesystem or initramfs

### Working PoC

```text
UEFI / EFI System Partition
             |
          bootloader
             |
       Plan2001 kernel
             |
        embedded oinit
             |
   MicroPython executable in GE/O
             |
       GE/O O partition
             |
    persistent "init" Space
             |
           run()
```

The normal kernel image embeds the small **`oinit` bootstrap** and the **`kbdfs` console helper**, not MicroPython. `oinit` is reached through the inherited internal boot interface and the read-only `devroot` machinery. It opens the O volume and the flat `init` Space, then calls the bounded native loader for the MicroPython executable stored at fixed OID `0x4f45584543000003`. There is no `/boot/mp` and no pathname-based MicroPython `exec` on the normal path. The embedded files are still a tiny kernel-memory file interface, **not initramfs, a disk filesystem, or the target object architecture**.

Once running, the PoC loads the Python Environment, compiled `.mpy` definitions, and persistent state **from the O partition without mounting a filesystem root**. The EFI System Partition and the developer's build-host files are boot/build inputs, not evidence that the O runtime needs files.

The normal persistent boot uses `init=/boot/oinit -vol PARTUUID=...`. For an interactive session, prepare a fresh disposable disk with `tools/mkrepl` and run the repository-root command `./repl_tui.sh`; both use the ordinary kernel and the same O-loaded interpreter. `tools/mkrepl` refuses to replace an existing disk without an explicit `FORCE=1`, so a persistent image is never silently reseeded.

### Intended architecture

```text
UEFI -> kernel
          |
          +-- hardware, memory, processes
          +-- GE/O access
          +-- native executable-object loader
          +-- minimal boot diagnostics
          |
          v
    GE/O: selected init program object
          |
          v
    user-space program (Python or native)
```

The embedded `oinit` and `kbdfs` are the remaining bootstrap dependencies, **not permanent architectural requirements**. A future kernel should reach the selected executable object without them and provide a small diagnostic path if that volume or object is missing or corrupt. This design does not require an initramfs or another root filesystem.

Do not replace the bootstrap harness with an initramfs or a pseudo-filesystem merely to preserve traditional `exec(path)` behavior. A bounded native executable-object experiment now exists; extending it to a general program loader remains work.

## 6. What about Plan 9 and 9P2000?

Plan 9 presents files, devices, and services through per-process hierarchical namespaces. Its `Chan` and `Dev` abstractions expose operations such as `walk`, `open`, `read`, and `write`; `devmnt` translates relevant operations into **9P2000** requests when a file server is involved. A `fid` is a connection-scoped protocol handle; a `qid` is a server-scoped file identifier. Neither defines Plan2001's persistent object identity.

Plan2001 retains useful *mechanisms* only where justified by experiments: process scheduling, memory protection, resource lifetime, reference management, device access, **byte-oriented files and streams**. **It does not adopt a root directory, hierarchical filesystem, pathname identity, `walk`, `fid`, `qid`, or 9P2000 as the native object model.**

The following still need deliberate design:

- How processes acquire, hold, share, and release references to native objects.
- How the kernel dispatches operations without requiring every object to behave like a file.
- How permissions and delegated authority work with objects and persistent namespaces.
- How native object relationships and transactions interact with concurrent processes.
- How live processes communicate (for example, message queues or FIFO channels).
- How objects and communication are represented across machines, if remote operation is required.

**A native remote object protocol has not been defined.** Do not create a 9P gateway, a file-shaped object service, or a generic compatibility boundary as a placeholder. In particular, do not let inherited `Chan`/`Dev` implementation details dictate GE/O object semantics. Solve the native identity, namespace, operation, and lifecycle questions first.

Authentication, users, and facilities analogous to Plan 9's `factotum` can be reconsidered in the object model. Their exact policy and kernel-enforcement mechanisms are not specified by this README.

## 7. What actually works today

The current **O-only PoC** demonstrates these operations in QEMU:

1. Open a GE-backed **native O volume** directly, without mounting an FS root.
2. Store and retrieve versioned objects using stable `(SpaceID, OID)` identities.
3. Seed an O volume with an Environment and compiled `.mpy` code; load that code from O at runtime.
4. Boot the normal amd64 path: embedded `oinit` loads the real MicroPython executable from O, restores the O-resident persistent `init` Space and runs its program.
5. Reboot the *same* ESP + O disk image three times: a saved counter advances **1 -> 2 -> 3**, preserving the same Python object identity and alias.
6. Reach an interactive REPL through the same O-loaded interpreter and keep a value across a restart of the same disk.

`tools/test-o-boot.sh` and `tools/test-o-boot-omp.sh` are the boot gates; `tools/mkrepl` prepares a disposable REPL disk for `./repl_tui.sh`. These results are documented test evidence, **not claims of production readiness or tests executed by every reader of this README**.

The remaining bootstrap dependencies are precise: the kernel still embeds `oinit` (reached through the inherited internal boot interface) and `kbdfs` (the console helper), plus the separate `ohandle`/`oexec` regression harnesses. MicroPython executable bytes, its Environment/code and persistent state come from O. This is not a claim that every runtime file interface has been removed.

### Critical limitations

**The native GE/O relationship graph described above does not yet exist in full.** The storage engine already supports OID-addressed, versioned records, but MicroPython currently serializes its whole persistent graph into **one `OID_GRAPH` object** on commit. The internal Python objects have persistent logical OIDs, but they are not yet independently stored and indexed as native GE/O objects and relationships.

Other current limitations include a small seeded `init` environment, limited native Space management, only a bounded native executable-object test path rather than a general loader, incomplete crash/failure recovery and diagnostics, and no defined native cross-process or network object protocol.

**Never mistake a design goal in this document for an implemented API.** The next experiments must close these gaps without inserting a filesystem facade.

## 8. Repository map and experiments

This repository descends from a much larger 9front/Plan 9 tree. That history explains existing source paths; it does **not** expand the scope of this PoC. The active architectural context should remain small and testable.

| Area | Current location |
| --- | --- |
| GE/O engine and native object records | `sys/src/9/gefs/` |
| Kernel-side native O system calls | `sys/src/9/port/devgefs.c` |
| MicroPython entry point | `sys/src/cmd/micropython/main.c` |
| Python persistence and Space integration | `sys/src/cmd/micropython/p9space.c` |
| Embedded bootstrap and console helper (`devroot`) | `sys/src/9/port/devroot.c`, `sys/src/cmd/oinit/` |
| O volume specification (implemented format) | `docs/O-FORMAT.md` |
| O volume and REPL image preparation | `tools/mkovol`, `tools/mkrepl` |
| Kernel driver operation map (generated, source analysis) | `docs/KERNEL-OPMAP.md`, `docs/KERNEL-OPMAP.json`, `tools/kernel_opmap.py` |
| Native O tests | `tools/test-o-volume.sh`, `tools/test-o-objects.sh`, `tools/test-o-exec.sh`, `tools/test-o-handles.sh` |
| Python/O and boot tests | `tools/test-o-space.sh`, `tools/test-o-boot.sh`, `tools/test-o-boot-omp.sh` |

**High-value next experiments:**

- Persist individual Python objects and **native GE/O namespace bindings/relationships**, without the monolithic `OID_GRAPH` snapshot.
- Demonstrate direct lookup by OID and indexed name, without path traversal; test sharing, aliases, cycles, and incremental commits.
- Extend the bounded native executable-object path beyond one test OID to catalogs and architecture selection, without `devroot` or a file wrapper.
- Define per-process object-handle lifetime and controlled sharing; replace current PoC-global handle bookkeeping.
- Test crashes, corrupt or missing objects, incomplete transactions, and recovery with machine-readable diagnostics.
- Establish which minimal kernel resource operations are actually required before designing any remote object protocol.

Tests and experiments may invalidate details of the design. Preserve the guiding principles while allowing implementation choices to change.

## 9. Development approach

Treat architecture as a hypothesis, the source as the implementation, and test logs as evidence. Keep these distinct. Prefer small reversible experiments to a prematurely fixed universal object model. Retain inherited Plan 9 mechanisms only when the current PoC needs them; they are not native design requirements.

Coding agents must follow [AGENTS.md](AGENTS.md). Verification and regression commands are maintained in [STATUS.md](docs/STATUS.md), not duplicated here.

---

**Plan2001-O retains files as object byte content, and removes the filesystem hierarchy as a required abstraction. Object identity and native graph relationships are independent of Python classes and Unix file metadata.**
