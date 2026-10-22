# Plan2001-O

**An experimental object-native operating system: persistent object identity rather than a mandatory filesystem hierarchy. Native relationships and direct executable-object loading are research goals.**

Plan2001-O explores an operating system in which **objects, rather than files, are the fundamental persistent entities**. Objects have identities independent of names or locations. The target architecture stores objects and their relationships natively in **GE/O**, a storage engine operating directly on a block-device partition. **Today's PoC stores versioned native O objects, but its persistent Python graph is still serialized into one `OID_GRAPH` object.**

The project is derived from Plan 9 / 9front, but it is **not an effort to reproduce Plan 9, Unix, POSIX, or their file-based interfaces**. Existing code is a starting point, not an architectural constraint. The goal is to discover a smaller, coherent object-native system through working experiments.

> **Core principle:** GE/O owns the persistent object and relationship model. Python is a client and a demonstration of that model—not the definition of it.

## Current implementation versus target

This README describes the **architectural hypothesis**. The following table distinguishes it from the imported, working O-only proof of concept. A feature present in source is not automatically a test result from this repository.

| Concern | Imported O-only PoC | Target / open experiment |
| --- | --- | --- |
| Persistent identity | Versioned GE/O records addressed by `(SpaceID, OID)` | Keep identity independent of location |
| Relationships | Python graph serialized as one `OID_GRAPH` object | Native, indexed GE/O bindings and relations |
| Namespaces | Seeded `init` Space and flat catalog | Persistent, shareable, non-hierarchical namespaces |
| Python | Kernel-embedded user-space MicroPython; code and state from O | Ordinary executable object loaded from O |
| Native executables | Embedded `/boot/mp` bootstrap plus a bounded test loader executing one O object by OID | General native object-ID-based loader |
| Process/remote interfaces | Inherited Plan 9 mechanisms for the PoC | Object handles, IPC and remote protocol to be explored |

**Document roles:** [README](README.md) explains the hypothesis; [POC](docs/POC.md) records what the source-branch experiments demonstrated; [STATUS](docs/STATUS.md) reports current verification and test instructions; [O-FORMAT](docs/O-FORMAT.md) specifies the *implemented* format. [AGENTS](AGENTS.md) is the coding-agent contract. Neither this README nor its diagrams establish an implemented API.

## 1. Objects are the native storage model

An object has a stable identity, content, and potentially relationships to other objects:

```text
GE/O volume
  SpaceID 1
    OID 100   universal text
    OID 101   Python source or compiled code
    OID 102   native amd64 executable
    OID 103   native arm64 executable
    OID 104   structured application data
    OID 105   namespace

    relationships and named bindings (native GE/O indexes)
```

**Identity is not a path.** The current on-disk format identifies object records by `(SpaceID, OID)` and stores their versions in GE's key/value tree. An OID is stable within its Space; it is not a globally unique identifier across all possible volumes and Spaces. Versioning and transactions are part of the object store.

Objects are not forbidden from being byte sequences. A source program, UTF-8 text, image, or machine-code binary is still ultimately bytes. **Offset-based read/write and seek-like cursors remain useful** for objects with byte-addressable content. What disappears is the requirement that every resource be represented as a *file in a directory tree*.

The native GE/O interface may therefore expose both content access and structured object operations. It must not assume that all object types have identical methods or that a pathname is necessary to obtain an object handle.

## 2. The relationship graph belongs to GE/O

**Target architecture:** relationships are native persistent data, indexed by GE/O and accessible independently of Python. They must not remain merely pointers hidden in a serialized MicroPython heap. **This is not yet implemented:** the current Python graph is written to one `OID_GRAPH` record.

A minimal useful model is a named binding:

```text
(namespace OID, name) -> target OID
```

For example:

```text
Namespace A (OID 10)
    "foo" -----> Module foo (OID 100)
    "bar" -----> Module bar (OID 200)
    "counter" -> Object     (OID 300)

Namespace B (OID 20)
    "foo" -----> Module foo (OID 100)
```

Two namespaces may refer to **the same object**, without copying it and without assigning it a canonical directory location. A namespace can itself be a persistent object. Its bindings can be committed and restored across boots, independently of the processes that use it.

General relationships may later include typed, directed, or multivalued edges. **The exact representation of an edge is still a research question**: it may be an indexed record, an object with its own OID, or both where appropriate. Do not invent a universal edge schema before it is needed by an experiment.

The graph may contain cycles. A cycle is valid persistent structure, not automatically an error. Traversal algorithms must handle cycles when they enumerate reachable objects, but **finding an object must not require traversing the graph**:

```text
(SpaceID, OID)         -> object
(namespace OID, name) -> target OID
(tag / indexed query) -> matching OIDs
```

Direct lookup and indexed relationships are central to the design. Tags are names or indexed relations, **not disguised filesystem paths**. A general tag index and a fully native relationship schema are goals, not implemented PoC features.

A relationship also need not mean communication. A namespace binding points to an object; a *Kahn process network* FIFO transfers values between running processes. A channel may itself have an object identity and be discoverable through the graph, but its message flow is a separate runtime behavior. Object relationships, process communication, ownership, and execution must not be conflated.

