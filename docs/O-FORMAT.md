# O Volume Format v1 — implemented experimental specification

**Scope:** the O-only PoC imported from `pereuna/Plan2001` at
`436ed30c894c4060638341ecebe82004d457f496`.
This document describes the **implemented** O profile and its current
MicroPython payloads, not the proposed native relationship graph.
It is an experimental format; it has no production compatibility promise.
See [POC.md](POC.md) for experiment history and [STATUS.md](STATUS.md)
for current verification.

## 1. GE volume and O profile

O is a profile of GE, **not** a second disk filesystem or allocator.
It reuses GE's superblock, arenas, allocation logs, snapshot key/value
tree, recovery mechanisms and sync machinery. It has no FS root,
directory tree, `adm` tree or 9P service.

The GE superblock retains version string `gefs9.00`.
Its `flag` field distinguishes profiles:

- `Ovolflag`: bit 63 set means native O volume.
- `Ovolvermask`: low 8 bits hold the O format version, currently **1**.
- The inherited FS profile has bit 63 clear (normally `flag == 0`).

The legacy FS opener `loadfs` rejects O volumes. The O opener `oopen`
requires the O bit, version 1 and catalog binding `init -> SpaceID 1`;
it rejects an FS volume. Opening **never** formats a volume, and an
ordinary boot does not initialize or repair missing O data.

References: `sys/src/9/gefs/o.c`, `sys/src/9/gefs/load.c`.

## 2. Flat Space catalog

Named catalog records are entries in GE's snapshot key/value tree.
For name `n`, the key and value are:

```text
key   = Ko | name_bytes                 # no terminating NUL
value = record_bytes
```

Names are **flat identifiers**. They are not directory paths and do
not imply parent traversal, path normalization or mount operations.
Version 1 seeds:

```text
Ko | "init"  ->  SpaceID = 1 (unsigned 64-bit little-endian)
```

`test.value` is a separate plain `Ko` record used by the GE/O
persistence regression. The current PoC has no general catalog
creation API or native namespace graph. The scope of an OID is its
Space; `(SpaceID, OID)` identifies an object *within the volume*.

Reference: `sys/src/9/gefs/o.c`.

## 3. Native object records

Object storage reuses GE's `Kobj` versioning engine. The older
filesystem-backed `DMOBJ` adapter uses a file's `qid.path` as its
store ID; **native O** instead uses the stable `SpaceID`. Native
operations enter the engine directly and do not use `fid`, `qid`,
a file path or a 9P object service.

```text
key:   Kobj | SpaceID[8]
value: N[8] | K[8] | W[8] | user[...]

key:   Kobj | SpaceID[8] | OID[8] | ~version[8] | chunk_index[4]
value: chunk_bytes
```

Integer fields use the engine's packed integer representation.
`N` is the latest published version; `K` is the oldest retained
version; `W` is the last begun transaction version. Each object's
visible value is the newest version `<= N`. `~version` means the
bitwise-complemented encoded version, which sorts recent versions
first in the key index.

For object data, chunk index 0 begins with a 4-byte length followed
by payload bytes. A length of `0xffffffff` denotes a tombstone.
Subsequent chunks continue the payload. Missing objects or
tombstones are not returned as live values. Version `N=0` denotes
an empty Space. The PoC's object read assembles a **whole** value
into a supplied buffer; it does not expose a native streaming cursor.

References: `sys/src/9/gefs/obj.c`, `sys/src/9/gefs/gdat.h`.

## 4. Transactions and visibility

- `ospaceget` sees **published** versions, not uncommitted writes.
- The first `ospaceput` begins a Space transaction. Its writes
  are initially invisible to published readers.
- `ospacecommit` publishes the version through GE's tree update
  and synchronizes it. A commit with no open transaction returns
  the already published version.
- The current Space handle has a writer lock; engine transaction
  rules reject concurrent begins for the same SpaceID.
- Closing a handle with an unfinished transaction aborts it.
  GE uses `W > N` to detect possibly abandoned versions and sweep
  them on a subsequent begin.

