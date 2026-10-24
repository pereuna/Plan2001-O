# E7 merge readiness: native IPv6 branch vs `origin/main`

**VERDICT: READY-FOR-SEPARATE-MERGE** (conditional on the conflict
resolutions and post-merge gates in this document).

No merge, rebase, cherry-pick, PR or `main` push was performed for this
report.  E7.5 (tunnel/authentication/key management/userspace transport) is
deferred; SEALED mode is not implemented.

## 1. Snapshot

| Item | Value |
| --- | --- |
| Branch | `design/ipv6-only-native-20261024` |
| E7 head | `8c69db9` (`E7.7: native-only IPv6 profile without executable IPv4/ARP`) |
| `origin/design/...` before this report | `770f4ac`; E7.4–E7.7 commits are local until the final push |
| Merge base with `origin/main` | `1c61dd175c0757e5eaed016c1a7305f7ccad5c91` |
| `origin/main` observed | `a1fbf12` (OpenCode completion after E9.3) |
| Merge-tree probe | `git merge-tree --write-tree HEAD origin/main` -> tree `b51d7c9...`, exit 1, five content conflicts |
| E7 commits from base | E7.1/E7.2/E7.3/E7.3.1, E7.4 (`c2ee2c0`, `f64bcce`), E7.6 (`d391fa6`), E7.7 (`8c69db9`) |

`origin/main` contains E6 (native SD core, `pc64onativedisk`), E8 dev pruning
and E9 service pruning; this branch contains E7 networking only.  Neither
side modifies the other's core sources except the shared build/boot/docs
files listed below.

## 2. What E7 adds to `main`

- `ethercore.c` extraction and native Ether sink, plus `ethernative.c`,
  `nativev6.c`, `nativeudp6.c`, `nativeinh6.c`.
- Chan-free IP core `ipcore.c`; `pc64e7native` (E7.6, full native IP) and
  `pc64e7v6only` (E7.7, no executable IPv4/ARP).
- `ip6only.c`, `iproute6.c`, `ipv6only.c` and the `E7_IPV6_ONLY` guards in
  `ipifc.c`, `arp.c`, `udp.c`, `ipaux.c`, `loopbackmedium.c`, `icmp6.c`.
- E7.1–E7.7 probes/tests and `docs/E7-*.md` reports.
- Build selectors `ETHER_PROBE`, `IPV6_PROBE`, `UDP6_PROBE`, `E74_PROBE`,
  `E76_NATIVE`, `E77_NATIVE` and the `IP6CFLAGS` path.

It does not add a generic `ipmux`, a userspace socket ABI, a TCP6 stream
service, WireGuard, crypto, SEALED mode or a replacement storage/disk path.

## 3. Conflict map

`git merge-tree` reports these true content conflicts:

| File | Branch side | `origin/main` side | Resolution |
| --- | --- | --- | --- |
| `sys/src/9/pc64/mkfile` | `CONFLIST=... pc64e71 pc64e72 pc64e73 pc64e74 pc64e7native pc64e7v6only`; `ethercore.$O`; `XCFLAGS=$IP6CFLAGS` | `CONFLIST=... pc64onativedisk`; `sdcore.$O` | Union both profile lists, keep both object entries, keep `XCFLAGS`. No profile is renamed. |
| `tools/build.sh` | E7.1–E7.7 selector chain, one exclusivity sum, `ip6cflags` for E77 | `ONATIVE_DISK` selector and an explicit `ONATIVE_DISK`/`NATIVE_PROBE`/`OCONSOLE` exclusion | Keep one combined exclusivity check for all opt-in modes (`NATIVE_PROBE`, `OCONSOLE`, `ONATIVE_DISK`, E7.1–E7.7). Keep both selector chains and both target-file blocks. E77 remains the only writer of `ip6cflags=-DE7_IPV6_ONLY`. |
| `sys/src/9/pc64/main.c` | E7 probe externs and dispatch after `onativeprobe_start()` | `sdinitcontrollers()` extern and call after `chandevreset()` | Keep both. `git merge-file` already auto-merges the call and dispatch; only the extern block conflicts. |
| `docs/to_chatgpt_review.md` | E7.3.1 branch summary at the top | E9 completion summary at the top | Take main's E9 top summary. Preserve E7 history via `docs/to_chatgpt_review_e731.md`, `e74`, `e76`, `e77`; add a one-line E7 branch pointer if desired. Do not drop the E7 reports. |
| `docs/to_opencode.md` | E7.4–E7.8 assignment | E9 assignment | Take main's E9 assignment. The E7.4–E7.8 plan remains in `docs/E7-NATIVE-IP-PLAN.md`; link it from the E7 reports. This is the known conflict `origin/main` already anticipates; do not delete E7 history. |

Auto-merged but requiring semantic review:

