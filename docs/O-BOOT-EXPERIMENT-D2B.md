# Boot Experiment D2b: native O server boot and durable three-boot proof

**Date:** 23 October 2026. **Source state:** implementation commit
`3cfd4ed27082c98e009030797290c6b1f84be380`, plus this documentation
follow-up. Runtime evidence was produced from that committed source with
`WHAT=all`, a clean `tools/selfroot`, and disposable QEMU images.

## Verdict

```text
D2b SERVER BOOT PASS
RUN 1/2/3 = run() -> 1 / 2 / 3; init: done after durable commits
SAME DISK = verified (one combined ESP+O image, no host reseed between boots)
PERSISTENCE = init versions 1/2/3 (O versions 2/3/4); Counter OID 7, alias 7 unchanged
NATIVE ONLY = zero legacy syscall attempts; namec/newchan/walk/devwalk/mount/exec = 0 at n=4/16/32/64
LEGACY CONTROLS = PASS
NEXT = smallest D2c input/REPL experiment (not implemented)
```

## Contract: `-N` native noninteractive server

The new `-N` mode is accepted only with native `-O` and `-S`:

```text
micropython -O PARTUUID=<fresh GUID> -S init -N
```

`-B` is unchanged and still runs the legacy `boot.py` sequence; D2a's
`oboot=mp` diagnostic remains `-O ... -S init -B`. The new boot selector
is `plan9.ini oboot=server`; A/B/C, `oboot=mp`, and the default O boot are
unchanged.

`-N` performs:

1. parse `-O`/`-S`/`-N` without an Environment or pathname lookup;
2. initialize the MicroPython VM/heap and `p9_space_o` (`OVOLOPEN`);
3. skip `bootpy` entirely;
4. call `__import__('space').open('init')`, i.e. the existing native
   `ospaceopen`/`ospaceget` Space path;
5. call the existing `p9_space_boot()` (fresh `odemo` import/init or saved
   graph restore, then `run()`);
6. commit through the existing `p9_space_commit(1)`/`OSPACE*` path;
7. report the existing Counter OID/alias and print `init: done` only after
   the durable commit;
8. sleep without reading console input or calling `p9_console_init()`.

`boot.py`, `/dev`, `kbdfs`, `#c`, the REPL and `namec`/`Chan` are not used
on this path. Native stdout/diagnostics use the D2a `IOWRITE` stream
(handle 1 OUT, 2 DIAG) with the same process/PID across `OEXECUTE`.

## Kernel selection and loader reuse

* `plan9.ini oboot=server` adds `oboot_server` at
  `sys/src/9/pc64/main.c:234,293`; it calls the same
  `o_user_bootstrap()`/`ouserproc()`/`otouser()` path as D2a.
* The one-page loader image and `OEXECUTE(OID_MP_EXEC)` are reused. The
  only change is the sixth argv element `-N` instead of `-B` and the
  grant of the same process-local `Iomout|Iomdiag` output handles
  (`sys/src/9/pc64/ouser.c`).
* The generated PARTUUID continues to arrive through `obootvol` and the
  user-stack `Oargs` block; no GUID is compiled in.
* `IOWRITE` capture, cumulative `userinit/proc0/init0` and
  `namec/newchan/walk/devwalk/mount/exec` counters, and a targeted
  post-MP legacy-syscall audit are tagged `OBOOT-D2B:` for the selected
  PID.

## Hidden legacy dependencies found and bypassed in `-N`

D2b did not assume that skipping `boot.py` was sufficient. Three reachable
optional legacy mechanisms were found:

* **`p9_spacetime` / `getenv`**: the native path called
  `p9_spacetime("restore", ...)` during `ospace_open`; `getenv` would open
  `/env/spacetime`. `p9_space_native_mode(1)` now makes `p9_spacetime`
  return before `getenv`. Legacy `-B` behavior is unchanged.
* **`nsec()`**: `ospace_open`, image restore/commit timing and
  `lastcommit` used libc `nsec()`, which opens `/dev/bintime`. A native
  `p9_now()` uses the existing `_NSEC` syscall (`nr=53`) when native mode
  is active; it falls back to libc `nsec()` for legacy boots. D2b logs
  show `_NSEC`, not `OPEN /dev/bintime`.
* **`loadmod`'s `libpath`/`getuser`**: even the native O branch computed a
  legacy library path; `getuser()` calls `dirstat("/proc/<pid>/status")`
  (`STAT nr=42`). In native O mode `loadmod` now leaves `lib` empty and
  never calls `libpath`/`getuser`; the O code-object branch is unchanged.

No `/env`, `/proc`, `/dev` hierarchy, fake FD/Chan, catch-all exception
suppression or global `getenv` change was added. Later legacy-only
`spaceslow`/`spacefail`/`spacecheck` calls are in the file-backed commit
branch and are not reached by native `ocommit`.

## Three-boot evidence

One disposable O image was built with the current build's MicroPython,
then combined once with an ESP:

```text
MicroPython length = 2,195,994 bytes
MicroPython sha256 = cb3fe6159cf9e6ea148da15ccca71cbc8d118de42b82fd28120a44ba70723eaa
9pc64 md5          = 5efa866b985bd766b6e5c3df3b37b8cf
9pc64mp md5        = 26169ae05bd177d899912bcf01cc4298
```

Seed log and kernel-read digest agree:

```text
seed: mpexec 2195994 4f45584543000003 cb3fe615...723eaa unchanged
seed: object mp oid=0x4f45584543000003 len=2195994
OBOOT-D2B: OEXECUTE oid=0x4f45584543000003 len=2195994 sha256=cb3fe615...723eaa ver=0x1
```

