# E7.7 review: native-only IPv6 profile without executable IPv4/ARP

**VERDICT: PASS** (E7.7 gate met; no SEALED and no E7.5 work).
**Branch:** `design/ipv6-only-native-20261024`.
**Base:** E7.6 head `d391fa6`.
**E7.7 commit:** the commit adding this report.
**Mode status:** `NORMAL only`; **SEALED NOT IMPLEMENTED**; **E7.5 USERSPACE
TUNNEL DEFERRED**.

## 1. Delivered

- New isolated profile `sys/src/9/pc64/pc64e7v6only` and
  `E77_NATIVE=1 WHAT=kernel tools/build.sh`.  E7.6's
  `pc64e7native` remains the full native IP profile; E7.7 does not silently
  change it.
- New `sys/src/9/ip/ip6only.c`: V6-relevant IP core subset derived from
  `ip.c` (`ip_init`, `iprouting`, `ipstats`, V6-only `initfrag`).  Legacy
  profiles still link `ip.c`.
- New `sys/src/9/ip/iproute6.c`: V6 route table/lookup/source and route
  insertion from `iproute.c`, with V4 and the legacy `#I` route-file parser
  removed.  Legacy profiles still link `iproute.c`.
- New `sys/src/9/ip/ipv6only.c`: the profile's `tcpmssclamp` no-op and the
  inherited ICMP common connect/announce/state helpers.
- `E7_IPV6_ONLY` compile-time selection in `ipifc.c`, `arp.c`, `udp.c`,
  `ipaux.c`, `loopbackmedium.c` and `icmp6.c`:
  - no V4 source/route lookup, no V4 route writer, no `ipselftabread`;
  - no ARP request/reply/translation path (NDP and `arpenter` remain);
  - no V4 UDP send/receive/translation/forwarding; V6 `udpadvise` is
    retained, V4 translation advice and `udpforward` are not;
  - loopback calls `ipiput6` only;
  - `icmpclose6` closes its own queues instead of calling IPv4 `icmpclose`.
- Compile flag plumbing: `tools/build.sh` -> `tools/build.rc` ->
  `IP6CFLAGS` -> `XCFLAGS` in `pc64/mkfile` and `port/portmkfile`.
- `sys/src/9/pc64/e74nhprobe.c`: E7.7-only checks for IPv4-mapped UDP6
  rejection, synthetic IPv4 EtherType drop, and a real-frame `rxother`
  counter.
- `tools/test-e77-ipv6-only.sh`: linked-symbol/generated-Dev audit plus the
  real VirtIO fixture with `--profile e77`.
- `tools/test_e74_ipproto.py`: optional E77 assertions; the existing
  `NEG-RESULT` parser accepts the new `other=` field.
- `tools/cons_migration_check.py`: `CONFLIST` membership check instead of an
  exact E5-era string, so the added E7 profiles do not break the E5 gate.

### Why source separation

The 9front `6c` used by the build rejects some `#ifndef E7_IPV6_ONLY` layouts
with `<eof> syntax error, last name: endif`.  `ip.c` and `iproute.c` keep
their original full V4/V6 sources for legacy profiles; the E7-native profile
links the directive-free V6-only copies.  The smaller guards in
`ipifc.c`/`arp.c`/`udp.c`/`ipaux.c`/`loopbackmedium.c`/`icmp6.c` compile in
both modes and retain the legacy branches when the macro is absent.

## 2. Gate evidence

### 2.1 Exact target

```sh
E77_NATIVE=1 WHAT=kernel tools/build.sh
# 9pc64e7v6only: 1736176 bytes
# md5 2b249a1d1ea6e75518cbc461390d1425
# BUILD-DONE
```

`build/amd64/pc64e7v6only.devc.c` has no `etherdevtab`, `ipdevtab` or
`wgdevtab`.

### 2.2 Linked-symbol audit

```sh
tools/test-e77-ipv6-only.sh
```

Absent from the exact kernel: `ipoput4`, `ipiput4`, `ipfraginit`,
`ipfragreass`, `ipfragtag`, `ipfragfree`, `ipfraglookup`, `tcpinit`,
`tcpiput`, `tcpconnect`, `tcpclose`, `icmpinit`, `icmpiput`, `icmpnohost`,
`v4lookup`, `v4source`, `v4lookupskip`, `arpwrite`, `arpread`, `convmac`,
`readipifc`, `ipselftabread`, and the legacy `etherdevtab`/`ipdevtab`/
`wgdevtab`/`etherattach`/`ipattach`/`wglisten`/`chandial`/`netifinit`/
`etherlegacyrx`/`ethermux`/`etheroq`.

