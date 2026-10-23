# Boot Experiment D2a: native output stream over the UART backend

**Date:** 23 October 2026. **Source state:** implementation commits
`4c2ae36f00ad976cf9a3efa7b258dc479f2e323c` (kernel/port/output) and
`182be33cd976439f6dff68a07356e3396bef5714` (gate native probing to
`-O` runs), plus this documentation follow-up. Runtime evidence was
produced from that committed source with `WHAT=all`, a clean
`tools/selfroot`, and disposable QEMU images.

## Verdict

```text
D2a OUTPUT PASS
NEXT BLOCKER = BIND (#¤ then /dev) from boot.py: bindmount/namec needs
               up->slash; slash is nil, so the second namec faults
               (kernel fault read addr=0x0).
LEGACY COMPATIBILITY = PASS (normal O/MicroPython three-boot gate).
STREAM API LIMITS = provisional: two fixed process-local handles (1 OUT,
                    2 DIAG) to the one console UART; no registry, input,
                    PTY, screen, kbmap, 9P or general device model.
```

The first real MicroPython diagnostic now arrives on the host UART from
the new user `iowrite` syscall. No `PWRITE(fd=2)` is attempted for it and
`up->fgrp` remains nil. The verified prefix through that message is
pathname-free. The next operation, `boot.py`'s first `bind`, is a
**downstream** failure and is reported rather than hidden.

## Durable contract vs experimental backend

**Intended to survive this experiment:** an output operation names a
process-owned **handle** to a stream. A handle is not an FD, `Chan`,
pathname or persistent OID. The process must hold an explicit grant in
`Proc.iomask`; absent/forged handles return a normal error. The grant is
preserved across `OEXECUTE` (same `Proc`/PID) and cleared when `newproc`
reuses the process slot. It is not inherited by unrelated processes.

**Temporary in D2a:** handle numbers `1` (OUT) and `2` (DIAG), the single
console-UART backend, the `putstrn` CRLF behavior, the syscall number
`62`, and `oboot=mp` as the only grant site. There is no stream registry,
generic device framework, input path, terminal model or final ABI.

## Kernel implementation

* `sys/src/9/port/portdat.h:670-674` defines provisional handle values
  `Iohout=1`, `Iohdiag=2` and grant bits `Iomout`, `Iomdiag`;
  `Proc.iomask` is at `:714`.
* `sys/src/9/port/proc.c:716` clears `p->iomask = 0` for every new or
  reused `Proc`.
* `sys/src/9/pc64/ouser.c:200-201` grants `Iomout|Iomdiag` only when
  `oboot=mp`. The grant survives `execo`/`execcommit` because the `Proc`
  is unchanged; `pexit`/process reuse clears it through `newproc`.
* `sys/src/libc/9syscall/sys.h:61` adds `IOWRITE 62`;
  `sys/src/9/port/systab.h:129,193` registers `sysiowrite` and its name.
  The ordinary amd64 libc stub generator therefore emits the user
  `iowrite` wrapper.
* `sys/src/9/port/sysfile.c:840-886` implements the syscall:

```c
long iowrite(int h, void *buf, long n);
```

  It validates the process grant (`up->iomask`), rejects absent/forged
  handles and negative or over-64-KiB lengths, returns 0 for a zero-length
  capability probe, checks the console UART is present, calls
  `validaddr()` on the user buffer, copies the bounded bytes to kernel
  memory, and then sends them through the existing `putstrn()` console
  path (the existing UART/serial queue and CRLF conversion). No user
  pointer reaches the UART driver and no bytes are emitted before the
  copy succeeds.
* `sys/src/9/port/chan.c:1342-1343` remains the pathname start point; the
  new output syscall never calls it.

## Independent D1 panic repair

`fdtochan()` (`sys/src/9/port/sysfile.c:145-148`) now checks for a nil
`up->fgrp` before `lock(f)` and returns the existing `Ebadfd` error. The
ordinary FD path is unchanged. The loader's user-originated legacy
`pwrite(2, ...)` therefore returns `-1` instead of faulting, and the
kernel stays alive. This does not create an FD table, console binding or
UART handling in the legacy write path.

## MicroPython port

* `p9console.c` has a port-local `p9_native_output()` probe using
  `iowrite(1, nil, 0)`. `p9_console_native(on)` is called from
  `main.c:162` only for `-O` runs; the normal seeding path
  (`micropython /tmp/oseed.py`, no `-O`) never probes the new syscall.
  This keeps the build VM's older 9front kernel safe while preserving
  the same MicroPython binary for normal O boots.
* `p9_console_write()` (Python `print`, exceptions, stdout) uses native
  handle 1 when the capability exists; otherwise it keeps the original
  `write(1)` behavior. It chunks writes and never silently falls back
  after native mode is selected.
