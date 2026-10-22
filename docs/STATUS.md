# Implementation status — Plan2001-O

**Status date:** 22 October 2026. **Current runtime evidence baseline:**
`main` at `016ccffebfe8c9baa93f09c7e6599315e65e4751` plus this task's
uncommitted working-tree changes (normal O-loaded MicroPython boot below);
the previous clean-tree baselines were `b41a102384efa81b17cdc5f923415b123341f8ca`
and `4678fada0d66f83b310291320e57aba12068934d`.
Original imported source: `pereuna/Plan2001`, branch `poc-o-only`,
commit `436ed30c894c4060638341ecebe82004d457f496`
(20 October 2026); imported without its Git ancestry.

This document is the **single source of truth for current verification**.
The architecture is in [README.md](../README.md), past source-branch
experiments in [POC.md](POC.md), and the implemented on-disk contract in
[O-FORMAT.md](O-FORMAT.md).

## Evidence levels

| Level | Current evidence |
| --- | --- |
| **Implemented** | The imported source contains GE/O O-profile volumes, versioned `(SpaceID, OID)` objects, the native O syscall boundary with process-owned O Space handle tables, a bounded native executable-object path with a snapshot-based, capacity-bounded argv copy, an O-resident Environment and `.mpy` loader, and a persistent MicroPython `init` Space. The normal amd64 `pc64` boot now embeds only `oinit`/`kbdfs` (and the separate `ohandle`/`oexec` harnesses) and loads the real MicroPython executable from O. A `pc64mp` kernel remains explicitly test-only for historical embedded-MicroPython gates. |
| **Demonstrated in the source branch** | Five reported GE/O QEMU regression gates, including three boots of one ESP + O image with counter `1 -> 2 -> 3` and preserved Counter OID/alias. See [POC.md](POC.md). |
| **Statically verified in Plan2001-O** | Documentation references and repository metadata checked at `5413fc6a1e801f377cd3f428336b3543d7ddf83d`; details below. |
| **Runtime verified in Plan2001-O** | **PASS:** the full amd64 build, selfroot, and all nine O-only gates (including both boot gates, REPL persistence, and the focused native-exec argv gate) passed on 22 October 2026 with KVM. This run used HEAD `016ccff` plus the uncommitted normal-O-boot working tree; earlier runs used `b41a102` and `4678fad`. See the records below and `build/verification/*.log`. |
| **Proposed, not implemented** | Native GE/O relationship indexes/edges, per-Python-object O records, general native executable-object loading (catalog, architecture selection, dynamic linking), general persistent namespaces, object IPC and a remote protocol. |

Never promote source inspection or a successful source-branch test into
a **current-repository runtime PASS**. A missing result is **NOT RUN**,
not PASS and not FAIL.

## Normal O-loaded MicroPython boot — 22 October 2026

**Source state:** HEAD `016ccffebfe8c9baa93f09c7e6599315e65e4751`, with
this task's source changes in an **uncommitted working tree**. This record
is not a claim about a clean committed revision. Earlier experiment records
below are unchanged history.

**Normal boot chain:** UEFI -> `9pc64` kernel -> embedded `/boot/oinit`
and `/boot/kbdfs` -> O volume and flat `init` Space -> the bounded native
loader executes `OID_MP_EXEC` (`0x4f45584543000003`) -> MicroPython ->
persistent `init` Space (`run()`/commit) or an interactive REPL. There is
no embedded `/boot/mp` and no pathname-based MicroPython `exec` on this
path.

**Implemented in this change**

- The normal `pc64` bootdir is `kbdfs`, `oinit`, `ohandle` and `oexec`;
  `micropython`/`mp` is absent. The previous `pc64omp` default candidate
  is removed. `pc64mp`/`9pc64mp` remains only as a clearly marked
  **test-only** embedded-MicroPython kernel for the historical Stage 1-4
  and legacy file/DMOBJ/REPL gates.
- `tools/mkovol ... SOURCE` seeds the built selfroot MicroPython byte for
  byte by default at `OID_MP_EXEC`; `NOMPEXEC=1` deliberately omits it for
  the missing-object diagnostic. The `ohello` BSS-header mutation remains
  confined to its fixture. An older image without the interpreter is not
  migrated; `oinit` reports the missing OID and exits without a fallback.
- `tools/mkrepl [OUT]` prepares a fresh ESP + O REPL disk with the normal
  kernel and `init=/boot/oinit -repl -vol PARTUUID=...`. It refuses to
  replace an existing image unless `FORCE=1`, so a persistent user image
  is never silently reformatted or reseeded. `./repl_tui.sh` is the exact
  human-facing command from the repository root.
- Retained bootstrap dependencies are explicit: `oinit` is still reached
  through the inherited internal boot interface, `kbdfs` is still the
  embedded console helper, and `devroot` plus the separate `ohandle`/
  `oexec` regression harnesses remain. MicroPython executable bytes, its
  Environment/code and persistent state come from O. This is not a claim
  that every runtime file interface has been removed.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
