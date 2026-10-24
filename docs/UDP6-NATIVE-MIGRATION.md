# Native UDP6 datagram migration map (E7.3)

**Status:** E7.3 source-backed operation map, endpoint contract and evidence.
**Branch:** `design/ipv6-only-native-20261024`.
**Scope:** the first kernel-native UDP-over-IPv6 datagram path on the tested
E7.1/E7.2 NIC/IP path. This is **TRANSITIONAL**: `#I`, `#l`, `#W`, IPv4,
ARP, TCP and legacy UDP file access remain linked in ordinary profiles.

## 1. Layers kept separate

| Layer | E7.3 treatment |
| --- | --- |
| Hardware / VirtIO | Existing `ethervirtio10` reset/attach/IRQ/rings, unchanged. |
| E7.1 Ether | `etheriq`, `ethercore_tx`, `ethercore_rxregister/unregister`, hardened lifecycle. |
| E7.2 IPv6 | `nativev6.c` Fs/Ipifc/medium/worker; `ipiput6`/`ipoput6`; ICMPv6/NDP. |
| UDP protocol | Existing `udpinit`, `udpiput`, `udpkick`, `udpannounce`, `udpctl`, `udpclose`, `Proto`/`Conv`/`Ipht`. |
| Native UDP6 API | `nativeudp6.c`: typed endpoint, one `Qmsg` datagram per receive, explicit send-to. |
| File namespace | `#I` `ipattach`/`devip.c`, `namec`, `Chan`, `#l`/`#W`; **not called** by the native endpoint or echo worker. |

## 2. Operation and ownership matrix

`status` is encoded in the caller/consumer column: `NATIVE(E7.3)`,
`REUSED`, `LEGACY`, or `HARDENED(E7.3)`.

