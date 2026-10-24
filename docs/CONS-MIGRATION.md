# `#c` / `consdevtab` migration manifest (E5)

**Scope:** source-oriented operation matrix for the inherited `sys/src/9/port/devcons.c` aggregator at the E5 implementation revision.
**Status vocabulary:** `native` = a concrete, independently callable kernel C operation exists; `legacy-only` = preserved only in the legacy `#c` adapter, with no manufactured native replacement; `intentionally-unsupported` = deliberately has no successor and the adapter preserves the historical refusal/error.
**Non-goals:** this is not a new filesystem, generic `Dev`/`Handle`/`Channel` layer, userspace ABI, or claim that `#b`, `#i`, `#v`, `#t` or UART/screen drivers migrated.

## Operation matrix

| Qid_or_symbol | current_read | current_write | legacy_perm | owner | native_operation | callers | security | state/lifetime | migration_status | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qdir | `devdirread` | none (`Egreg`) | `DMDIR\|0555` | legacy namespace | none | legacy `#c` walk/dirread only | inherited `devopen`/perm | per-open `Chan` | legacy-only | `devcons.c:consread`; no pathless consumer |
| Qbintime | binary time snapshot | binary time set/trim/freq | `0664` | Time service | `todget`, `todset`, `todsetfreq`; serialization stays in adapter | kernel time users; legacy `/dev/bintime` | adapter `timecontrolallowed`, binary widths preserved | tod global state | native | `devcons.c:readbintime/writebintime`; `tod.c` |
| Qcons | `Egreg` | console byte output | `0660` | Console service | `consputstr(str,n,usewrite)` | `print`, `iprint`, legacy `/dev/cons` | `devopen` for legacy; kernel callers trusted | log ring + serialo/kprint queues | native | `cons.c:consputstr`; `devcons.c:conswrite Qcons` |
| Qconsctl | `Egreg` | `Egreg` | `0220` | none | none | none | historical refusal | none | intentionally-unsupported | `devcons.c:consread/conswrite Qconsctl` |
| Qcputime | six accounting fields | none | `0444` | Proc observation | `proccputimes(uvlong*,int)` | legacy `/dev/cputime` | current `up` only; kernel-internal | current process | native | `procobs.c:proccputimes`; `cons.c` formatting in adapter |
| Qdrivers | legacy `Dev` listing | `chdev` mask command | `0666` | legacy namespace/mask | none | legacy `#c` only | `Pgrp` `devmask`; not a native driver inventory | per-`Pgrp` mask | legacy-only | `devcons.c:consread/conswrite Qdrivers`; `devmask()` |
| Qkmesg | snapshot of log ring | none | `0440` | Console/log service | `kmesgreadat(void*,long,vlong)`, `kmesgwrite` | `print`/`consputstr`; legacy `/dev/kmesg` | `devopen` for legacy; unlocked snapshot policy documented | `kmesg` ring under `ilock` | native | `cons.c:kmesgwrite/kmesgreadat` |
| Qkprint | exclusive console stream | none | `DMEXCL\|0440` | Console/log service | `kprintacquire`, `kprintread`, `kprintrelease` | legacy `/dev/kprint`; E5 probe | exclusive `tas`; close hangs up queue | `kprintoq` + `kprintinuse` | native | `cons.c:kprintacquire/kprintread/kprintrelease`; `devcons.c:consopen/consclose` |
| Qhostdomain | `hostdomain` | `hostdomainwrite` | `0664` | system configuration | `hostdomainget`; existing `hostdomainwrite` | legacy `/dev/hostdomain` | write requires `iseve` in `auth.c` | global `hostdomain[DOMLEN]` | native | `sysinfo.c:hostdomainget`; `auth.c:hostdomainwrite` |
| Qhostowner | `eve` | `hostownerwrite` | `0664` | system configuration/identity | `hostownerget`; existing `hostownerwrite` | legacy `/dev/hostowner` | write requires `iseve`; also renames users/groups/server | global `eve`; process credentials | native read; legacy #c write | `sysinfo.c:hostownerget`; `devcons.c:hostownerwrite` (E9.1 moved the legacy write helper here) |
| Qnull | `0` (EOF) | discard | `0666` | synthetic semantics | `nulldiscard(void*,long)`; read remains EOF | legacy `/dev/null`; E5 probe | none | stateless | native | `sysinfo.c:nulldiscard`; `devcons.c` |
| Qosversion | constant `2000` | none | `0444` | system configuration | `osversionget` | legacy `/dev/osversion` | read-only | stateless constant | native | `sysinfo.c:osversionget` |
| Qpid | current PID text | none | `0444` | Proc observation | `procpid`; E4 `consqpidread` remains the text adapter/generated entry | generated `native_cons_qpid_read`, legacy `/dev/pid`, E5 probe | current `up` only; kernel-internal | current process | native | `procobs.c:procpid`; `devcons.c:consqpidread`; `KERNEL-NATIVE-GENERATOR.md` |
| Qppid | current parent PID text | none | `0444` | Proc observation | `procppid`; E4 `consread_qppid_read` remains the text adapter/generated entry | generated `native_cons_qppid_read`, legacy `/dev/ppid`, E5 probe | current `up` only; kernel-internal | current process | native | `procobs.c:procppid`; `devcons.c:consread_qppid_read`; `KERNEL-NATIVE-GENERATOR.md` |
| Qrandom | entropy bytes | none | `0444` | Random service | `randominit`, `randomread` | kernel users; legacy `/dev/random`; E5 probe | `up` not required for read; init before use | ChaCha state under `QLock` | native | `random.c`; `cons.c:consinit` |
| Qreboot | none | `reboot`, `panic`, `rdb` commands | `0220` | system control | existing `rebootcmd`, `panic`, `rdb`/`consdebug` | legacy `/dev/reboot` only | adapter `timecontrolallowed`; destructive controls stay kernel/trusted only | machine state | native | `devcons.c:conswrite Qreboot`; `rebootcmd.c`, `rdb.c` |
| Qsysname | `sysname` | set sysname | `0664` | system configuration | `sysnameget`, `sysnameset` | legacy `/dev/sysname`; E5 probe | legacy `devopen`; kernel callers trusted | global `sysname` string | native | `sysinfo.c:sysnameget/sysnameset` |
| Qsysstat | multi-CPU statistics | reset counters | `0664` | monitoring | `sysstatget`, `sysstatreset` | legacy `/dev/sysstat`; E5 probe | legacy `devopen`; reset is kernel-only policy | per-`Mach` counters | native | `sysinfo.c:sysstatget/sysstatreset`; `Sysstat` in `portdat.h` |
| Qtime | text time snapshot | set seconds | `0664` | Time service | `todget`; serialization in adapter; set via `todset` | kernel time users; legacy `/dev/time` | adapter `timecontrolallowed` | tod global state | native | `devcons.c:readtime/writetime`; `tod.c` |
| Quser | current user name | `userwrite` (`none`) | `0666` | Proc identity | `procusername`; existing `userwrite` | legacy `/dev/user`; E5 probe | `userwrite` only permits `none` | current process credentials | native | `procobs.c:procusername`; `auth.c:userwrite` |
| Qzero | zero-filled bytes | none (`Egreg`) | `0444` | synthetic semantics | `zerofill(void*,long)` | legacy `/dev/zero`; E5 probe | none | stateless | native | `sysinfo.c:zerofill` |
| Qmordor | deliberate error | deliberate error | `0666` | none | none | negative test only | historical refusal | none | intentionally-unsupported | `devcons.c:consread/conswrite Qmordor` |
| Qconfig | `configfile` | `Eperm` | `0444` | system configuration | `configget`; no writer | legacy `/dev/config`; E5 probe | read-only by design | boot configuration text | native | `sysinfo.c:configget`; `devcons.c:Qconfig` |
| consinit | lifecycle | lifecycle | n/a | Console/Time/Random lifecycle | `consinit` (idempotent `todinit` + `randominit`) | `main.c` boot core and legacy `consdevtab.reset` | early boot; no `up` required | one-time service start | native | `cons.c:consinit`; `main.c` call before `chandevreset` |
| devreset | n/a | reset | n/a | legacy `Dev` | `consinit` | generated `consdevtab` only | no `up` required | one-time | native | `devcons.c:consdevtab` |
| devshutdown | n/a | shutdown | n/a | legacy `Dev` | default `devshutdown` (no-op) | generated `consdevtab` only | none | none | legacy-only | `devcons.c:consdevtab` |
| consattach | attach | n/a | n/a | legacy namespace | none | `#c` attach only | inherited `devattach` | per-`Chan` | legacy-only | `devcons.c:consattach` |
| conswalk | walk | n/a | n/a | legacy namespace | none | `#c` walk only | inherited `devwalk` | per-`Chan` | legacy-only | `devcons.c:conswalk` |
| consstat | stat | n/a | n/a | legacy namespace | none | `#c` stat only | inherited `devstat` | per-`Chan` | legacy-only | `devcons.c:consstat` |
| consopen | open | n/a | n/a | legacy namespace | `kprintacquire` for Qkprint | `#c` open only | inherited `devopen` | per-`Chan` | legacy-only | `devcons.c:consopen` |
| consclose | n/a | close | n/a | legacy namespace | `kprintrelease` for Qkprint | `#c` close only | inherited exclusivity | per-`Chan` | legacy-only | `devcons.c:consclose` |
| putstrn0 | n/a | console bytes | n/a | Console service | `consputstr` (renamed; `usewrite` argument explicit) | former internal callers | same as `print` | log ring + queues | native | `cons.c:consputstr` |
| putstrn | n/a | console bytes | n/a | Console service | `putstrn` -> `consputstr(...,0)` | kernel callers | kernel-internal | log ring + queues | native | `cons.c:putstrn` |
| print | n/a | formatted console bytes | n/a | Console service | `print` | kernel-wide | kernel-internal | log ring + queues | native | `cons.c:print` |
| iprint | n/a | IRQ-safe console bytes | n/a | Console service | `iprint` | kernel-wide | `splhi`, best-effort lock | log ring not used; UART/screen | native | `cons.c:iprint` |
| panic | n/a | formatted panic output | n/a | Console service | `panic` | kernel-wide | crash context; disables kprint; preserved semantics | terminal | native | `cons.c:panic` |
| sysfatal | n/a | formatted panic | n/a | Console service | `sysfatal` -> `panic` | inherited libmp/gefs paths | crash context | terminal | native | `cons.c:sysfatal` |
| _assert | n/a | formatted panic | n/a | Console service | `_assert` -> `panic` | kernel-wide `assert` | crash context | terminal | native | `cons.c:_assert` |
| pprint | n/a | per-process stderr | n/a | legacy process I/O | `pprint` (retained; still uses `up->fgrp->fd[2]` -> `Chan`) | `fault.c`, trap paths | legacy fd 2 mode/`CMSG` checks | process `Fgrp` | legacy-only | `cons.c:pprint` |
| prflush | n/a | drain serial queue | n/a | Console service | `prflush` | panic/shutdown paths | polling with `HZ` bound | serial queue | native | `cons.c:prflush` |
| consactive | serial queue state | n/a | n/a | Console service | `consactive` | panic/cpu shutdown | no lock | serial queue | native | `cons.c:consactive` |
| cpushutdown | n/a | stop CPU | n/a | system control | `cpushutdown` | reboot/shutdown paths | privileged kernel caller | `active` state | native | `cons.c:cpushutdown` |
| kmesgputs | n/a | append log ring | n/a | Console service | `kmesgwrite` (renamed) | `consputstr` | `ilock`; huge writes keep tail | `kmesg` ring | native | `cons.c:kmesgwrite` |
| screenputs | n/a | screen byte output | n/a | Screen driver callback | `screenputs` global | `consputstr`/`iprint` | driver-owned locking | screen driver | native | `cons.c`; assigned by screen driver |
| serialoq | n/a | serial output queue | n/a | Console/UART | `serialoq` global | console output | `Queue` locking in UART code | queue lifetime boot | native | `cons.c`; `devuart.c` |
| kprintoq | exclusive reader queue | console output queue | n/a | Console/log service | `kprintoq` + kprint operations | console output | `qnoblock`, hangup on close | queue lifetime | native | `cons.c` |
| readnum | n/a | format decimal field | n/a | shared formatting | `readnum` | many legacy `Dev` readers | kernel-internal | stateless | native | `cons.c:readnum` |
| readstr | n/a | copy string with offset | n/a | shared formatting | `readstr` | many legacy `Dev` readers | kernel-internal | stateless | native | `cons.c:readstr` |
| readtime | text time | n/a | n/a | legacy text encoding | `todget` | `#c` adapter only | adapter policy | none | legacy-only | `devcons.c:readtime` |
| readbintime | binary time | n/a | n/a | legacy binary encoding | `todget` | `#c` adapter only | adapter policy | none | legacy-only | `devcons.c:readbintime` |
| writetime | n/a | parse/set seconds | n/a | legacy text encoding | `todset` | `#c` adapter only | `timecontrolallowed` | none | legacy-only | `devcons.c:writetime` |
| writebintime | n/a | parse/set binary time | n/a | legacy binary encoding | `todset`, `todsetfreq` | `#c` adapter only | `timecontrolallowed` | none | legacy-only | `devcons.c:writebintime` |