for gate in test-o-boot-omp test-o-boot test-o-exec-args test-o-exec \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate-default-o.log"
done
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `f5f989838226c6b8135c0b137a5f813c` (SHA-256 `0254386260027b6f3be197d17a87ab08ea554fc44761f08d370c96190e772d16`), test-only `9pc64mp` md5 `39ef7f6af90766c88095a8da11e999fe` (SHA-256 `f661e97404284355154ff5029a9e77784c63025302f34a36456b663cb1f5914f`), plus loader and userspace binaries. `build/verification/build-default-o.log` |
| selfroot | **PASS** | `build/selfroot` at HEAD `016ccff`; `gefs`, `micropython`, `oinit`, `ohello`, `oexec`, `ohandle` and `kbdfs` present. `build/verification/selfroot-default-o.log` |
| Generated default boot contents | **PASS** | `build/amd64/pc64.rootc.c` has `addbootfile("oinit"`, `addbootfile("kbdfs"`, `ohandle` and `oexec`, and no `addbootfile("mp"`. The test-only `pc64mp.rootc.c` still has `mp`. Asserted by `test-o-boot-omp.sh`. |
| Fresh O image seed | **PASS** | `mkovol` seeded the 2,191,593-byte MicroPython executable by default at `OID_MP_EXEC`, SHA-256 `1487111f358ac845db3ca2b9485a561e722675c59c0632ca105ddd02c13b7e53`, unchanged, matching the built selfroot binary. `build/amd64/ompbootvm/mkovol.log`, `build/amd64/obootvm/mkovol.log` |
| Normal O boot, three boots | **PASS** | One ESP + O disk, no FS root, normal `9pc64`: `run()` 1 -> 2 -> 3, Counter OID/alias 7/7, O object hash equal to the host binary, no root FS mount. `build/verification/test-o-boot-default-o.log`, `build/verification/test-o-boot-omp-default-o.log`, `build/amd64/obootvm/three-boots.log`, `build/amd64/ompbootvm/omp-boots.log` |
| REPL and persistence | **PASS** | The supported `tools/mkrepl` image and `oinit -repl` path reached a prompt, evaluated `OINIT-REPL 42`, committed `kept = 4242`, and after a restart of the same disk restored the graph and printed `REPL-KEPT 4242`. `build/amd64/ompbootvm/repl1.log`, `build/amd64/ompbootvm/repl2.log` |
| Missing/malformed and older image | **PASS** | Missing and malformed OIDs returned errors while preserving the O handle; a fresh image made with `NOMPEXEC=1` printed `MicroPython object 0x4f45584543000003 is missing from O` and did not use an embedded interpreter. `build/amd64/ompbootvm/check.log`, `build/amd64/ompbootvm/legacy.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`; rollback and handle assertions unchanged. `build/verification/test-o-exec-default-o.log` |
| Native argv bounds | **PASS** | `PASS: native O argv bounds, rollback and race`; argv/Tos/BSS, boundary, malformed-copy, rollback and mutation assertions unchanged. `build/verification/test-o-exec-args-default-o.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-default-o.log` |
| GE, O volume, O objects, Python/O | **PASS** | `PASS: GE volume, raw key/value, no FS`; `PASS: O volume, no FS`; `PASS: native O objects, no FS`; `PASS: Stage 4 Environment, code and Space graph from O (no FS)`. These historical harnesses use the test-only `9pc64mp` kernel where they still need `/boot/mp`. `build/verification/test-ge-default-o.log`, `test-o-volume-default-o.log`, `test-o-objects-default-o.log`, `test-o-space-default-o.log` |

Log completion times (UTC): build 20:17:29; selfroot 20:17:34; O-loaded
MicroPython boot 20:19:26; normal O boot 20:20:01; argv 20:20:26; native
exec 20:20:51; handles 20:21:14; GE 20:21:25; O volume 20:22:25; O
objects 20:22:53; Python/O 20:23:25. The documented `test-o-space`
shutdown diagnostic (`panic: boot process died: unknown`) is unchanged
and is not a gate failure. The older image in the missing-object test also
ends when its init process exits; that diagnostic is expected, not a
fallback.

**Remaining limits:** the normal path still uses a fixed experimental OID
and embedded `oinit`/`kbdfs`; there is no program catalog, architecture
selection, permissions framework, dynamic linking or general
executable-object format support. The `pc64mp` kernel is test-only and is
never a normal or fallback boot path. The on-disk format is unchanged.

## Phase C validation record

### Static audit — 21 October 2026

