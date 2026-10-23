# O boot dependencies and the pathless storage experiment

**Date:** 23 October 2026. **Source state:** implementation commit
`e3843009a79f762f30e70a459fffafb7c85e9a8f` on `main`, plus this
documentation/test-report follow-up. The runtime evidence below was
produced from that commit with the normal amd64 `9pc64` boot and
disposable QEMU images only.

## Verdict

| Level | Result | Scope actually demonstrated |
| --- | --- | --- |
| **A — native GE/O storage I/O pathless** | **PASS** | A `PARTUUID=` O volume is found in GPT directly from enumerated SD units, opened, read/written, synced and cache-flushed through an internal block provider with **zero** new `namec`, kernel `Chan`, walk, mount or path-exec events after the O volume-open window begins. |
| **B — native bootstrap pathless** | **NOT YET** | The executed path still enters `initcode.c:startboot`, binds `#c/#d/#e/#ec/#p/#s/#σ`, opens `/dev/cons`, and pathname-execs `/boot/oinit` through `devroot`; `oinit` is itself a `/boot` executable. |
| **C — entire normal O boot pathless** | **NOT YET** | Even after B, MicroPython's `boot.py` binds devices, spawns `/boot/kbdfs`, opens `/dev/cons`, and `p9console.c` uses fd 1 and `/dev/consctl`. Console/stdin/stdout are a real remaining namespace dependency. |

This is therefore **A PASS; B/C NOT YET**. No distributed, machine-wide
or remote identity claim is made. The on-disk GE/O v1 format, OID
allocator, Space content and user object bytes are unchanged.

## Definitions used

- **Level A** means no kernel `Chan`, `namec`, dev walk, 9P, directory
  enumeration or path exec in the executed disk discovery, GE/O block
  I/O, write-cache flush or retry chain.
- **Level B** means the kernel reaches a minimal bootstrap and executes
  the existing `OID_MP_EXEC` object without the legacy `initcode.c`
  bind/open/exec pathname sequence, `/boot` tree lookup or filesystem
  Chan.
- **Level C** means the complete selected normal O boot, including the
  console/stdin/stdout actually used by the test, is free of those
  events from power-on to the durable PASS marker.

GE's own `wrchan`/`rdchan`/`mkchan` queues are internal GE message
channels, not kernel `Chan`s. The instrumentation below counts the
kernel's `newchan`, `namec`, `walk`, `devwalk`, `cmount` and `sysexec`
entry points, not GE's internal names.

## Baseline executed chain before this change

Power-on -> UEFI loader -> `main.c:main` -> `userinit.c:proc0`
(`userinit.c:43` `namec("#/")`, `userinit.c:46` `cclone`) ->
`main.c:init0` (`main.c:148`) -> `touser` (`main.c:209`) ->
`initcode.c:startboot` (`sys/src/9/port/initcode.c:31`):

1. `bind("#c", "/dev")`, `#d`, `#e`, `#ec`, `#p`, `#s`, `#σ`
   (`initcode.c:35-41`);
2. `open("/dev/cons")` three times (`initcode.c:43-45`);
3. `exec("/boot/oinit", ...)` (`initcode.c:47`), which enters
   `sysexec` -> `namec` -> `devroot`'s embedded boot table.

`oinit` (`sys/src/cmd/oinit/oinit.c:134`) then calls `ovolopen`
(`oinit.c:61`) -> `sysovolopen` -> the old `gevolume` `namec` path ->
`oopen`/`geopen` -> `loadge`; it reads `OID_MP_EXEC` and calls
`oexecute` (`oinit.c:164`) -> `execo`. MicroPython then runs `boot.py`
(`sys/src/cmd/micropython/boot.py:38-63`), which binds devices, spawns
`/boot/kbdfs`, opens `/dev/cons` and duplicates it to fds 0/1/2.
`p9console.c:23-31` uses `fd2path(0)` and opens `/dev/consctl`;
`p9console.c:82-85` writes fd 1. Only then does `p9_space_boot` run the
O Space's `run()` and commit.

The measured pre-window counts in the final gate confirm this is real
execution, not just linked code: before the O volume window the normal
boot had already performed `namec=38`, `newchan=110`, `walk=57`,
`devwalk=82`, `mount=7`, path `exec=1`.

