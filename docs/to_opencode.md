# Plan2001-O — Boot Experiment D2b: native O server boot and durable three-boot proof

**Assignment for the continuing OpenCode agent.** Repository `pereuna/Plan2001-O`, current `main`. Continue from **D2a OUTPUT PASS** (implementation `4c2ae36` + `182be33`, evidence `docs/O-BOOT-EXPERIMENT-D2A.md`). Implement **one bounded vertical slice**: boot the real O-resident MicroPython as a persistent, noninteractive server, restore or initialize `init` Space, execute `run()`, commit, and repeat across **three consecutive QEMU boots of the same GE/O disk** — without the legacy `boot.py`, any `/dev` namespace, `kbdfs`, `Chan`/file path operations or a mounted root.

This task follows the user's distinction: **files/content are legitimate; what must not be compulsory is navigation through a hierarchical filesystem**. Streams, active handles, and devices remain separate concepts. **Do not reconstruct `/dev`**, fabricate a `Chan` to pass this gate, or make a special FD=2 workaround. D2a's native `IOWRITE` is already the diagnostic/output channel.

## 0. Confirm baseline and protect working tree

Run `git status --short`, `git log -8 --oneline`; read `AGENTS.md`, `docs/STATUS.md`, `docs/O-BOOT-EXPERIMENT-D2A.md`, `docs/O-BOOT-EXPERIMENT-D1.md`. Preserve unrelated edits and tests; do not `git reset --hard`, `git clean -fd`, force-push or `git add .` indiscriminately. Test only on disposable QEMU disk images.

Inspect actual source and call graph before editing:
- `sys/src/9/pc64/main.c`, `ouser.c`, `trap.c`; embedded user loader `sys/src/9/pc/obootoid.c`.
- `sys/src/cmd/micropython/main.c` (flag parsing, `bootpy`, `p9_console_init`, `p9_space_boot`, `p9_space_commit`, `p9_space_report`, and its post-success sleep loop).
- `sys/src/cmd/micropython/p9space.c` (native `p9_space_o`, `ospace_open`, `p9_space_boot`, `ocommit`, `p9_spacetime`, code import); `p9console.c`, `p9hal.c`, `boot.py`.
- `tools/test-o-boot.sh` (proven old three-boot counter and alias gate), `tools/test-oboot-output.sh` (D2a panic-after-BIND diagnostic), `tools/mkovol`, `tools/gefsdisk`, `tools/odemo.py`.

Previous D2a trace: real OID MicroPython completes `mp_init` and `p9_space_o`, outputs `space: O volume selected: ...` with native `IOWRITE`, then `boot.py` immediately calls `bind`; `namec("/dev")` dereferences `up->slash=nil` and panics. **D2b does not repair `bind` by providing a slash/dot.** The native boot must not call the legacy device bootstrap at all.

## 1. A real userland native startup contract: `-N`

Add one explicit MicroPython startup mode, preferably:

```
micropython -O PARTUUID=<fresh GUID> -S init -N
```

`-N` is the native **noninteractive server startup**, not an unrelated “ignore all errors” flag. Accept it only in combination with native `-O` and `-S <Space>`; invalid combinations must fail clearly rather than enter an REPL or fall back to legacy boot. In this minimal D2b gate the Space is `init`, as already implemented. Maintain the exact O volume / Space semantics.

The native `-N` path must:
1. parse args without legacy environment or pathname resolution;
2. initialize the MicroPython VM and heap as normal;
3. open native O volume using existing `p9_space_o` / `OVOLOPEN`;
4. **skip** execution of `bootpy` altogether;
5. invoke the existing `space.open('init')` through the `space` module's native `ospaceopen` / `ospaceget` path, restoring the saved Python graph if present, or initializing the seeded O module if fresh;
6. execute `p9_space_boot()`, including the existing one-time `odemo` initialization and `run()`;
7. commit with the **existing** `p9_space_commit(1)` / native `OSPACEPUT` and `OSPACECOMMIT`; do not fake a commit by printing a line;
8. report existing Counter OID/alias, version and `init: done` using D2a's native diagnostic/output streams; only report “done” after the durable commit;
9. remain alive without reading console input; preserve the successful server process rather than exiting via legacy `exits` and panicking the kernel.

**Do not call `p9_console_init()` on the native `-N` path**: it invokes `fd2path(0)`, and the future stdin and line discipline belong to D2c. Preserve `p9console` legacy behavior on `-B`/ordinary REPL paths. Any native stdout must use `IOWRITE` (process-held capability) and never FD 0/1/2.

Keep the existing `-B` meaning **unchanged**: it executes the old `boot.py` sequence for legacy-compatible boot, including current `oboot=mp` **D2a diagnostic behavior**. Do not remove or edit `boot.py`, `kbdfs`, `#c`, `/dev` or previously seeded Python state. Do not duplicate the Space persistence engine or introduce a second way to commit. The small `-N` entry-branch should converge on existing server boot/commit code.