**Checked:** 21 October 2026 against the Phase B commit
`5413fc6a1e801f377cd3f428336b3543d7ddf83d`.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| GitHub source and document availability | **PASS (static)** | `README.md`, `AGENTS.md`, `docs/POC.md`, `docs/STATUS.md` and `docs/O-FORMAT.md` were read from the repository. |
| Documentation navigation | **PASS (static)** | 21 relative Markdown links and 32 backtick-formatted source/tool/document path references in those five Markdown files resolved to entries in the repository tree at the checked commit. This is **not** an exhaustive scan of all inherited source comments. |
| Phase B file metadata | **PASS (static)** | Git trees before/after Phase B were compared; the 22 modified executable tool files retained executable mode, and no tracked file's mode changed. |
| Build dependency review | **PASS (source inspection)** | `WHAT=all tools/build.sh` produces the root binaries used by `tools/selfroot build/selfroot`. `WHAT=kernel` alone does **not** prepare `build/selfroot/amd64/bin/gefs` or `micropython`. |

### Runtime execution — 22 October 2026

**Executed:** 22 October 2026 against
`f23d5624a153bd3645be8f8b540b3bc243ebabec` on a Debian/amd64 host with
accessible `/dev/kvm`, QEMU, OVMF and mtools. The existing prepared
9front `base.qcow2` was reused by `tools/vm-setup`.
Gate start times (UTC, recorded in `build/verification/*.timestamp`):
GE 15:11:44, O volume 15:12:23, O objects 15:13:26, Python/O 15:13:56,
O init 15:14:31.

| Check | Result | Evidence |
| --- | --- | --- |
| Host/tooling and KVM | **PASS** | `tools/vm-setup` found the prepared base image; its package, OVMF and `/dev/kvm` checks passed. The five gates ran with the target's `-accel kvm -cpu host`. `build/verification/vm-setup.log` |
| Full amd64 build | **PASS** | `WHAT=all tools/build.sh` exited 0 and printed `BUILD-DONE`; `build/amd64/9pc64`, `bootx64.efi`, `gefs` and `micropython` were present. `build/verification/build.log`, `build/amd64/session.log` |
| selfroot preparation | **PASS** | `ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot` exited 0. The generated clone's origin is `https://github.com/pereuna/Plan2001-O.git`; its HEAD is `f23d562`, and the expected `amd64/bin/gefs` and `amd64/bin/micropython` are executable. `build/verification/selfroot.log` |
| GE gate | **PASS** | `tools/test-ge.sh` exited 0: `PASS: GE volume, raw key/value, no FS`; raw value crossed reboot (0 → 1 → 2). `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile gate | **PASS** | `tools/test-o-volume.sh` exited 0: `PASS: O volume, no FS`; the O volume persisted 0 → 1 → 2 and wrong-profile opens were rejected. `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects gate | **PASS** | `tools/test-o-objects.sh` exited 0: `PASS: native O objects, no FS`; both OIDs were restored on the second boot. `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O gate | **PASS** | `tools/test-o-space.sh` exited 0: `PASS: Stage 4 Environment, code and Space graph from O (no FS)`; boot 2 restored the graph (41 → 42), same alias/OID, and committed version 2. `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init gate | **PASS** | `tools/test-o-boot.sh` exited 0: `PASS: three O-only boots, persistent Counter and run() from O (no FS)`; one disk, `run()` returned 1, 2, 3, Counter OID stayed 7, no root FS mount. `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log` |

The `test-o-space` serial log also contains
`panic: boot process died: unknown` after each
`space: O: committed init version N` line. The gate's required
assertions and exit status are **PASS**; this shutdown-path diagnostic
is recorded as an observation and was not used to change the gate or
the specification.

## Process-local O handle experiment — 22 October 2026

**Source state:** this experiment is committed as
`30e9ae16c0b7ab82fcc6404cdffddbbb246c8ebd`. The results below were
first run from its working tree before that commit; the same handle
regression was rerun in the final native-exec suite recorded below.

**Design:** each `Proc` owns an opaque eight-entry table of `Ohand`
sessions. An entry holds an `Ospace *` and a `Ref`. Table lookup takes a
temporary reference under the table lock, then releases the lock before
calling storage. Explicit close removes the entry under the lock and
drops the ownership reference; the last reference calls
`onativeclose()`/`ospaceclose()`, which aborts an unfinished transaction
and never commits. Process exit and successful `exec` detach all entries
under the lock, then release sessions outside it. Failed `exec` does not
call the cleanup hook. Children start empty, including `RFMEM` children.
The global volume instance and volume authorization are unchanged.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 114 programs; kernel and loader present. `build/verification/build-ohandles.log` |
| selfroot binaries | **PASS** | `build/selfroot/amd64/bin/{gefs,ohandle}` present and executable. `build/verification/selfroot-ohandles.log` |
| Process-local O handles | **PASS** | one ESP + O boot, no FS root; isolation, independent sessions, explicit-close and exit capacity, abort on close/exit, successful/failed `exec`, and invalid/double close. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC): process-local handles 15:35:46,
GE 15:36:19, O volume 15:36:30, O objects 15:37:31, Python/O 15:37:58,
O init 15:38:29.