## Mechanism classification

| Category | Core necessary mechanism | Legacy facade on the current path |
| --- | --- | --- |
| Device discovery | SD controller probe, unit enumeration, online geometry, GPT header/entry parsing in `devsd.c` | `#S` directory read and `convM2D` in `devgefs.c:scandisks` (still used by explicit-device and FS paths) |
| O volume open | `oblockopenpart`, `sdunitready`, partition bounds | `gevolume` `namec("#S/.../data")` for non-`PARTUUID=` specs |
| GE block I/O | `sdblockrw` -> `SDifc.bio`, bounce/DMA alignment, bounds, media-change retry | kernel `Chan`/`devtab->read/write` in `kern.c:rw` |
| Cache flush | `sdblockflush` -> raw 0x35 -> virtio flush | `gflushdev` reopening `#S/.../raw` through `namec` |
| GE engine | superblocks, arenas, B-tree, recovery, OID allocator, O transactions | unchanged; no FS mount or 9P needed for O |
| Bootstrap | embedded bytes and process/exec setup | `devroot` `/boot` path, `bind`/`open`/path `exec`, `oinit` program |
| Console | serial hardware output primitive exists | `/dev/cons`, `kbdfs`, `consctl`, fds 0/1/2 |

## Level A implementation

- `sys/src/9/port/devsd.c`: `sdunititer` (`:381`) enumerates units
  without a Chan; `sdunitready` (`:415`) initializes geometry;
  `sdblockrw` (`:438`) is absolute block I/O with the existing bounce,
  bounds, media-change and `SDmaxio` behavior; `sdblockflush` (`:553`)
  issues the driver's synchronize-cache command through `sdrio`
  (`:1138`) without opening `#S/.../raw`.
- `sys/src/9/port/devgefs.c`: `oblockrw` (`:186`), GPT parsing
  `oblockgptpart` (`:213`), unit scan/discovery `oblockopenpart`
  (`:265`), and `sysovolopen`'s `PARTUUID=` branch (`:639`). The block
  provider is bound to the GE instance by `ovolopenblk` (`:624`).
- `sys/src/9/gefs/kern.c`: `geopen0` (`:928`) accepts the optional
  provider; `rw` (`:525`) routes through it; `gflushdev` (`:611`) uses
  `sdblockflush`. `loadge` still calls `open`/`dirfstat`, but macros
  resolve to `gopen`/`gdirfstat` over the in-memory synthetic fd table,
  not to `namec`.
- `sys/src/9/gefs/o.c`: `oopenblk` (`:109`) selects the block path
  while `oopen` keeps the legacy path.
- Instrumentation: `chan.c:9-10` counters and increments at
  `newchan:190`, `cmount:664`, `walk:993`, `namec:1310`;
  `dev.c:171` `devwalk`; `sysproc.c:695` path `sysexec`. `opathdump`
  (`devgefs.c:569`) prints compact `opath:` lines only with
  `plan9.ini opath=1`.
- `tools/test-o-pathless.sh` is the dedicated gate. It checks
  `opath=1`, `oblocktest=1` and `sdflushlog=1`; it does not modify any
  existing normal boot configuration or legacy gate.

The block provider is partition-relative. `oblockrw` rejects writes
outside the partition before touching the driver and returns 0 for reads
at/after the end. `sdblockrw` clamps a request to `SDmaxio` (2 MiB), as
the existing `sdbio` does, and reports the actual transferred length.
This graph is for the active O volume only; explicit-device specs still
use the legacy `namec` path and are not claimed pathless.

## Source anchors and size

The implementation commit changes 12 files, +775/−19 lines
(`git show --stat e384300`). The main anchors are:

