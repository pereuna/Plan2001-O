# Coding task: local native OID registration (Plan2001-O)

**Repository:** pereuna/Plan2001-O, current main branch.
**Task type:** one narrow, buildable implementation and its regression tests.
**Architectural decision:** OIDs are LOCAL, not globally unique over IP. This task implements registration in the existing native GE/O Space; it does not implement a global Space service or remote object access.

Read AGENTS.md, README.md, docs/GENERAL-SOFTWARE-SPECIFICATION.md, docs/OLIO-OBJEKTI-MANIFESTI.md, docs/OBJECT-MODEL.md, docs/O-FORMAT.md, docs/STATUS.md, and the actual source before editing. The source is authoritative for the current transaction and ABI implementation. The philosophical manifesto is not a demand to redesign bytes or hardware.

## 1. Ontology and scope: do not confuse identity with location or interpretation

- An **olio** is an independently registered occurrence. Its sole REQUIRED application-visible property at this level is its local OID. It may have no application name, type, graph membership, provenance, or nonempty payload.
- It becomes an **object** in an observation, operation, or relation. Registration is an operation; it does NOT install permanent object/type semantics.
- **Local uniqueness:** within one actual OID scope, at a given time a numeric OID designates at most one registered occurrence. Multiple in-memory buffers and retained content versions are not separately registered occurrences.
- **No global numeric identity:** silli:42 and kuha:42 can denote unrelated local occurrences. Registering the same bytes independently on two machines is allowed to yield the same number. No IP address, hostname, UUID, content digest, timestamps, or machine identity is stored as a compulsory per-olio property.
- **Remote observation is not registration.** A future machine may read/stream/display a remote occurrence without creating a local OID or making a durable local copy. This task creates NO remote protocol, automatic cache-to-O persistence, network mount or graph_mount.
- **Import/copy is explicit new registration:** if bytes are deliberately retained on another machine, that destination creates its own local OID. Any relationship to the original is optional graph/provenance data at a higher layer, not intrinsic to the OID.
- **Moving a stored occurrence** is NOT implemented here. Do not promise remote identity preservation, remote deletions, or distributed atomicity.
- No global allocator or globally ordered creation sequence.

**Important scope boundary:** today's implemented persistent identity is (GE volume, SpaceID, OID), commonly displayed as (SpaceID, OID) inside one active volume; the normal PoC uses one O volume and its init Space. Implement uniqueness and durability **within this existing active native O Space**. This is not yet a machine-wide allocator spanning every RAM resident, O disk, removable disk and multiple Space instances. Do NOT silently declare those larger scopes solved. Document this limitation clearly, without changing GE/O v1 disk format or inventing a new volume namespace. Reserve the machine-wide scope question for a separate design decision.

## 2. Requested user-visible behavior

Provide a minimal MicroPython API in the existing built-in space module:

```python
import space

a = space.oregister()               # a fresh local OID, empty payload
b = space.oregister(b"hello\n")     # a different fresh local OID

assert a != b
assert space.oget(a) == b""
assert space.oget(b) == b"hello\n"

c = space.oregister(b"hello\n")
assert c != b                        # bytes equality does not imply identity
space.oput(b, b"new content")       # revise existing OID, do NOT allocate
assert space.oget(b) == b"new content"
assert space.oget(c) == b"hello\n"
```

Contract:

1. `space.oregister(data=b"") -> int` allocates a never-before-*committed* OID in the current native O Space, publishes its payload (including zero bytes) and the durable allocation state, and returns ONLY after native GE/O commit/sync has succeeded. It MUST work when the Python graph is unchanged, and the result must be recoverable after a reboot of the same disk.
2. No data argument creates a real, independently retrievable **empty-payload occurrence**, not a missing record or a sentinel. Do not introduce a compulsory file type, timestamp, name, metadata dict, class, graph binding, or Python object serialization.
3. At minimum accept byte-like inputs as already supported by `space.oput`. Explicitly reject str and non-byte objects. Keep the existing conservative 1 MiB whole-object limit unless actual source constraints justify a narrower bound; never truncate.
4. Use the same -O native volume plus -S Space requirement as `oget/oput`; unsupported/legacy mode raises a clear error, not a filesystem fallback.
5. Existing `space.oget` and `space.oput` behavior remains intact; they still operate on native GE/O payloads, while `space.oid` still reports a Python serialized-graph *logical* OID. Numeric coincidence between a Python logical OID and a native record does not merge them.
6. The result is a local uint64 numeric identifier with well-defined reserved/excluded ranges, no wraparound or signed truncation. When the available range is exhausted, fail rather than reuse.
7. Do NOT expose an allocator-internal record or counter as an ordinary registerable OID or allow external writes to corrupt it.

