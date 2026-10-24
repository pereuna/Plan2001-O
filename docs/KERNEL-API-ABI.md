# Plan2001-O kernel API/ABI: terminology and boundary contract

**Status:** normative vocabulary and migration rules for **new Plan2001-O code**; proposed API/ABI design, **not an implemented or frozen binary ABI**.
**Revision:** 0.1, 2026-10-24.
**Source baseline inspected:** `main` at `373497917be36e03e36fd5f6a92d880fcf2a8bf2`. Source references are evidence at that revision, not eternal line numbers.
**Audience:** coding agents implementing or reviewing kernel, low-level C userspace, MicroPython bindings, and source-to-source migration. This is a working contract, not a general OS survey.
**Task boundary:** this document makes **no code changes**, adds **no syscall**, and does not authorize removal of working legacy paths.

## 0. Agent entry: rules to apply before editing code

1. **One concept, one canonical name.** In all new API/ABI names, type declarations, design documents, tests and agent reports, use the exact term defined in section 2 for that concept. Never swap `Queue`, `Stream`, `Pipe`, `Handle`, `Channel`, `File` or `OID` for stylistic variety. Same operation and semantics imply the same term; a different contract requires a different name.
2. **Keep meanings separate.** Hardware state, buffered data structures, transfer protocols, persistent data, resource references, and authorization are distinct layers, even if existing code happens to implement several in one C function.
3. **Reuse existing names when the meaning matches.** The kernel's real `Queue`, `Block`, `Pipe`, `Proc`, `VGAscr`, `Memimage`, `QLock`, `Rendez` and `Ohand` are starting points. Their existence does not mean they are safe or suitable for a public ABI.
4. **Do not make `Dev` a new generic `Device` class.** Prefer concrete C functions plus records with domain-specific names. Shared interfaces require a proven shared mechanism, not a universal `open/read/write/close` function table.
5. **A kernel C API is not a syscall ABI.** Kernel pointers never cross into userspace as usable pointers to kernel records. A handle value, a persistent OID, a C pointer and a permission grant are four different things.
6. **Never claim a proposed facility is implemented.** Use `EXISTING`, `LEGACY`, `PROPOSED` and `OPEN` as defined below, including in tests and reports.
7. **Migration is additive until tested.** Introduce/verify a concrete native operation first; let a legacy `Dev` branch delegate to the same logic; remove legacy routing only when all remaining callers and security/lifetime obligations are accounted for.
8. **Do not silently invent semantics.** When this contract or the inspected source does not settle allocation, EOF, blocking, framing, transfer, rights, memory lifetime, cancellation, error representation or ABI encoding, mark it `OPEN` and obtain a design decision before exposing a public interface.

**Terms are normative; sample proposed signatures are NOT declarations to copy verbatim.** The authoritative implemented signature always comes from the corresponding C header/source.

### Status vocabulary

| Status | Precise meaning |
| --- | --- |
| `EXISTING` | Concrete structure/function/behavior inspected in the current repository; still verify when editing another revision. |
| `LEGACY` | Existing inherited interface retained for compatibility, not the intended basis for a new native interface. |
| `PROPOSED` | Intended semantic distinction or migration direction; no implication that a named API/ABI exists. |
| `OPEN` | Contract or implementation choice not yet accepted. Do not guess. |

An existing mechanism can also be LEGACY. A semantic rule may be binding for new code while its implementation remains PROPOSED.

## 1. Four boundaries that must not collapse

`Hardware/controller ↔ kernel implementation ↔ kernel C API ↔ userspace ABI/client API`

- **Hardware/controller**: IRQs, I/O ports, mapped memory, DMA, device-specific operations, concrete device state.
- **Kernel implementation**: `Queue`, `Block`, `Lock`, `QLock`, `Rendez`, scheduling, buffering, format conversion, reference counting. Implementation details may change without becoming ABI.
- **Kernel C API**: directly callable C functions and C records for a defined operation, with documented caller context, ownership, locking, errors and side effects. Passing `T*` to another trusted kernel function is ordinary C, **not a userspace handle**.
- **Userspace ABI**: syscall entry/number, argument widths/layout/alignment, validated user memory, ownership, rights, lifetime, return/error encoding, blocking and compatibility rules. A language-level client API such as a MicroPython module is **not identical to** this ABI.

A fifth, independent concern is **GE/O persistent identity and contents**. It is not a device registry, kernel-memory pointer scheme or implicit live-resource namespace.

**Required proof for a "native/no Chan" claim:** trace actual called functions in the measured execution path and account for `Chan`, `Qid`, `namec`, `walk`, `Dev` dispatch, blocking/locks and authorization. An operation may be Chan-free without the whole driver or kernel becoming Chan-free.