These are current PoC semantics, **not** a durability, concurrency
or crash-recovery guarantee for arbitrary failures. The engine's
limited retained version history is not a general immutable object
history API.

Reference: `sys/src/9/gefs/obj.c`.

## 5. Native engine API and system-call boundary

The GE/O kernel API in `sys/src/9/gefs/obj.c` is:

```text
ospaceopen(volume, "init")                 -> Ospace
ospaceget(space, oid, buffer, len, &ver)   -> length or -1
ospaceput(space, oid, buffer, len)
ospacecommit(space)                        -> published version
ospaceclose(space)
```

The PoC's direct user-space syscall interface is implemented in
`sys/src/9/port/devgefs.c` and exposed through
`sys/src/libc/9syscall/sys.h`:

```text
ovolopen(spec, len)                        -> volume handle
ospaceopen(vol, name, len)                 -> Space handle
ospaceget(space, oid, buf, len, &ver)      -> bytes or -1
ospaceput(space, oid, buf, len)
ospacecommit(space, &ver)                  -> publish and sync
ospaceclose(space)
oexecute(space, oid, argv, argc)            -> execute object (no return on success)
```

`spec` may denote `PARTUUID=...` or a device specification.
A `nil` buffer and length zero request the object's size.
The kernel owns `Gefs` and `Ospace` pointers; callers see integer
handles. This boundary does not use `#G`, a device file, pathname
lookup, 9P or a synthetic filesystem for object operations.

### 5.1 Process-local runtime handles

The on-disk format is **unchanged**. The following is runtime state
only; no handle record is stored in GE/O.

- Each process has its own eight-entry O Space handle table. Resolving
  an integer handle uses only the calling process. The same integer in
  two processes can name different sessions.
- `(SpaceID, OID)` remains the persistent object identity. A handle is
  a process-local runtime session, not an object identity and not a
  durable capability.
- Opening allocates a session and one ownership reference. Lookup
  takes a temporary reference under the table lock; the reference is
  released on success and error. The table lock is not held during
  storage operations.
- Explicit close removes the table entry and drops its ownership
  reference. The last reference closes the native `Ospace`; an
  unfinished transaction is aborted by the existing engine path.
  Cleanup never commits implicitly.
- Process exit releases all remaining handles. The exiting process's
  table is detached before the sessions are released, so one failing
  close cannot hide the others. A reused `Proc` starts with no table.
- A child starts with an empty table, including `RFMEM` children.
  Successful `exec` closes all handles; failed `exec` preserves them.
  Handle inheritance and cross-process transfer are deferred.
- Closing an already closed or invalid handle fails; it does not
  affect another process's table.

The volume instance (`Gefs *ovol`) is still global to this
experiment. Volume acquisition and authorization remain separate work;
these process-local handles do **not** constitute complete capability
security.

### 5.2 Native executable-object loading (bounded experiment)

`oexecute(space, oid, argv, argc)` resolves `space` only in the calling
process, reads one published object value, and follows `exec` semantics:
on success the calling process is replaced and does not return; on
failure the original image and its handles remain. The on-disk format is
unchanged. `argc` is bounded (32); `argc == 0` keeps the original
synthetic `oexec <oid>` argv[0].

The read is a **bounded whole-object read**. The kernel allocates
`8 MiB` (`Objexecmax`) for the object, so this temporary memory cost is
paid even for a small executable, and an object larger than the limit is
rejected. There is no size-then-read pair: `ospaceget` selects one
published version and copies that version's bytes in a single call, so
the header and payload cannot come from different versions. The real
MicroPython executable is 2,191,593 bytes, so the limit is unchanged.

The loader reuses the existing `Exec`/a.out validation and segment
machinery. Before committing it checks the architecture magic, header
length, text/data/bss sizes, segment bounds and rounding, object length
against `text+data`, the entry point's membership in the text segment,
and the user-address bounds. Segment addresses (`adata`, `abss`, `ebss`)
remain `uintptr`; only sizes are narrower. It then builds ordinary text,
data and BSS segments and the exec stack, and enters the shared
process-transition path.