| File:line | Role |
| --- | --- |
| `sys/src/9/port/devsd.c:381` | `sdunititer`, no-Chan unit enumeration |
| `sys/src/9/port/devsd.c:415` | `sdunitready`, online geometry |
| `sys/src/9/port/devsd.c:438` | `sdblockrw`, bounded absolute block I/O |
| `sys/src/9/port/devsd.c:553` | `sdblockflush`, raw 0x35 through the driver |
| `sys/src/9/port/devgefs.c:186` | `oblockrw`, partition-relative provider |
| `sys/src/9/port/devgefs.c:213` | `oblockgptpart`, direct GPT parse |
| `sys/src/9/port/devgefs.c:265` | `oblockopenpart`, unit scan/PARTUUID |
| `sys/src/9/port/devgefs.c:624` | `ovolopenblk`, O-volume block selection |
| `sys/src/9/port/devgefs.c:639` | `sysovolopen`, `PARTUUID=` branch |
| `sys/src/9/gefs/kern.c:525` | `rw`, provider routing |
| `sys/src/9/gefs/kern.c:611` | `gflushdev`, provider flush |
| `sys/src/9/gefs/kern.c:928` | `geopen0`, optional provider setup |
| `sys/src/9/gefs/o.c:109` | `oopenblk`, O-specific selection |
| `sys/src/9/port/chan.c:9` | namespace/Chan counters |
| `sys/src/9/port/dev.c:171` | `devwalk` counter |
| `sys/src/9/port/sysproc.c:695` | path-`sysexec` counter |

## Runtime evidence

Command:

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-pathless.sh
```

Logs: `build/verification/build-pathless-final.log`,
`build/verification/selfroot-pathless-final.log`,
`build/verification/test-o-pathless-final.log`, and the per-boot
`build/amd64/pathlessvm/boot{1,2,3}.log`.

Measured level-A window (identical on all three boots):

```
opath: volopen-enter  namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
opath: volopen-opened namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
opath: volopen-started namec=38 newchan=110 walk=57 devwalk=82 mount=7 exec=1
o: O volume #S/sdF0/data@68157440, 192 MiB, opened without FS (native SD block)
```

The non-zero initial counts are the positive control: the legacy
`/boot` bootstrap did execute `namec`, walks, mounts and a path exec
before the O storage window. The deltas across open and GE start are
zero. The failed-discovery cases show the same invariant:

```
opath: volopen-enter  namec=34 newchan=94 walk=49 devwalk=70 mount=7 exec=1
opath: volopen-error  namec=34 newchan=94 walk=49 devwalk=70 mount=7 exec=1
```

Additional assertions passed on every boot:

- `oblocktest: PASS in-range-read`
- `oblocktest: PASS read-at-end`
- `oblocktest: PASS oversized-read-clamped`
- `oblocktest: PASS write-past-end`
- `sdvirtio: flush PASS` (the virtio driver's actual 0x35/`vioblkreq`
  flush path, not a wrapper returning 0)
- `Oreg: PASS first-boot`, `second-boot`, `third-boot` with unchanged
  payloads, distinct equal-byte OIDs, monotonically increasing new IDs,
  and no allocation from repeated reads
- missing `PARTUUID` and a malformed GPT header on another attached unit
  both failed with `no disk has that partition` and the same namespace
  counts before and after discovery

## Level B — exact blockers

The executed bootstrap still is the legacy one:

- `initcode.c:35-47` binds seven device trees, opens `/dev/cons`, and
  path-execs `/boot/oinit`.
- `/boot/oinit` comes from the embedded `devroot` boot table
  (`sys/src/9/pc64/pc64` `bootdir`, `devroot.c`); `sysexec` walks that
  name through `namec`/`Chan`.
- `proc0` also seeds `up->slash`/`up->dot` with `namec("#/")`
  (`userinit.c:43-46`) before userspace starts.

A bounded experiment was attempted: replace `startboot`'s bind/open/exec
branch with `ovolopen`/`ospaceopen`/`oexecute(OID_MP_EXEC)` directly in
`initcode.c`. It did not fit the inherited one-page `initcode` image.
The next boot faulted in `proc0` at the one-page `kmap`/`memset` of the
larger `initcode` blob (panic transcript in
`build/verification/test-o-boot-pathless-block.log`), so the experiment
was reverted rather than weakening the one-page constraint. The smallest
credible next step is a separate flat embedded bootstrap image/table
with its own mapped size and a minimal `execo` handoff, or an equivalent
kernel-native O startup path; that requires process/argv/rollback/exit
tests comparable to the existing `oexec` gates. It is not implemented
or claimed here.

## Level C — exact blockers

The normal O-loaded MicroPython still performs namespace operations on
every boot:

- `boot.py:38-41` binds `#¤ #¶ #P #S #f #æ #t #b #m` onto `/dev`;
- `boot.py:47-56` spawns `/boot/kbdfs`, opens `/dev/cons`, and duplicates
  it to fds 0, 1 and 2;