## 2. Canonical glossary — authoritative definitions

The **canonical token** below is what new code and design prose must mean. `Source` names existing evidence, not a proposed new header. Terms shown as EXISTING can remain in inherited function names, even if an eventual public API is refactored.

| ID | Canonical term | Exact meaning and exclusion | Status / source |
| --- | --- | --- | --- |
| T01 | `Queue` | In-kernel **buffering and synchronization structure** for queued `Block` data; supports `qread`, `qwrite`, `qproduce`, `qpass`, `qclose` etc. Neither an end-user stream type nor a resource identifier. `Qmsg` alters framing behavior, so do not assume all queues have byte-stream semantics. | EXISTING: `sys/src/9/port/qio.c`, `portdat.h`, `portfns.h` |
| T02 | `Block` | Kernel-managed contiguous payload buffer with metadata/linkage used by queue and network paths. **Not** a disk block, an OID or a whole logical file. | EXISTING: `qio.c`, `portdat.h` |
| T03 | `Stream` | **Transfer/access semantics** for ordered bytes across an interface, without requiring random-access offsets or persistent storage. May be implemented using `Queue` or another mechanism. It is not the name of a `Queue` C struct and not an OID. | PROPOSED native boundary, already conceptually defined in `docs/OBJECT-MODEL.md`; inherited code also uses the word descriptively |
| T04 | `Pipe` | A **connection** joining two communicating ends; in inherited `devpipe.c`, a `Pipe` contains two `Queue*` and lifetime/reference accounting. Not a synonym for `Queue` or `Stream`. A pipe can provide stream transfer. | EXISTING structure, LEGACY `Dev` exposure: `sys/src/9/port/devpipe.c` |
| T05 | `Endpoint` | One independently usable **end of a connection** such as a pipe. An endpoint has direction/rights/lifetime under its eventual contract. **Not** automatically a `Chan`, fd, queue, OID or dedicated C type. | PROPOSED term for native connection APIs; ABI representation OPEN |
| T06 | `FIFO` | **Ordering property**, first-in-first-out; not a generic kernel subsystem or a second name for `Queue`/`Pipe`. Use only to state ordering behavior actually provided. | Terminology rule |
| T07 | `Message` | A bounded **unit of transferred data whose boundary matters**, rather than an arbitrary portion of a byte stream. `Qmsg` in `qio.c` is existing message-mode behavior; do not equate it with a specific public message ABI. | Existing internal queue mode; public contract OPEN |
| T08 | `Event` | A **reported occurrence**, with an event-specific contract (type, payload, ordering/time if relevant). Can be buffered in `Queue` or transferred over a `Stream`, but is not itself either. Raw keyboard scancodes do not become normalized `KeyEvent` records merely by renaming them. | PROPOSED general semantic term |
| T09 | `Handle` | A **lifetime-limited process-visible reference** resolved by kernel-maintained state. A handle is not a memory pointer, `fd`, `Chan`, `OID` or grant by itself. Which object it references and its attached rights must be specified per ABI. | PROPOSED general term; concrete narrower O Space implementation exists as `Ohand` |
| T10 | `Capability` | A **validatable authorization** for specified operations on a resource, with an explicit holder, scope and transfer/revocation rules. A numeric handle is not automatically a capability. Avoid this term for an unchecked integer or a mere global mask. | PROPOSED security contract; general implementation OPEN |
| T11 | `OID` | Persistent identifier of a stored occurrence, scoped to its defined GE/O `Space` (currently 64-bit). Not a byte address, `Handle`, `Chan`, path, global UUID or resource permission. | EXISTING scoped identity: `docs/O-FORMAT.md`, `docs/OBJECT-MODEL.md` |
| T12 | `Space` | GE/O persistence scope containing OID-addressed contents/versions. Not a process address space, device file tree or a `Queue`. | EXISTING O operations, `devgefs.c`; native graph relations remain a separate development target |
| T13 | `File` | **Finite byte content** of an identifiable stored occurrence in the Plan2001-O object model; excludes mandatory pathname/owner/stat/directory/Unix inode metadata. Not a `Stream` or `Pipe`, although a stream may transfer its bytes. | Normative architecture: `docs/OBJECT-MODEL.md`; storage profile described separately in `docs/O-FORMAT.md` |
| T14 | `Proc` | Kernel process record/current execution context. A process's PID is an integer observation, not an object pointer or `Handle` to an arbitrary process. | EXISTING: `portdat.h` |
| T15 | `Driver` | Code plus state that controls a **concrete device/controller class** (e.g. PS/2 controller, framebuffer). No universal `Dev` callback table required. | PROPOSED architectural use; concrete inherited code EXISTING |
| T16 | `Service` | Kernel-provided operation not necessarily tied to a physical device, e.g. process information, clock, logging or reboot. Do not categorize all `#c` functions as console hardware. | PROPOSED architectural use; concrete existing functions |
| T17 | `Console` | Textual diagnostics/input/output policy, potentially routed to screen or UART. Not the same as graphical `Screen`, raw framebuffer or `Keyboard` hardware. | EXISTING: `devcons.c`, `putstrn/putstrn0` and related routines |
| T18 | `Screen` | Visible **presentation surface** used by drawing/display. The name is a conceptual surface, NOT a declaration that a `Screen` C struct exists. Use actual `VGAscr`, `Memimage` and `Rectangle` where required by existing code. | EXISTING subsystem: `sys/src/9/pc/screen.c`; proposed native API OPEN |
| T19 | `Framebuffer` | Mapped or otherwise addressable **pixel storage** with format, dimensions, stride and access/flush rules. Not an application drawing protocol or necessarily the whole `Screen` state. | EXISTING implementation: `screen.c`, `bootscreeninit` |
| T20 | `Keyboard` | Physical/logical **input device source** with controller state, input delivery and optional LED control. Do not conflate PS/2-specific operations with a universal USB/HID protocol. | EXISTING PS/2 implementation: `sys/src/9/pc/devkbd.c`; common API OPEN |
| T21 | `Scancode` | Raw controller/protocol key code delivered by the existing PS/2 path, currently bytes in a queue. No implied Unicode code point or normalized key semantics. | EXISTING `Qscancode`: `devkbd.c` |
| T22 | `KeyEvent` | Interpreted/normalized key event **only if** a translation layer defines encoding, key state, modifiers and ordering. Not interchangeable with `Scancode`. | PROPOSED only; no general native `KeyEvent` ABI approved |
| T23 | `Dev` | Inherited Plan 9 device interface table (`attach/walk/stat/open/read/write/...`), even for nonhardware services. Not the new kernel driver model. | LEGACY/EXISTING: `portdat.h`, `devcons.c` etc. |
| T24 | `Chan` | Inherited **Plan 9 channel** with `Qid`, offset, flags and namespace/mount relations. Do not use "channel" as a synonym for `Queue`, `Stream` or native endpoint. | LEGACY/EXISTING: `portdat.h` |
| T25 | `Qid` / `Dirtab` / `Walkqid` | Inherited file-tree identity, directory table and traversal results. Not native operation identities, graph relations or OIDs. | LEGACY/EXISTING: `portdat.h` |
| T26 | `fd` / `Fgrp` | Inherited process file descriptor index/table mapping to `Chan*`. An `fd` is not the new generic `Handle`, although both can be represented numerically. | LEGACY/EXISTING: `sysfile.c`, `portdat.h` |
| T27 | `Ohand` / `Ohtab` | Existing **O-Space-specific** reference and per-process slot table used by native `OSPACE*` calls. This is a concrete instance of handle-like behavior, **not** a universal, rights-bearing capability system. | EXISTING: `sys/src/9/port/devgefs.c` |
| T28 | `Lock` / `QLock` / `Rendez` / `Ref` | Existing distinct kernel synchronization and lifetime primitives; none is a `Queue` merely because of the letter Q in `QLock`. Use actual types and proper interrupt/sleep context. | EXISTING: `portdat.h`, `qio.c` |
| T29 | `SDev` / `SDunit` / `SDifc` | Concrete C storage-controller registry, live unit and controller-operation interface. `SDifc` is a controller interface (`pnp`/`enable`/`verify`/`online`/`bio`/`rio`/...), not a new file-like `Dev`. A live `SDunit*` is kernel state, not an OID, pathname, userspace `Handle` or `Capability`. Native block calls use an absolute **unit byte offset**; the legacy `#S` adapter adds partition-relative offsets and `Chan` permissions separately. `sdcore.c` owns registry/unit/block operations; `devsd.c` remains the legacy `#S` adapter. | EXISTING/IMPLEMENTED: `sys/src/9/port/sd.h`, `sdcore.c`, `devsd.c`; evidence in `docs/SD-MIGRATION.md` |

