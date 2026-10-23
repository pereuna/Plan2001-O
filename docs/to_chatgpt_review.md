# Review: first native O byte-object slice

**Implementation commit:** `bf2117e0c6a01310d5cfc7acaaeb06534ad10eca`
(`micropython: add native O byte objects by OID`).
This report and the STATUS record are a docs-only follow-up commit.

## Changed files

- `sys/src/cmd/micropython/p9space.c` — added `space.oget(oid)` and
  `space.oput(oid, data)` as direct bindings to the existing
  `ospaceget`/`ospaceput`/`ospacecommit` syscalls. Added OID validation,
  reserved-write checks, a 1 MiB whole-object limit and a bounded
  size/read retry.
- `sys/src/cmd/micropython/genhdr/qstrdefs.generated.h` — regenerated
  for `MP_QSTR_oget`/`MP_QSTR_oput` (`make genhdr`).
- `tools/obytefile.py` — normal O demo module used by the focused gate.
- `tools/test-o-bytefile.sh` — executable QEMU/O gate.
- `docs/OBJECT-MODEL.md`, `docs/O-FORMAT.md` — implemented API example
  and the boundary between native OIDs and Python logical graph OIDs.
- `docs/STATUS.md` — new dated evidence section.

No kernel, GE/B-tree, on-disk v1 format, directory, 9P or Python class
change was made.

## Tested commands and results

All commands ran at `bf2117e` on Debian/amd64 with the target's normal
`-accel kvm -cpu host`. The login was not in the `kvm` group, so the same
commands were invoked with the `kvm` supplementary group via `setpriv`;
no emulation or gate change was used. No physical disk was touched.

```bash
WHAT=all tools/build.sh
# PASS: BUILD-DONE; 9pc64 md5 e31ae9fb0aa0c1a816b5ef55062b8896,
# 9pc64mp md5 17a87e214c6016f612dfd668a10bbdc1

ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
# PASS: selfroot at bf2117e; micropython SHA-256
# d3f715cd111c15986de66929acfbee6ea4b52dc58720f231d50e77fe12fb75f1

tools/test-o-bytefile.sh
# PASS: native O byte objects by OID, no FS or Python graph

for gate in test-o-boot test-o-boot-omp test-o-exec test-o-exec-args \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    tools/$gate.sh
done
# PASS: all nine existing gates
```

Logs: `build/verification/build-bytefile.log`,
`build/verification/selfroot-bytefile.log`,
`build/verification/test-o-bytefile.log`,
`build/verification/regressions-bytefile.log`, and the per-gate
`build/verification/*-bytefile.log`.

Focused gate detail (normal `9pc64`, one ESP + O disk, no FS root):

- Three boots of the same O volume. Boot 1 wrote `OID 42 = b"hello\n"`;
  boot 2 and boot 3 read the identical six bytes by OID. The Python
  `OID_GRAPH` was restored normally (`version 1 -> 2 -> 3`) and its
  Counter OID/alias stayed stable.
- Empty `b""`, binary `b"\x00\xff\x00"`, and a 2048-byte value (over
  `Objchunk = 480`) round-tripped exactly.
- Two OIDs held identical bytes; changing one left the other intact.
- An overwrite committed on boot 2 was read back on boot 3.
- Missing OID, string/float/negative/2^64 OIDs, non-bytes data, reserved
  OIDs (roots/first, `OID_GRAPH`, `OID_ENV`, `OID_CODE` region, upgrade
  metadata, native-exec test/boot OIDs), and over-limit writes all
  failed predictably; subsequent reads and the Python graph stayed
  intact.
- A REPL image booted with `-O` but no `-S`; both calls raised
  `OSError: space: no native O Space is open` instead of using a path.

## Main design choices

- **Path:** add two functions to the existing `space` module rather than
  a new object layer, file abstraction or kernel interface.
- **Commit independence:** `oput` calls `ospacecommit` synchronously.
  No change to the `OID_GRAPH` serializer or its early-return path was
  needed; a completed `oput` never leaves a native transaction pending.
- **Errors:** missing reads raise `OSError`; invalid types raise
  `TypeError`; negative/too-wide OIDs raise `OverflowError` (MicroPython's
  unsigned conversion); reserved and over-limit writes raise
  `ValueError`.
- **Safety check:** writes are refused for `oid <= OID_FIRST`, all OIDs
  `>= OID_CODE`, and the three native-exec OIDs. This is deliberately a
  PoC guard, not an allocator. Reads may address any published OID.
- **Bound and race:** 1 MiB whole-object limit, below the kernel's 64 MiB
  transaction cap; size then read, retried at most three times if the
  size changes.
- **Identity distinction:** `space.oid()` is untouched. Native OID 42 and
  a Python logical OID 42 are independent namespaces; docs say so.

## Unresolved risks / limits

- No OID allocation, listing, deletion, permissions, ownership or native
  relationship edges. The example `implements` relation for OID 43/100
  remains conceptual.
- The 1 MiB cap and three-retry race policy are PoC choices, not a
  durability or concurrency contract.
- Writes inside `space.atomic()` still publish immediately, because the
  byte object is a separate native transaction; this is intentional but
  should be documented more broadly if transactions become user-visible.
- Native commit failure/abort relies on the existing engine path and is
  surfaced as an exception; crash recovery and concurrent-writer
  semantics are not newly proven.
- `ospaceget` returns `-1` for both absence and some errors; `oget`
  reports those as a missing object for the PoC.