The same combined image (`build/amd64/obootd2b.img`) was booted three
times. The host did not rerun `mkovol`/`gefsdisk`, reseed, copy or restore
the O volume between boots; only the disposable OVMF variables were
recreated per boot.

| Boot | Fresh/restore | run() | Commit | Counter |
| --- | --- | --- | --- | --- |
| 1 | `init has no graph`, one-time `odemo` init | 1 | init version 1 (O version 2) | n=1, OID 7, alias 7 |
| 2 | restored version 1, no module initialization | 2 | init version 2 (O version 3) | n=2, OID 7, alias 7 |
| 3 | restored version 2, no module initialization | 3 | init version 3 (O version 4) | n=3, OID 7, alias 7 |

Key output on each boot:

```text
OBOOT-D2B: P9-SPACE-O
OBOOT-D2B: SPACE-OPEN
space: O: init has no graph, Environment e1e...
or space: O: init restored (odemo), no module initialization
init: run() -> N
OBOOT-D2B: RUN
space: O: committed init version N (O version N+1)
OBOOT-D2B: COMMIT
init: shared Counter n N, alias same, OID 7 (alias 7)
init: done
```

`init: done` follows the successful native commit and report. The process
then remains in its sleep loop; QEMU is stopped externally. No
`boot.py`, `BIND`, `OPEN`, `PWRITE`, `FD2PATH`, `namec`, `newchan`, `walk`,
`devwalk`, `mount` or path-exec occurred on any of the three boots.

## Native/path audit

The guarded `OBOOT-D2B:` trace showed:

```text
OBOOT-D2B: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-D2B: AFTER-SYSCALLS n=4 ... path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-D2B: AFTER-SYSCALLS n=16 ... all zero
OBOOT-D2B: AFTER-SYSCALLS n=32 ... all zero
OBOOT-D2B: AFTER-SYSCALLS n=64 ... all zero
```

The targeted audit prints `OBOOT-D2B: LEGACY-ATTEMPT` for any user
`BIND/OPEN/READ/WRITE/PWRITE/FD2PATH/CREATE/MOUNT/REMOVE/STAT/...`; there
were **zero** such records on all three boots. The only visible output
syscalls were `IOWRITE` (handle 2) from MicroPython; `init: done` was
delivered by that native path, not a kernel replica.

## Negative cases

1. **`run()` raises**: a separate disposable O image compiled from a
   test-only source whose `run()` raises. Boot reaches `-N` and
   `p9_space_boot`; it reports `init: run failed`, `init: failed, no
   commit`, and never prints `init: done` or `COMMIT` or a new version.
   The process stays alive; there is no panic/fault.
2. **Missing `OID_MP_EXEC`** (`NOMPEXEC=1`): the loader's `OEXECUTE`
   returns `-1` before MicroPython, the same handle still reads the
   209-byte code object (`OSPACEGET ret=0xd1`), and it reports
   `alarm(0xbaf)`. No MicroPython text, no `init: done`, no commit and no
   panic.

Logs: `build/verification/test-oboot-server-fail-experiment-d2b.log`,
`test-oboot-server-missing-experiment-d2b.log`.

## Commands and controls

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-d2b.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-d2b.log
tools/test-oboot-server.sh 2>&1 | tee build/verification/test-oboot-server-experiment-d2b.log
tools/test-oboot-output.sh
tools/test-oboot-oid.sh
tools/test-oboot-user.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A oboot=probe disposable QEMU boot
```

| Check | Result | Log |
| --- | --- | --- |
| Build | **PASS** (`BUILD-DONE`) | `build/verification/build-experiment-d2b.log` |
| selfroot at `3cfd4ed` | **PASS** | `build/verification/selfroot-experiment-d2b.log` |
| D2b server three boots | **PASS** | `build/verification/test-oboot-server-experiment-d2b.log`, `...-boot1/2/3-...log` |
| `run()` failure | **PASS (negative)** | `test-oboot-server-fail-experiment-d2b.log` |
| Missing OID_MP_EXEC | **PASS (negative)** | `test-oboot-server-missing-experiment-d2b.log` |
| D2a output diagnostic | **PASS** | `test-oboot-output-experiment-d2b.log` |
| Boot C / Boot B / Boot A | **PASS** | `test-oboot-oid-experiment-d2b.log`, `test-oboot-user-experiment-d2b.log`, `test-oboot-probe-experiment-d2b.log` |
| Normal O boot | **PASS** | `test-o-boot-experiment-d2b.log` |
| Native O storage | **PASS** | `test-o-pathless-experiment-d2b.log` |
| Native exec/argv/handles | **PASS** | `test-o-exec-*-experiment-d2b.log`, `test-o-handles-experiment-d2b.log` |

The `test-o-pathless` negative cases retain their documented expected
`panic: boot process died: fail`; the gate exits 0.

## Limits

* `-N` is a fixed `odemo`/`init` server proof, not a general program
  catalog or daemon framework. It does not implement input/REPL, serial
  RX, keyboard events, line discipline, screen memory, a general stream
  registry, `/dev`, 9P, a file tree or desktop mode.
* The output stream handles 1/2 and UART backend remain the experimental
  D2a mechanism. The process-local grant contract is the durable part.
* No graph corruption beyond the separate `run()`-raises fixture was
  tested; the positive disk was not modified for negative tests.
* The current Space is one active native O volume and one `init` Space.