### Disambiguation requirements

- "queue of keyboard scancodes" means a `Queue` whose payload is `Scancode` data; it does **not** mean a `KeyEvent` ABI or a generic `Stream` object type.
- "stream backed by a queue" means `Stream` transfer behavior implemented with `Queue`; neither name may replace the other.
- "pipe endpoint" refers to one end of `Pipe`. Its native representation may eventually be a `Handle`, but no such ABI is yet approved.
- "native O Space handle" means `Ohand/Ohtab`-mediated process-local access. An `OID` denotes persisted identity **within** that space, not the handle.
- "capability" only when a documented access right is actually validated. Today's `Proc.iomask` and inherited permission checks must be described by their **real** semantics; they do not automatically implement the proposed generic capability model.
- `Queue` and `QLock` are unrelated concepts, regardless of naming resemblance.
- A source code variable named `channel` does not establish that its value is a Plan 9 `Chan`; always check its declared type. Conversely, a `Chan*` remains legacy even when no path lookup occurred on a particular call.

## 3. Data movement model and contracts

All terms below are independent axes; do not collapse them into "an I/O object."

| Axis | Allowed distinction | Representative current mechanism | Requires an explicit decision when exposed |
| --- | --- | --- | --- |
| Information persistence | `File`/OID content and published version | GE/O `Space`, OID, get/put/commit | Publication/commit, version, errors |
| Transfer semantics | `Stream` (ordered bytes), `Message` (boundary preserved), discrete `Event` | `Queue` can serve different modes | Ordering, truncation, EOF, cancellation, blocking |
| Buffering | `Queue` and `Block` | `qio.c` | Boundedness, backpressure, allocation |
| Connection | `Pipe` with `Endpoint` roles | `devpipe.c` uses two `Queue*` | Direction, peer close, ownership, sharing |
| Authority/lifetime | `Handle` resolved for a process; `Capability` is a verified right | O `Ohand`, separate `iomask`, legacy `fd` | Ownership, grant, transfer, revoke, exec/exit |
| Device/action | `Driver` concrete operation, or `Service` operation | i8042, screen, console, `Proc` | Initialization, IRQ safety, privileges |