The `argv` interface is Plan 9's bounded pointer-and-count form. The
kernel checks the array alignment and mapping, every string pointer and
NUL termination, the argument count and total byte length, and the
resulting stack bounds. It copies the strings into kernel-owned memory
before the process image is replaced, then builds the new stack with
`sizeof(Tos)` reserved first and argv and its strings below that
reservation. The strings and argv array do not overlap. No pathname,
synthetic file, `Chan`, `Fid`, Qid, mount or 9P operation is involved.
Successful transition applies the current close-on-exec O handle rule.

Native segments carry no file image, so the shared loader sets an
internal `SG_NOSWAP` flag on its text, data, BSS and stack segments and
`dupseg()` tolerates a data segment whose `image` is `nil`. This keeps
`rfork` and the page reclaimer from treating the loaded bytes as
file-backed or swappable pages. Those pages stay resident instead of
being reclaimed; the bounded image, BSS and stack are the memory cost.
It does not change the on-disk format.

Test and bootstrap objects are seeded through the existing `gefs -O -i`
seed layout:

```text
OID_EXEC_TEST    = 0x4f45584543000001   small amd64 executable (BSS test)
OID_BADEXEC_TEST = 0x4f45584543000002   truncated executable header
OID_MP_EXEC      = 0x4f45584543000003   real MicroPython amd64 executable
```

`tools/mkovol ... SOURCE` accepts `NATIVEEXEC=FILE`, which is stored
under `OID_EXEC_TEST` (plus the malformed test record), and
`MPEXEC=FILE`, which is stored byte for byte under `OID_MP_EXEC`.
For the BSS boundary regression only, the host seeding path patches the
`NATIVEEXEC` target's BSS header field to `0xffffffff`, so the BSS extent
crosses 4 GiB and the program probes a high BSS page. The MicroPython
seed is never patched; `tools/oseed.py` reads the copy back and the
`/boot/oinit` harness prints the SHA-256 of the object read from O, which
the regression compares with the host binary.

The seed builder in `sys/src/cmd/gefs/ream.c` builds a sorted GE tree
bottom-up from the seed records. Small seeds are still one leaf; a large
executable is split into many leaf blocks with pivot blocks above them.
The seed is therefore not limited to one catalog leaf, and the on-disk
record representation is unchanged. `/boot/oinit` is the small embedded
bootstrap harness; `/boot/oexec` remains the native-exec regression
harness. Neither is the loader and neither is a production bootstrap.

Limits of this experiment: no program catalog, architecture selection,
permissions, dynamic linking, or general executable-object format
support. It does not remove `devroot` or `kbdfs` from the ordinary boot
configuration, and it does not change the on-disk format.

References: `sys/src/9/port/devgefs.c`, `sys/src/9/port/sysproc.c`,
`sys/src/cmd/oinit/oinit.c`, `tools/test-o-boot-omp.sh`.

## 6. Reserved OIDs and MicroPython payloads

The current seeded `init` Space reserves:

```text
OID_ENV     = 0xfffffffffffffffc   Environment manifest
OID_GRAPH   = 0xfffffffffffffffd   serialized Python graph stream
OID_CODE    = 0xffffffff00000000   base of host-assigned code OIDs
OID_MP_EXEC = 0x4f45584543000003   experimental MicroPython executable
```

The Environment manifest is an object containing text:

```text
runtime <mp-version>-mpy<MPY_VERSION>.<MPY_SUB_VERSION>
<import_name> <definition_sha256> <mpy_sha256> <code_oid_16_hex>
```

The source definition's SHA-256 determines its definition identity.
Each code OID refers to a compiled `.mpy` payload verified by its
SHA-256; the loader also checks the MicroPython MPY ABI. On the
native O import path there is no file search path, source fallback
or `sys.path` lookup. Host-side preparation may still use files.

**The Python graph is not a GE/O-native edge index.** At commit,
MicroPython turns the V7 graph's object stream into one byte stream
stored at `OID_GRAPH`. It contains a header and per-Python-object
records, conceptually:

