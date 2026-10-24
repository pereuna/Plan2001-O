# E7.3 completion report — native UDP6 datagrams on the E7 path

VERDICT: APPROVE

BRANCH / HEAD / COMMITS:
- repo: `pereuna/Plan2001-O`
- branch: `design/ipv6-only-native-20261024`
- upstream: `origin/design/ipv6-only-native-20261024`
- E7.3 work started at `7addc29` (after restoring the shared general review file from an automation summary) on top of `272e8d8`.
- commits: `c3edcc5` (E7.3.0 map), `3c1f88b` (E7.3.1 lifecycle/hardening), `936ca55` (E7.3.2 native UDP6 API), `a55c5b5` (E7.3.3 fixture), plus this E7.3.4 report commit.
- `main` was not checked out, merged, rebased, committed to or pushed; PR #1 was not merged; the mistaken `design/e72-native-ipv6-20261024` branch was not touched.

UDP6 CALL GRAPH & CONV STATE:
```text
host UDP6 frame -> VirtIO rxproc -> etheriq
  -> E7.2 native sink/worker -> ipiput6 -> existing udpiput
     -> checksum/length/zero-checksum validation
     -> iphtlook: one Announced Conv, headers=7
     -> 52-byte envelope (src,laddr,ifcaddr,sport,dport) -> qpass(c->rq Qmsg)

echo worker -> udp6_recv -> one complete datagram + peer/local metadata
  -> udp6_sendto -> 52-byte envelope + payload -> qbwrite(c->wq)
  -> qbypass -> existing udpkick (UDPv6 checksum) -> ipoput6
  -> E7.2 native medium -> ethercore_tx -> VirtIO TX -> host
```
Conv states: `Idle -> Announcing -> Announced` (`Fsprotoclone`, explicit
`c->state=Announcing`, `udpannounce`/`Fsconnected`, `iphtadd` with
`IPmatchpa`), `Announced -> Idle` on `udp6_close`/`closeconv`/`udpclose`
(`iphtrem`, `qclose rq/wq/eq`). `headers=7` avoids the `Fsnewcall` child
path; one listener receives every source peer/port. Details:
`docs/UDP6-NATIVE-MIGRATION.md`.

PUBLIC KERNEL C CONTRACT / MESSAGE OWNERSHIP:
- `udp6_open(Ipv6Native*, local[16], port, Udp6Endpoint**)`: process context,
  IPv6 unicast only, nonzero port, duplicate-port rejection, no Chan.
- `udp6_recv(ep, Udp6Msg*, timeout_ms)`: one `Qmsg` datagram per call;
  zero-length payload preserved; returns a caller-owned payload `Block` plus
  source/destination IPv6 and UDP ports; timeout/closed/error are distinct.
- `udp6_sendto(ep, peer[16], peerport, Block*)`: explicit peer; success
  consumes the payload, failure leaves it to the caller; uses the inherited
  `udpkick` path. A positive result is “accepted for delivery”, not a NIC
  completion claim.
- `udp6_close`: sets closed, wakes blocked receives, `closeconv` qcloses the
  queues, waits for in-flight receives; repeat close `Udp6ErrClosed`; no
  send/receive after close.
- This is kernel C only, not a userspace socket/fd/Handle/OID ABI.

E7.2 LIFECYCLE FIXES:
- `ipv6native_start`: one-shot terminal `NvFailed`/`NvStopped` state; Fs is
  not freed because inherited ARP/IP kprocs may reference it; restart after
  failure/stop returns `EtherErrBusy` instead of leaking another stack.
- `ipv6native_stop`: `RUNNING -> STOPPING -> STOPPED`; unregister RxSink,
  qclose RX queue, wake worker, wait for actual exit. A timeout returns
  `EtherErrBusy` and leaves STOPPING; `nativeone` is retained.
- UDP endpoints must close before IPv6/Fs teardown. Probe order is endpoint
  close/echo exit, then `ipv6native_stop`.
- `udpiput` V6 hardening: reject UDP length `< 8`, UDP length beyond the
  delivered IPv6 payload, and zero UDP checksum. IPv4 semantics unchanged.
- `Udpstats.udpDropFull` counts `qfull` drops and appears in UDP stats.
- E7.1/E7.2 packet-path meaning is unchanged; both fixtures still pass.

HOST-VERIFIED RX/TX PACKETS:
Same real QEMU/VirtIO guest:
- valid NS -> valid NA (E7.3 reuses E7.2 ND);
- six UDP6 requests from source ports 40001–40006, including two sent
  back-to-back, with payload lengths `0`, `1`, `17`, `1452` and two 8-byte
  paired messages;
- host validated every reply’s Ethernet/IPv6/UDP source/destination, UDP
  source port `20001`, host destination port, UDP length, nonzero UDP6
  pseudoheader checksum and exact unchanged payload;
- guest: `POSITIVE rx=6 tx=6 bytes=1486`; `OutDatagrams=8` (6 positive +
  alive + link-down attempt).

NEGATIVES:
- no NIC: `NODEV n=0`, DONE, no UDP service or panic;
- UDP bad checksum, zero checksum, UDP length 4, UDP length too long,
  truncated header: no echo; UDP stats `InErrors=5`;
- valid datagram to unbound port 20009: no echo, host observed and validated
  an ICMPv6 Port Unreachable; `NoPorts=1`;
