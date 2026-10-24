# E7.6 review: isolated NORMAL IPv6 profile without #l/#I/#W

**VERDICT: PASS** (E7.6 gate met; no SEALED and no E7.5 work).
**Branch:** `design/ipv6-only-native-20261024`.
**Base:** E7.4 head `f64bcce`.
**E7.6 commit:** the commit adding this report.
**Mode status:** `NORMAL only`; **SEALED NOT IMPLEMENTED**; **E7.5 USERSPACE
TUNNEL DEFERRED**.

## 1. Delivered

- New isolated profile `sys/src/9/pc64/pc64e7native` and
  `E76_NATIVE=1 WHAT=kernel tools/build.sh`.
- New Chan-free IP core `sys/src/9/ip/ipcore.c` extracted from `devip.c`
  (`ipfsinit`, `Fsproto`, `Fsprotoclone`, `Fsrcvpcol`, `Fsnewcall`,
  `closeconv`, address/port helpers, `newipaux`, `scalednconv`, plus
  `ipfmtinstall`).
- Shared legacy Qid constants in `sys/src/9/ip/ipdevqid.h`.
- `sys/src/9/ip/ethernative.c`: `ethermediumframe6`, a V6-only NDP/framing
  helper with no `Chan`.
- `ethercore.c` optional hooks `etherlegacyrxhook` and
  `ethernetifinithook`; `devether.c` installs them in legacy profiles.
  Shared `ethersetspeed`, `ethersetlink`, `ethercrc` moved from
  `devether.c` to `ethercore.c`.
- `nativev6.c` now uses `ethermediumframe6`.
- `port/mkdevc` indentation/`sub` bug fixed; generated tables rechecked.
- `tools/test-e76-network.sh`: generated-Dev/symbol audit plus the real
  E7.4 VirtIO fixture against `9pc64e7native`.
- Audit in `docs/E7-NETWORK-CUTOVER.md`.

Ordinary `9pc64`, `9pc64mp`, E7.1-E7.4 and E5 profiles still link/register
`#l`, `#I`, `#W`; only `pc64e7native` omits them.

## 2. Gate evidence

### 2.1 Exact target and generated Dev table

```sh
E76_NATIVE=1 WHAT=kernel tools/build.sh
# 9pc64e7native: 1816135 bytes
# md5 28ed2683222f3d815a2f080c8f594ef7
# BUILD-DONE
```

`build/amd64/pc64e7native.devc.c` `devtab[]` contains: root, cons, swap,
arch, pnp, env, pipe, proc, mnt, srv, shr, dup, rtc, tls, cap, kprof, fs,
draw, mouse, vga, sd, uart, usb, kbd, segment, gefs. It has **no**
`etherdevtab`, `ipdevtab` or `wgdevtab`.

### 2.2 Linked-symbol audit (exact binary)

Absent: `etherdevtab`, `ipdevtab`, `wgdevtab`, `etherattach`, `ipattach`,
`wglisten`, `chandial`, `netifinit`, `etherlegacyrx`, `ethermux`, `etheroq`.

Present: `ethermediumframe6`, `ipfsinit`, `Fsproto`, `Fsprotoclone`,
`ethercore_rxregister`, `ipv6native_start`, `nativeip6_register`,
`udp6_open`.

`namec` is present as a general kernel symbol for unrelated Devs; it is not
reached by the native network path. The executed-path evidence is the guest
counter line below.

### 2.3 Real VirtIO traffic and native-path Chan counters

```sh
tools/test-e76-network.sh
```

Actual result:

```text
generated devtab: no etherdevtab/ipdevtab/wgdevtab
absent legacy symbol: etherdevtab
absent legacy symbol: ipdevtab
absent legacy symbol: wgdevtab
absent legacy symbol: etherattach
absent legacy symbol: ipattach
absent legacy symbol: wglisten
absent legacy symbol: chandial
absent legacy symbol: netifinit
absent legacy symbol: etherlegacyrx
absent legacy symbol: ethermux
absent legacy symbol: etheroq
present native symbol: ethermediumframe6
present native symbol: ipfsinit
present native symbol: Fsproto
present native symbol: Fsprotoclone
present native symbol: ethercore_rxregister
present native symbol: ipv6native_start
present native symbol: nativeip6_register
present native symbol: udp6_open
PASS: absent controller (no IPv6 consumer)
GUEST-LL: fe80::5054:ff:fe12:3456
NDP: NA ok
ICMPv6: echo ok
UDP6: echoed len 0,1,17
IP253: echo ok, no duplicate
NEG: no 253 reply for 254/HBH/version/length/truncated/IPv4
PASS: real VirtIO NDP/ICMP/UDP6/Next Header 253 and negatives
PASS: E7.6 native profile has no legacy #l/#I/#W adapter and keeps NORMAL IPv6
```

Guest serial (`build/verification/e76/boot-virtio.log`):

```text
E74IP: INIT rc=1 inits=1 probes=67
E74IP: INIT-IDEMP rc=1 probes=0 idempotent=1
E74IP: POSITIVE iprx=1 iptx=1 ipbytes=13 udprx=3 udptx=3
E74IP: CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1
E74IP: STOP rc=0
E74IP: DONE pass=1 fails=0
```

No-NIC (`build/verification/e76/boot-nonic.log`): `NODEV n=0`,
`DONE pass=1 fails=0`.

The probe's init check was made profile-agnostic: legacy profiles initialize
the Ether core at boot via `#l` reset, while `pc64e7native` has no such
reset. The probe now performs the first `ethercore_init` and then verifies a
second call is idempotent (`INIT-IDEMP ... idempotent=1`).

## 3. Regression matrix actually run after the split

| Profile | Command | Actual result |
| --- | --- | --- |
| E7.1 | `ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh` | PASS: native TX/RX, legacy `#l` RX, negatives |
| E7.2 | `IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh` | PASS: NA + ICMPv6 Echo + negatives |
| E7.3 | `UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh` | PASS: UDP6 lengths/checksums/races/teardown; `in=48 out=10 noports=1 inerrors=5` |
| E7.4 | `E74_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e74-ipproto.sh` | PASS: Next Header 253 + NDP/UDP6/ICMPv6 coexistence |
| Default | `WHAT=kernel tools/build.sh && tools/test-qemu.sh` | PASS: kernel up to init0; `9pc64` and `9pc64mp` built |
| E5 console | `OCONSOLE=1 WHAT=kernel tools/build.sh` + `tools/cons_migration_check.py` | PASS: 23 Qids, 19 native, no `cons` Dev |

The E7.1 legacy `#l` RX test passing confirms the new
`etherlegacyrxhook`/`ethernetifinithook` wiring preserved legacy behavior.

## 4. Known limits / non-claims

- IPv4/ARP are still linked in `pc64e7native`; E7.7 removes them.
- TCP is still linked/initialized; no native TCP6 API is claimed.
- `devip.c`, `devether.c`, `netif.c`, `devwg.c`, `ethermedium.c` remain in
  the tree and in ordinary profiles.
- `loopbackmedium.c` still contains an inherited `ipiput4` call; E7.7 must
  address it.
- No SEALED mode, mode switch, crypto, userspace tunnel, socket ABI or WireGuard.
- Physical non-VirtIO NICs were not exercised in this stage.
