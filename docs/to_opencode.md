# E9 — OpenCode: legacy Dev pruning (E9.1–E9.2), then production profile specification (E9.3)

**ACTIVE implementation assignment on `main`.** E8 is COMPLETE on `main`; its final `pc64onativedisk` generated `devtab[]` has 21 registrations. E7 Ethernet/IPv6 development is running independently on `design/e72-native-ipv6-20261024` (derived from `design/ipv6-only-native-20261024`). **Do not modify or merge E7.** E9 does not implement native networking, 9P, or a new kernel API. The only objective is to remove two now-unnecessary *legacy Dev registrations* from the opt-in O-only kernel, after establishing and testing that their shared host-owner rename dependency is legacy-only.

**Task boundary:** E9.1: audit and move `hostownerwrite()` out of always-linked `auth.c` into its actual legacy `#c` owner, if source/link analysis confirms this is safe. E9.2: remove `srv` and `shr` individually **only** from `sys/src/9/pc64/pc64onativedisk`, with linked-symbol and complete O boot verification after each removal. `mnt` is **out of scope** and MUST remain. The target 21 -> 19 is a hypothesis, not permission to force a build.

## Worktree and branch safety

1. Start from the current `origin/main`. Confirm `git branch --show-current` = `main`, `git rev-parse HEAD`, `git status --short`, upstream/remote, and baseline against `docs/STATUS.md` and `docs/DEV-PRUNING.md`. At assignment time the latest observed main HEAD was `aad64f7a3c38f44c12eb5f69c451e1566a43d309` (E8 report); verify actual HEAD rather than assuming that SHA. Use the dedicated main worktree/clone; do not disrupt another agent's worktree.
2. E7 branches must remain unmodified: no checkout, cherry-pick, merge, rebase, reset, shared uncommitted working-directory edits, or push targeting either E7 branch. Do not touch `ethercore.c`, `devether.c`, `devip.c`, `devwg.c`, `sys/src/9/ip/*`, network configs, network build/probe scripts, `pc64/main.c`, or E7 reports. Do not regenerate E7-only files.
3. No force-push, `git clean`, hard reset or overwriting unrelated work. If `main` advances, inspect/reconcile before editing. E7 also edits `docs/to_opencode.md` on its branch: this is a known **future integration conflict**. Do not resolve it by merging E7 now or by deleting E7's task/history.
4. The existing automated OpenCode commit/report/push workflow may be used, but make sure it targets **main only**. Avoid duplicate commits/pushes if a hook already does them. Keep one bounded implementation stage per commit and a separate documented final report.

## Read and inspect first

- `AGENTS.md`, `docs/KERNEL-API-ABI.md`, `docs/STATUS.md`, `docs/DEV-PRUNING.md`, `docs/CONS-MIGRATION.md`, `docs/SD-MIGRATION.md`.
- `sys/src/9/port/auth.c`, `devcons.c`, `devsrv.c`, `devshr.c`, `devmnt.c`, `portfns.h`, `sysinfo.c`, and the relevant source lists/mkfiles.
- `sys/src/9/pc64/pc64onativedisk`, `pc64`, `pc64mp` configuration/generator and `sys/src/9/port/mkdevlist`.
- `tools/build.sh`, `tools/test-oboot-server.sh`, `tools/test-o-boot.sh`, `tools/sd_migration_check.py`, `tools/kernel_opmap.py` and its regression tests.

E8 specifically found that `auth.c:hostownerwrite` unconditionally calls `srvrenameuser` and `shrrenameuser`, making both `devsrv.c` and `devshr.c` link dependencies even though `#c` is already absent from `pc64onativedisk`. `devcons.c` uses `hostownerwrite` for `Qhostowner`. **This is a candidate architectural boundary, NOT proof that there are no other callers.** Validate all current definitions, references, function-pointer/indirect uses and linked object ownership before modifying anything.

## E9.0 — capture source and executable baseline

Record the actual baseline `pc64onativedisk` `dev` entries and generated `devtab[]`; expected 21 with `srv` and `shr` present and `cons`, `sd`, six E8 removals absent. Build and execute the existing O-only D2b gate using **disposable** QEMU images. Record command, exact commit SHA, generated devtab source, linked symbol evidence, exit statuses and log paths under `build/verification/e9/baseline/`. Do not claim success from E8's historical logs.

Perform a repo-wide concrete reference audit (including declaration versus definition, direct and indirect call sites) for:
- `hostownerwrite`, `srvrenameuser`, `shrrenameuser`;
- `hostdomainwrite`, `userwrite` and adjacent host-owner/security code, only to ensure E9 does not accidentally alter them;
- `devsrv.c` and `devshr.c` exported global symbols, reset/init/shutdown callbacks, and any link-time or actually reached O D2b clients.