**Examples of semantics, not new APIs:**

```text
PS/2 interrupt -> Scancode bytes -> Queue -> approved reader
                                          ^         ^
                                          |         |
                                     buffering   transfer/API/ABI contract
```

```text
Pipe: Endpoint A <-> two internal Queue buffers <-> Endpoint B
                      (devpipe implementation)
```

```text
Space + OID -> finite File content/version
        |             |
    persistent     transferred in chunks as needed
    identity       (transfer does not change identity)
```

**In particular:** a stream is not guaranteed to persist; a file is not guaranteed to be an in-RAM byte array; a queue is not inherently a public stream; and a pipe does not have to be registered as a persistent OID.

## 4. API vs ABI: requirements and explicitly undecided parts

### 4.1 Kernel C API: direct, concrete, domain-specific

- Name a function for its **effect**, not for an artificial file operation (`present`, `flush`, `setleds`, `getscancode`, `transmit`, `readblocks`, `parentpid` as appropriate).
- Use a pointer to an existing concrete C record when needed for controller/surface/instance state. Passing many related arguments in a C record is allowed; do not invent universal `Device`, `Object` or `IoRequest` wrappers.
- Reuse the source's actual data types and lifetimes; e.g. the framebuffer code uses `VGAscr`, `Memimage` and `Rectangle`, not a verified type named `Display`.
- The kernel C contract for each operation **MUST** specify: required initialization; permissible execution context (IRQ, kproc/process, sleep); ownership and lifetime of records/buffers; input/output validity; locking; return/errors; side effects; reentrancy; and whether it uses any legacy `Chan` path.
- Do not hand-roll a second queue, timer, mutex or memory allocator when an existing kernel primitive with matching semantics suffices.
- Domain-specific operations may legitimately use `read`/`write` **when they truly transfer bytes**. Prohibition concerns turning every device action into a fictitious file with offset/stat/walk.

**Current executable examples, not proposed API:**
- `putstrn(char*, int)`: kernel text-output path; `devcons.c`.
- `flushmemscreen(Rectangle)`: screen-memory flush operation; `pc/screen.c`.
- `qread(Queue*, void*, int)`, `qwrite(Queue*, void*, int)`: queue operations; `qio.c`.
- `i8042intr` produces raw bytes into `kbd.q` through `qproduce`; `devkbd.c`.

**Design intent, not implemented signatures:** direct kernel calls for presenting dirty screen regions, reading raw keyboard scancodes, setting keyboard LEDs, and querying process information. Select their exact C identifiers and prototypes only after reviewing actual callers/types; do not code an imagined `Display*` or `Keyboard*` as though existing.

### 4.2 Userspace ABI: stable crossing, not direct kernel pointers

An eventual public operation MUST define:

