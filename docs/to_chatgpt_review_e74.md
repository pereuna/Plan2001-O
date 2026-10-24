# E7.4 review: experimental native IPv6 Next Header consumer

**VERDICT: PASS** (E7.4 gate met; no SEALED and no E7.5 work).
**Branch:** `design/ipv6-only-native-20261024`.
**E7.4.0 design commit:** `c2ee2c0`.
**E7.4.1/E7.4.2 implementation + tests:** the commit adding this report.
**Base before E7.4:** `770f4ac` (E7.3.1 head).
**Mode status:** `NORMAL only`; **SEALED NOT IMPLEMENTED**; **E7.5 USERSPACE
TUNNEL DEFERRED**. Next Header 253 is an RFC 3692 experiment selector, not
WireGuard, not encryption, not an authenticated transport.

## 1. What was implemented

| Piece | Source | Purpose |
| --- | --- | --- |
| Design/source map and future SEALED seam | `docs/E7-NATIVE-IP-PLAN.md` | Exact RX/TX path, registration ownership, explicit NOT IMPLEMENTED seam. |
| Native consumer | `sys/src/9/ip/nativeinh6.c`, `nativeinh6.h` | One `Proto` for Next Header 253 via existing `Fsproto`/`Fsrcvpcol`; validated receive callback; fixed-protocol sender through `ipoput6`. |
| Opt-in probe | `sys/src/9/pc64/e74nhprobe.c` | Registers the consumer, echoes 253, opens a UDP6 echo endpoint, exercises lifecycle and negatives. |
| Test profile | `sys/src/9/pc64/pc64e74`, `CONFLIST`, `E74_PROBE=1` | Isolated E7.4 kernel; legacy profiles unchanged. |
| Host fixture | `tools/test-e74-ipproto.sh`, `tools/test_e74_ipproto.py` | Real VirtIO raw-L2 frames; host verifies bytes, not guest markers alone. |

The receive path is the inherited one:

```text
VirtIO rxproc -> etheriq -> native sink qpass(rxq)
  -> ipv6native worker -> ipiput6 -> procxtns -> Fsrcvpcol
  -> t2p[253]->rcv = nativeip6_rcv -> one consumer callback
TX: callback -> nativeip6_send -> ipoput6 -> nativebwrite
  -> ethermediumframe -> ethercore_tx -> VirtIO txproc
```

No `ipmux`, no `f->ipmux`, no new `Fs`/`Dev`/`Chan`, no filter language, no
userspace raw-packet API and no generic IPv6 injector were added.

## 2. Contract summary

- **Registration:** exactly one consumer; second registration `-3`
  (`NativeIp6ErrBusy`); nil net/callback `-1`.
- **Duplicate protocol:** `Fsproto` rejects an occupied `t2p[253]`; the
  wrapper also checks it.
- **Unregister:** clears `t2p[253]`, marks the consumer disabled, waits for an
  in-flight callback, returns `-4` on a repeat unregister. The `Proto` record
  is retained (one bounded record) so a lookup/callback race cannot become a
  use-after-free; re-register reuses it without a second `f->p[]` entry.
- **Receive ownership:** one concatenated `Block`; callback owns it; `m.bp`
  starts at the payload byte; `src`, `dst`, `ifc`, `proto` are explicit.
- **Validation before callback:** `BLEN >= IP6HDR`, version 6, Next Header
  253, declared payload length equals delivered IPv6 payload, payload within
  `IP_MAX`; inherited `ipiput6` already trimmed/rejected bad versions and
  lengths before the Proto call.
- **Send:** fixed to Next Header 253 and a running registered consumer;
  IPv4/IPv4-mapped, unspecified, multicast, non-253, nil/multi-Block and
  over-MTU payloads are rejected. Success consumes the payload; failure
  leaves it to the caller.
- **Context:** callback runs in the native IPv6 worker (process context),
  after `rlock(ifc)`. It is not called from the NIC IRQ sink.

## 3. Actual test evidence

### 3.1 E7.4 build (opt-in only)

```sh
E74_PROBE=1 WHAT=kernel tools/build.sh
# kernel pc64e74
# 1978636 bytes, md5 1148174a6d5193daf85ff73fe560268a
# BUILD-DONE
```

Generated `pc64e74.devc.c` retained full device/architecture/uart entries
(`archgeneric`, `sdiahciifc`, `i8250physuart`, etc.), proving the build name
workaround described below did not truncate the profile.

### 3.2 Real VirtIO fixture

```sh
tools/test-e74-ipproto.sh
```

Actual output:

```text
PASS: absent controller (no IPv6 consumer)
GUEST-LL: fe80::5054:ff:fe12:3456
NDP: NA ok
ICMPv6: echo ok
UDP6: echoed len 0,1,17
IP253: echo ok, no duplicate
NEG: no 253 reply for 254/HBH/version/length/truncated/IPv4
PASS: real VirtIO NDP/ICMP/UDP6/Next Header 253 and negatives
PASS: E7.4 Next Header fixture
```

Guest serial evidence (`build/verification/e74/boot-virtio.log`):