## 2. Separate boot selector, reusing the same loader

Prefer a new opt-in `plan9.ini` selection `oboot=server` for the new `-N` run, leaving:
- `oboot=probe` (Boot A),
- `oboot=user` (Boot B),
- `oboot=oid` (Boot C),
- `oboot=mp` (D1/D2a diagnostic; still `-O ... -S init -B`),
- legacy/default normal O boot

**unchanged**. This avoids redefining D2a's existing test, which intentionally expects the inherited `boot.py` bind panic.

Reuse the existing **embedded one-page OID loader** and `OEXECUTE(OID_MP_EXEC)`, generated PARTUUID argument transport, image verification and `otouser` ring-3 process creation. For `oboot=server` pass the six-argument contract:

```
argc=6
argv={"micropython","-O","PARTUUID=<generated>","-S","init","-N"}
```

No path based exec, no alternate kernel MicroPython blob, no new interpreter OID, no special `/boot/oinit` or kernel-driven Python evaluation. Extend the opt-in D2a process-local `IOWRITE` grants to the new server mode using the minimum change (same `Proc` / same PID through `OEXECUTE`). Prefer one shared real implementation for D2a/D2b where possible; do not duplicate `ouserproc` and the loader.

If `oboot=server` creates a significant duplicate state or ABI complication, choose the smallest equivalent distinct opt-in selector, explain it and retain the prior D2a harness unaffected. Do **not** switch all existing `oboot=mp` boots to `-N`.

## 3. Audit for *hidden* legacy dependencies in the native path

This is especially important: simply skipping `boot.py` is not automatically proof of complete pathlessness. Trace runtime behavior through open, initial import, restore, commit and report.

Check `p9space.c:p9_spacetime`: it invokes `getenv("spacetime")` and is called during O Space restoration. Under Plan9, `getenv` may attempt to access legacy `/env`. Other `getenv("spaceslow"/"spacefail"/"spacecheck")` code exists, although several calls are in file-backed/legacy branches that the native path should not enter. For any such reachable optional legacy feature: show whether it is actually reached, and if it is, bypass **only the optional legacy instrumentation** in the `-N` path using a small explicit predicate, or supply a truly native configuration value. Do NOT create an `/env` hierarchy, silently catch and ignore all path exceptions, or globally change `getenv` semantics. Do not eliminate important data verification or write durability to make boot succeed.

Also inspect `atnotify`, native `p9_console_restore`, the current module importer, `getpid`, `p9_space_report` and libc routines actually executed. Preserve legitimate existing native `OSPACE*` calls and the O binary/graph semantics. Any new pathname/FD syscall is a **failure to be diagnosed** rather than a test to paper over.

**Instrumentation:** guarded `OBOOT-D2B:` checkpoints for the selected server mode/PID, including `-N` argv, `OEXECUTE` image transition, after `p9_space_o`, after `space.open`, after `run()`, and **after successful native commit**. Keep the established `opath_namec/newchan/walk/devwalk/mount/exec` and legacy `userinit/proc0/init0` counters cumulative. In addition to counters, capture **attempted legacy pathname and FD syscalls even if they fail before calling `namec`** (D1 lesson). Define a bounded trace or a targeted syscall-attempt audit that can substantiate absence through all three boots. Avoid flooding serial output or changing all syscall instrumentation globally.

Note that log strings such as `space: O: odemo code OID ...` are ordinary text, NOT evidence of a runtime `.py` file. Likewise the final executable resides on O despite the build machine having files. The test must distinguish actual runtime access from incidental diagnostic strings.

## 4. Three consecutive boots of the EXACT same disk

Create `tools/test-oboot-server.sh` (name indicative); follow the real `tools/test-o-boot.sh` logic and `tools/test-oboot-output.sh` for native QEMU setup.