| Field | Required contract |
| --- | --- |
| Operation | Stable semantic name and concrete effect; syscall number/dispatch, if a syscall is chosen |
| Identity/reference | Which process-visible handle or other explicit identifier is accepted; how resolved and validated |
| Access | Required grant, who bestows it, what is checked on each call, transfer/revocation policy |
| Memory | Integer widths, signedness, pointer/buffer direction, layout/size/alignment, user address checks |
| Lifetime | Creation/acquisition, duplicate/share (if supported), exec inheritance, process exit and close |
| Execution | Blocking, wakeups, cancellation, concurrency, interrupt safety, ordering and partial transfers |
| Result/error | Return values, errors, EOF/hangup, invalid handle, denied rights, device absent |
| Version | Supported architecture, call convention and compatibility/version negotiation where necessary |

An ordinary userspace `Handle` is not a `T*`; a kernel must resolve it before calling a trusted internal C function. A Python `import`/method name is a *language binding* above the ABI, not a specification of its implementation or persistent graph type.

**No general handle table, capability encoding, keyboard/display syscall numbers, stable `KeyEvent` structure or generic dispatch syscall is authorized by this document.** A future implementation requires a separate reviewed ABI decision covering the full table above.

### 4.3 Concrete existing ABI evidence

- Legacy `OPEN/PREAD/PWRITE/CLOSE/PIPE` and `fd` use `Chan`/`Fgrp`; see `sysfile.c` and `systab.h`. They remain for compatibility.
- Current O `OVOLOPEN` and `OSPACEOPEN/GET/PUT/CREATE/COMMIT/CLOSE` exist; `devgefs.c` owns process-local `Ohand` / `Ohtab`, validates user addresses and drops O handles on `oprocexec/oproc exit`. This is **not** a general device handle table or permission system.
- Current native `IOWRITE` uses a process `iomask` for constrained output grants (`docs/STATUS.md`, `sys/src/9/port/systab.h`). It does not specify a generic Stream API or a transfer-of-capability protocol.
- E4 has three reviewed native `readnum` reads in total: `native_rtc_read(...)` dispatches `Qrtc`, while `native_cons_read(selector, ...)` dispatches `Qpid` and `Qppid`. It is a **kernel-internal transitional dispatcher**, **not** a proposed universal driver or userspace ABI. Its numeric Qid-derived selectors are not persistent identifiers.
- E5 adds kernel-only service operations in `port/cons.c` (`consputstr`, `kmesgreadat`/`kmesgwrite`, `kprintacquire`/`kprintread`/`kprintrelease`, `consinit`), `port/procobs.c` (`procpid`, `procppid`, `procusername`, `proccputimes`) and `port/sysinfo.c` (`sysnameget`/`sysnameset`, `hostownerget`, `hostdomainget`, `configget`, `osversionget`, `sysstatget`/`sysstatreset`, `timecontrolallowed`, `nulldiscard`, `zerofill`). They take no `Chan*`, `Qid`, `Dirtab` or path. Existing `todget`/`todset`/`todsetfreq`, `randominit`/`randomread`, `rebootcmd`, `panic`, `rdb`, `userwrite`, `hostownerwrite` and `hostdomainwrite` are reused directly. No userspace ABI, syscall number or generic handle was added by E5.
- No generic rights-bearing `Handle`/`Capability` ABI for display and keyboard is implemented.

### 4.4 Security and identity separation

```text
Kernel pointer:  VGAscr*, Queue*, Proc*, Ohand*   (trusted kernel memory)
Handle:          process-visible index/token     (lifetime-limited; lookup needed)
Capability:      validated right(s)              (authorization, not merely a number)
OID:             persistent Space-scoped identity (does not grant device access)
Legacy fd:       inherited Fgrp->Chan reference   (not the new Handle ABI)
```

For a new public operation, do **not** infer rights from an accessible integer, a matching OID, an open legacy file, or an existing kernel pointer. E4's extracted `consread_qppid_read` relies on kernel-trusted callers and `up != nil`; the legacy `consdir` 0444 mode is not enforcement for arbitrary direct callers.

## 5. Real device boundaries: what migrates, what does not

### 5.1 `#c` is a legacy service aggregator, not a keyboard/display driver

`sys/src/9/port/devcons.c` currently registers `consdevtab` (`Dev`), implements `consattach`/`conswalk`/`consstat`/`consopen`/`consread`/`conswrite` and multiplexes unrelated responsibilities:

| Legacy `#c` path/branch | Native conceptual owner | Important preservation |
| --- | --- | --- |
| console text, `Qcons` | `Console` service | log ring (`kmesg`), routing to `screenputs`/UART, panic/print behavior, queue/locking |
| `Qpid`, `Qppid` | process service (`Proc`) | identity of current process, process-context requirement, formatting only in legacy wrapper |
| `Qtime`, `Qbintime` | time service | clock semantics, privilege for writes |
| `Qrandom` | random service | entropy/initialization and read semantics |
| `Qkmesg`, `Qkprint` | log service | one-reader/queue ownership, close/hangup semantics |
| `Qreboot` | system-control service | authorization and safe reboot behavior |
| `Qsysname`, `Qhostowner` etc. | system configuration | policy, lifetime, read/write validation |