```text
E74IP: CTLR ctlrno=0 name=ether0 ea=525400123456 link=1
E74IP: LLADDR fe80::5054:ff:fe12:3456
E74IP: CHECK reg-nilnet rc=-1
E74IP: CHECK reg-nilcb rc=-1
E74IP: REG rc=0 proto=253
E74IP: CHECK dup-reg rc=-3
E74IP: CHECK udp-open rc=0
E74IP: POSITIVE iprx=1 iptx=1 ipbytes=13 udprx=3 udptx=3
E74IP: CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1
E74IP: NEG-RESULT iprx=2 iptx=2 unhandled=2 badhdr=2
E74IP: CHECK send-big rc=-5
E74IP: CHECK send-v4 rc=-6
E74IP: CHECK send-proto rc=-1
E74IP: CHECK send-nil rc=-1
E74IP: CHECK queue-sat drop=127
E74IP: UNREG-WAIT active=1
E74IP: UNREG rc=0 active=0 registered=0
E74IP: CHECK unreg-twice rc=-4
E74IP: REARM rc=0
E74IP: REARM-OK iprx=4 iptx=3
E74IP: UNREG-FINAL rc=0
E74IP: TXDOWN txdown=1
E74IP: STOP rc=0
E74IP: CHECK repeat-stop rc=-9
E74IP: DONE pass=1 fails=0
```

No-NIC boot (`build/verification/e74/boot-nonic.log`):

```text
E74IP: INIT rc=0 inits=2 probes=89 idempotent=1
E74IP: NODEV n=0
E74IP: DONE pass=1 fails=0
```

### 3.3 What the host verified byte-for-byte

- NDP: valid NA for the guest link-local, target/guest MAC/flags and checksum.
- ICMPv6 Echo Request -> Echo Reply with matching id/seq/payload and checksum.
- UDP6: three datagrams (0, 1, 17-byte payloads) to guest port 20001; replies
  from port 20001 to the host source port with valid UDP6 pseudoheader
  checksums and exact payloads.
- Next Header 253: one request `E74-HELLO-253` -> one reply with the same
  payload, IPv6 version 6, Next Header 253, guest source and host destination;
  a further 0.8 s drain found zero duplicate replies.
- ALIVE `e74-alive` after the negative window -> one 253 reply.
- REARM `e74-rearm` after unregister/re-register -> one 253 reply.
- Negative window: Next Header 254, HBH+253, bad version, payload length
  larger than the frame, L2-truncated IPv6, and Ethernet IPv4 produced no 253
  reply. Guest counters showed `unhandled=2`, `badhdr=2`.
- Unregister with a callback in flight: the host sent `e74-hold` after
  `UNREG-READY`; the guest reported `active=1`, unregister waited and returned
  `rc=0 active=0 registered=0`, and the subsequent re-register echoed.
- Link-down: a 253 frame sent while the native link was down produced no
  reply and incremented `txdown`.

### 3.4 Regression matrix actually run

| Profile | Command | Result |
| --- | --- | --- |
| E7.1 | `ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh` | PASS: native TX/RX, legacy `#l`, NODEV |
| E7.2 | `IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh` | PASS: NA + ICMPv6 Echo + negatives |
| E7.3 | `UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh` | PASS: UDP6 lengths/checksums/races/teardown |
| Default | `WHAT=kernel tools/build.sh && tools/test-qemu.sh` | PASS: kernel up to init0 |
| E5 console | `OCONSOLE=1 WHAT=kernel tools/build.sh` + `tools/cons_migration_check.py` | PASS: 23 Qids, no `cons` Dev |

E7.3.1 behavior is covered by the unchanged E7.3 fixture, which includes the
E7.3.1 race/lifecycle/alloc tests and passed with `in=48 out=10 noports=1
inerrors=5`.

## 4. Known limitations / explicit non-claims

- Experimental 253 only; plaintext test vectors. No authentication,
  encryption, anti-replay, SEALED filtering or userspace tunnel.
- Bare 253 and reassembled fragments reach the consumer. Inherited code does
  not re-demultiplex after a hop-by-hop/routing header, so HBH+253 is safely
  dropped as unknown. No new extension-header parser was added.
- Single consumer, single network instance; `Proto` record retained after
  unregister by design (bounded one-shot allocation, not per-packet).
- Callback runs in one IPv6 worker; a slow callback delays all native IPv6
  receive. The API is kernel C only; there is no userspace raw packet ABI.
- No TCP6, DNS, DHCPv6 or application-service claim is made.
- Physical non-VirtIO NICs were not exercised; the fixture uses the same
  isolated VirtIO dgram transport as E7.1-E7.3.

## 5. Build-name constraint found

The inherited `port/mkdevc` strips indentation from `misc` entries and then
re-tests the stripped line as a possible section header. A `misc` token whose
name contains `dev`, `ip`, `link`, `misc` or `port` ends misc collection and
silently drops later device/architecture objects. For that reason the source
files are named `nativeinh6.c` and `e74nhprobe.c` (no triggering substring),
while the kernel C symbols remain `nativeip6_*` and `e74ipprobe_start`.
This is documented in `docs/E7-NATIVE-IP-PLAN.md` section 6.1.