- IPv4 EtherType frame: no UDP dispatch and no reply;
- duplicate bind on 20001: `CHECK dupbind rc=-6`;
- IPv4-mapped local address: `CHECK v4-open rc=-4`;
- RX queue saturation on unread 20002 with limit 1000:
  `SAT pending=342`, `CHECK sat-dropfull=14`, no echo;
- link down: host request gets no echo, `TXDOWN txdown=1`; UDP send is
  `accepted` but the native medium drops it;
- close with pending datagrams: `sat-close rc=0`; main close wakes echo
  worker (`ECHO-EXIT exited=1`); repeat close `-7`; post-close recv/send
  `-7`/`-7`; stop `0`, repeat stop `-9`, restart after stop `-7`.
- Host failed closed on unexpected UDP echoes/wrong ports/payload/checksum
  and on guest panic/fault.

CHAN COUNTERS:
- Snapshot before native IPv6 start through bind, receive, echo replies:
  `CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1`.
- Counters are supplemental; host-verified bytes and UDP stats are primary.

LEGACY AND E7.1/E7.2 REGRESSIONS:
- E7.2 fixture: PASS (`NDP NA + ICMPv6 Echo Reply + negatives`).
- E7.1 fixture: PASS (real VirtIO L2 TX/RX and legacy `#l` data read).
- default `9pc64` + `9pc64mp` build and `tools/test-qemu.sh`: PASS.
- E5 `9pc64oconsole` build and cons check: PASS, 23 Qids, no `consdevtab`.
- Legacy `#I` UDP4/UDP6, `udpconnect`, headers=0 `Fsnewcall`, TCP, IPv4/ARP,
  `#l` and `#W` remain linked and unchanged in ordinary profiles.

COMMANDS / ACTUAL OBSERVED OUTPUTS:
```sh
UDP6_PROBE=1 WHAT=kernel tools/build.sh   # BUILD-DONE, 9pc64e73 2081839 bytes
tools/test-e73-udp6.sh
# PASS: absent controller (no UDP service)
# GUEST-LL: fe80::5054:ff:fe12:3456
# NDP: NA ok
# POSITIVE: lengths 0,1,17,1452 and paired messages
# NEG: no UDP echo; port-unreachable=True
# COUNTERS: in=34 out=8 noports=1 inerrors=5
# PASS: real VirtIO UDP6 datagrams, checksums and negatives
# PASS: E7.3 UDP6 fixture

IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh   # PASS
ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh # PASS
WHAT=kernel tools/build.sh && tools/test-qemu.sh                    # PASS
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole \
  --devc build/amd64/pc64oconsole.devc.c                           # PASS
```
Guest markers also observed: `CHECK open rc=0`, `v4-open=-4`, `dupbind=-6`,
`open-sat=0`, `CHECK sat-dropfull=14`, `CHECK sat-close=0`, `TXDOWN=1`,
`CLOSE=0`, `ECHO-EXIT=1`, `repeat-close=-7`, `post-close-recv=-7`,
`post-close-send=-7`, `STOP=0`, `repeat-stop=-9`, `restart-after-stop=-7`,
`INIT idempotent=1`, `DONE pass=1 fails=0`.

LOCAL LOG PATHS (ignored, not in Git):
- `build/verification/e73/build-e73.log`, `test-e73.log`
- `build/verification/e73/boot-virtio.log`, `serial-virtio.log`
- `build/verification/e73/boot-nonic.log`, `serial-nonic.log`
- `build/verification/e73/build-e72.log`, `test-e72.log`
- `build/verification/e73/build-e71.log`, `test-e71.log`
- `build/verification/e73/build-default.log`, `test-default.log`
- `build/verification/e73/build-oconsole.log`, `test-oconsole.log`

NOT RUN / OPEN:
- no E6/E8/E9 integration, no merge/rebase of `main`;
- no native UDP4, TCP6, TLS, DNS/DHCPv6, routing daemon, userspace socket or
  MicroPython `socket`, no WireGuard implementation;
- no final `#I/#l/#W`/IPv4 removal or IPv6-only-linkage claim; no physical NIC;
- `ipv6native_start` failure paths after Fs allocation are terminal rather
  than destructively freed; failure injection was not attempted;
- production multicast filtering is not done: the test NATIVE medium enables
  promiscuous reception; `addmulti` is a no-op;
- `udp6_sendto` reports acceptance; actual hardware completion is proven by
  host bytes, not a NIC completion counter;
- UDP TX has no queue of its own (`qbypass`). Link-down is tested against the
  real NIC; full/closed queue primitives are covered by E7.1/E7.2 `qpasstry`
  tests, not presented as a UDP queue.

E6/E8 INTEGRATION CONFLICTS:
- `origin/main` now contains E6/E8/E9 work (`pc64onativedisk`, `sdcore`,
  Dev pruning, OMAP regeneration, later E9 assignment).
- Both sides change `sys/src/9/pc64/main.c`, `sys/src/9/pc64/mkfile`,
  `tools/build.sh`; main also changes `sys/src/9/port/mkdevc`,
  `docs/STATUS.md`, `docs/KERNEL-API-ABI.md`.
- Expected conflicts: `main.c` handoff chain, `pc64/mkfile` `CONFLIST`,
  `tools/build.sh` opt-in profile dispatch, and generated Dev/OMAP files.
  E8’s pruned `pc64onativedisk` intentionally differs from E7’s transitional
  ordinary profiles. No integration was attempted while E8/E9 are active.
- Later gate: clean review branch; reconcile dispatch/config, then rerun E6
  O-server, E8 pruned profile, E9 work, default/E5, E7.1, E7.2 and E7.3.