**No single future `consdevtab` replacement should own all these services.** Separate by responsibility, not by a directory tree or artificial Python class.

Current E2/E4 shared helpers `consqpidread` and `consread_qppid_read` are a successful **transitional** extraction. A natural final process C API would produce typed process data rather than 12-byte formatted `readnum` records; its exact signature remains to be specified and checked. Retain compatibility wrappers until userspace migrations are proven.

### 5.2 Keyboard `#b` is separate from `#c`

`sys/src/9/pc/devkbd.c` currently exposes `Qscancode` and `Qleds` via `kbddevtab`:
- `i8042intr` reads the controller and calls `qproduce(kbd.q, &c, 1)`. `Queue` is the internal scancode buffer.
- `kbdpoll` can poll when the buffer is empty; `kbdread` performs `qread(kbd.q, ...)`. This is a *raw-scancode byte transfer*, not normalized `KeyEvent`.
- `kbdwrite` controls LEDs; `setleds` is controller-side behavior.
- `kbdopen` enforces `iseve()` and exclusive acquisition through `kbd.ref` for scancode reading; `kbdclose` releases it. These rules cannot disappear merely because `Chan` does.

A viable first native extraction separates **controller input / scancode buffering / ownership / reader ABI**, preserving actual PS/2 IRQ/polling behavior. If a new `KeyEvent` layer is later added, document raw-to-normalized conversion and support for other keyboard protocols separately. Never rename raw scancode bytes to `KeyEvent`.

### 5.3 Screen and display are not `#c`

- `sys/src/9/pc/screen.c` uses `VGAscr`, `Memimage`, framebuffer mappings and `Rectangle`; `bootscreeninit` initializes bootloader/firmware framebuffer state, while `flushmemscreen` flushes a changed area.
- `sys/src/9/port/devdraw.c` retains the legacy `#i` draw client/namespace path and substantial image/client lifetime logic.
- `sys/src/9/pc/devvga.c` is legacy VGA control (`#v`).
- `devcons.c` may route text to `screenputs`, or serial `uartputs`; neither creates a native screen ABI.
- `sys/src/9/port/devuart.c` exposes the UART driver and existing `PhysUart` callbacks.

Start with a concrete **screen presentation operation** that invokes established screen code, with explicit pixel-format, bounds, ownership, memory visibility and flush conditions. Do **not** mistake a proof that `flushmemscreen` works for a removal of `devdraw`, an implemented generic graphics ABI, or a keyboard driver conversion.

### 5.4 `Pipe`/`Stream`/`Queue` migration

In `sys/src/9/port/devpipe.c`, `Pipe` has two queue pointers (`q[2]`) and reference accounting (`qref[2]`); reads from one queue and writes into the peer's queue. Closing one end can hang up the peer. Any Chan-free pipe must preserve **both directions, ownership, peer hangup, buffering, backpressure, read/write blocking, and error delivery**.

This is a stronger test of lifecycle semantics than the three scalar E4 reads; it cannot be certified by copying an underlying `qread` call alone. Do not expose raw `Queue*` as a userspace "stream handle".

## 6. Naming rules for new code and generated code

The **semantic glossary IDs T01–T28** are the source of truth. Follow these rules even when porting legacy functionality:

1. **Function name = domain + action**, where it clarifies the operation. Prefer already-existing precise C names (`flushmemscreen`, `qread`) for existing behavior; do not mechanically rename them for consistency.
2. **A type name must say what its value represents.** `Queue*` is a buffering object. `Proc*` is process state. `OID` is durable identity. `Handle` is an unresolved process-local reference. None may stand in for the others.
3. **Do not append `stream`, `queue`, `pipe` or `event` to an API unless its contract meets T01–T08**. In particular do not name a method `read_event` when it still returns raw PS/2 scancode bytes.
4. **Existing kernel symbols are evidence, not universal prescriptions.** Historical names such as `qopen` and `pipeattach` may remain during migration. `qopen` allocates a queue; `pipeattach` creates a legacy channel. They do not establish an API-wide `open` operation.
5. **Never use `channel` as a generic euphemism.** `Chan` is a precise legacy structure; an endpoint, queue, byte stream and IPC connection each have their own term.
6. **No generic `Dev` replacement record/vtable without proof.** E.g. don't introduce `NativeDev.read/write/open/close` just to preserve the old callback slots.
7. **No fake OID mapping.** Do not make device IDs, syscall selector integers, queue pointers or kernel handles into stored olio OIDs without an explicit independently reviewed persistence design.
8. **No new public API before a normative ABI specification.** Function names for experimental internal calls can be selected locally; never assume exported ABI compatibility from naming similarity alone.
9. **Case is meaningful in C.** Canonical glossary names use capitalized concept words (`Queue`, `Pipe`, `Handle`); their existing symbols and proposed identifiers use the correct actual C casing (`Queue*`, `qread`, `Ohand`). Do not conflate a glossary term with a declaration.
10. **No speculative synonym tables.** Historical aliases are recorded for migration but are not permitted alternatives in new definitions. If source code says `fd`, call it a legacy file descriptor; do not relabel it `Handle` in technical claims.