Present: `ipoput6`, `ipiput6`, `v6lookup`, `v6source`, `icmp6init`,
`icmpiput6`, `udp6_open`, `ndpsendsol`, `ethermediumframe6`,
`tcpmssclamp`, `arpenter`, `nativeip6_register`, `ipv6native_start`,
`ipfsinit`, `Fsproto`, `Fsprotoclone`, `ethercore_rxregister`,
`ipfmtinstall`.

`arpenter` is present because IPv6 neighbor discovery uses the inherited ARP
table machinery; the V4 `arpwrite`/`arpread`/`convmac` entry points are
absent.

### 2.3 Real VirtIO traffic

`tools/test-e77-ipv6-only.sh` boots `9pc64e7v6only` with the E7.4 fixture and
checks both the normal IPv6 path and the IPv4 negatives.

```text
E74IP: CHECK udp6-open-v4 rc=-4
E74IP: CHECK ipv4-drop other=1 rxframes=0
E74IP: POSITIVE iprx=1 iptx=1 ipbytes=13 udprx=3 udptx=3
E74IP: CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1
E74IP: NEG-RESULT iprx=2 iptx=2 unhandled=2 badhdr=2 other=1
E74IP: ALIVE iprx=2 iptx=2
E74IP: CHECK send-v4 rc=-6
E74IP: UNREG-WAIT active=1
E74IP: UNREG rc=0 active=0 registered=0
E74IP: REARM-OK iprx=4 iptx=3
E74IP: TXDOWN txdown=1
E74IP: STOP rc=0
E74IP: DONE pass=1 fails=0
```

Interpretation:

- `udp6-open-v4 rc=-4` is the `Udp6ErrFamily` rejection of an IPv4-mapped
  local address before any endpoint is created.
- `ipv4-drop other=1 rxframes=0` is an injected `0x0800` EtherType frame
  dropped by the native L2 gate with no `rxframes` increment.
- `NEG-RESULT ... other=1` is the real host `0x0800` frame counted as
  non-IPv6 by the VirtIO receive path.  The host fixture also verifies the
  guest emitted **zero** IPv4 EtherType frames.
- NDP NA, ICMPv6 Echo, UDP6 lengths 0/1/17 and Next Header 253 echo all pass;
  malformed/HBH/wrong-version/254 negatives produce no 253 reply.
- No NIC: `E74IP: NODEV n=0`, `E74IP: DONE pass=1 fails=0`.

Logs: `build/verification/e77/static.log`,
`build/verification/e77/boot-virtio.log`,
`build/verification/e77/boot-nonic.log`.

## 3. Regression matrix actually run

| Profile | Command | Actual result |
| --- | --- | --- |
| E7.1 | `ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh` | PASS: native TX/RX, legacy `#l` RX, negatives |
| E7.2 | `IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh` | PASS: NA + ICMPv6 Echo + negatives |
| E7.3 | `UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh` | PASS: UDP6 lengths/checksums/races/teardown |
| E7.4 | `E74_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e74-ipproto.sh` | PASS: Next Header 253 + NDP/UDP6/ICMPv6 coexistence |
| E7.6 | `E76_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e76-network.sh` | PASS: full native profile, no legacy Devtabs, IPv6/NDP/UDP6/253 |
| E7.7 | `E77_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e77-ipv6-only.sh` | PASS: no executable IPv4/ARP, IPv6 path preserved |
| Default | `WHAT=kernel tools/build.sh && tools/test-qemu.sh` | PASS: `9pc64` and `9pc64mp` built; kernel up to init0 |
| E5 console | `OCONSOLE=1 WHAT=kernel tools/build.sh` + `python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c` | PASS: 23 Qids, 19 native, no `cons` Dev |

The legacy `ip.c`/`iproute.c` paths were exercised by the default build and
the E7.1/E5 builds; E7.1's legacy `#l` RX remains green.

## 4. Known limits / non-claims

- `tcpmssclamp` is a documented no-op in `pc64e7v6only`; there is no native
  TCP6 stream service and no user route-file (`#I`) writer in this profile.
  A gated-forwarding path would not clamp TCP MSS.
- `ip.c`, `iproute.c`, `arp.c`, `udp.c`, `ipaux.c`, `ipifc.c` and
  `loopbackmedium.c` remain in the tree and in legacy profiles.  E7.7 is a
  profile/link selection, not a repository-wide deletion.
- `arpenter` and the ARP table remain for IPv6 neighbor state; only the V4
  packet/ARP entry points are absent.
- The E77 profile is not the default and does not implement SEALED mode,
  WireGuard, crypto, a userspace tunnel, a socket ABI, a route-file parser or
  a native TCP6 API.
- Physical non-VirtIO NICs and a full O-boot regression were not rerun in
  this stage.  The default kernel smoke gate and the E5 static/console gate
  passed; the IP changes are profile-gated.