## Native executable-object experiment — 22 October 2026

**Source state:** clean tree at
`4678fada0d66f83b310291320e57aba12068934d`. This commit fixes the two
review findings against `ab3a77e`: the exec stack now reserves
`sizeof(Tos)` before placing `argv` and its strings, and segment
addresses (`abss`/`ebss`) remain `uintptr` through both loader paths.
The target now asserts `argv[0]`, intact `Tos` fields and a high BSS
page; host seeding enlarges the target's BSS header to `0xffffffff` so
the BSS extent crosses 4 GiB. This STATUS update is a docs-only follow-up
commit.

**Loader:** `OEXECUTE`/`oexecute(space, oid)` resolves the handle only in
the calling process, retains its session reference for one bounded
whole-object read (`Objexecmax` = 8 MiB, a single published version),
then releases the reference before parsing. `execparse` is shared with
`sys_exec` and validates the amd64 a.out magic, header length,
text/data/bss arithmetic and bounds, object length, entry point and
user-address limits. `execo` builds ordinary text/data/BSS segments from
the object bytes, then uses the shared `execcommit` process-transition
path (segments, stack, close-on-exec handles, text/args, notes, MMU
flush). Failure before commit leaves the old image and handles intact;
there is no pathname, `Chan`, `Fid`, Qid, mount or 9P step.

The target program `ohello` exists only as an O object. `/boot/oexec`
is an embedded regression harness (test bootstrap, not the loader).
`tools/mkovol` seeds the target at `OID_EXEC_TEST` and malformed bytes
at `OID_BADEXEC_TEST` through the existing `-i` seed layout.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
NATIVEEXEC=build/selfroot/amd64/bin/ohello \
  tools/mkovol build/amd64/oexec-o.img 192 tools/odemo.py
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build | **PASS** | `BUILD-DONE`; 116 programs; kernel and loader present. `build/verification/build-bssboundary.log` |
| selfroot binaries | **PASS** | `gefs`, `ohello`, `oexec` built; selfroot at `4678fad`. `build/verification/selfroot-bssboundary.log` |
| Native executable object | **PASS** | one ESP + O boot, no FS root; child loaded `ohello` by OID, checked `argv[0]`, intact `Tos` fields and a BSS page beyond 4 GiB, printed both target markers, exited 0, parent observed success; missing OID and a truncated valid header failed while the handle remained usable; close-on-exec handle rule held. `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| Process-local O handles | **PASS** | all isolation, lifetime, abort, exec and error checks. `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and O init all exited 0. `build/verification/test-ge.log`, `test-o-volume.log`, `test-o-objects.log`, `test-o-space.log`, `test-o-boot.log` |

Gate start times (UTC, clean tree at `4678fad`): native executable
16:50:09, process-local handles 16:50:33, GE 16:50:56, O volume
16:51:07, O objects 16:52:07, Python/O 16:52:35, O init 16:53:05. The
binary-grep false positive in `test-o-boot.sh` remains fixed; no
assertion was weakened.

## Native O MicroPython experiment — 22 October 2026

**Source state:** HEAD `122e585a172f39bdc1fb31eca79841acfe2e6d27`, with
this experiment's source changes in an **uncommitted working tree**. The
binaries and images below were built from that tree; this record is not
a claim about a clean committed revision. The previous native-executable
results above are unchanged history.

**Implemented:** `oexecute(space, oid, argv, argc)` passes a bounded,
validated argument vector, copies the strings to kernel-owned memory
before the process image is replaced, and places `Tos`, strings and argv
on the exec stack without overlap. The native loader marks its
image-less text/data/BSS/stack segments `SG_NOSWAP`, and `dupseg()`
accepts a data segment with no file image, so `rfork` and the page
reclaimer do not treat the O-loaded bytes as file-backed pages. The
small embedded `/boot/oinit` harness opens the O volume and `init` Space
and executes `OID_MP_EXEC` (`0x4f45584543000003`), passing the argv that
`sys/src/cmd/micropython/main.c` requires. The dedicated `pc64omp`
kernel configuration embeds only `oinit` and `kbdfs`; the ordinary
`pc64` configuration still embeds `/boot/mp`.

The seed builder in `sys/src/cmd/gefs/ream.c` now builds a normal
multi-level GE tree from the sorted seed records, so a large executable
is not limited to one catalog leaf. `tools/mkovol MPEXEC=FILE` seeds the
real MicroPython executable **byte for byte**; `tools/oseed.py` reads
the prepared copy back, and `/boot/oinit` prints the SHA-256 of the
object read from O. The BSS-header patch remains confined to the
`NATIVEEXEC`/`ohello` fixture.