### Acceptance examples

| Statement | Verdict | Why |
| --- | --- | --- |
| "`kbd.q` is a `Queue` of raw `Scancode` bytes." | ACCEPT | Actual kernel representation and payload semantics |
| "Expose `Queue*` to userspace as a `Stream` pointer." | REJECT | Implementation pointer crosses ABI; wrong abstraction |
| "`Pipe` uses two internal `Queue` buffers." | ACCEPT | Verified `devpipe.c` |
| "`FIFO` is the new generic keyboard/pipe type." | REJECT | Ordering property is not a resource kind |
| "The `OSPACEOPEN` integer is an O-Space-specific handle." | ACCEPT | Narrow existing ABI, explicit scope |
| "An OID is a capability or device handle." | REJECT | Persistent identity is not authorization or live resource |
| "`Qscancode` already emits portable `KeyEvent` objects." | REJECT | Current implementation reads raw bytes |
| "`Qppid` is now a Chan-free internal operation." | ACCEPT with scope | E4 internal path only; rest of `#c` remains legacy |
| "Replacing `Dev` with a generic object implementing file methods removes file semantics." | REJECT | Changes names, not semantics |
| "A normal device byte transfer can be named read/write." | ACCEPT | Actual byte transfers are permitted without file metadata |

## 7. Migration procedure for coding agents

For **each** selected operation, produce a minimal audit and prove each gate. An agent MUST NOT generalize from scalar E4 reads to an entire device or unrelated operations.

**M0 — Classify.** State device/service owner, current paths, all involved `Dev` branches, internal C functions, concrete structs, `Queue`/`Block`/`Pipe`/`Stream`/`Event` semantics, current callers and user-visible behavior. Use `tools/kernel_opmap.py` inventory as evidence, not semantic proof.

**M1 — Name and contract.** Reuse section 2. Specify data representation, kernel C signature, initialization, resource ownership, permissions, blocking/IRQ constraints, lifetime and failures. Clearly label proposals. Stop if one source identifier ambiguously denotes two glossary concepts.

**M2 — Split mechanically, fail closed.** Extract/reuse the concrete operation while leaving a narrow legacy `Dev` wrapper. Never discard a pre-dispatch side effect, guard, shared local or lifetime action. For generator-produced C, review exact source span, SHA, resulting patch and dependent call chain. `DIRECT-CANDIDATE` is **not** approval.

**M3 — Review access and ownership.** Legacy file permission checks do not transfer magically to a direct C call or new ABI. Preserve exclusive scancode ownership, pipe endpoint close rules, console locks/queues, and any process-specific authorization. No kernel pointer may be passed to userspace.

**M4 — Test the smallest meaningful slice.** Compile the actual sources, link where appropriate, test the native path with one bounded real QEMU probe and preserve one pertinent legacy behavior test. Include one negative for denied access or invalid resource and one for end-of-stream/hangup if relevant. No massive unrelated battery without cause.

**M5 — Document the result.** Record commit, exact source/helper, glossary IDs, ABI status, changed files, tests actually executed (PASS/FAIL/NOT RUN), evidence/log location, and remaining `Chan` edges. Update this document if a new approved semantic category truly arose, not to retroactively rationalize an implementation.

**M6 — Remove old code only with proof.** Account for all former `attach/walk/stat/open/read/write/close` users, init/IRQ/shutdown, mixed-mode and recovery paths. No source deletion merely because a new API appears to work.

### Small required change report (machine-readable prose keys)

```text
OPERATION:
SOURCE_REV:
SOURCE_C_PATHS:
CANONICAL_TERMS: Txx, Tyy, ...
CURRENT_LEGACY_ENTRY:
NATIVE_KERNEL_CALL:
USER_ABI: EXISTING / PROPOSED / NONE
BUFFERING_AND_TRANSFER: Queue / Stream / Message / Event / Pipe / N/A
OWNERSHIP_AND_LIFETIME:
AUTHORIZATION:
IRQ_BLOCKING_AND_LOCKS:
PERSISTENT_IDENTITY: OID / NONE
NATIVE_PATH_CHAN_DEPENDENCIES:
TESTS_ACTUALLY_RUN:
UNDECIDED_CONTRACTS:
VERDICT: APPROVE / HOLD / REJECT
```