* `p9_dprintf()` is a bounded port-local formatter for the existing
  `fprint(2, ...)` diagnostics in `main.c`/`p9space.c`. With native output
  it uses handle 2; in legacy boot it formats and calls
  `fprint(2, "%s", buf)`, preserving the existing text. There is no
  recursive error printer and no native-to-fd-2 fallback.
* `boot.py`, `p9console.c` input/`/dev/consctl`, `/dev/cons`, `kbdfs` and
  the persisted Python model are unchanged.

## Provenance

The D2a build produced:

```text
MicroPython length = 2,195,102 bytes
MicroPython sha256 = 96a82678e03dbd2c1425b50c4e97fcbfb60b6b344af564a741b8bff80bf5c086
normal 9pc64 md5   = cca9f4f64b7b819ec9cf1ddc51bdfd72
test 9pc64mp md5   = 644b90f7e2a80b818e8770ca7594aae2
```

`tools/mkovol MPEXEC=<current build>` stored that exact byte sequence:

```text
seed: mpexec 2195102 4f45584543000003 96a82678...bf5c086 unchanged
seed: object mp oid=0x4f45584543000003 len=2195102
```

The kernel independently hashed the bytes returned by `onativeget`:

```text
OBOOT-D1: OEXECUTE oid=0x4f45584543000003 len=2195102 sha256=96a82678...bf5c086 ver=0x1
```

The `RAWEXEC`/`NATIVEXEC` fixtures are not used.

## Observed transcript (key lines)

```text
OBOOT-D1: KERNEL-READY pid=1 entry=0x200028 ... slash=nil dot=nil
OBOOT-D1: ARGV argc=6 <micropython> <-O> <PARTUUID=...> <-S> <init> <-B>
...
OBOOT-D1: IOWRITE-ENTRY pid=1 h=99 buf=0x0 n=0 text=*ouser*
OBOOT-D1: IOWRITE-RETURN pid=1 h=99 buf=0x0 n=0 ret=-1
OBOOT-D1: IOWRITE-ENTRY pid=1 h=1 buf=0x0 n=-1 text=*ouser*
OBOOT-D1: IOWRITE-RETURN pid=1 h=1 buf=0x0 n=-1 ret=-1
OBOOT-D1: IOWRITE-ENTRY pid=1 h=2 buf=0x0 n=65537 text=*ouser*
OBOOT-D1: IOWRITE-RETURN pid=1 h=2 buf=0x0 n=65537 ret=-1
OBOOT-D1: SYSCALL-RETURN ... nr=51 ... ret=0xffffffffffffffff text=*ouser*
...
OBOOT-D1: OEXECUTE oid=0x4f45584543000003 len=2195102 sha256=96a82678...bf5c086 ver=0x1
OBOOT-D1: SYSCALL-RETURN ... nr=60 ... text=micropython
OBOOT-D1: SYSCALL-RETURN ... nr=54 ... ret=0x1 ... text=micropython
OBOOT-D1: IOWRITE-ENTRY ... h=1 buf=0x0 n=0 text=micropython
OBOOT-D1: IOWRITE-RETURN ... h=1 buf=0x0 n=0 ret=0
OBOOT-D1: IOWRITE-ENTRY ... h=2 buf=0x7fffffffe4b8 n=72 text=micropython
space: O volume selected: PARTUUID=60e27a6a-2499-4bd6-b5e3-fd1c4608d140
OBOOT-D1: IOWRITE-RETURN ... h=2 buf=0x7fffffffe4b8 n=72 ret=72
OBOOT-D2A: OUTPUT h=2 n=72 counters namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
OBOOT-D1: SYSCALL-ENTRY ... nr=24 ... text=micropython
OBOOT-D1: SYSCALL-RETURN ... nr=24 ... ret=0x0 ... text=micropython
OBOOT-D1: SYSCALL-ENTRY ... nr=2 ... text=micropython
OBOOT-D1: BIND-ENTRY ... slash=0x0 counters ... all zero
OBOOT-D1: NAMEC-ENTER ... counters namec=1 newchan=0 walk=0 devwalk=0 ...
OBOOT-D1: NAMEC-ENTER ... counters namec=2 newchan=2 walk=1 devwalk=1 ...
panic: kernel fault: read addr=0x0
```

The UART message is the real user-supplied `p9_dprintf` text, not a
kernel replica. The `IOWRITE` entry/return records prove it came from the
new syscall. No `PWRITE` from `text=micropython` occurs before it.

## Startup phases