| File | Why review is needed | Required check |
| --- | --- | --- |
| `sys/src/9/port/mkdevc` | Branch removes the `sub(/^[ \t]*/)` misc-bug fix; main adds `if(devsd \|\| nsdifc)`. | Regenerate E6 `pc64onativedisk.devc.c` and E7 `pc64e7v6only.devc.c`; verify no legacy network Devtabs and correct `sdifc[]`/`cons`/`sd` handling. |
| `sys/src/9/port/portmkfile` | Branch adds `$XCFLAGS` to all port/IP compile rules; main adds `sdcore.c`. | Build E6 (`ONATIVE_DISK=1`) and E77; `E7_IPV6_ONLY` must not change `sdcore.c` behavior. |
| `sys/src/9/arm64/mkfile` | Branch adds `ethercore.$O`; main adds `sdcore.$O`. | Keep both entries; arm64 is not a runtime gate here. |
| `sys/src/9/pc64/onativeprobe.c` | Branch appends E7.1–E7.4 stubs; main adds the E6 legacy `#S` read block. | Keep both; E7 stubs return 0, so the E6 probe block is unchanged. |
| `docs/STATUS.md` | Branch adds a branch-local E7.7 section before E5; main updates the top summary and appends E6/E9 sections. | Move/label the E7.7 section clearly as branch-local; reconcile the top "Last runtime verification" and scope line so E9 remains the current `main` statement and E7 is not read as merged. |
| `docs/GENERAL-SOFTWARE-SPECIFICATION.md` | Branch bumps the proposal to 0.3 and adds the IPv6-only scope section; main adds the 12.1 deployment/security section. | Keep both sections. Reconcile the version line and the "does not prescribe a network protocol"/"application-level" wording. The IPv6-only text remains a normative target; E7.7 implements it only in `pc64e7v6only`, not repository-wide. |

No source conflict exists in `sys/src/9/ip/*`, `sys/src/9/port/ethercore.c`,
`sys/src/9/port/devether.c`, the E7 configurations, or the E7 tests: those
are branch-only additions/modifications relative to the merge base.

## 4. Post-resolution verification gate

After a separate merge session resolves the five conflicts:

```sh
# default and E7 profiles
WHAT=kernel tools/build.sh && tools/test-qemu.sh
E77_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e77-ipv6-only.sh
E76_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e76-network.sh
ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh
IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh
UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh
E74_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e74-ipproto.sh

# E5 and E6/E9 shared surfaces
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
ONATIVE_DISK=1 WHAT=kernel tools/build.sh
python3 tools/sd_migration_check.py
python3 tools/kernel_opmap.py --check
python3 tools/test_kernel_opmap.py
```

`ONATIVE_DISK=1 tools/test-oboot-server.sh` and `tools/test-o-boot.sh` also
belong in the post-merge gate.  They were **NOT RUN in this E7 workspace**
because `build/selfroot/amd64/bin/{gefs,micropython}` is absent; their E6/E9
evidence on `main` is not evidence for the merged tree.  The E7 branch did
run the default kernel smoke gate and the E5 static/console gate.

Expected post-resolution invariants:

- `9pc64onativedisk` retains no `consdevtab`/`sddevtab` and links the native
  SD core; `9pc64e7v6only` retains no `ipoput4`/`ipiput4`/`tcpinit`/
  `icmpinit`/`v4lookup`/`arpwrite`/`convmac` and no legacy network Devtabs.
- `9pc64e7native` remains the full E7.6 native profile; E77's IPv4 removal
  does not leak into it.
- The E7.1 legacy `#l` RX path, E5 console profile and default `9pc64`/
  `9pc64mp` still behave as before.
- `tools/cons_migration_check.py` accepts the union `CONFLIST` (membership,
  not an exact E5-era string).
- `mkdevc` generates correct `devtab[]` for both `pc64onativedisk` and
  `pc64e7v6only`.

## 5. Risks and non-claims

- The `build.sh` conflict is the highest-risk mechanical merge: a careless
  union can let `ONATIVE_DISK` combine with an E7 profile or let
  `E77_NATIVE` lose `ip6cflags`.  Keep one combined exclusivity check.
- `mkfile` must not drop `pc64onativedisk` or the E7 profiles; neither side
  may rename an existing kernel.
- `STATUS.md` and `to_chatgpt_review.md` are historical/current records, not
  code.  Losing the E7 reports or presenting E7 as merged would be an
  evidence error.
- E7.5 remains deferred; no SEALED mode, WireGuard, crypto, userspace
  tunnel, socket ABI or TCP6 stream service is claimed.  Next Header 253
  remains an RFC 3692 plaintext experiment.
- `pc64e7v6only` still carries `arpenter`/the ARP table for IPv6 neighbor
  state and a no-op `tcpmssclamp`; neither is an IPv4 executable path.
- Physical non-VirtIO NICs, IPv6 fragmentation/extension-header fuzzing on
  physical hardware, E6 physical AHCI/NVMe, and full O-boot on the merged
  tree were not exercised here.

## 6. Merge procedure (not performed here)

1. Use a separate merge session/worktree; do not rewrite the E7 branch.
2. Merge `origin/main` into the E7 branch or the E7 branch into a dedicated
   integration branch, per the project's chosen direction.  Resolve only the
   five conflicts above; keep both sides' profiles and reports.
3. Regenerate every generated `.devc.c` and rerun the gate in section 4.
4. If any post-resolution gate fails, treat the merge as blocked and fix the
   resolution, not the gate.
5. Push/PR only after the merged tree passes; do not combine E7.5/SEALED.