**Object and limits:** MicroPython 2,191,593 bytes, SHA-256
`1487111f358ac845db3ca2b9485a561e722675c59c0632ca105ddd02c13b7e53`;
`oinit` 76,349 bytes, SHA-256
`70b4d0050606507fa46e3f215e6f017e2f36e096083a25154c5656d677fa3f18`.
`Objexecmax` remains 8 MiB. The test O image is 192 MiB; no disk-format
revision was added.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-boot-omp.sh
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build, both kernels | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `8df642b1daaccaa2c539005a4aaa30e0`, `build/amd64/9pc64omp` md5 `aa1a3ae158a6809bcf7254c1edbe366c`. `build/verification/build-omp.log` |
| selfroot | **PASS** | `build/selfroot` at HEAD `122e585`; `oinit`, `gefs` and `micropython` present. `build/verification/selfroot-omp.log` |
| Generated boot contents | **PASS** | `build/amd64/pc64omp.rootc.c` has no `addbootfile("mp"` and has `oinit`/`kbdfs`; `build/amd64/pc64.rootc.c` still has `mp`. Asserted by the new gate. |
| MicroPython from native O | **PASS** | one ESP + O disk, no FS root, dedicated `9pc64omp`; three boots of the same disk: `run()` 1 -> 2 -> 3, Counter OID/alias 7/7, object SHA-256 equals the host binary; REPL evaluated `OINIT-REPL 42`; missing/malformed objects returned errors with the O handle preserved. `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl.log`, `build/amd64/ompbootvm/check.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`; argv/Tos/BSS and rollback assertions. `build/verification/test-o-exec-omp.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-omp.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and embedded O init all exited 0. `build/verification/test-ge-omp.log`, `test-o-volume-omp.log`, `test-o-objects-omp.log`, `test-o-space-omp.log`, `test-o-boot-embedded.log` |

Log timestamps (UTC, completion of each log write): build and selfroot
19:10:25; O-loaded MicroPython 19:11:15; native executable 19:11:43;
handles 19:12:05; GE 19:12:16; O volume 19:13:16; O objects 19:13:44;
Python/O 19:14:15; embedded O init 19:14:49. The documented
`test-o-space` shutdown diagnostic (`panic: boot process died: unknown`)
is unchanged and is not a gate failure.

**Remaining limits:** the O-loaded path is demonstrated only by the
dedicated `pc64omp` test configuration and documented OID. The ordinary
`pc64` boot still embeds MicroPython through `devroot`; `kbdfs` and the
small `oinit` harness are still embedded. There is no program catalog,
architecture selection, dynamic linking, permissions framework, or
general executable-object format support. The on-disk format is
unchanged.

## Native O exec argv copy fix — 22 October 2026

**Source state:** HEAD `b41a102384efa81b17cdc5f923415b123341f8ca`, with
the fix in an **uncommitted working tree**:
`sys/src/9/port/sysproc.c`, `sys/src/cmd/oexec/oexec.c`,
`sys/src/cmd/ohello/ohello.c`, `docs/O-FORMAT.md`, this file and the new
`tools/test-o-exec-args.sh`. This record is not a claim about a clean
committed revision.

**Source-review conclusion (not runtime evidence):** the previous
`execo()` measured each user string with `vmemchr()`, allocated from that
total, then reread `uargv[i]` and used unbounded `strlen()` before
`memmove()`. An RFMEM peer could change a pointer, terminator or string
between passes, so the later copy was not bounded by the earlier check.
The fix:

- snapshots the bounded pointer array once into kernel storage after an
  `okaddr()` range check; later code never rereads the live array;
- copies each string with `execargcopy()` into kernel memory, checking
  each page with `okaddr()` and never writing past the remaining
  destination capacity;
- accepts a length and terminating NUL only from the copied bytes, then
  uses bounded scans on that private snapshot;
- enforces `Oargmax = 32` and `Oargbytes = 16 KiB` including every NUL,
  plus the existing `Tos`, argv-pointer, alignment and 16 MiB stack
  checks; and
- reports bad pointers as ordinary `-1` syscall errors via `okaddr()`
  rather than the note-posting `validaddr()`, so the caller can verify
  its O handle after a failed call.

Concurrent modification is explicitly not an atomic all-argument
snapshot: a bounded copied result or a clean error is accepted. Failure
before process transition still releases the object buffer, argument
allocations, session reference and any partially constructed segments.

**Commands**

```bash
WHAT=all tools/build.sh
ORIGIN=https://github.com/pereuna/Plan2001-O.git tools/selfroot build/selfroot
tools/test-o-exec-args.sh
tools/test-o-boot-omp.sh
tools/test-o-exec.sh
tools/test-o-handles.sh
tools/test-ge.sh
tools/test-o-volume.sh
tools/test-o-objects.sh
tools/test-o-space.sh
tools/test-o-boot.sh
```

| Check | Result | Evidence |
| --- | --- | --- |
| Full amd64 build, both kernels | **PASS** | `BUILD-DONE`; `build/amd64/9pc64` md5 `d028692a55eda1a6ae60215b51c7ffda`, `build/amd64/9pc64omp` md5 `24a8c66c27ac40f02b683326c8a77253`. `build/verification/build-args.log` |
| selfroot | **PASS** | HEAD `b41a102`; `oexec` SHA-256 `68d4fe842c254ec8125c3de361a6b97032fc5d0447c8dd2115af72fe7755b6f0`, `ohello` SHA-256 `2d1b022e29aafe95333cf6452601262c50a0777b6ec70e4b39800f46d8f16afd`. `build/verification/selfroot-args.log` |
| Focused native-exec argv gate | **PASS** | synthetic `argc == 0`, 5 valid arguments including an empty one, 32 arguments, the exact 16 KiB aggregate boundary accepted, one byte over rejected, missing NUL, negative and excessive argc, nil and misaligned argv, invalid string pointer, cross-page string, repeated failures with usable handles, and 32 shared-memory mutation attempts. `build/verification/test-o-exec-argv.log`, `build/amd64/oexecargsvm/serial.clean.log` |
| O-loaded MicroPython | **PASS** | `PASS: MicroPython loaded from a native O object (no embedded mp)`; three boots and the REPL smoke test. `build/verification/test-o-boot-omp-args.log` |
| Native executable object | **PASS** | `PASS: native executable object from O, exec and rollback`. `build/verification/test-o-exec-existing.log` |
| Process-local O handles | **PASS** | `PASS: process-local O handles, isolation/lifetime/cleanup`. `build/verification/test-o-handles-args.log` |
| Existing five O-only gates | **PASS** | GE, O volume, O objects, Python/O and embedded O init all exited 0. `build/verification/test-ge-args.log`, `test-o-volume-args.log`, `test-o-objects-args.log`, `test-o-space-args.log`, `test-o-boot-args.log` |

Log timestamps (UTC, completion of each log write): build 19:42:10;
selfroot 19:42:11; focused argv 19:42:34; embedded O init 19:43:32;
native executable 19:43:56; handles 19:44:19; GE 19:44:29; O volume
19:45:29; O objects 19:45:56; Python/O 19:46:27; O init 19:47:02. The documented
`test-o-space` shutdown diagnostic (`panic: boot process died: unknown`)
is unchanged and is not a gate failure. No focused-gate failure or kernel
panic occurred in the recorded run.

## Reproduction on a prepared Debian/amd64 host

Run from the repository root with a **committed, clean source tree**.
Verify `git status --short` and record `git rev-parse HEAD` first:
`tools/overlay` can include working-tree files, whereas
`tools/selfroot` clones **committed HEAD**, so testing uncommitted
sources risks mixing incompatible binaries and code.

`tools/vm-setup` checks Debian packages, OVMF, the selected VM
accelerator and a pinned 9front bootstrap image. The **O-only QEMU suite
(nine gates) currently expects KVM**: `tools/targets/amd64` supplies
`-accel kvm -cpu host` directly to those guest invocations.
`VM_ACCEL=tcg` is supported by the bootstrap `tools/vm` path, but it
does **not** automatically switch these standalone gate scripts to TCG.
Use a host with accessible `/dev/kvm` for the commands below.

```bash
set -euo pipefail
mkdir -p build/verification
git rev-parse HEAD | tee build/verification/commit.txt
git status --short

