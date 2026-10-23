# Review: pathless normal O boot feasibility

**Verdict: A PASS; B/C NOT YET.** Implementation commit
`e3843009a79f762f30e70a459fffafb7c85e9a8f` (`ge/o: route native O
storage through direct SD blocks`), plus a docs-only follow-up.

## What changed

- `sys/src/9/port/devsd.c`, `sd.h`: internal `Sditer` unit iteration,
  `sdunitready`, absolute `sdblockrw` with sdbio-style bounds/bounce/media
  handling, and `sdblockflush` issuing the driver's 0x35 synchronize-cache
  request without opening `#S/.../raw`.
- `sys/src/9/port/devgefs.c`: partition-relative `Oblock`, direct GPT
  parsing from SD units, no-`namec` PARTUUID discovery, pathless O-volume
  open, `opath`/`oblocktest` instrumentation, and block-provider wiring.
- `sys/src/9/gefs/{gdat.h,gfns.h,kern.c,o.c}`: optional GE I/O provider
  (`oblk`) so reads/writes/sync/flush can bypass kernel Chans; legacy
  `Chan` path preserved unchanged.
- `sys/src/9/port/{chan.c,dev.c,sysproc.c}`, `sdvirtio10.c`: switchable
  counters for `namec`/`newchan`/`walk`/`devwalk`/`cmount`/path `sysexec`,
  and a driver-level virtio flush marker.
- `tools/test-o-pathless.sh`: dedicated disposable-QEMU gate.

No GE/O v1 layout, OID allocator, Space content, user bytes or existing
boot configuration was changed. `PARTUUID=` O boots now print `opened
without FS (native SD block)`; explicit-device specs and legacy FS paths
still use `namec`.

## Evidence

- Build/selfroot: PASS. `9pc64` md5 `d9f3184e9ab545ef9a433fb220e87d0d`.
  Logs `build/verification/build-pathless-final.log`,
  `selfroot-pathless-final.log`.
- `tools/test-o-pathless.sh`: PASS. Three boots of one disk had
  `opath: volopen-enter/opened/started namec=38 newchan=110 walk=57
  devwalk=82 mount=7 exec=1` — zero delta in the O open/GE start window.
  Missing PARTUUID and malformed GPT both failed with identical
  enter/error counts, no `namec` fallback. `oblocktest` range/oversize
  checks and `sdvirtio: flush PASS` passed on every boot.
  Log `build/verification/test-o-pathless-final.log`; per-boot logs
  `build/amd64/pathlessvm/boot{1,2,3}.log`.
- `tools/test-o-register.sh`: PASS (registration/persistence/concurrency/
  corrupt-state/unsupported-mode).
  Log `build/verification/test-o-register-pathless.log`.
- `tools/test-o-bytefile.sh`: PASS.
  Log `build/verification/test-o-bytefile-pathless.log`.
- Nine existing O-only gates: PASS. Logs
  `build/verification/test-o-*-pathless.log`.

## Exact blockers

- **B:** `initcode.c:startboot` still binds device trees, opens
  `/dev/cons`, and path-execs `/boot/oinit` through `devroot`; `proc0`
  also creates `namec("#/")`. An attempted O branch inside `initcode`
  exceeded the inherited one-page image and faulted in `proc0`'s
  `kmap`/`memset`; reverted. Next step: a separate flat bootstrap
  image/table with its own mapping and a tested `execo` handoff.
- **C:** `boot.py` binds devices, spawns `/boot/kbdfs`, opens
  `/dev/cons`; `p9console.c` uses fd 1 and `/dev/consctl`. A pathless
  console/stdin/stdout (or direct serial-backed interpreter console) is
  still required. No C claim is made.

## Risks / scope

Level A is one active O volume selected by `PARTUUID=` on an enumerated
SD unit; it is not a machine-wide allocator or remote protocol. Explicit
device specs remain legacy. The volume holds one `SDev` reference for its
lifetime; hot unplug is not designed. Flush durability depends on the
controller's existing `rio` implementation; QEMU virtio was verified.
All tests used disposable images; no physical disk was written.

Full call-chain audit and classification: `docs/O-BOOT-DEPENDENCIES.md`.
Dated runtime record: `docs/STATUS.md`, section “Pathless native O
storage — 23 October 2026”.
