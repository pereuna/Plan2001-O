# E7.6 native network cutover: #l/#I/#W removal from the E7-only profile

**Status:** implemented and host-verified for the opt-in `pc64e7native`
kernel. Ordinary profiles remain unchanged in behavior and still register
`#l`, `#I` and `#W`.
**Branch:** `design/ipv6-only-native-20261024`.

## 1. Result

The new `pc64e7native` profile (built with `E76_NATIVE=1`) links the NORMAL
IPv6 path without:

- the `ether` Dev (`devether.c` / `etherdevtab`, `#l`),
- the `ip` Dev (`devip.c` / `ipdevtab`, `#I`),
- the `wg` Dev (`devwg.c` / `wgdevtab`, `#W`),
- `netif.c` (`Netfile` file fanout / `netifinit`),
- `ethermedium.c` (`etherbind`/`etherread*` `namec`/`chandial` adapters).

The native path keeps: VirtIO driver registration, `ethercore`, the inherited
`Fs`/`Proto`/`Conv` IP core, ICMPv6/NDP, UDP6, the E7.4 Next Header 253
consumer, and `ipoput6`/`ethercore_tx` output.

`Fs`, `Proto` and `Conv` are still used as **native C structures**. That is
not a `Chan` edge: no native path calls `namec`, `chandial`, `walk`,
`devwalk`, `mount`, `ipattach`, `etherattach`, `etherbind`, `etherread*` or
`wglisten`. The E7.4 probe's `CHAN-NATIVE ... namec=0 newchan=0 walk=0
devwalk=0 mount=0 exec=0 clean=1` remains the executed-path evidence.

## 2. Native versus legacy edges

| Symbol / edge | Source | E7-native treatment |
| --- | --- | --- |
| `etherdevtab`, `etherattach`, `etherwalk/open/read/write/bread/bwrite/close`, `ethermux`, `etheroq`, `etherlegacyrx`, `netconsole`, `dmatproxy` | `port/devether.c` | **not linked**. The `ether` Dev line is absent from `pc64e7native`. |
| `netifinit`, `Netfile`, `netifopen/read/write/bread/wstat/close`, multicast/bridge/bypass policy | `port/netif.c` | **not linked**. `etherprobe` detects a nil `ethernetifinithook` and performs only the minimal `Netif` field setup (`f=nil`, `nfile=0`, `limit=0`). MAC/link/counters remain in the embedded `Netif`. |
| `ipdevtab`, `ipattach/walk/open/read/write/bread/bwrite/close`, `ipgen`, `ipread`, `ndb*` | `ip/devip.c` | **not linked**. Those Dev functions stay only in legacy profiles. |
| `ipfsinit`, `newipaux`, `Fsproto`, `Fsbuiltinproto`, `Fsprotoclone`, `Fsconnected`, `Fsrcvpcol`, `Fsrcvpcolx`, `Fsnewcall`, `closeconv`, `Fsstdconnect/announce/bind`, `setluniqueport`, `lportinuse`, `unusedlport`, `scalednconv` | new `ip/ipcore.c` | **linked**. Extracted unchanged from `devip.c`; no `Chan`, `Dirtab`, `devattach`, `ipfs[]` or file walk. |
| `Qid` encoding constants | new `ip/ipdevqid.h` | shared by `devip.c` and `ipcore.c` so the inherited `Proto.qid` value remains compatible for legacy `#I`. |
| `eipfmt` / `fmtinstall('i','I','E','V','M')` | `ipcore.c` `ipfmtinstall()` | native-only profile has no `ipreset`/`etherreset` Dev reset, so the shared core installs the formats. |
| `etherbind`, `etherbwrite`, `etherread4`, `etherread6`, `recvarpproc`, `sendarpreq`, `sendgarp` | `ip/ethermedium.c` | **not linked**. |
| `ethermediumframe` (V4/V6 framing, ARP/NDP) | `ip/ethermedium.c` | replaced in the native path by `ethermediumframe6` in `ip/ethernative.c` (V6 NDP and Ethernet header only, no Chan). |
| `ethermedium`, `gbemedium` registration | `ip/ethermedium.c` | **not linked**; the native `Ipifc` gets `ipv6nativemedium` directly. |
| `wgdevtab`, `wglisten`, `wgreader` | `ip/devwg.c` | **not linked**. |
| `etherlegacyrx` call in `etheriq` | `port/ethercore.c` | now an optional hook. `devether.c` installs every legacy RX frame into it; the native profile leaves it nil and frees the original frame. |
| `netifinit` call in `etherprobe` | `port/ethercore.c` | now an optional hook, installed by `devether.c`; native profile uses the minimal path. |
| `ethersetspeed`, `ethersetlink`, `ethercrc` | moved from `devether.c` to `ethercore.c` | shared by drivers in every profile; no legacy file policy. `ethersetlink` already returns early when `f == nil`. |
| `ip_init`, `arpinit`, `netloginit`, `ipifcinit`, `icmp6init`, `udpinit`, `tcpinit` | inherited core | **linked**; IPv6/NDP/UDP6 remain the working NORMAL stack. |
| `ipoput6`, `ipiput6`, `procxtns`, `v6lookup`, `ipifcoput`, `icmpiput6`, `udpiput`, `udpkick` | inherited core | **linked**; no `Chan` in the native execution path. |
| `loopbackmedium` | `ip/loopbackmedium.c` | linked for `ipoput6` loopback. It still contains an inherited `ipiput4` call; IPv4 removal is E7.7. |
| `chandial` | `ip/chandial.c` | **not linked** in the native target. |
| core `namec` / general `Chan` machinery | `port/chan.c` | present because other non-network Devs (root/fs/mnt/draw/...) use it; **not reached** by the native network path (`CHAN-NATIVE ... clean=1`). |