Distinguish the always-linked kernel source owner from runtime reachability and from the `Dev` namespace adapter. Document all blockers found. A symbol not exercised in the D2b observation window is not automatically safe to delete; a legacy symbol in a linked source is not proof that it executes at runtime.

## E9.1 — move the legacy `hostownerwrite` implementation; preserve semantics

If **and only if** the caller/ownership audit supports it, relocate the *complete existing implementation* of `hostownerwrite(char*, int)` from `sys/src/9/port/auth.c` to `sys/src/9/port/devcons.c` as a legacy `Qhostowner` operation helper. Preserve its exact behavior and sequence:

```c
if(!iseve()) error(Eperm);
if(n <= 0) error(Ebadarg);
if(n >= KNAMELEN) error(Etoolong);
/* bounded copy plus terminating NUL */
renameuser(eve, buf);
srvrenameuser(eve, buf);
shrrenameuser(eve, buf);
kstrdup(&eve, buf);
procsetuser(buf);
return n;
```

Do not replace `srvrenameuser` or `shrrenameuser` with no-ops, conditional fake hooks or new interface layers; do not change authorization, validation order, namespace owner updates, ownership or error semantics in default/legacy kernels. Keep the public prototype usable for the legacy build (adjust declarations only if strictly needed). Do **not** refactor `renameuser`, `auth.c`'s other syscalls, `hostdomainwrite`, `userwrite`, userspace identity semantics, or O authorization.

Once moved, verify:
- `9pc64` and `9pc64mp` compile and link with exactly one `hostownerwrite` definition, still callable from `Qhostowner`; `srvrenameuser` and `shrrenameuser` remain correctly available there.
- `ONATIVE_DISK=1` compiles and links, and no longer pulls `hostownerwrite` into its executable merely due to `auth.c`. Check with the actual symbol table, not only with a grep of the source.
- The full D2b test still passes **before** removing `srv`/`shr`.
- Audit whether an existing suitable legacy test exercises authorized and unauthorized host-owner writes without affecting a real host. If feasible, extend an isolated disposable-kernel regression test for permission, size, owner/namespace propagation and return value. If not feasible, record runtime coverage as **NOT RUN** and rely only on the actual source-equivalence plus build/link proof; do not call it runtime-tested.

If another legitimate non-`#c` consumer needs `hostownerwrite`, stop the relocation and report **E9.1 BLOCKED** with exact call sites. Do not paper over the dependency with stubs or speculative redesign.

## E9.2 — prune `srv`, then `shr`, as separate verified changes

With E9.1 proven and committed (or held if blocked), modify **only** the `dev` section of `sys/src/9/pc64/pc64onativedisk`:

1. Remove `srv` alone; rebuild `ONATIVE_DISK=1`; inspect generated `pc64onativedisk.devc.c` (`&srvdevtab` absent) **and** linked `9pc64onativedisk` (`srvdevtab` and unneeded `devsrv` symbols absent). Run the full three-boot `ONATIVE_DISK=1 tools/test-oboot-server.sh`, including its negative gates. Retain the removal only on PASS. If it fails, restore only the candidate line and document the linker/runtime blocker.
2. Repeat separately for `shr`, from the latest known-good profile, with generated `&shrdevtab` absence, linked symbol absence and a **fresh** complete D2b run. If `srv` was blocked, still investigate `shr` independently, but do not force either removal.
3. Finally rebuild and re-run D2b on the **combined** config; do not infer combined success from individual passes. Expected count after both accepted removals: 19. Confirm `mnt`, `root`, `swap`, `arch`, `pnp`, `env`, `pipe`, `proc`, `rtc`, `ether`, `ip`, `wg`, `draw`, `mouse`, `vga`, `uart`, `usb`, `kbd`, `gefs` are preserved exactly as before E9. Keep `consdevtab`, `sddevtab`, `sdloopifc` absent.

The 21 -> 19 count is only a **success criterion if both independently pass**; partial completion is acceptable. No removal of `mnt`: its `mntattach`/`mntversion`/`mntauth`/`mntrah*`/`muxclose` dependencies were separately established by E8 and require a different task. Do not extract 9P core or weaken linker/test gates to make the counter smaller.

## Required verification

Execute at least these gates as relevant to each phase; capture per-gate PASS/FAIL/NOT RUN, exact command and log location:

