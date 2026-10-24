# E9 report

## E9.1–E9.2 implementation

**VERDICT: COMPLETE.** Base `main` `772d195`; implementation commits
`c7d5498` (E9.1), `0cba30d` (E9.2a, `srv`), `eda24c8` (E9.2b, `shr`),
`1c222d5` (evidence/OMAP binding). E9.3 documentation is the commit that
contains this report.

**Edited implementation files:** `sys/src/9/port/auth.c`,
`sys/src/9/port/devcons.c`, `sys/src/9/pc64/pc64onativedisk`,
`tools/kernel_opmap.py` (reviewed binding hashes only). No E7/network,
bootloader, on-disk, syscall or MicroPython persistence change.

**Ownership audit.** `hostownerwrite` had exactly one caller:
`devcons.c` `Qhostowner`. `srvrenameuser` (devsrv.c) and `shrrenameuser`
(devshr.c) had exactly one caller each: `hostownerwrite`. No indirect
function-pointer references existed. `hostdomainwrite`/`userwrite` had
only their `#c` callers and stayed in `auth.c`. E9.1 moved the complete
`hostownerwrite` function unchanged to `devcons.c`; `renameuser` and
`procsetuser` remained in `proc.c`.

**Pruning.** `pc64onativedisk` generated `devtab[]`: 21 -> 20 (`srv`) ->
19 (`shr`). Final: `root swap arch pnp env pipe proc mnt rtc ether ip wg
draw mouse vga uart usb kbd gefs`. `mnt` was deliberately kept and is
**not** part of E9.2. `consdevtab`, `sddevtab`, `sdloopifc`,
`hostownerwrite`, `srvdevtab`, `srvrenameuser`, `shrdevtab` and
`shrrenameuser` are absent from the final linked O-only kernel. Native
SD/O symbols remain.

**Build/link proof.** After E9.1, `9pc64` and `9pc64mp` linked
`hostownerwrite`/`srvrenameuser`/`shrrenameuser` and retained all legacy
`Dev` registrations; `9pc64onativedisk` no longer contained
`hostownerwrite`. After each removal, the generated devc lacked the
matching `&*devtab` and the linked kernel lacked the adapter and rename
symbols. Final linked proof: `srvdevtab`, `shrdevtab`,
`hostownerwrite`, the two rename helpers absent; `mntdevtab`/`mntattach`
and native SD symbols present.

**O boot.** Baseline, E9.1, `srv`, `shr`, and final combined builds each
ran the full fresh `ONATIVE_DISK=1 tools/test-oboot-server.sh` against
the exact binary: PASS. The same disposable O disk booted three times,
`run() -> 1,2,3`, Counter OID/alias 7, native SD init/flush and
`oblocktest` bounds, clean failing-`run()`/missing-OID negatives,
wrong-PARTUUID and malformed-GPT negatives, no panic/fault, and the
established zero path counters. No gate was weakened.

**Legacy/control gates.** `WHAT=kernel tools/build.sh` PASS;
`tools/test-o-boot.sh` PASS (`run() -> 1,2,3`, OID 7);
`OCONSOLE=1 WHAT=kernel tools/build.sh` PASS; `sd_migration_check.py`
source and linked forms PASS; `kernel_opmap.py --check` PASS; 29/29 OMAP
tests PASS. OMAP regenerated after review: only the `pc64onativedisk`
`devsrv`/`devshr` removal, profile counts, `hostownerwrite` function
record move, and source fingerprints changed. The reviewed devcons SHA
was added to the native binding and the historical E3 pinned set, with
old hashes retained.

**Limitations.** No runtime write test for the legacy `hostownerwrite`
operation was added (`NOT RUN`); the claim is source-equivalence plus
build/link proof. Only QEMU VirtIO block I/O was exercised. `mnt`
requires a separate task. Logs: `build/verification/e9/` (ignored);
details: `docs/E9-SERVICE-PRUNING.md`.

## E9.3 production boot and authority design (documentation only)

**VERDICT: COMPLETE (documentation/design only).** This did not implement
production secure boot, GE/O encryption, passkey administration or
rootless kernel authorization.

**Documents:** new `docs/PRODUCTION-BOOT-AND-AUTHORITY.md`; concise
alignment in `docs/GENERAL-SOFTWARE-SPECIFICATION.md` §12.1, `AGENTS.md`,
`README.md`, and a short proposed-link note in `docs/STATUS.md`.
`git diff --name-only` for E9.3 contains only documentation.

**Decisions encoded:** no native universal `root`/`sudo`/`eve` superuser
in the target; inherited `eve`/`hostowner`/`iseve` remains legacy and
unchanged; one logical Administration environment with multiple distinct
authenticated humans; individual identity retained for audit/revocation;
unattended boot with UEFI setup protection separated from boot-time
input; deployment-controlled, authenticated machine-specific kernel
updates with explicit signature/replay policy; remote administration is
narrow (status, named services, schedules, reboot, authorized update),
not a root shell or raw memory/disk interface; no POSIX multiuser/home
requirement; `(SpaceID,OID)` is identity, never permission; desktop model
left `OPEN`.

**Boot-secret and trust distinctions:** firmware/boot authenticity,
kernel-image confidentiality and embedded secrets, GE/O encryption and
key release, and runtime rights are separate. Machine-specific embedded
symmetric keys are recorded only as a deployment proposal with exposure
limits; TPM-sealed/protected GE/O keys and separate build-time signing
keys are discussed as a more defensible option, not implemented or
mandated. Key creation/rotation/recovery/replacement/rollback are `OPEN`.

**Compatibility retained:** USB support and its current registrations,
UEFI boot, and GRUB chainload/recovery workflows must remain; future
authenticated netboot is additive, not a replacement. Current O boot,
volume opener, executable OID, plan9.ini, disk layout and MicroPython
persistence are unchanged. E7 IPv6/network work remains untouched on its
own branch.

**Verification:** `NOT RUN (documentation-only, no executable changes)`.
The separate E9.1–E9.2 build and D2b evidence remains the executable
evidence and is not replaced by this design stage. No Secure Boot,
TPM sealing, GE/O encryption, passkey verification or native admin
service is claimed to exist.
