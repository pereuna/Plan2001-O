# Review report: local native OID registration

**Date:** 23 October 2026
**Implementation commits:** `a9c3247`, `077ba29`
**Test-fixture commit:** `09cb651`
**Runtime evidence:** clean tree at `09cb651` for the dedicated gate; the
ten pre-existing O-only gates ran at `077ba29` (only test scripts changed
afterward). This report and the documentation updates are a docs-only
follow-up.

## Changed files

Native storage / syscall boundary:

- `sys/src/9/gefs/obj.c` — allocator state, candidate checks,
  `ospacecreate`, serialization lock.
- `sys/src/9/gefs/o.c`, `sys/src/9/gefs/gfns.h` — native wrapper and
  declarations.
- `sys/src/9/port/devgefs.c`, `sys/src/9/port/systab.h`,
  `sys/src/libc/9syscall/sys.h`, `sys/src/cmd/syscall/syscall.c` —
  `OSPACECREATE` syscall. The previously unregistered `OEXECUTE` handler
  is also entered in `systab.h`; without that entry the existing native
  exec syscall number had no dispatcher.
- `sys/src/cmd/gefs/ream.c`, `tools/mkovol`, `tools/oseed.py` — optional
  `REGALLOC` corrupt-state test fixture; normal seeding is unchanged.

MicroPython and regression harness:

- `sys/src/cmd/micropython/p9space.c` +
  `sys/src/cmd/micropython/genhdr/qstrdefs.generated.h` —
  `space.oregister([data])`.
- `sys/src/cmd/ohandle/ohandle.c` — `-reg -vol SPEC` two-process
  registration mode.
- `tools/oregister.py`, `tools/oregcorrupt.py`,
  `tools/test-o-register.sh` — focused gate.

Documentation:

- `docs/O-FORMAT.md` — actual allocator encoding, scope, transactions,
  reserved range, migration/corruption behavior.
- `docs/OBJECT-MODEL.md`, `docs/GENERAL-SOFTWARE-SPECIFICATION.md`,
  `README.md` — align the concrete local scope with the conceptual
  Space/OID distinction.
- `docs/STATUS.md` — dated runtime evidence.

## Native allocator design

The allocator high-water mark is appended to the existing Kobj Space
header `user[...]` value. It is not an OID and cannot be reached by
`space.oput`.

```text
legacy seed: env_sha256[64] | next[8]                         (72 bytes)
allocator:   env_sha256[64] | next[8] | "OALLOC01" | next[8]  (88 bytes)
```

- Missing user part or the 72-byte pre-allocator seed starts at candidate
  64 and upgrades on first create.
- An existing 88-byte marker parses `next`.
- A malformed marker/length or out-of-range `next` is rejected; it is not
  reset to zero.
- Candidate range: `64 <= oid < 0xffffffff00000000` (`OID_CODE`), minus
  the native-exec OIDs `0x4f45584543000001`-`03`.
- Each candidate is checked in the same serialized transaction against
  published records (including tombstones) and pending transaction
  entries. Explicit future IDs are skipped and the high-water mark moves
  past them. The mark never decreases, so there is no reuse through
  tombstones or retained-version pruning. Exhaustion returns an error and
  does not wrap.
- `ospacecreate` writes the payload and the new header user part in one
  Space transaction, commits, and calls `gesync`. The OID is returned
  only after sync succeeds.
- A native `oalloclk` serializes whole creates and `ospacecommit`
  including sync. This closes the observed two-process dirty-block assert
  during concurrent create/sync; concurrent registrations queue.
- The occurrence and allocator advancement become published together.
  Failure before publication aborts the transaction (`W > N`); an
  uncommitted candidate may be retried because no durable OID was
  returned.

There is no new key type, separate database or GE/O v1 layout revision.
The Python graph and `sp.next` are not read by the native allocator.

## ID scope and incompatibilities

The allocator is local to the active native O volume and `init` Space.
The same numeric OID may name unrelated occurrences on another volume or
machine. No host name, IP address, UUID, content digest or timestamp is
stored per object. There is no machine-wide allocator spanning multiple
volumes, Spaces, RAM state or removable disks, no remote registration,
no OID transport, no copy-on-read and no OID migration.

The implementation remains compatible with existing explicit-ID writes:
42-49 and the native-exec fixtures remain ordinary explicit identifiers
and are protected only by collision checks. A future machine-wide scope
needs a separate design.

## Build and test commands

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-register.sh
for gate in test-o-bytefile test-o-boot-omp test-o-boot test-o-exec-args \
            test-o-exec test-o-handles test-ge test-o-volume \
            test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate-register.log"
done
```

## Results

All commands below exited 0.

| Check | Result | Log |
| --- | --- | --- |
| Full amd64 build (`9pc64`, test-only `9pc64mp`, loader) | **PASS** | `build/verification/build-register.log` |
| selfroot at `077ba29` | **PASS** | `build/verification/selfroot-register.log` |
| Dedicated registration gate, 4 boots + contention + corruption + REPL mode | **PASS** | `build/verification/test-o-register-final.log`, `build/amd64/oregistervm/boots.log` |
| Two-process independent handles | **PASS**, 16 distinct readable OIDs | `build/amd64/oregistervm/concurrency.log` |
| Corrupt allocator state | **PASS**, rejected twice, no reset | `build/amd64/oregistervm/corrupt.log` |
| Unsupported `-O` without `-S` | **PASS**, explicit `OSError` | `build/verification/test-o-register-final.log` |
| `test-o-bytefile.sh` unchanged | **PASS** | `build/verification/test-o-bytefile-register.log` |
| Existing nine O-only gates | **PASS** | `build/verification/test-*-register.log` |

The dedicated gate covers: empty payload; six-byte text; embedded-NUL
binary; 2048-byte multi-chunk payload; missing OID versus empty; equal
bytes with distinct OIDs; revision via `oput` without allocation;
explicitly written IDs 64 and 70 skipped, including a cursor that
approaches a future candidate; persistence across four boots; new IDs
strictly above the previous mark; and read-only accesses not advancing
the allocator.

## Concurrency and failure evidence

The first concurrency run exposed
`panic: gefs: assert failed for [0]: checkflag(b, Bdirty,
Bqueued|Bstatic)` because two processes could overlap create/commit with
`gesync`. The fix serializes the complete create/commit-and-sync path
with `oalloclk`. The rerun completed both processes with distinct IDs:
parent/child pairs 65/64 through 79/78, all payloads readable. This is
real executed evidence, not a source-only claim.

The corruption fixture boots with an 88-byte header whose allocator
`next` is zero. Registration fails with `O: corrupt allocator state`,
twice; `oget(65)` remains missing, and the module completes. This checks
that corrupt state is not silently reset.

The test does not claim a distributed or machine-wide race was tested,
nor arbitrary crash/fault injection beyond an ordinary failed
registration/abort path.

## Remaining risks

- Local, not global, OID scope. The README and specification now state
  this explicitly.
- The header user-part encoding is an additive PoC convention. A future
  format extension using that area would need to supersede it explicitly.
- The global `oalloclk` is simple and correct for this PoC but
  serializes all native create/commit syncs; it is not a scalability
  design.
- Corrupt-state repair is not implemented; the safe behavior is
  rejection.
- No deletion/GC/retention API, remote registration, machine-wide
  allocator or cross-volume identity.
- The 1 MiB whole-object limit and single active O volume remain PoC
  constraints.