```sh
ONATIVE_DISK=1 WHAT=kernel tools/build.sh
ONATIVE_DISK=1 tools/test-oboot-server.sh
WHAT=kernel tools/build.sh
tools/test-o-boot.sh
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/sd_migration_check.py
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py
```

Also check `python3 tools/sd_migration_check.py --profile pc64onativedisk --devtab <fresh-generated-devc.c> --kernel <fresh-linked-kernel>` with **real resolved paths** from the build; do not copy an E8 artifact path. If any test's artifacts are overwritten by subsequent profiles, save and inspect the relevant fresh binaries beforehand.

Maintain D2b evidence: the **same disposable O image** boots three times with `run() -> 1,2,3`, stable Counter OID/alias, expected commit versions, native SD initialization and flush, `oblocktest` bounds, clean missing-executable/failing-`run()` negatives, wrong-PARTUUID and malformed-GPT negatives, no panic/fault, and unchanged zero `namec/newchan/walk/devwalk/mount/exec` counters in the established measured windows. Do not widen the claim to whole-kernel `Chan` independence or reinterpret the measured window.

After reviewed source/config changes, regenerate `docs/KERNEL-OPMAP.*` **only if** current OMAP fingerprints/check require updating and inspect the entire generated diff: it must correspond to E9's source/config changes, not import E7. Re-run `--check` and `tools/test_kernel_opmap.py`. Preserve normal `pc64`/`pc64mp` legacy registration and behavior.

## Report and finish

Record each gate and accepted/blocked candidate in `docs/E9-SERVICE-PRUNING.md`; update `docs/STATUS.md` in a bounded E9 section. Write the human+AI-readable final summary in **`docs/to_chatgpt_review.md`** on main, covering: baseline/final SHA; exact edited files; before/after registrations; verified `hostownerwrite` callers and source ownership; legacy behavioral evidence; generated and linked symbol checks; E9.1/E9.2 per-step decisions; D2b/legacy test matrix; negative tests; log locations; limitations and follow-up (the `mnt` dependency is NOT E9.2).

Commit the E9.1 source-ownership change independently from E9.2's each accepted registration removal where possible; push using the already configured main-only workflow and report resulting SHAs. Do not duplicate automation commits. No changes to E7 files/branches, networking, GE/O OID/Space/on-disk layout, MicroPython persistence, public syscalls, generic device abstractions or physical disks.

**Final verdict rules:** `COMPLETE` only if E9.1 is safe and both Dev removals build/link/boot on the final combined image; otherwise report `PARTIAL` or `BLOCKED` with exact evidence and a clean stable main. Never mask failed verification.



---

# E9.3 — production server/embedded boot, administration and authority model (DOCUMENTATION ONLY)