| symbol | exact_source | caller/consumer | context/locking | input/output | Block_ownership | bound_queue | Chan/Netfile_dependency | test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `udpinit` | `ip/udp.c` | `ipfsinit` via `ipprotoinit[]` | process, `Fsproto` | registers Proto 17, `Udppriv`, `Ipht` | none | none | none | REUSED; native `F->t2p[17]` exists |
| `udpcreate` | `ip/udp.c` | `Fsprotoclone` | process | `c->rq=qopen(512K,Qmsg)`, `c->wq=qbypass(udpkick,c)` | queues own Blocks | `c->rq` Qmsg | none | REUSED; endpoint open |
| `Fsprotoclone` | `ip/devip.c` | `udp6_open` | caller `qlock(udp)` | new/reused `Conv`, `Udpcb`, queues | Conv owned by Proto array | `c->rq` | none (no Chan) | REUSED; `open rc=0` |
| `udp->ctl("headers")` | `ip/udp.c` | `udp6_open` | `qlock(c)` via ctl caller | sets `Udpcb.headers=7` | none | none | none | REUSED; single listener, no `Fsnewcall` |
| `udpannounce` | `ip/udp.c` | `udp6_open` after `c->state=Announcing` | process; `setluniqueport` locks Proto | local addr/port -> `Announced`, `srcip`, `iphtadd` | none | `c->rq` | none | REUSED; `open rc=0`, duplicate bind `-6` |
| `Fsstdannounce` / `setladdrport` | `ip/devip.c` | `udpannounce` | Proto lock for port | parses `address!port`, checks `ipforme`, unique port | none | none | none | REUSED; LL bind |
| `setluniqueport` / `lportinuse` | `ip/devip.c` | `setladdrport`, `udp6_open` | `qlock(p)` | duplicate-port check | none | none | none | REUSED + precheck; `dupbind -6` |
| `iphtadd` | `ip/ipaux.c` | `udpannounce` | `lock(ht)` | `Iphash` match: `IPmatchpa` for wildcard peer + local addr/port | none | none | none | REUSED; `iphtlook` matches host peers |
| `iphtlook` | `ip/ipaux.c` | `udpiput` | `lock(ht)` | peer/local tuple -> `Iphash` -> `Conv` | none | none | none | REUSED; multi-peer datagrams reach one endpoint |
| `udpiput` | `ip/udp.c` | `ipiput6` via `f->t2p[17]->rcv` | `qlock(udp)`, then `qlock(c)` | IPv6 UDP packet -> checksum/length -> `Qmsg` envelope -> `qpass(c->rq)` | takes packet; qpass owns; drop frees | `c->rq` | none | REUSED + HARDENED; `POSITIVE`, `InErrors=5`, `NoPorts=1` |
| `qpass(c->rq)` | `port/qio.c` | `udpiput` | `ilock` | one complete datagram | queue owns on success; frees/returns on full | `c->rq` 512K Qmsg | none | REUSED; datagram boundaries |
| `udpkick` | `ip/udp.c` | `c->wq` `qbypass` from `udp6_sendto` | caller process; may call `ipoput6` | headers=7 envelope -> UDP/IPv6 header/checksum -> `ipoput6` | consumes envelope Block; async route may hold/free | none (bypass) | none | REUSED; host bytes, `OutDatagrams=8` |
| `ipoput6` / native medium / `ethercore_tx` | `ip/ipv6.c`, `ip/nativev6.c`, `port/ethercore.c` | `udpkick` | process/worker; route/ARP/NDP locks | UDP6/IPv6 -> Ethernet -> VirtIO TX | core consumes on success; medium frees on error | `Ether.oq` | none | REUSED; host NA/UDP replies |
| `udpclose` | `ip/udp.c` | `closeconv` | `qlock(c)` | `iphtrem`, `qclose(rq/wq/eq)`, reset addr/port | closes queues and frees queued Blocks | `c->rq` | none | REUSED; `close rc=0`, pending sat close |
| `closeconv` | `ip/devip.c` | `udp6_close`, failure rollback | `qlock(c)` | decrement `inuse`; call Proto close at zero | Conv remains allocated for reuse | none | none | REUSED; repeat close `-7` |
| `udp6_open` | `ip/nativeudp6.c` | E7.3 probe | process only; `qlock(udp)`, announce | endpoint create/bind | endpoint owns a Conv reference | `c->rq` Qmsg | none | NATIVE(E7.3); `open rc=0`, v4 `-4`, dup `-6` |
| `udp6_recv` | `ip/nativeudp6.c` | echo worker | process; no lock across qbread | one Qmsg -> payload Block + src/dst/ports | returned Block owned by caller | `c->rq` | none | NATIVE(E7.3); lengths 0/1/17/1452, paired messages |
| `udp6_sendto` | `ip/nativeudp6.c` | echo worker / test | process; endpoint lock across bypass send | payload + peer/port -> 52-byte envelope -> `qbwrite(wq)` | success consumes payload; failure leaves it | none (bypass) | none | NATIVE(E7.3); host checksum/ports/payload |
| `udp6_close` | `ip/nativeudp6.c` | probe / echo teardown | process; endpoint lock + wait | closed flag, wake, `closeconv`, wait `recvactive==0` | frees queued Blocks through qio | `c->rq` | none | NATIVE(E7.3); close/repeat/post-close tests |
| `udp6_stats` / `udp6_pending` | `ip/nativeudp6.c` | probe | read-only snapshot | endpoint counters/pending bytes | none | `c->rq` | none | NATIVE(E7.3); saturation evidence |
| `Udpstats.udpDropFull` | `ip/udp.c` | `udpiput` qfull branch | `qlock(c)` | dropped datagram counter | dropped Block freed | `c->rq` | none | HARDENED(E7.3); `DropFull=14` |
| `ipattach` / `devip.c` | `ip/devip.c` | `#I` legacy | Chan/devattach | file namespace over Fs | legacy | legacy | `Chan`/`Qid` | LEGACY; not used on native path |
| `udpconnect` / `Fsstdconnect` / `Fsnewcall` | `ip/udp.c`, `ip/devip.c` | legacy `#I` connected/Announce headers=0 | legacy | connected UDP / child Conv per peer | legacy | `c->rq` | none directly, called from Chan ops | LEGACY; **not used** by `headers=7` endpoint |
| `ethermedium.c` `etherbind`/`etherbwrite`/`etherread6` | `ip/ethermedium.c` | legacy `#I`/`#l` | legacy | `namec`/`chandial`/`devtab[bwrite]` | legacy | `Netfile` | `Chan`/`Netfile` | LEGACY; not used |
| `wglisten`/`wgreader` | `ip/devwg.c` | `#W` | legacy | `namec("/net/udp/clone")`, Chan | legacy | Chan | `Chan` | LEGACY; future WG outer UDP6, not E7.3 |

## 3. RX/TX graph