## 3. Build-tool fix

`port/mkdevc` used `sub(/^[ \t]*/, "")` on a `misc` line and then re-tested
the stripped line as a possible section header. A `misc` object whose name
contained `dev`, `ip`, `link`, `misc` or `port` therefore ended misc
collection and silently dropped later device/architecture entries. The
`sub` had no remaining purpose (`misc[]` is unused), so it was removed. This
is a correctness fix for every profile; the generated tables were rechecked
for `pc64`, `pc64mp`, `pc64oconsole`, E7.1-E7.4 and `pc64e7native`.

## 4. Generated/linked evidence

`E76_NATIVE=1 WHAT=kernel tools/build.sh` produced:

- kernel `9pc64e7native`, 1816135 bytes,
  md5 `28ed2683222f3d815a2f080c8f594ef7` (E7.6 verification build);
- `pc64e7native.devc.c` whose `devtab[]` contains no `etherdevtab`,
  `ipdevtab` or `wgdevtab`;
- `strings` symbol audit: absent `etherdevtab`, `ipdevtab`, `wgdevtab`,
  `etherattach`, `ipattach`, `wglisten`, `chandial`, `netifinit`,
  `etherlegacyrx`, `ethermux`, `etheroq`; present `ethermediumframe6`,
  `ipfsinit`, `Fsproto`, `Fsprotoclone`, `ethercore_rxregister`,
  `ipv6native_start`, `nativeip6_register`, `udp6_open`.

These are the **authoritative emitted tables and the exact target binary**
from the E7.6 build, not greps of the source tree. The E76 fixture reruns
the symbol audit from that binary.

## 5. Executed evidence

`tools/test-e76-network.sh`:

```text
generated devtab: no etherdevtab/ipdevtab/wgdevtab
absent legacy symbol: etherdevtab
absent legacy symbol: ipdevtab
absent legacy symbol: wgdevtab
absent legacy symbol: netifinit
absent legacy symbol: etherlegacyrx
present native symbol: ethermediumframe6
present native symbol: ipfsinit
present native symbol: nativeip6_register
present native symbol: udp6_open
PASS: absent controller (no IPv6 consumer)
NDP: NA ok
ICMPv6: echo ok
UDP6: echoed len 0,1,17
IP253: echo ok, no duplicate
NEG: no 253 reply for 254/HBH/version/length/truncated/IPv4
PASS: real VirtIO NDP/ICMP/UDP6/Next Header 253 and negatives
PASS: E7.6 native profile has no legacy #l/#I/#W adapter and keeps NORMAL IPv6
```

Guest markers from the same run:

```text
E74IP: INIT rc=1 inits=1 probes=67
E74IP: INIT-IDEMP rc=1 probes=0 idempotent=1
E74IP: POSITIVE iprx=1 iptx=1 ipbytes=13 udprx=3 udptx=3
E74IP: CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1
E74IP: STOP rc=0
E74IP: DONE pass=1 fails=0
```

Regression runs after the shared-core split:

| Profile | Actual result |
| --- | --- |
| E7.1 | PASS: VirtIO native TX/RX, legacy `#l` RX, negatives |
| E7.2 | PASS: NDP NA + ICMPv6 Echo + negatives |
| E7.3 | PASS: UDP6 0/1/17/1452, checksums, races, teardown; `in=48 out=10 noports=1 inerrors=5` |
| E7.4 | PASS: Next Header 253 + no interference with NDP/UDP6/ICMPv6 |
| Default | PASS: kernel up to init0 (no root=); `9pc64` + `9pc64mp` built |
| E5 console | PASS: 23 Qids, 19 native, no `cons` Dev |

## 6. Explicit holds / next stage

- IPv4 parsing/forwarding/ARP and `ipoput4`/`ipiput4` are still linked in
  `pc64e7native`; removing them is **E7.7**, not E7.6.
- TCP is still linked and initialized (inherited); no new native TCP6 API is
  claimed. `NORMAL` means the conventional IPv6 stack only for the
  implemented/linked protocols.
- `devether.c`, `netif.c`, `devip.c`, `devwg.c` and `ethermedium.c` remain
  in the tree and remain linked in ordinary/E7.1-E7.4 profiles.
- The core `namec` symbol exists for unrelated Devs; the native network path
  does not call it.
- No SEALED mode, no E7.5 tunnel, no crypto, no userspace networking ABI.