| Milestone | Status |
| --- | --- |
| Loader ring 3, OVOLOPEN, OSPACEOPEN, OEXECUTE(OID_MP_EXEC) | **REACHED** |
| MicroPython entry and `p9_space_o` OVOLOPEN | **REACHED** |
| `p9_space_o` returned | **REACHED** (boot.py executes next) |
| Native output probe and `space: O volume selected` on UART | **REACHED** |
| `boot.py` entered | **REACHED** |
| First `bind` (`#¤` then `/dev`) | **ATTEMPTED, downstream failure** |
| `space.open('init')` | **NOT REACHED** |
| `p9_space_boot`, run(), durable commit | **NOT REACHED** |

At the output checkpoint the cumulative legacy/path counters are all
zero: `userinit=proc0=init0=0`, `namec=newchan=walk=devwalk=mount=exec=0`.
After the milestone, `bind` enters `namec` and the counters become
`namec=1`, then `namec=2 newchan=2 walk=1 devwalk=1`; these are reported,
not suppressed.

## Next blocker

The next current operation is `boot.py:41`:

```python
for d in ('#¤', '#¶', '#P', '#S', '#f', '#æ', '#t', '#b', '#m'):
    try:
        p.bind(d, '/dev', p.MAFTER)
```

`sysbind` -> `bindmount` -> `namec(arg1, "/dev")` reaches
`chan.c:1342-1343`:

```c
c = up->slash;
incref(c);
```

`up->slash` is nil, so the second `namec` faults at address 0 and the
kernel panics. The first `namec` for `#¤` is recorded; the failure is in
the `/dev` destination path, not in the new output stream. This is the
next actual namespace dependency and is explicitly **not fixed** in D2a.

## Negative and compatibility tests

* User-originated native-output negatives: absent handle `99` returns
  `-1`; negative length `-1` returns `-1`; oversize length `65537`
  returns `-1`. A legacy `pwrite(2, ...)` from the same nil-`Fgrp`
  process returns `-1` instead of panicking (the independent `fdtochan`
  repair).
* A deliberately invalid user pointer is rejected by `validaddr()`
  before any copy/output. It was not injected into the positive pid-1
  boot because a bad syscall address is a normal process note that would
  terminate the bootstrap; no UART bytes can be produced because the
  copy happens before `putstrn()`.
* Missing `OID_MP_EXEC` (`NOMPEXEC=1`): `OEXECUTE` returns `-1`, the
  same handle still reads the 209-byte code object (`OSPACEGET` ret
  `0xd1`), the loader reports `alarm(0xbaf)`, no MicroPython text and no
  panic.

## Commands and results

```bash
WHAT=all tools/build.sh 2>&1 | tee build/verification/build-experiment-d2a.log
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot \
  2>&1 | tee build/verification/selfroot-experiment-d2a.log
tools/test-oboot-output.sh 2>&1 | tee build/verification/test-oboot-output-experiment-d2a.log
tools/test-oboot-user.sh
tools/test-oboot-oid.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A oboot=probe QEMU boot
```

| Check | Result | Log |
| --- | --- | --- |
| Full amd64 build | **PASS** | `build/verification/build-experiment-d2a.log` |
| selfroot at `182be33` | **PASS** | `build/verification/selfroot-experiment-d2a.log` |
| D2a output gate | **PASS** | `build/verification/test-oboot-output-experiment-d2a.log`, `...-pos-...log`, `...-missing-...log` |
| Boot A probe | **PASS** | `build/verification/test-oboot-probe-experiment-d2a.log` |
| Boot B | **PASS** | `build/verification/test-oboot-user-experiment-d2a.log` |
| Boot C | **PASS** | `build/verification/test-oboot-oid-experiment-d2a.log` |
| Normal O boot | **PASS** | `build/verification/test-o-boot-experiment-d2a.log` |
| Native O storage | **PASS** | `build/verification/test-o-pathless-experiment-d2a.log` |
| Native exec/argv/handles | **PASS** | `build/verification/test-o-exec-*-experiment-d2a.log`, `test-o-handles-experiment-d2a.log` |

The historical `tools/test-oboot-mp.sh` D1 harness is now marked
superseded: it expects the pre-D2a nil-`Fgrp` `PWRITE` panic and is not a
D2a regression gate.

## Limits and non-claims

* Not a console server, REPL, input path, PTY, screen buffer, kbmap or
  `namec`/`Chan` removal.
* No `boot.py` rewrite or automatic skipping of its device setup.
* The next BIND failure is a downstream diagnostic, not a successful
  console migration and not D2b/D2c.
* The stream handles and UART-only backend are experimental and
  provisional; the process-local authorization contract is the intended
  durable part.
* Normal legacy `write(1)`/`fprint(2,...)` paths remain for compatibility
  and are used outside `oboot=mp` native output.