```text
host UDP6 frame -> VirtIO rxproc -> etheriq
  -> native sink (0x86DD, own/mcast MAC, bounded qpass)
  -> ipv6native worker -> ipiput6
     -> udpiput (existing UDP Proto)
        -> checksum/length/zero-checksum checks
        -> iphtlook: one Announced Conv with headers=7
        -> 52-byte envelope (src,laddr,ifc,rport,lport)
        -> qpass(c->rq Qmsg)

echo worker -> udp6_recv
  -> qbread one Qmsg -> envelope parse -> complete payload Block + peer metadata
  -> udp6_sendto
     -> 52-byte envelope + payload -> qbwrite(c->wq)
     -> qbypass -> udpkick (existing UDPv6 checksum/output)
     -> ipoput6 -> native Medium.bwrite -> ethermediumframe
     -> ethercore_tx -> VirtIO txproc -> host
```

## 4. Conv state transitions

```text
Idle
  --udp6_open: Fsprotoclone--> Announcing
  --udpannounce/Fsconnected--> Announced (iphtadd: local addr+port)
  --udpiput (headers=7)--> qpass one Qmsg per datagram
  --udp6_sendto--> wq qbypass -> udpkick
  --udp6_close/closeconv/udpclose--> iphtrem, qclose(rq/wq/eq) -> Idle
```

`headers==0` on an `Announced` Conv causes the inherited `Fsnewcall`
child-Conv path. E7.3 sets `headers=7`, so a single listener receives all
source peers/ports and no per-datagram Conv is allocated.

## 5. Public kernel C contract

`nativeudp6.h` is kernel C only; it is not a userspace socket/fd/Handle/OID
API.

- `udp6_open(Ipv6Native*, uchar local[16], ushort port, Udp6Endpoint **out)`
  - process context; IPv6 unicast local address, nonzero port;
  - returns typed error (`Udp6ErrFamily`, `Udp6ErrInUse`, `Udp6ErrBind`,
    ...); no Chan.
- `udp6_recv(ep, Udp6Msg *msg, ulong timeout_ms)`
  - one complete `Qmsg` datagram per call; zero-length payload preserved;
  - returns payload as a caller-owned `Block` after the 52-byte envelope;
  - `msg` carries source/destination IPv6 and UDP ports;
  - timeout/closed/error distinct; a blocked receive wakes on close.
- `udp6_sendto(ep, peer[16], peerport, Block *payload)`
  - explicit IPv6 peer/port, no implicit routing/path lookup;
  - success consumes `payload`; failure leaves it to the caller;
  - builds the existing `headers=7` envelope and uses `qbwrite(wq)` ->
    inherited `udpkick`; a positive result means "accepted for delivery",
    not a NIC completion proof;
  - rejects IPv4/IPv4-mapped addresses, zero port, lists, and payloads larger
    than the interface's non-fragmenting IPv6/UDP maximum.
- `udp6_close(ep)`
  - sets closed under the endpoint lock, wakes receivers, calls `closeconv`
    (qclose wakes blocked reads), waits for in-flight receives; repeat close
    returns `Udp6ErrClosed`;
  - no send/receive succeeds after close.
- `udp6_stats`, `udp6_pending`, `udp6_setlimit` are observability/test
  helpers; they do not change protocol semantics.

## 6. E7.3 hardening and lifecycle

- `udpiput` V6 now rejects `UDP length < 8`, `UDP length > delivered IPv6
  payload`, and zero UDP checksum before checksum processing. IPv4 semantics
  are unchanged.
- `Udpstats.udpDropFull` counts `qfull` drops; exposed in UDP stats text.
- `ipv6native_start`: one-shot terminal state on failure; `Fs` is not freed
  because inherited ARP/IP kprocs may reference it. A failed/stopped instance
  remains reachable so restart returns a deterministic `EtherErrBusy`
  instead of allocating another stack.
- `ipv6native_stop`: RUNNING -> STOPPING -> STOPPED; unregister sink, close
  RX queue, wake worker, wait for actual worker exit; timeout returns
  `EtherErrBusy` and leaves state STOPPING. `nativeone` is retained for a
  terminal one-shot; a restart after STOPPED is rejected.
- UDP endpoints must close before the IPv6 medium/Fs teardown. The probe does
  this and verifies echo-worker exit.

## 7. Still legacy / later work

- `#I` UDP4/UDP6 file semantics, `udpconnect`, headers=0 child Convs, TCP,
  IPv4/ARP, `#l` and `#W` remain linked in ordinary profiles.
- No userspace networking ABI, socket/fd/Handle, MicroPython `socket`, or
  WireGuard implementation was added. WireGuard outer UDP6 is a later
  consumer of this endpoint shape.
- Final `#I/#l/#W` removal, IPv4/ARP executable exclusion, native TCP6 and
  native IPv6-only linkage remain later gates.