tools/vm-setup 2>&1 | tee build/verification/vm-setup.log
WHAT=all tools/build.sh 2>&1 | tee build/verification/build.log

# Work around tools/selfroot's inherited Plan2001 origin default
# until that separate functional cleanup is made.
ORIGIN=https://github.com/pereuna/Plan2001-O.git \
  tools/selfroot build/selfroot 2>&1 | tee build/verification/selfroot.log

test -s build/amd64/9pc64
test -s build/amd64/9pc64mp        # test-only historical harness kernel
test -s build/amd64/bootx64.efi
test -x build/selfroot/amd64/bin/gefs
test -x build/selfroot/amd64/bin/micropython
test -x build/selfroot/amd64/bin/ohandle
test -x build/selfroot/amd64/bin/oexec
test -x build/selfroot/amd64/bin/ohello
test -x build/selfroot/amd64/bin/oinit

for gate in test-o-boot-omp test-o-boot test-o-exec-args test-o-exec \
            test-o-handles test-ge test-o-volume test-o-objects test-o-space; do
    "tools/$gate.sh" 2>&1 | tee "build/verification/$gate.log"
done
```

The normal human REPL uses a fresh disposable image; an existing
`build/amd64/repl.img` is kept, not reseeded:

```bash
tools/mkrepl                     # refuses to replace an existing image
./repl_tui.sh                    # UEFI -> 9pc64 -> oinit -> O MicroPython
```

**Safety:** these scripts create, overwrite or reformat disposable
images under `build/`. Run them in a dedicated development checkout;
**never substitute a real disk or partition**. Do not use
`tools/selfroot -p DEV`, `dd` to block devices or `tools/mkovol`
on a real device as a regression shortcut. Build scripts may require
significant free space for the VM and disk images.

`set -euo pipefail` makes a failed build, precondition or QEMU gate
stop the sequence; `tee` saves the output and does not conceal a
nonzero exit status. **A test's name or log-file existence is not
evidence of PASS.**

## Runtime gate acceptance and logs

| Gate | Required check | Main outputs |
| --- | --- | --- |
| Build | Exit 0, `BUILD-DONE` in the build session, normal `9pc64` and test-only `9pc64mp` kernels + UEFI loader + `gefs` + MicroPython + `ohandle` + `oexec`/`ohello`/`oinit` binaries present | `build/verification/build.log`, `build/amd64/session.log`, `build/vm/serial.log` |
| GE | `tools/test-ge.sh` exits 0 and reports `PASS: GE volume, raw key/value, no FS`; same raw value survives reboot. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-ge.log`, `build/amd64/getestvm/serial.log` |
| O profile | `tools/test-o-volume.sh` exits 0 with `PASS: O volume, no FS`; wrong-profile open attempts are rejected. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-volume.log`, `build/amd64/ovolvm/serial.log` |
| O objects | `tools/test-o-objects.sh` exits 0 with `PASS: native O objects, no FS`; two OIDs survive reboot. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-objects.log`, `build/amd64/oobjvm/serial.log` |
| Python/O | `tools/test-o-space.sh` exits 0 with its Environment/code/Space graph PASS; same alias/OID and O code survive two boots. Historical `/boot/mp` harness runs on test-only `9pc64mp`. | `build/verification/test-o-space.log`, `build/amd64/ospvm/serial.log` |
| O init | `tools/test-o-boot.sh` exits 0 with `PASS: three O-only boots`; normal `9pc64` + `oinit`, one disk, `run()` yields 1, 2, 3, same Counter OID, no root filesystem mount, O object hash equals the host binary | `build/verification/test-o-boot.log`, `build/amd64/obootvm/three-boots.log`, `boot1.log`–`boot3.log` |
| O handles | `tools/test-o-handles.sh` exits 0 with both its per-check markers and `PASS: process-local O handles`; isolation, independent sessions, close/exit capacity, abort, exec rules and invalid handles pass | `build/verification/test-o-handles.log`, `build/amd64/ohandvm/serial.clean.log` |
| O execute | `tools/test-o-exec.sh` exits 0 with `PASS: native executable object from O, exec and rollback`; the O-only target marker appears once, the child exits successfully, missing/malformed loads preserve the caller's handle, and native exec closes handles | `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| O argv | `tools/test-o-exec-args.sh` exits 0 with `PASS: native O argv bounds, rollback and race`; valid/empty/32-argument argv, the exact aggregate boundary, over-limit and malformed copies, bad counts/pointers, repeated rollback with usable handles, and shared-memory mutation attempts pass, with the synthetic argv/Tos/BSS markers appearing exactly once | `build/verification/test-o-exec-argv.log`, `build/amd64/oexecargsvm/serial.clean.log` |
| O MicroPython | `tools/test-o-boot-omp.sh` exits 0 with `PASS: MicroPython loaded from a native O object (no embedded mp)`; the generated normal `pc64` boot contents contain `oinit`/`kbdfs` and no `mp`; three boots of one disk yield `run()` 1, 2, 3 with the same Counter OID/alias; `tools/mkrepl` + the REPL evaluate an expression and keep a value across a restart; missing/malformed objects and an older image without the interpreter return clear diagnostics and preserve the handle where the object exists | `build/verification/test-o-boot-from-o.log`, `build/amd64/ompbootvm/omp-boots.log`, `build/amd64/ompbootvm/repl1.log`, `repl2.log`, `check.log`, `legacy.log` |