## Implemented ownership map

| File | Owns | Not owned here |
| --- | --- | --- |
| `sys/src/9/port/cons.c` | Console byte output, `print`/`iprint`/`panic`, log ring, `kprint` queue/exclusivity, `readnum`/`readstr`, console lifecycle, CPU shutdown | `Chan` namespace adapters; time encoding; configuration strings |
| `sys/src/9/port/procobs.c` | Typed current-process PID/PPID/user/accounting observations | Process control, handles to arbitrary processes |
| `sys/src/9/port/sysinfo.c` | System name/domain/owner/config getters, sysname setter, typed `Sysstat`, privileged clock gate, null/zero semantics | `Dev` enumeration, `Pgrp` masks, command parsing |
| `sys/src/9/port/tod.c`, `random.c` | Existing time and entropy implementations | Legacy text/binary encoding |
| `sys/src/9/port/devcons.c` | Legacy `#c` `Chan`/`Qid`/`Dirtab` adapter, text/binary encoding, and the legacy `Qhostowner` write helper | Kernel service implementation |

## O-only profile proof

`sys/src/9/pc64/pc64oconsole` is the normal `pc64` device set with the `cons` line deliberately absent from its `dev` section. `mkdevlist` therefore does not add `devcons.$O`, and `mkdevc` generates a `devtab[]` without `&consdevtab`. The core files `cons.c`, `procobs.c` and `sysinfo.c` are unconditional `PORT` objects, so `print`, `iprint`, `panic`, `putstrn`, `readnum`, `readstr`, `todinit`/`randominit` and the native services remain linked.

`pc64`, `pc64mp` and `pc64native` retain the `cons` registration for legacy comparison and the E4 probe. The O-only profile is selected only by `OCONSOLE=1` in `tools/build.sh`; it is not the default. This manifest does **not** claim that all legacy `#c` code was deleted from the repository, only that it is not registered or linked as a `Dev` in `pc64oconsole`.

## Unresolved / deliberately open

- No userspace ABI was added. Process, log, clock, configuration and control operations remain kernel-only. A future userspace consumer needs a reviewed rights/lifetime/layout contract; `IOWRITE` was not broadened.
- `Qdrivers` remains a Plan 9 namespace/`Pgrp`-mask facility, not a native driver-inventory service.
- `Qdir`/attach/walk/stat/open/close remain legacy namespace operations.
- `Qmordor` and `Qconsctl` remain deliberate refusals.
- `pprint` still depends on legacy fd 2/`Fgrp`/`Chan`; it was not concealed behind a native console function.