## 3. Implement the allocator in native GE/O, not in Python

Relevant implementation:

- sys/src/9/gefs/obj.c: `Ospace`, `ospacetx`, `begin`, `ospaceputdata`, `ospaceput`, `ospacecommit`, `ospaceget`, `ospaceclose`, and the existing Kobj versioning/commit engine.
- sys/src/9/gefs/o.c and sys/src/9/gefs/gfns.h: native O Space API.
- sys/src/9/port/devgefs.c: process-owned O handles and syscall boundary.
- sys/src/libc/9syscall/sys.h and relevant syscall dispatch/ABI declarations.
- sys/src/cmd/micropython/p9space.c, p9space.h: current 64-bit OID validation, reserved OIDs, `oget/oput` binding, and the DIFFERENT Python graph `sp.next` state.
- tools/mkovol, tools/obytefile.py, tools/test-o-bytefile.sh, plus normal QEMU/O-loader harness.

Introduce one narrow native operation (name it `ospacecreate` / `ospacealloc` or a similarly clear name after checking conflicts) which **both allocates an OID and writes the initial payload**, with one publication/sync boundary. Wire a thin user-space syscall and MicroPython binding to it. Do not implement a read-counter -> user-space allocate -> oput -> separate counter-commit sequence.

**Atomicity requirement:** allocation state and the new occurrence must be part of the SAME native Space transaction and become visible together. In particular:

- The next candidate cannot be guessed in Python or derived from the serialized `OID_GRAPH` / `sp.next` / Python `space.oid` allocator.
- Never return an OID before the corresponding occurrence AND allocator advancement are durably published.
- Two concurrent register operations cannot both return the same OID in the same Space. Respect the existing GE/O store-writer serialization and locking; a documented retryable busy error is acceptable if contention is not internally queued.
- Committed OIDs must not be reused after an ordinary delete/tombstone, restart, process exit, abort, or failed operation. Explicitly document which uncommitted candidates may be retried, since no durable ID was returned.
- First registration against an existing seeded/native O volume with NO allocator state must work without reformatting or destroying it. Existing hand-chosen native IDs (e.g. 42, 44..49), reserved low/header IDs, seeded Environment, code, and O executable IDs must not be overwritten.
- Current `space.oput(oid, data)` can create explicitly numbered native records. Preserve that prior behavior and tests. Therefore the allocator must account for possible manually created IDs in its candidate range: test/skip occupied candidates **inside the serialized native operation**, and advance the persistent high-water mark. Never assume the candidate is free merely because the allocation counter says so.
- Do not reassign a previously committed, later-retired OID simply because `ospaceget` would now return missing. Avoid OID reuse through tombstones and retained-version pruning by relying on the persistent high-water mark and a clear policy for externally supplied IDs. Since explicit future-ID writes remain possible, check collisions robustly.
- Use a small documented allocator-state record in the EXISTING GE/O Kobj/Space transaction machinery if appropriate. Any new reserved identifier must be forbidden to ordinary native writers and guarded at the relevant native boundary, not merely hidden by a Python check. Make initialization, corruption/malformed-state detection, and upgrade of older O volumes explicit. Do not modify the GE/O v1 layout, introduce a separate database, or build a global scan/index unless necessary for demonstrated correctness.
- Audit lock order (Space handle lock, fs->mutlk, GE tree scan), failed `begin`/`commit`/`gesync`/abort, and error paths. Do not read an unpublished candidate or leave the active transaction poisoned on error.
- Existing OID regions (especially `OID_ROOTS`, `OID_FIRST`, `OID_CODE`, `OID_ENV`, `OID_GRAPH`, `OID_UPGRADE_META` and `OID_MP_EXEC`/other O-exec fixtures) must remain safe. An implementation may choose a constrained, monotonic user-ID range, but it must justify the bounds and test collisions.

If the interaction between current explicit-ID writes and immutable never-reuse semantics cannot be made safe with a straightforward bounded design, implement the safe limited scope, report the exact unsolved scenario, and do not claim full machine-wide/permanent uniqueness. Prefer an explicit restriction over a silent collision.

## 4. Dedicated executable regression gate (normal O-loaded MicroPython)

