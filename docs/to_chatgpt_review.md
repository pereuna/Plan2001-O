# E5 completion report — OpenCode

```text
E5 VERDICT: APPROVE

BASE / FINAL COMMIT(S) / BRANCH:
  base dd3c4f2cc3bd462a6a6f285daccb322a52e9ef9b (after the ff-only update)
  implementation 53785d754cd6239d7ac3e0ce70e5792f543a07d1
  branch main (this report is a second, documentation-only commit)

EXPLICIT SCOPE: O-only no #c registration / full repository legacy removal
  PROVEN: pc64oconsole does not register or link consdevtab.
  NOT CLAIMED / NOT DONE: the legacy #c adapter is still present in the
  repository and in pc64, pc64mp and pc64native.  No global deletion of
  Chan, Dev, Qid, Dirtab or other drivers was attempted.

23-QID COVERAGE: native 19, legacy-only 2, intentionally-unsupported 2,
                 unclassified 0
  Qids: Qdir, Qbintime, Qcons, Qconsctl, Qcputime, Qdrivers, Qkmesg,
  Qkprint, Qhostdomain, Qhostowner, Qnull, Qosversion, Qpid, Qppid,
  Qrandom, Qreboot, Qsysname, Qsysstat, Qtime, Quser, Qzero, Qmordor,
  Qconfig (23).
  legacy-only: Qdir, Qdrivers.
  intentionally-unsupported: Qconsctl, Qmordor.
  Full rows: docs/CONS-MIGRATION.md; checker: tools/cons_migration_check.py.

CORE SYMBOLS:
  print       native, sys/src/9/port/cons.c
  iprint      native, cons.c (splhi + best-effort lock; UART/screen)
  panic       native, cons.c (kprint disabled, consdebug, prflush,
              dumpstack and reboot/hang policy preserved)
  putstrn     native, cons.c -> consputstr(str,n,0)
  pprint      legacy-only, retained in cons.c; still uses up->fgrp->fd[2]
              and Dev->write(Chan*) for fault paths; not used by O-only boot
  readnum     native shared formatting helper, cons.c
  readstr     native shared formatting helper, cons.c
  init        consinit native, cons.c (idempotent todinit + randominit);
              called by legacy consdevtab.init and by ouserproc/onativeprobe
              on paths that never call chandevinit()
  shutdown    devshutdown legacy no-op in the adapter; cpushutdown native
              in cons.c

KERNEL C API: actual functions, files and ownership
  sys/src/9/port/cons.c:
    consputstr(char*,int,int); print/iprint/panic/putstrn;
    kmesgwrite/kmesgreadat; kprintacquire/kprintread/kprintrelease;
    consinit; consactive; prflush; cpushutdown; readnum/readstr.
  sys/src/9/port/procobs.c:
    procpid; procppid; procusername; proccputimes(uvlong*,int).
  sys/src/9/port/sysinfo.c:
    sysnameget/sysnameset; hostownerget; hostdomainget; configget;
    osversionget; sysstatget/Sysstat/sysstatreset; timecontrolallowed;
    nulldiscard; zerofill.
  Reused directly, not wrapped:
    todget/todset/todsetfreq; randominit/randomread; rebootcmd; panic; rdb;
    userwrite; hostownerwrite; hostdomainwrite; Queue/qread/qwrite.
  No new function takes Chan*, Qid, Dirtab or a path.

USERSPACE ABI:
  implemented: none.
  existing reused: none broadened.  The native operations are kernel-only.
  OPEN: any user exposure of process observations, log subscription,
  clock setting, reboot/rdb, hostowner/identity or config would need a
  reviewed rights/lifetime/layout contract.  IOWRITE and the O syscalls were
  deliberately not changed.

LEGACY #c:
  retained in pc64, pc64mp and pc64native for compatibility and E4.
  removed from O-only registration in pc64oconsole: the config has no
  "cons" line in its dev section, the generated pc64oconsole.devc.c has no
  &consdevtab, and the linked 9pc64oconsole has no consdevtab symbol.
  devcons.c is now only the Chan/Qid/Dirtab adapter, time text/binary
  encoding and the two E4 text helpers.

BUILD AND RUNTIME: exact commands and results
  PASS  python3 tools/cons_migration_check.py
  PASS  python3 tools/kernel_opmap.py --write
  PASS  python3 tools/kernel_opmap.py --check
  PASS  python3 tools/test_kernel_opmap.py            (29/29)
  PASS  NATIVE_PROBE=1 WHAT=kernel tools/build.sh     (9pc64native)
  PASS  tools/test-o-native-generator.sh              (E4 + E5 probe)
  PASS  WHAT=kernel tools/build.sh                    (9pc64, 9pc64mp)
  PASS  tools/test-o-boot.sh                          (legacy 9pc64)
  PASS  OCONSOLE=1 WHAT=kernel tools/build.sh         (9pc64oconsole)
  PASS  python3 tools/cons_migration_check.py --kernel
        build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
  PASS  OCONSOLE=1 tools/test-oboot-server.sh         (3 boots + negatives)
  NOT RUN: WHAT=all, GUI boot, unrelated network/storage batteries; not
  required for this gate.  The O-only D2b used the already-built selfroot
  MicroPython/gefs/O seed and the freshly built kernel, not a full tree
  rebuild.
  Logs (ignored): build/verification/e5/oconsole/, e5/native/, e5/build/.

PATHLESS EVIDENCE:
  O-only D2b boot 1/2/3 each printed
  "OBOOT-D2B: AFTER-SYSCALLS n=64 legacy userinit=0 proc0=0 init0=0 path
   namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0"
  and "cons: init tod=1 random=1", with run() -> 1/2/3 and no panic/fault.
  The native read/service probe printed BEGIN/END with
  namec=newchan=walk=devwalk=mount=exec=0 for its measured window.  The
  legacy adapter control in the same probe intentionally runs after END and
  is not part of the pathless window.  This is a measured-window claim, not
  a whole-kernel claim.

SECURITY/LIFETIME:
  - Legacy devopen/Dirtab permission checks remain on the #c adapter.
  - Qtime/Qbintime/Qreboot writes call timecontrolallowed(); no current eve
    or an unprivileged process is denied.  The probe verifies denial without
    calling panic/rdb/reboot.
  - Qhostowner/Qhostdomain writes keep the existing iseve checks in auth.c.
  - Quser write keeps userwrite's "none"-only rule.
  - kprint retains tas exclusivity, qopen(8K,Qcoalesce), qnoblock, read via
    qread, and qhangup on close; the probe verifies busy, read and reopen.
  - kmesg keeps its ilock ring and unlocked snapshot policy.
  - Queue/Stream/Pipe meanings were not collapsed; no generic handle or
    capability system was added.
  - consinit starts randomseed only in a real process context (ouserproc or
    the probe), avoiding a parentless boot kproc panic.

UNRESOLVED:
  - Qdir/attach/walk/stat/open/close remain legacy namespace operations;
    no native path replacement is proposed.
  - Qdrivers remains a legacy Dev listing/Pgrp mask, not native inventory.
  - Qmordor and Qconsctl remain deliberate refusals.
  - pprint remains legacy-only and still reaches fd 2 through Fgrp/Chan.
  - No userspace ABI exists for the new kernel services; exposing any of
    them needs a separate reviewed contract.
  - Full repository legacy removal is out of scope and not claimed.
```
