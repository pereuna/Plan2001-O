# Task: first implementation commit for the Plan2001-O object/file model

## Objective

Implement **one small, verifiable vertical slice** of the object/file model defined in `docs/OBJECT-MODEL.md`: an interactive MicroPython user can store and read the **raw bytes of a native GE/O object addressed by a numeric OID**, without a pathname, directory, file metadata record, Python `File` class, or Python persistent-object serialization.

This is the **first implementation commit under the new architecture**, not a full migration, a new filesystem, a new object type system, or a namespace project.

Read `AGENTS.md`, `README.md`, `docs/OBJECT-MODEL.md`, `docs/O-FORMAT.md`, and relevant source before editing. **The current implementation is authoritative about existing APIs and constraints.**

## Why this step

The GE/O engine already supports versioned raw byte values keyed by `(SpaceID, OID)`:
- `sys/src/9/gefs/obj.c`: `ospaceget`, `ospaceput`, `ospacecommit`;
- `sys/src/9/port/devgefs.c`: native process-owned O handles and syscalls;
- `sys/src/cmd/micropython/p9space.c`: O volume/Space handles and bindings to the existing syscalls.

However, the current interactive Python persistence demo serializes a Python graph into `OID_GRAPH`; this is **not** an independent GE/O byte object per Python value. Add a **minimal direct byte-object interface** that makes this distinction observable.

The demonstration is:

```text
OID 42
    content = "hello\n"
```

The six bytes alone constitute the file content. There is no mandatory `stat`, pathname, directory, type field, or Python inheritance involved.

The separate conceptual example

```text
OID 43
    content = <6c binary>

OID 100
    implements → OID 43
    purpose    → C compiler
    target     → amd64
```

**does not authorize implementing** `implements` edges, program catalogs, program execution, a `File` superclass, or an `object` class framework in this commit.

## Implementation scope

Implement just two narrowly defined operations using existing native O calls, preferably in the existing built-in `space` MicroPython module rather than introducing another general object layer:

```python
import space
space.oput(42, b"hello\n")   # persist bytes immediately
assert space.oget(42) == b"hello\n"
```

Contract:

1. `space.oget(oid) -> bytes`: fetch the **published native GE/O byte payload** for an explicit unsigned 64-bit OID in the currently opened native O Space. Return an exact `bytes` value, including embedded NULs; empty content must return `b""`. A nonexistent OID produces a clear error (choose/document `OSError` or equivalent), **not** a fabricated empty object.
2. `space.oput(oid, data) -> None`: accept bytes-like raw data with a well-defined exact byte length (at minimum immutable `bytes`), write it using native O `ospaceput` and **publish/sync with `ospacecommit` before returning**. This must not depend on REPL Python-graph dirty tracking or the next statement's automatic Python commit. Rewriting the same OID updates its published byte content without changing its identity.
3. Available **only when a native `-O` volume and `-S` Space are active**. In legacy/DMOBJ mode or without an open native O Space, fail explicitly; do not fall back to paths or file APIs.
4. **Do not let the interface overwrite implementation-reserved OIDs**: in particular the current `OID_GRAPH`, `OID_ENV`, the code-OID region, `OID_MP_EXEC`, and known native-exec test/boot reserved OIDs. Inspect definitions and enforce a straightforward safety check for writes. Do not pretend this is a universal future OID allocator. Use ordinary unreserved OIDs (42 and nearby) for the demo, and document that these are PoC identifiers, not globally allocated identities.
5. Validate the OID as an integer in the supported unsigned 64-bit range; reject negative, overflow, and noninteger input without wrapping or truncation. Bound whole-object read/allocation by a documented conservative PoC limit, aligned with actual kernel/MP constraints; fail cleanly rather than allocating unbounded memory or silently truncating. Safely handle a size-query/read version change (retry in a bounded manner or give a clear error).
6. Preserve existing `space.oid()` and its meaning for *Python logical graph OIDs*. Do not treat the Python graph's internal object IDs as separately persisted native GE/O records. Make this distinction visible in the API documentation, even if their numeric values overlap.
7. No `type=file` field is required or introduced. No kernel, on-disk v1 or GE/B-tree format change. Prefer a short direct C binding in the existing MicroPython port; no Python object wrapper, `File` class, class hierarchy, new storage service, 9P adapter, root FS, or directory naming.
8. Keep writes independent of Python graph persistence. Inspect the existing `ocommit()` path carefully; it can return early when the Python graph is unchanged. If necessary, adjust narrowly to ensure a pending native byte transaction is not stranded. Do **not** rewrite the graph serializer or commit pipeline just for this task. Report how failures/aborts are handled and avoid reporting a successful write when the native commit fails.

If these exact Python API names conflict with existing real interfaces, select the smallest nonconflicting names, document the reason, and preserve the behavior above.

## Regression test

Add a **focused executable test** under `tools/` using the repository's established QEMU/O harness; prefer extending an appropriate existing test helper over duplicating boot infrastructure. Use a disposable O image. The core test must run against the **normal O-loaded MicroPython path**, not only the legacy embedded `pc64mp` test kernel.

Test at least:

- First boot in native O mode: `space.oput(42, b"hello\n")`; `space.oget(42)` reads **exactly six bytes**.
- A second, independent boot of **the same O disk**: `space.oget(42) == b"hello\n"`, independently of whether any Python graph value was changed; no filesystem root is mounted for O data.
- Empty bytes `b""`, binary bytes including `b"\x00\xff\x00"`, and a value larger than one GE object chunk (see `Objchunk` in `obj.c`), all round-trip without loss.
- Overwrite the same OID with new data and verify it across a reboot; two distinct OIDs containing identical bytes remain distinct identities.
- Missing OID, invalid OID values, reserved OID writes, unsupported mode, and over-limit content fail predictably without corrupting `OID_GRAPH` or seeded executable code.
- Existing O boot, Space persistence, native object and native executable regression gates still pass where the available environment permits.

Prefer observable, machine-checkable `PASS/FAIL` markers plus a nonzero exit on failure, not visual REPL-only inspection. Verify the persisted bytes directly through native O (not merely `space.oid(x)` or by saving a Python `bytes` object in `OID_GRAPH`).

## Documentation and evidence

- Update `docs/OBJECT-MODEL.md` or a short relevant runtime section to show the **actual implemented** `oget/oput` example and note exactly what is still conceptual. Do not turn the definition into a Python-oriented class model.
- Update `docs/O-FORMAT.md` only if explaining an observed API boundary; **do not rewrite the v1 format**.
- Append a **new, dated** result in `docs/STATUS.md` recording source changes and real test evidence, without changing older evidence or claiming unexecuted tests pass.
- Write a concise report to `docs/to_chatgpt_review.md` stating changed files, exact tested commands/results, main design choices, any unresolved risks, and the new commit hash.

## Deliverable and limits

Implement, test, **commit** and **push** one focused implementation change to the existing `Plan2001-O` repository branch. Do not include unrelated refactors, a kernel-driver abstraction cleanup, 6c/mk migration, a build system rewrite, native namespace work, generic graph indexes, global OID allocation, or new Python class/type semantics.

Preserve all existing tests and never use a physical disk for formatting. Stage only intended files. If QEMU/KVM or toolchain prerequisites are missing, make the narrow implementation and static checks, mark runtime tests **NOT RUN** with the actual blocker, and do not claim the vertical slice is proven.

**Acceptance condition:** from a fresh normal O boot, raw `b"hello\n"` is committed as an independent GE/O value addressed by `OID 42`, survives reboot of the same O volume, and is read back as the identical six bytes by OID, without any directory tree or Python object hierarchy.