**SEQUENTIAL FOLLOW-UP within E9, on \`main\`.** First complete/report E9.1–E9.2 as specified above, or record their exact BLOCKED/PARTIAL state. E9.3 is a bounded architecture decision and source-backed migration plan, **not** permission to implement a new bootloader, security mechanism, authentication service, storage encryption, authorization ABI or networking stack now. The E9.1–E9.2 instruction to preserve all legacy semantics remains in force. E7 keeps its independent IPv6 development branch. Do not touch E7 network code, branch or tests.

## Decisions to encode (server and embedded production profile)

1. **No native universal superuser.** The target Plan2001-O production profile has no all-powerful \`root\`, \`sudo\` or Plan 9 \`eve\` principal. The inherited \`eve\`/\`hostowner\`/\`iseve\` behavior is **LEGACY, currently present** and must be preserved until a separate, tested authorization migration replaces it. Do not quietly change the behavior of \`pc64\`, \`pc64mp\`, \`#c\`, \`auth.c\` or existing O calls.
2. **One Administration environment, multiple authenticated operators.** For a server/embedded deployment, specify a *single logical administration environment/service*, accessible to multiple distinct human operators (e.g. Web + passkeys). The human identities exist at the management/service layer; they are not necessarily POSIX accounts, \`/home/*\` trees, kernel UIDs or one universal admin identity. A named \`Administration\` service is NOT a special kernel user with unrestricted memory/disk access. Even if the first deployment gives all authenticated operators the same management privileges, keep individual identity for audit, revocation and future delegation. Services/jobs/processes receive narrow, validated operation rights; an admin-facing interface does not inherit unlimited kernel privileges.
3. **Unattended operation.** After provisioning, the machine can power on or remotely reboot without a person interacting with a boot prompt. A *UEFI setup/admin password* can protect firmware settings; a password demanded on every power-on would contradict the unattended requirement. Separate firmware setup protection, remote management authentication and O storage key unlock.
4. **Deployment-controlled kernel acquisition and updates.** The desired future network workflow downloads the appropriate **machine-specific, authenticated kernel image** from a controlled distribution endpoint (HTTP(S) or suitable EFI boot facility); the network location can be reachable only from a controlled management network. Source-address restriction, private networking or an URL secret **alone** does not authenticate kernel bytes. Image signature/verified boot and replay/downgrade policy must be designed independently. Pre-kernel WireGuard is not assumed: firmware HTTP boot does not automatically implement WG; a separately verified EFI network-stage/secure gateway would be required if WG is mandatory before the kernel. Never put long-lived passwords, tokens, signing keys or real production secrets in repo files, examples, URLs or logs.
5. **Storage and runtime threat boundary.** GE/O confidentiality-at-rest is a **goal**, not implemented by the existing O format. A signature on a kernel does not encrypt its bytes or prevent an alternative kernel from reading raw ciphertext. State explicitly the difference between (a) firmware/boot-chain authenticity, (b) kernel-image confidentiality and embedded secrets, (c) GE/O disk encryption and key release, and (d) runtime rights checked by the approved kernel. The user has suggested building per-machine secrets into a regularly updated kernel: record it as a **deployment proposal with explicit exposure limits** (anyone obtaining the image can potentially extract embedded symmetric keys). Compare a protected/TPM-sealed GE/O data key and separate build-time signing keys as a more defensible future production option. **Do not implement or silently mandate TPM, Secure Boot, full-disk encryption, attestation or a key server in E9.3.** Document keys' creation, rotation, upgrade/recovery, loss, replacement-board and rollback requirements as OPEN.
6. **Remote administration is narrow.** Record desired operations such as view service status, start/stop/restart named services, create/cancel schedules, reboot, and request authorized updates. A constrained service/operation authority is required; no generic root shell, arbitrary kernel memory read, raw disk I/O, privilege-setting backdoor or always-enabled profiler in production. Profiling/debug kernels may exist as distinct development builds without automatic production GE/O key access. The existing \`Ohand\`, \`iomask\`, OID and \`eve\` checks do **not** yet form a complete general capability system. Do not claim passkeys, service management, capability delegation or GE/O access control are already implemented.
7. **NO legacy multiuser filesystem requirement.** The production server/embedded model does not require POSIX UID/home-directory semantics, shared-login shell hosting, \`/home/user1\` or Plan 9 process-local namespace hierarchies. Existing legacy mechanisms may remain as temporary compatibility dependencies. This does **not** eliminate process isolation, authentication, quotas, audit, revocation or authorization per O Space/object. \`(SpaceID,OID)\` is object identity, not proof of permission; knowing an OID alone must never imply access. Historical provenance/ownership is distinct from authority.
8. **Desktop UNDECIDED.** Do not declare server-only to be a universal Plan2001-O architectural requirement. Keep local keyboard/display/desktop options in source; defer interactive desktop security and UI/session model without inventing a policy.

## Non-negotiable boot compatibility — maintain existing paths

- **Retain USB support** in current kernel profiles, including \`usb\` registration/controllers where already present. No removal of USB boot media, USB storage access or USB diagnostics by architectural assumption. Do not claim existing USB paths are proven unless tests demonstrate them.
- **Retain UEFI boot and GRUB boot support/workflows** as they exist today. Do not delete, disable, replace or rewrite GRUB EFI assets, EFI partition logic, boot scripts, loader/configuration or USB boot paths. GRUB/UEFI and local/USB paths remain valid development and recovery choices even if signed network boot is later implemented. Do not assert GRUB is tested or is the only loader without actual evidence.
- Future netboot is **additive/optional**, not a replacement. Specify preservation of at least one usable local/recovery boot path and an authenticated previous-good kernel fallback for remote machines, with an explicit downgrade policy. Both unattended normal boot and usable recovery should be possible under the chosen trust model.
- Do not change any \`bootdir\`, bootloader, image-generation script, disk layout, firmware variables, \`plan9.ini\`, executable OID, O volume opener, or existing QEMU/physical-boot behavior in E9.3.

## Deliverable 1 — authoritative design record

Write a new English file \`docs/PRODUCTION-BOOT-AND-AUTHORITY.md\` with sections:

- Status/Scope: \`TARGET/PROPOSED\` for server and embedded; desktop \`OPEN\`; \`IMPLEMENTED/LEGACY/TESTED\` clearly distinguished.
- Trust boundaries and concrete actor/resource diagram: firmware/EFI/GRUB/USB; image-distribution server; boot loader; kernel; GE/O encrypted-at-rest target; OID/Space; service/scheduler; one logical Administration environment; multiple authenticated humans; independent runtime services.
- Two separate lifecycle sequences: (A) normal unattended startup and remotely supplied kernel *as future option*, and (B) signed update, recovery/rollback and offline or network-unavailable startup; mark unavailable existing capabilities as OPEN.
- Boot-secret matrix: signing private/public keys, preboot network credentials, machine identity, kernel runtime credentials and GE/O encryption key; holder, usage, exposure and recovery. Distinguish UEFI setup password from boot-time user input. No actual keys or fake example passwords.
- Operation authorization model: identity vs ownership/provenance vs boot trust vs resource-scoped rights. Distinguish kernel-authorized resource operations, management-service authentication, and persisted O identities; avoid conflating an OID/handle/UID with a permission.
- Evidence matrix for actual inherited \`eve\`/\`iseve\`, \`hostownerwrite\`, \`timecontrolallowed\`, \`devproc\`, \`Ohand/Ohtab\`, \`OVOLOPEN/OSPACEOPEN/GET/PUT/COMMIT\`, \`iomask\`, USB, UEFI and GRUB integration. Use concrete source paths/functions/tests. Record unimplemented behavior honestly.
- Scope boundaries and staged follow-up tasks **without coding them**: (a) privilege/OSPACE authorization, (b) admin service/API and authenticating humans, (c) signed/attested boot and key handling, (d) encrypted GE/O device, (e) remote deployment/recovery, (f) desktop model later. For each include smallest independently testable proof and possible backward-compatibility break.

Do not define mandatory hierarchical \`File\` classes, universal filesystem owner/mode fields, abstract \`NativeDev\`, systemd-like service manager, general kernel capability ABI, Python security ontology, or new persistent GE/O format as part of the target. Describe essential semantics and leave the encoding/implementation OPEN.

## Deliverable 2 — align authoritative agent context without falsely claiming deployment

After the architecture record, minimally update:

- \`docs/GENERAL-SOFTWARE-SPECIFICATION.md\`: a concise security/deployment-profile section linking the record; maintain its philosophical scope and no-implementation assertions.
- \`AGENTS.md\`: add a short, explicit instruction that server/embedded production profile follows the record, no native all-powerful account, USB+GRUB/UEFI **must be retained**, and legacy \`eve\` behavior must remain intact during incremental migration.
- \`README.md\`: one short production-profile paragraph linking the record, visibly marked proposed; do not rewrite boot description to imply secure netboot, encrypted O, passkeys or rootless authorization already work.
- \`docs/STATUS.md\`: at most a short link in the "proposed/not implemented" context; DO NOT change last-runtime-verification date or claim new tests.
- \`docs/to_chatgpt_review.md\`: append a short **E9.3 design-only report** after the E9.1–E9.2 implementation report (or write \`docs/to_chatgpt_review_e93.md\` and link to it when the prior report is still agent-owned). Never overwrite live E9 implementation evidence.

Preserve \`docs/OLIO-OBJEKTI-MANIFESTI.md\`, \`docs/O-FORMAT.md\`, and all old O/boot test instructions except explicitly reviewed cross-references. Never edit E7's branch/spec artifacts.

## Verification and handoff

- This stage changes **documentation only**. Enforce \`git diff --name-only\` contains exclusively the approved documentation files. No C, build, script, generated kernel, UEFI/GRUB, EFI files or configuration changes.
- Check consistency with existing \`docs/KERNEL-API-ABI.md\` and \`docs/O-FORMAT.md\`: existing O handles are not capabilities, OID not an authorization token; storage format and current server boot unchanged.
- Confirm main-only worktree, staging and push. Review the full diff for accidental claims of Secure Boot, WG-preboot, TPM sealing, GE/O encryption, passkey verification or native admin service already existing.
- Do not rerun expensive kernel or QEMU gates for documentation-only edits; explicitly report \`NOT RUN (documentation-only, no executable changes)\`. If E9.1/E9.2 code was changed in the same ongoing session, retain its separate build and D2b evidence, and never pass E9.3 as a substitute for these gates.
- Final report: source-based findings; design decisions vs OPEN questions; exact documentation filenames/commit SHA; explicit USB, GRUB/UEFI compatibility retention; non-interference with E7; no silent privilege behavior changes.

**E9.3 verdict:** \`COMPLETE (documentation/design only)\` when documents are internally consistent and the reviewed diff is documentation-only. This does NOT mean production secure boot, GE/O disk encryption, passkey administration or rootless kernel authorization has been implemented.
