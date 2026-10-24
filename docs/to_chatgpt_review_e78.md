# E7.8 review: merge readiness only

**VERDICT: READY-FOR-SEPARATE-MERGE** (conditional on the documented
conflict resolutions and post-merge gates).
**Branch:** `design/ipv6-only-native-20261024`.
**E7 code head:** `8c69db9` (`E7.7`); this report is the E7.8 docs commit.
**Merge base:** `1c61dd175c0757e5eaed016c1a7305f7ccad5c91`.
**`origin/main` observed:** `a1fbf12`.
**No merge, rebase, cherry-pick, PR or `main` push was performed.**
**E7.5 remains deferred; SEALED is not implemented.**

## 1. Purpose and result

E7.8 is verification and merge-readiness only.  The detailed conflict map,
resolution choices, risks and post-merge gate are in
[E7-MERGE-READINESS.md](E7-MERGE-READINESS.md).

`git merge-tree --write-tree HEAD origin/main` exits 1 with five content
conflicts:

```text
docs/to_chatgpt_review.md
docs/to_opencode.md
sys/src/9/pc64/main.c
sys/src/9/pc64/mkfile
tools/build.sh
```

All five are mechanical, independent-evolution conflicts:

- `mkfile`: union E7 profile list with `pc64onativedisk`; keep `ethercore`
  and `sdcore`.
- `build.sh`: combine E7.1–E7.7 selectors with `ONATIVE_DISK`; keep one
  exclusivity check and the E77-only `ip6cflags`.
- `main.c`: keep both the E7 probe externs/dispatch and main's
  `sdinitcontrollers()` call.  The call and dispatch auto-merge; only the
  extern block conflicts.
- `to_chatgpt_review.md`: take main's E9 summary; preserve E7 evidence in
  the dedicated E7 reports.
- `to_opencode.md`: take main's E9 assignment; preserve the E7 plan in
  `E7-NATIVE-IP-PLAN.md`.

Auto-merged shared files need a post-merge check: `mkdevc` (branch `sub`
fix + main `nsdifc`), `portmkfile` (`XCFLAGS` applies to main's `sdcore`),
`arm64/mkfile`, `onativeprobe.c`, `STATUS.md` and
`GENERAL-SOFTWARE-SPECIFICATION.md`.

## 2. Branch evidence inherited from E7.7

```sh
E77_NATIVE=1 WHAT=kernel tools/build.sh
tools/test-e77-ipv6-only.sh
```

`9pc64e7v6only`: 1736176 bytes, md5
`2b249a1d1ea6e75518cbc461390d1425`.  No `ipoput4`, `ipiput4`, `tcpinit`,
`icmpinit`, `v4lookup`, `v4source`, `arpwrite`, `convmac` or legacy network
Devtabs.  Real VirtIO NDP, ICMPv6, UDP6 and Next Header 253 pass; a real
IPv4 EtherType frame is counted as `rxother=1` with no IPv4 TX; an
IPv4-mapped UDP6 open returns `Udp6ErrFamily`; no-NIC passes.  Details:
[to_chatgpt_review_e77.md](to_chatgpt_review_e77.md).

## 3. Regression matrix on the final E7 code

| Gate | Command | Result |
| --- | --- | --- |
| E7.1 | `ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh` | PASS: native TX/RX, legacy `#l` RX, negatives |
| E7.2 | `IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh` | PASS: NDP NA, ICMPv6 Echo, negatives |
| E7.3 | `UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh` | PASS: UDP6 lengths/checksums/races/teardown |
| E7.4 | `E74_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e74-ipproto.sh` | PASS: Next Header 253 + NDP/UDP6/ICMPv6 |
| E7.6 | `E76_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e76-network.sh` | PASS: full native profile, no legacy Devtabs, IPv6 path |
| E7.7 | `E77_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e77-ipv6-only.sh` | PASS: no executable IPv4/ARP, IPv6 path preserved |
| Default | `WHAT=kernel tools/build.sh && tools/test-qemu.sh` | PASS: `9pc64`/`9pc64mp` built; kernel up to init0 |
| E5 console | `OCONSOLE=1 WHAT=kernel tools/build.sh` + `tools/cons_migration_check.py --kernel ... --devc ...` | PASS: 23 Qids, 19 native, no `cons` Dev |

The E5 checker now validates `pc64oconsole` membership in `CONFLIST`
instead of an exact E5-era string, because E7 adds profiles.  This is a
scope-preserving test update, not a weakened check.

## 4. Not run / limits

- `tools/test-o-boot.sh`, `OCONSOLE=1 tools/test-oboot-server.sh`,
  `ONATIVE_DISK=1 tools/test-oboot-server.sh` and
  `python3 tools/sd_migration_check.py` were **not rerun in this E7
  workspace**: `build/selfroot/amd64/bin/{gefs,micropython}` is absent.
  E6/E9's prior runtime evidence is on `main`, not evidence for the merged
  tree.  These are mandatory post-resolution gates.
- Physical non-VirtIO NICs, E6 physical AHCI/NVMe, IPv6 extension-header
  fuzzing on physical hardware and full merged-tree O boot remain NOT RUN.
- E7.5 (userspace tunnel/authentication/key management) is deferred; no
  WireGuard, crypto, SEALED mode, on/off switch, scheduler, classifier or
  fake security boundary is claimed.  Next Header 253 is an RFC 3692
  plaintext experiment.
- `pc64e7v6only` keeps `arpenter`/the ARP table for IPv6 neighbor state and
  a no-op `tcpmssclamp`; these are not IPv4 executable paths.

## 5. Required merge-session actions

1. Resolve the five conflicts exactly as mapped in
   `E7-MERGE-READINESS.md`; keep both sides' profiles and reports.
2. Regenerate all `.devc.c` files.
3. Run the post-resolution gate in `E7-MERGE-READINESS.md` section 4,
   including the O-boot/selfroot and SD checks not available here.
4. Do not merge E7.5/SEALED work; do not combine this branch with an
   unrelated rewrite.
5. Push/PR only after the merged tree passes.