- `main.c:219-221` runs `boot.py` and `p9_console_init`;
- `p9console.c:23-31` calls `fd2path(0)` and opens `/dev/consctl`;
- `p9console.c:82-85` writes fd 1.

A direct serial output primitive exists in the kernel (`putstrn`), but
the interpreter's normal stdin/stdout and REPL path still depend on the
console Chan/fd machinery. A Level C proof therefore needs a tested
pathless console/stdin/stdout path (or a direct serial-backed console in
the interpreter) plus a pathless bootstrap from B. Merely changing
print output would not prove the input/REPL path, so no C claim is made.

## Regression gates

All commands were run on implementation commit `e3843009...` with
disposable QEMU images; no physical disk was written or reformatted.

| Gate | Result | Log |
| --- | --- | --- |
| `WHAT=all tools/build.sh` | **PASS** (`BUILD-DONE`; `9pc64` md5 `d9f3184e9ab545ef9a433fb220e87d0d`) | `build/verification/build-pathless-final.log` |
| `tools/selfroot build/selfroot` | **PASS** | `build/verification/selfroot-pathless-final.log` |
| `tools/test-o-pathless.sh` | **PASS** | `build/verification/test-o-pathless-final.log` |
| `tools/test-o-register.sh` | **PASS** | `build/verification/test-o-register-pathless.log` |
| `tools/test-o-bytefile.sh` | **PASS** | `build/verification/test-o-bytefile-pathless.log` |
| `tools/test-o-boot-omp.sh` | **PASS** | `build/verification/test-o-boot-omp-pathless.log` |
| `tools/test-o-boot.sh` | **PASS** | `build/verification/test-o-boot-final.log` |
| `tools/test-o-exec.sh` | **PASS** | `build/verification/test-o-exec-pathless.log` |
| `tools/test-o-exec-args.sh` | **PASS** | `build/verification/test-o-exec-args-pathless.log` |
| `tools/test-o-handles.sh` | **PASS** | `build/verification/test-o-handles-pathless.log` |
| `tools/test-ge.sh` | **PASS** | `build/verification/test-ge-pathless.log` |
| `tools/test-o-volume.sh` | **PASS** | `build/verification/test-o-volume-pathless.log` |
| `tools/test-o-objects.sh` | **PASS** | `build/verification/test-o-objects-pathless.log` |
| `tools/test-o-space.sh` | **PASS** | `build/verification/test-o-space-pathless.log` |

`test-o-boot-omp.sh` and `test-o-space.sh` retain their documented
expected shutdown diagnostics (`panic: boot process died: ...`); they
are not path failures and the gate scripts report PASS. The baseline
three-boot transcript before this change is
`build/verification/test-o-boot-pathless-baseline.log`.

## Remaining risks and limits

- The pathless O backend is for the one active native O volume selected
  by `PARTUUID=` on an enumerated SD unit. Explicit device specs, a
  second simultaneous O volume, machine-wide allocation, removal/media
  change under a live volume, and remote observation are not implemented
  as pathless.
- `sdunititer` holds one `SDev` reference for the volume's lifetime; the
  volume is not torn down separately from the machine. This is consistent
  with the existing `ovol` lifetime but is not a general hot-unplug
  design.
- GPT parsing is deliberately bounded to 512/4096-byte logical blocks and
  at most 1024 entries; malformed sizes, out-of-range LBAs/partitions and
  missing GUIDs are rejected. The test corrupts one primary header on a
  disposable unit and confirms rejection.
- Write-cache durability is only as good as the driver's flush; the test
  verifies the virtio flush command reached `vioblkreq` in QEMU. Other
  controllers inherit their existing `rio` behavior.
- B and C remain the real architectural blockers: a flat pathless
  bootstrap and a pathless console. Level A alone does not make the
  normal boot pathless.