Add a focused self-contained `tools/test-o-register.sh` (and a small O-resident Python test module if useful). Use existing tools/mkovol, disposable ESP + O images and the regular **9pc64 -> oinit -> OID_MP_EXEC -> MicroPython** path, NOT only the test-only embedded `9pc64mp` kernel.

Required machine-checkable scenarios:

1. **Fresh Space**: register empty, six-byte text, embedded-NUL binary, and a 2048-byte multi-chunk payload; each `oget(oid)` returns exactly its bytes, with missing OID distinguishable from empty bytes. A fresh OID is an int in the allowed range.
2. **Identity**: register equal payloads twice; assert distinct OIDs. Mutate one with `oput`; the other remains unchanged, and revision does not allocate a new OID.
3. **Persistence**: save returned OIDs in a test-controlled way (e.g. deterministic test logs or an already existing test graph variable; storing test bookkeeping in the Python graph is allowed ONLY for the test). Reboot the SAME disk twice, verify all payloads and IDs, and register again; new IDs are strictly above previous allocator-issued IDs and never equal earlier ones.
4. **Legacy coexistence**: preseed explicitly numbered native OIDs (including existing bytefile fixtures where practical). A new registration never overwrites them. Verify an explicitly written future candidate is skipped, including if the allocator cursor approaches it. The current `test-o-bytefile.sh` still passes unmodified.
5. **Multi-handle/multi-process contention**: two processes or independent native Space handles try to register at once. Both successes have distinct IDs; or one receives a clean documented busy error and a successful later retry gets a fresh ID. No duplicate IDs, partial occurrences, deadlocks or panics. Do not claim a race was tested unless it really ran.
6. **Failures**: malformed input and over-limit data rejected; unsupported mode rejected; corrupted allocator state rejected safely (not reset to zero); exhausted/reserved range handled cleanly. If a deterministic transaction abort or fault-injection harness is feasible, interrupt before publication and verify no half-published allocation; distinguish this from ordinary QEMU shutdown after a successful commit. Never write/reformat real physical disks.
7. **No hidden persistence on read**: reading or observing a result never invokes registration. No network implementation is required: verify locally that `oget`/read-only access does not change the allocator state or create extra OIDs, and document the conceptual future remote rule.
8. **Existing gates**: run the prior nine O-only gates AND `test-o-bytefile.sh`; preserve native executable loader, Space graph, oinit, and handle lifetime behavior. Report actual PASS / FAIL / NOT RUN, not anticipated results.

Prefer deterministic `PASS/FAIL` markers, a nonzero exit status on failed assertions, and captured QEMU log paths.

## 5. Documentation and evidence

- Update docs/O-FORMAT.md with the **actual** allocator-state encoding, local scope, published transaction semantics, reserved IDs and migration/initialization behavior. Do not inaccurately call an additive Kobj record a new disk-format revision.
- Update docs/GENERAL-SOFTWARE-SPECIFICATION.md and/or docs/OBJECT-MODEL.md ONLY as necessary to align the concrete scope: globally accessible conceptual Space does not imply a global numeric OID; machine/peer names are addressing context and do not become compulsory olio metadata. Clearly distinguish concept from implemented PoC.
- Update README.md only for a concise real API example if the implementation passes; keep current architectural caveats.
- Add a dated implementation + runtime-test section to docs/STATUS.md. Retain past evidence unchanged.
- Write docs/to_chatgpt_review.md with changed files, native allocator design, ID scope and incompatibilities, exact build/test commands + results + logs, concurrency and failure evidence, remaining risks and commit SHA.

## 6. Delivery and non-goals

Implement, test, commit and push ONE focused change (or the smallest clean sequence) on the current Plan2001-O branch. Stage only intended paths. Existing automatic OpenCode review/push integration may do reporting; make the report accurate.

**Do not implement:** a global OID server; distributed consensus; content-addressed identity; cross-machine UUIDs; hostname as an inherent object property; copying data during observation; a browser/cache; network object transport; tags, indexed queries or graph_mount; a Unix/Plan9 filesystem facade; classes/type inheritance; full object deletion/GC; a generic ontology system; a wholesale GE/O rewrite.

**Acceptance condition:** an ordinary O-loaded MicroPython on a disposable persistent O volume can call `space.oregister()` or `space.oregister(bytes)` to obtain a previously unused LOCAL OID, retrieve the exact empty/binary content by that OID, reboot and retain its identity, and register more occurrences without collision or dependence on the Python serialized graph. An attempted registration that fails never reports a durable OID. There is no implied persistence or new OID from merely observing remotely stored content.
