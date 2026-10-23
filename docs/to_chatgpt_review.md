**Boot C PASS** — the first ring-3 process opened a generated `PARTUUID=` O volume, loaded a genuinely O-resident executable via `OEXECUTE`, and ran it after the image transition.

- Chain: embedded loader → `OVOLOPEN` (ret 1, exact GUID) → `OSPACEOPEN` (`h=1`) → `OEXECUTE` OID `0x4f45584543000004` (`len=2088 sum=3f ver=0x1`) → `execo`/`execcommit` → target.
- Post-exec proof: `SYSCALL-RETURN nr=60 ... text=obootctarget pc=0x200098 cs=0x2b ss=0x23`; target then gets `ospaceget` → `-1` (old handle gone), `alarm(0x42)`, `sleep(0x1234)`, `sleep(0x5678)`.
- Counters before and after exec: `userinit=proc0=init0=0`; `namec=newchan=walk=devwalk=mount=exec=0`.
- Negatives PASS: wrong GUID fails at `OVOLOPEN` with no fallback; missing OID returns `-1`, handle survives (`ospaceget` returns 209 bytes), target never runs, no panic.
- Controls PASS: Boot A, Boot B, normal O/MicroPython, pathless storage, native exec, argv, handles.
- Commits: `3374eb9` (implementation), `5e3683e` (docs), pushed. Evidence: `docs/O-BOOT-EXPERIMENT-C.md`, `build/verification/test-oboot-oid-*.log`.

**Must execute:** scheduler/`Proc`/`Pgrp`, timers, `chandevreset`, GE/O worker kprocs and native SD block reads, trap/syscall path, `otouser`, `execo`/`execcommit`/`execregs`, `oprocexec`, segment/page allocation. **Linked/initialized only:** `namec`, `Chan`, `Dev` file operations, `devroot`, 9P, `bind`/`mount`/path `exec`, `/boot`, `Fgrp`/`Egrp`/`Rgrp`, `slash`/`dot`, console, and the legacy `userinit`/`proc0`/`init0`/`initcode` chain.

**Next step (not implemented):** point the same ring-3 `OEXECUTE` path at `OID_MP_EXEC` with the existing `-O`/`-S init` argv and add a direct serial-backed console/stdin/stdout so `boot.py` and the REPL no longer depend on `/dev/cons`, `kbdfs`, or an FD console.