A report with `NONE` or `N/A` is acceptable when true. Invented universality is not.

## 8. Unresolved decisions — explicit design boundaries

These are **not** left to individual coding agents to decide implicitly:

- Generic `Handle` table format, generation numbers, types, sharing/duplication and stale-reference guarantees.
- Whether authorization should be represented by an explicit `Capability` type, rights on a handle, process-local grants, or a combination; transfer/revocation and exec inheritance.
- Public keyboard ABI: raw scancodes versus normalized `KeyEvent`s; layout, versioning, exclusivity/fanout, USB/HID translation, wait and cancellation.
- Public screen ABI: pixel buffers or higher-level commands, ownership of framebuffer mappings, flush timing, format/mode changes, multiple clients and security.
- General `Stream` and `Pipe` ABI, byte vs message modes, half-close/hangup, endpoint ownership, partial I/O and error model.
- Public syscall numbering, stable data type widths, return/error encoding, ABI versioning and language bindings.
- Exactly which `#c` services merit userspace exposure versus only trusted kernel C functions.
- How (if ever) a live service/resource is named in the future GE/O graph; no mandatory OID for a device or process is implied.

Until separately approved, preserve the existing narrow interfaces rather than exposing an invented public ABI.

## 9. Source and evidence index

Use these as entry points. **Inspect the specific current version before modifying it**; the source is the authority on IMPLEMENTED behavior, this document on new terminology.

| Component | Evidence path | What to inspect |
| --- | --- | --- |
| Core types, Dev/Chan/Queue declarations | `sys/src/9/port/portdat.h` | `Chan` and `Dev` struct, `Fgrp`/`Proc`, incomplete `Queue`, `Qmsg` flags |
| Queue implementation and API | `sys/src/9/port/qio.c`, `portfns.h` | `Queue` internals, `qread`, `qwrite`, `qproduce`, `qhangup`, blocking/framing |
| Pipe | `sys/src/9/port/devpipe.c` | `Pipe.q[2]`, `qref[2]`, data0/data1 paths, open/close/hangup |
| Console | `sys/src/9/port/devcons.c` | `consdevtab`, `consread` and writes, `putstrn0`, E4 Qpid/Qppid |
| PS/2 keyboard | `sys/src/9/pc/devkbd.c` | `i8042intr`, `kbd.q`, `kbdpoll`, `kbdopen`/exclusive reader, LED writes |
| Screen/FB | `sys/src/9/pc/screen.c` | `VGAscr`, `Memimage`, `bootscreeninit`, `flushmemscreen` |
| Legacy drawing and VGA | `sys/src/9/port/devdraw.c`, `sys/src/9/pc/devvga.c` | drawing client lifetime, Dev dispatch, VGA control |
| UART | `sys/src/9/port/devuart.c` | queueing, UART callbacks, console routing |
| Legacy fd ABI | `sys/src/9/port/sysfile.c`, `systab.h` | `fd → Fgrp → Chan` resolution and legacy syscalls |
| Native O Space handles | `sys/src/9/port/devgefs.c` | `Ohand`, `Ohtab`, `ohandles`, `OSPACE*`, exec/exit release |
| Native extraction tool | `tools/kernel_opmap.py`, `docs/KERNEL-NATIVE-GENERATOR.md` | E4 review bindings, generated helpers, fail-closed proposals |
| E4 acceptance and limits | `docs/to_astra_review.md`, `docs/STATUS.md` | actual tests and bounded QEMU claim |
| File, Stream, OID, semantic object | `docs/OBJECT-MODEL.md`, `docs/O-FORMAT.md` | architectural distinction versus implemented O storage |
| Kernel map | `docs/KERNEL-OPMAP.json`, `docs/KERNEL-OPMAP-NOTES.md` | machine-auditable graph, unresolved edges; do not dump entire JSON into normal agent context |

### Document update rule

This file is the **single canonical glossary for the native kernel API/ABI**. Changes to terminology require (a) evidence of collision or a previously undefined concept, (b) a stable revised glossary entry/ID, (c) a list of affected call sites/docs/tests, (d) explicit status and compatibility consequences, and (e) an approval separate from merely passing a build.

Do not create a competing glossary in `AGENTS.md` or an agent prompt. Agents may link to this document and quote the relevant stable IDs. If existing code contradicts a proposed API, document the difference; **do not claim the implementation already conforms**.

**Acceptance principle:** a reader must be able to determine whether a particular name denotes a data structure, a transferred byte sequence, a connection, an event, an ephemeral process reference, an authorization grant, or a persistent identity — without inspecting what the writer "probably meant."