## 3. Python is the first object-native programming environment

Python replaces the traditional OS scripting layer: `rc`, `sh`, `awk`, and filesystem-based `init` scripts. It provides a familiar language for boot configuration, administration, automation, and applications, while demonstrating persistent state at much finer granularity than saved files.

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

A persistent namespace may bind `foo`, `bar`, `counter`, and `run` to their corresponding persistent representations. The objects can outlive the interpreter process and remain identifiable after reboot. Imports resolve code and establish bindings without requiring `.py` files in directories.

**Python semantics remain Python semantics.** `import foo` includes module resolution, loading, and initialization. `a.foo` is attribute access, which may involve descriptors, inheritance, or custom methods. GE/O provides durable identity and bindings; it does not need to implement Python's language-specific attribute rules in the kernel.

Not every Python value needs a separately allocated GE/O record, and not every runtime resource can or should survive a reboot. The persistence boundary, primitive-value representation, code identity, interpreter compatibility, and object lifecycle must be tested explicitly.

`pip`-style package installation, arbitrary third-party Python compatibility, and fine-grained persistence for every Python object are **not implemented**. Source archives may be used by host-side preparation tools without making a filesystem the native runtime storage model.

## 4. GE/O stores programs—not just Python data

A persistent object may contain text, a module definition, a native executable, or any other byte-addressable or structured content. The target system must be able to load architecture-specific programs **directly from GE/O**.

One possible organization is:

```text
Program object (OID 500)
    "source"  -----> Source text  (OID 501)
    "amd64"   -----> Executable   (OID 502)
    "arm64"   -----> Executable   (OID 503)
    "riscv64" -----> Executable   (OID 504)
```

Here the arrows illustrate possible native relationships, **not an implemented program schema**. The loader selects the appropriate code representation for the current machine, maps executable memory, and starts a process. It does not need `/bin/program` or a synthetic file interface to do so.

MicroPython is intended to become one such loadable program. **The kernel must not depend on Python**; another native program could serve as the initial user process. Executable formats, ABI compatibility, code integrity, selection policy, and process permissions remain separate engineering questions.

## 5. Boot without a root filesystem or initramfs

### Working PoC

```text
UEFI / EFI System Partition
             |
          bootloader
             |
       Plan2001 kernel
             |
   embedded MicroPython binary
             |
       GE/O O partition
             |
    persistent "init" Space
             |
           run()
```

The current kernel image embeds a normal **user-space MicroPython executable** and its console helper. Inherited Plan 9 `devroot` code exposes those embedded bytes as `/boot/mp` and `/boot/kbdfs` for the existing program loader. This is a tiny, read-only kernel-memory file interface, **not initramfs, a disk filesystem, or the target object architecture**.

Once running, the PoC loads the Python Environment, compiled `.mpy` definitions, and persistent state **from the O partition without mounting a filesystem root**. The EFI System Partition and the developer's build-host files are boot/build inputs, not evidence that the O runtime needs files.

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

The current embedded MicroPython executable is a practical bootstrap, **not a permanent architectural requirement**. A future kernel should load executable objects from O and provide a small diagnostic path if that volume is missing or corrupt. This design does not require an initramfs or another root filesystem.

Do not replace the embedded executable with an initramfs or a pseudo-filesystem merely to preserve traditional `exec(path)` behavior. A bounded native executable-object experiment now exists; extending it to a general program loader remains work.

## 6. What about Plan 9 and 9P2000?

Plan 9 presents files, devices, and services through per-process hierarchical namespaces. Its `Chan` and `Dev` abstractions expose operations such as `walk`, `open`, `read`, and `write`; `devmnt` translates relevant operations into **9P2000** requests when a file server is involved. A `fid` is a connection-scoped protocol handle; a `qid` is a server-scoped file identifier. Neither defines Plan2001's persistent object identity.

Plan2001 retains useful *mechanisms* only where justified by experiments: process scheduling, memory protection, resource lifetime, reference management, device access, and byte-oriented I/O. **It does not adopt the file hierarchy, `walk`, `fid`, `qid`, or 9P2000 as the native object model.**

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
4. Boot an embedded MicroPython interpreter into an O-resident persistent `init` Space and run its program.
5. Reboot the *same* ESP + O disk image three times: a saved counter advances **1 -> 2 -> 3**, preserving the same Python object identity and alias.

The test script is `tools/test-o-boot.sh`. These results are documented PoC test evidence, **not claims of production readiness or tests executed by every reader of this README**.

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
| Existing embedded-boot implementation | `sys/src/9/port/devroot.c` |
| O volume specification (implemented format) | `docs/O-FORMAT.md` |
| O volume preparation | `tools/mkovol` |
| Native O tests | `tools/test-o-volume.sh`, `tools/test-o-objects.sh` |
| Python/O tests | `tools/test-o-space.sh`, `tools/test-o-boot.sh` |

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

**Plan2001-O asks what an operating system becomes when persistent identity and graph relationships are native, programs are objects, and the filesystem hierarchy is no longer the foundation.**