Individual QEMU serial logs may be **overwritten between boots** by
their scripts. The captured `build/verification/*.log` output and
`test-o-boot.sh`'s three-boot transcript are the primary evidence.
Preserve relevant failure logs or copies before rerunning a gate.

For each execution record **UTC timestamp, commit SHA, host/VM setup,
exact command, exit status, PASS/FAIL/NOT RUN and log path**. If a gate
fails, record its first relevant diagnostic and leave its status FAIL;
do not edit the test to manufacture a PASS. Do not add historical
source-branch logs as evidence of execution at a newer commit.

## Kernel driver operation map — static inventory

**What this is:** a checked-in, deterministic source analysis of the kernel
driver surface, not a runtime change or a claim about device behaviour.
Artifacts:

- [KERNEL-OPMAP.md](KERNEL-OPMAP.md) — generated coverage report, operation
  tables, representative chains and unresolved-work list.
- [KERNEL-OPMAP.json](KERNEL-OPMAP.json) — the machine-readable operation map.
- [KERNEL-OPMAP-NOTES.md](KERNEL-OPMAP-NOTES.md) — separate source-checked
  manual annotations (not generated).

**Source state:** kernel tree `sys/src/9` at commit
`c1c4bc9bd26b5d00d5e4896ac9ba28b479ea9fdf`, clean at generation; source
fingerprint `bacd6bc3245bb33ff47472f1ee80f6816625e8e2d10305bdff63a12197a0a071`.
The generator is `tools/kernel_opmap.py` v1.