- Build the current kernel and **the freshly built MicroPython** using the repository's real build workflow. Seed one disposable O image (the existing `tools/odemo.py` example, its immutable O-resident code/Environment, graph initially absent, and `OID_MP_EXEC` as a real executable object). Confirm host executable SHA-256 equals seed log and kernel's native `onativeget/OEXECUTE` SHA-256. Never seed the historical `selfroot` interpreter by accident if it differs from this build.
- Form one combined ESP+O GPT disk image, no `root=`, no `init=/boot/...`, with only generated `obootvol=PARTUUID=@PARTUUID@`, `oboot=server` and required neutral console setting. Inspect saved `plan9.ini` and generated `.partuuid`; no hard-coded GUID.
- Boot 1 until verified **`init: done` after commit**; preserve serial output and stop QEMU externally, cleanly after durability evidence. Use the **same combined image unchanged by host** on boots 2 and 3. Do not rerun `mkovol`/`gefsdisk`, re-seed, regenerate or copy/restore the O volume between boots. Reset disposable firmware variables per boot only as normal tests already do.
- On boot 1 assert `init` has no graph, initializes `odemo` once, `run() -> 1`, commits native init version 1, reports a shared Counter / alias with concrete OID.
- On boot 2 assert `init` restored version 1, **no module top-level reinitialization**, `run() -> 2`, commits version 2, original Counter OID and alias identity unchanged.
- On boot 3 assert `init` restored version 2, **no reinitialization**, `run() -> 3`, commits version 3, same Counter OID and alias.
- Prove the three programs really executed the O-seeded `OID_MP_EXEC=0x4f45584543000003` image through native `OEXECUTE`, not `/boot/mp` or a host-injected Python command.
- Assert **no `boot.py` execution, `BIND`, `OPEN`, `PWRITE`, `FD2PATH`, `namec`, `newchan`, `walk`, `devwalk`, `mount` or legacy path-exec** at any point through all three completed `init: done` events; `userinit=proc0=init0=0`, `slash/dot/fgrp=nil`. Use syscall-attempt tracing to ensure `OPEN/BIND/FD2PATH` are not merely failing before counters increment. Do not reset counters to engineer a PASS.
- Confirm an actual `IOWRITE` from native MicroPython delivered the `run()`, commit and `init: done` messages on host UART. No fabricated kernel messages to satisfy the assertions.
- Bounded timeouts and explicit FAIL on missing checkpoints, QEMU crash, unexpected fault/note/panic, wrong version or OID/alias mutation, failure/no commit, unexpected legacy syscall or unintended console read. Keep readable combined and per-boot logs in `build/verification`.

**Negative, independently reproducible:** using separate fresh disposable disks, test a missing `OID_MP_EXEC` (must fail before MicroPython, preserve O handle and avoid fallback) and one persistent-code or graph failure, e.g. deliberately corrupted stored `OID_GRAPH` / manifest, or a `run()` raising an exception. Its important invariant: **no `init: done` and no new successful commit/version** following the failure; do not corrupt the positive disk. If that failure cannot be injected without new unsafe/test-only storage hacks, explain the limit and do not claim it was tested. Preserve native O commit atomicity; never write an invalid object to the real test disk.

## 5. Keep regression evidence honest

Run and report **the actual results and commands** for:

```sh
WHAT=all tools/build.sh
# tools/selfroot, as required by repository scripts — record exact invocation
tools/test-oboot-server.sh
tools/test-oboot-output.sh   # D2a diagnostic still intentionally encounters boot.py/BIND
tools/test-oboot-oid.sh
tools/test-oboot-user.sh
tools/test-o-boot.sh
tools/test-o-pathless.sh
tools/test-o-exec.sh
tools/test-o-exec-args.sh
tools/test-o-handles.sh
# Boot A: oboot=probe disposable QEMU gate documented in docs/O-BOOT-EXPERIMENT-A.md
```

Do not quietly modify D2a's test to remove its expected post-output BIND dependency. Existing normal O three-boot control uses `/boot/oinit` and legacy `boot.py`; it should remain PASS separately. Report PASS, FAIL or NOT RUN; a pre-existing earlier PASS is not proof the latest source still passes.

Do not implement input streams, keyboard events, keymap daemon, line discipline, REPL interaction, serial RX, screen memory, a generic I/O registry, file tree, 9P, device path normalization, new OID ontology or desktop mode. Those are later independent experiments.

## 6. Stop condition and deliverables

If the true native runtime needs a broad rewrite of Plan9 libc, scheduler, O persistent graph format, process semantics or filesystem machinery, **stop at D2b NOT YET**, report the *actual* first failing operation, stack/PC/source location and the smallest proposed follow-up. Fix only small verified blockers belonging to this exact `-N` call graph. Avoid speculative architecture sweeping.

Update:
- `docs/O-BOOT-EXPERIMENT-D2B.md`: exact user/kernel call graph, `-N` contract and boot selector, three-boot same-disk evidence (versions, Counter OID, alias, exact output), strong hashes, negative results, syscall and path counters including attempted syscall audit, limitations.
- `docs/STATUS.md`: append factual D2b source/verification status preserving A/B/C/D1/D2a and Storage Level A.
- `docs/to_chatgpt_review.md`: concise outcome and evidence + smallest next user-facing REPL/input experiment, if D2b PASS.
- Minimal C/build/test changes; commit and push intended files via existing OpenCode completion automation without races or unrelated staging.

**Required final verdict:**

```
D2b SERVER BOOT PASS / NOT YET
RUN 1/2/3 = ...
SAME DISK = verified / not verified
PERSISTENCE = versions and unchanged OID/alias, or precise failure
NATIVE ONLY = syscall-attempt & path-counter evidence
LEGACY CONTROLS = PASS/FAIL/NOT RUN
NEXT = smallest justified D2c experiment (do not implement)
```

**PASS requires all 3 boots, real durable commits and unchanged Counter identity across reboots**, not just the first `init: run() -> 1` print.