```text
'H' | graph_N[8] | graph_K[8] | user_length[4] | user[72]
'o' | python_oid[8] | graph_version[8] | byte_length[8] | bytes
... repeated 'o' records
```

The 72-byte user header includes the Environment hash and the
next-Python-OID value. Python objects in this *internal stream* have
logical OIDs and can preserve identity and aliases after reboot, but
**they do not each have a separate native GE/O `Kobj` record**.
The graph stream's version and the enclosing O Space's version are
separate counters. On commit the graph is rewritten as a whole.
The Environment and referenced code objects are put again in the
same O transaction to keep them available under history sweeping.

References: `sys/src/cmd/micropython/p9space.c` and
`sys/src/cmd/micropython/p9image.c`.

## 7. Preparation, seeding and initialization

`tools/mkovol OUT [MIB] [SOURCE]` formats a **fresh disposable
image** using the built `gefs -O` program in the 9front build VM.
The default image size is 512 MiB; the minimum is 129 MiB because
GE ream requires more than 128 MiB. This operation **formats its
output**: never point it at a disk containing data.

If `SOURCE` is supplied, the host-side setup compiles and seeds
one demo Environment and its `.mpy` code through
`tools/oseed.py` and `gefs -O -i`. The PoC seeds a small, fixed
catalog/Environment. This is not general package management.

The ordinary O-only boot configuration still embeds MicroPython:

```text
UEFI -> kernel -> inherited /boot/mp user-space executable
             -> -O PARTUUID=... -S init -B
             -> restore/initialize the O-resident init Space
             -> call persistent run()
```

The embedded `/boot/mp` executable and `/boot/kbdfs` helper are
made visible through inherited read-only `devroot` machinery; they
are **not** an initramfs, the O volume or a native executable loader.

The bounded O-loaded test configuration `pc64omp` embeds no
MicroPython. Its generated boot directory contains only `oinit` and
the `kbdfs` console helper:

```text
UEFI -> kernel (9pc64omp) -> /boot/oinit -vol PARTUUID=...
             -> ovolopen + ospaceopen("init")
             -> oexecute(space, OID_MP_EXEC, argv, argc)
             -> argv: micropython -O PARTUUID=... -S init -B
             -> boot.py + kbdfs; Environment, code and init Space from O
             -> commit; persistent run()
```

The same harness with `-repl` passes `-O PARTUUID=... -B` (no `-S`),
so `boot.py` sets up the console and the O-loaded interpreter reaches
its REPL. The harness contains no MicroPython copy and opens no
executable file. The ordinary `pc64` configuration and its embedded
`/boot/mp` path are unchanged.

On the **first** O boot, missing `OID_GRAPH` causes import of the
seeded demo module `odemo`. Its top level and `init()` initialize
state and persistent `run`. On later boots the Space and `run`
are restored without rerunning module initialization. On normal
return, the interpreter commits and syncs. An unhandled exception
skips the final commit; the previous published version remains.
The tested three-boot result is `1 -> 2 -> 3` on the same disk.

References: `sys/src/cmd/micropython/main.c`,
`sys/src/cmd/micropython/p9space.c`, `tools/mkovol`.

## 8. Compatibility and limits

- The superblock O-profile version is **1**. There is no declared
  stable compatibility contract or migration tool for future formats.
- A flat seeded `init` Space is not a general persistent namespace
  or relation model. There is no native tag/edge index yet.
- The current Python payload format is separate from GE/O's native
  object-record layout and must not be generalized into the native
  graph specification.
- The PoC relies on a fixed module seed, one native O volume, a small
  per-process Space-handle table and whole-value object reads.
- Object deletion/tombstones and engine-level version retention do
  not constitute a complete object lifecycle, GC or capability model.
- Missing/corrupt-volume diagnostics, arbitrary interruption recovery,
  concurrency and production durability have not been established.

**Evolution rule:** document a future format or native relation
encoding as a *proposal* until implemented and demonstrated; do not
silently repurpose this version-1 description.