**Commands run**

```bash
python3 tools/kernel_opmap.py --write
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py
```

**Results**

| Check | Result | Evidence |
| --- | --- | --- |
| Regeneration | **PASS** | `--write` wrote both artifacts; deterministic output is sorted and contains no timestamps or machine-specific absolute paths. |
| Staleness check | **PASS** | `--check` reported `kernel operation map: up to date`. |
| Analyzer tests | **PASS** | 10 tests: comments/strings, multiline Qid/Cmdtab branches, if-based Qid branches, indirect callbacks, duplicate symbols, conditional compilation, deliberate parse failure, manual commands, determinism/no allowlist, and per-file accounting. |
| Coverage | **PASS (static)** | 226 files scanned (167 C, 37 headers, 7 assembly, 4 configs, 11 build helpers); 167 C files parsed; 69 registrations; 976 exposed operations; 613 shared chains; 59 native entry points. |
| Build split | **PASS (static)** | Normal amd64 `pc64`: 148 active C files, no unresolved objects; `pc64mp` test-only has the same object selection; `arm64/qemu` (planned) has 93 active C files and explicit unresolved `devbridge`/`devpci`; `riscv64` source tree is absent. |
| Representative chains | **PASS (source-checked)** | GE/O `OVOLOPEN` still reaches `Chan`/`Dev` through `gevolume` before `oopen`/`geopen`; devsd Qpart reaches `SDifc.bio` with NVMe/AHCI/virtio/loop/RAM candidates; kbd reaches `inb`; console reaches the `PhysUart.putc` interface; ethernet reaches the queue-kick `Ether.transmit`; `sdgen` exercises dynamic Qid dispatch. See the generated chain tables and NOTES. |
| Unresolved visibility | **PASS (static)** | The JSON/report keep partial and unresolved edges explicit: 45 hardware-primitive chains, 82 controller-primitive chains, 868 partial operations and 63 unresolved operations. Duplicate non-static symbols across architecture trees remain ambiguous rather than guessed. |

**Logs:** `build/verification/kernel-opmap-write.log`,
`build/verification/kernel-opmap-check.log` and
`build/verification/kernel-opmap-tests.log` (ignored build evidence).

**Scope boundary:** `kbdfs` is embedded as a `bootdir` binary but remains a
user-space 9P service; only its kernel endpoints (`devcons`, `devkbd`,
`devuart`, `screenputs`, `PhysUart` callbacks) are in this inventory.

No kernel source, syscall table, driver, libc or boot behaviour was changed.

## Known limits and follow-up work

- GE/O has no native graph edge, tag or indexed namespace relation API.
- Python logical object OIDs live inside a whole `OID_GRAPH` payload;
  native per-Python-object storage and incremental updates are absent.
- The normal `pc64` configuration embeds no MicroPython: `oinit` loads
  the real interpreter from a native O object by the fixed `OID_MP_EXEC`.
  The bounded loader still has no program catalog, architecture selection,
  permissions, dynamic linking or general object-loading contract.
  Inherited `devroot`, `oinit`, `kbdfs` and the separate `ohandle`/`oexec`
  regression harnesses remain. The `pc64mp`/`9pc64mp` kernel is test-only
  for historical embedded-MicroPython gates and is never a normal or
  fallback boot path.
- Native O Space handles are now process-local, but handle inheritance
  and cross-process transfer are not implemented; each process has at
  most eight handles. The volume instance remains global, there is no
  per-volume/per-Space authorization, and this is not a complete
  capability model.
- The process-local handle table is independent of `Fgrp`, `Chan`,
  namespaces and 9P, by design for this experiment.
- Crash/corruption recovery, incomplete transactions, concurrency,
  performance and physical hardware behavior lack production validation.
- Inherited 9front/Monolith code and legacy FS/9P tests are separate from
  the nine O-only gates. Preserve them as needed for bootstrap but do not
  treat them as native GE/O architecture.
- `tools/selfroot` still defaults its remote origin to
  `pereuna/Plan2001.git`, and the legacy `tools/test-selfroot.sh`
  still clones that repository. The 22 October run used the documented
  `ORIGIN=https://github.com/pereuna/Plan2001-O.git` override; the
  default and that legacy test still require a **separate functional
  tools fix**, which this validation intentionally does not make.
