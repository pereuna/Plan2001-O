# Native Ethernet-to-IPv6 migration map (E7.2)

**Status:** E7.2 source-backed audit, implementation record and evidence.
**Branch:** `design/ipv6-only-native-20261024`.
**Scope:** the first real native IPv6 receive/response slice over VirtIO.
This is **TRANSITIONAL**: legacy `#l`, `#I`, `#W`, IPv4, ARP, UDP and TCP
remain linked in ordinary profiles. It is not an IPv6-only kernel claim.

## 1. Four separate layers

| Layer | E7.2 treatment |
| --- | --- |
| Hardware / VirtIO | Existing `ethervirtio10` reset/attach/IRQ/rings unchanged. |
| E7.1 Ether core | `ethercore_attach/tx/rxregister/rxunregister/etheriq`; hardened in E7.2.1. |
| IP packet logic | Reused `Fs`, `Ipifc`, `Proto`, `v6lookup`, `ipiput6`, `ipoput6`, `icmp6`, NDP and ARP cache. |
| File/namespace policy | Legacy `ipattach`, `devip.c`, `ethermedium.c` channel code, `#l`/`#I`/`#W`; not used by the native slice. |

The native slice never calls `namec`, `chandial`, `devtab[...]->bread/bwrite`,
`ipattach`, `etherbind`, `etherread4/6` or `wglisten`.

## 2. Operation map

`Chan_or_Netfile_edge` is `none` only for the executed function body and its
native callees. A `Netif` field embedded in `Ether` is not itself a Chan edge;
`netifinit` allocating `Netif.f` is legacy state but not a native frame
operation.

| symbol | source | callers | required_state | init_owner | call_context/locking | Block_ownership | Chan_or_Netfile_edge | native_reuse | test_evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ethercore_attach` | `port/ethercore.c` | E7.2 probe, legacy `#l` | registry entry; `Ether.attach` may sleep | core | process context; per-controller `QLock`; `attached=1` only after driver attach | none | none | E7.1 core, hardened | `ATTACH`/`repeat-attach rc=0`, E7.1 fixture |
| `ethercore_tx` | `port/ethercore.c` | native medium, E7.1 probe | attached, link up, `oq`, MTU | core | process context; `qpasstry` atomic capacity+insert | success consumes; failure leaves caller block | none | E7.1 core, hardened | host NA/Echo frames; E7.1 TX |
| `ethercore_rxregister/rxunregister` | `port/ethercore.c` | E7.2 start/stop | process context; no IRQ sleeping | core | `rxlock`; unregister waits for `rxactive==0` via `tsleep` | caller owns `arg` until unregister returns | none | E7.1 core, hardened | `STOP rc=0`, `repeat-stop rc=-9` |
| `etheriq` | `port/ethercore.c` | VirtIO `rxproc` | registered Ether; optional sink | core | driver RX context (worker or IRQ); copy + sink; legacy original | copy to sink; original to legacy | calls `etherlegacyrx` for compatibility only | E7.1 core | real NS/Echo RX; `POSITIVE rx=2` |
| `etherlegacyrx` | `port/devether.c` | `etheriq` | legacy `Netfile` state | legacy | RX context; existing mux | legacy | `ethermux`/`Netfile.f[]` | retained, not used by native IP | marked legacy linkage |
| `ipfsinit` | `ip/devip.c` | `ipattach`, `ipv6native_start` | process context, `up` | IP | `smalloc` Fs; no Chan | none | none (extracted from `ipattach`) | shared Fs initializer | `INIT`/`START` markers |
| `ipattach` | `ip/devip.c` | `#I` attach | legacy `ipfs[dev]==nil` | legacy | process, `QLock` | none | Chan/devattach | thin wrapper over `ipfsinit` | default kernel boot; source |
| `ip_init` / `ip_init_6` | `ip/ip.c`, `ip/ipv6.c` | `ipfsinit` | zeroed Fs | IP | process | fragments pools | none | reused | `START` |
| `arpinit` | `ip/arp.c` | `ipfsinit` | process, scheduler for `rxmitproc` | IP | starts kproc; `Arp` lock | none | none | reused for NDP cache/retransmit | NA/Echo works |
| `netloginit` | `ip/netlog.c` | `ipfsinit` | zeroed Fs | IP | process | ring buffer | none | reused | compile/runtime |
| `ipifcinit` | `ip/ipifc.c` | `ipfsinit` via `ipprotoinit[]` | zeroed Fs | IP | process | `Proto`, `f->self` | none | reused | `Fsprotoclone` succeeds |
| `icmp6init` | `ip/icmp6.c` | `ipfsinit` via `ipprotoinit[]` | `f->ipifc` | IP | process | `Proto`, `Icmppriv6` | none | reused for NS/NA/Echo | real NA/Echo |
| `Fsproto` | `ip/devip.c` | every `*init` | process | IP | no blocking lock | `Proto.conv` | none | reused | compile/runtime |
| `Fsprotoclone` | `ip/devip.c` | `ipv6native_start` | `f->ipifc` locked; process | IP | caller `qlock(f->ipifc)`; creates Conv | `Conv`, `Ipifc` | none (no Chan) | reused | `START` |
| `ipifccreate` | `ip/ipifc.c` | `Fsprotoclone` | Proto ptclsize | IP | allocation | `rq/wq/sq`, `Ipifc` | none | reused | `START` |
| `ipifcadd` | `ip/ipifc.c` | `ipv6native_start` | bound `ifc->m`; process | IP | ifc wlock; adds routes/self | none | none | reused | `LLADDR`, NS works |
| `addselfcache` / `addroute` | `ip/ipifc.c`, `ip/iproute.c` | `ipifcadd` | `f->self`, `f->ip`, `ifc->m` | IP | `self`/`routelock` | routes | none | reused | NS `ipforme`, Echo route |
| `ipforme` / `v6lookup` | `ip/ipifc.c`, `ip/iproute.c` | `ipiput6`, `ipoput6` | self/routing tables | IP | `self`/`routelock` as existing | none | none | reused | NA/Echo delivered |
| `ipiput6` | `ip/ipv6.c` | native worker (and legacy `etherread6`) | `ifc->lifc`, `f->ip/t2p` | IP | worker `rlock(ifc)`; consumes Block | takes ownership | none on native path | reused packet logic | `POSITIVE rx=2`, real NA/Echo |
| `ipoput6` | `ip/ipv6.c` | `icmpna6`, `icmpiput6`, `icmpns6`, IP | route/self/ifc | IP | `rlock(ifc)`; calls medium | takes ownership | none on native path | reused packet logic | host NA/Echo reply |
| `ipifcoput` | `ip/ipifc.c` | `ipoput6` | `ifc->m` | IP | `ifc->out`; shaping disabled (`speed=0`) | passes to `m->bwrite` | none | reused | host frames |
| `icmpiput6` / `valid` | `ip/icmp6.c` | `ipiput6` via `f->t2p[58]` | `icmp6` Proto | IP | worker; consumes Block | takes ownership | none | reused NS/NA/Echo/validation | NA flags, Echo ID/seq |
| `icmpna6` / `icmpns6` | `ip/icmp6.c` | NS/NA handling, NDP | `f->t2p[ICMPv6]` | IP | process/worker; builds ICMP + `ipoput6` | new Block, `ipoput6` owns | none | reused NDP | real NA; host verifies |
| `mkechoreply6` | `ip/icmp6.c` | `icmpiput6` Echo | valid Echo Request | IP | worker; reuses Block | `ipoput6` owns | none | reused | real Echo Reply |
| `arpget` / `arpenter` / `ndpsendsol` | `ip/arp.c` | `ethermediumframe`, `icmpiput6` | `f->arp`, `ifc->m` | IP | Arp lock; process/worker | holds/passes Blocks | none | reused NDP cache | NA cache; Echo route |
| `ethermediumframe` | `ip/ethermedium.c` | legacy `etherbwrite`, native `nativebwrite` | `f->arp`, `ifc`, MAC/MTU | IP adapter | medium `bwrite` context; `padblock`/NDP | returns frame or nil (queued/hold) | legacy V4 solicitation only; V6 none | shared framing helper | NA/Echo frames |
| `nativebwrite` | `ip/nativev6.c` | `ipifcoput` via native Medium | `ni`, `Ether`, link up | E7.2 adapter | process/worker; no Chan; `ethercore_tx` | `ipoput6` owns; core consumes on success, medium frees on error | none | new typed adapter | host NA/Echo; `TXDOWN n=1` |
| `ipv6native_etherinput` | `ip/nativev6.c` | `ethercore` RX sink | queue ready | E7.2 adapter | IRQ/driver worker; cheap L2 checks + `qpass` | copy owned by queue; drops free | none | new fixed-purpose sink | real host NS/Echo |
| native worker | `ip/nativev6.c` | `kproc` | `Ifc`/Fs ready; process | E7.2 adapter | process; `qbread`, `rlock(ifc)`, `ipiput6` | owns dequeued Block | none | new fixed-purpose worker | `POSITIVE rx=2` |
| `qpass` / `qpasstry` | `port/qio.c` | sink / `ethercore_tx` | Queue | core/qio | `ilock`; no sleeping | qpass frees on drop; qpasstry leaves caller owner | none | reused qio | queue saturation/full |
| `etherbind`/`etherbwrite`/`etherread4/6` | `ip/ethermedium.c` | legacy `#l`/`#I` | legacy `Etherrock`, Chans | legacy | kprocs/process | legacy | `namec`/`chandial`/`devtab[Chan]` | **not used** by native slice | E7.1 legacy `#l` test |
| `wglisten` / `wgreader` | `ip/devwg.c` | `#W` | legacy | legacy | process/kproc | legacy | `namec("/net/udp/clone")`, Chan | **not used** | source audit only |

## 3. RX/TX call graph (native slice)

```text
VirtIO rxproc
  -> etheriq(Ether*, Block*)
     -> native sink: L2 length/type/dest checks, qpass -> bounded Queue
     -> original Block -> etherlegacyrx -> ethermux/Netfile (legacy, separate)
  -> ipv6native worker (process context)
     -> strip 14-byte Ethernet header exactly once
     -> rlock(ifc); ipiput6(f, ifc, Block*); runlock(ifc)
        -> ipforme/v6lookup -> icmpiput6 -> NS/NA or Echo Reply
           -> ipoput6 -> native Medium.bwrite
              -> ethermediumframe (arpget/NDP, pad, EtherType 0x86DD)
              -> ethercore_tx(Block*) -> qpasstry -> VirtIO txproc -> host
```

Legacy compatibility still runs in parallel: `etheriq` gives the original
frame to `etherlegacyrx` for `#l`/`Netfile` consumers. In the E7.2 test
profile no `#l` IPv6 data subscription is opened, so legacy does not
duplicate the native IPv6 response. The legacy adapter remains linked and is
called for every frame.

## 4. Legacy dependencies and separation

- `netifinit` is still called by E7.1 `etherprobe` to allocate `Netif` state
  for legacy `#l`/ip. The native slice does not call `netif*` file helpers.
- `etheriq` still calls `etherlegacyrx`; therefore `ethercore.c` is **not**
  independent of `devether.c` yet. E7.2 does not claim otherwise.
- `ethermediumframe` is shared with the legacy `etherbwrite`; for V4 its
  solicitation still uses legacy `Etherrock` channels. Native IPv6 never
  passes V4 to it.
- The native Fs is initialized by `ipfsinit`, the same code path used by
  `ipattach`; `ipattach` is now a thin wrapper. No `Fs` or `Proto` is
  duplicated on repeated native start (`EtherErrBusy`).
- `#I` file policy (`devip.c` walk/open/read/write/ctl), `etherbind`'s
  `namec/chandial`, and `#W` `wglisten` remain untouched and are not used on
  the demonstrated native chain.

## 5. E7.2.1 lifecycle/ownership repairs

| E7.1 issue | E7.2 change | Evidence / residual |
| --- | --- | --- |
| `attached=1` published before `Ether.attach` completed | per-controller `QLock` held across attach; state published only after success; second caller waits and returns Ok | `repeat-attach rc=0`; E7.1 fixture |
| `qfull` then `qpassnolim` not atomic | new `qpasstry()` checks capacity and inserts under the same Queue lock; returns -1 closed / -2 full without freeing; native TX frees its private copy on error | `txq-full rc=-2`, `txq-closed rc=-1`; host TX still works |
| RX unregister could race an in-flight sink | `rxactive`/`rxunregistering` + `Rendez`; unregister clears sink then waits in process context for in-flight callbacks; IRQ path never sleeps | `STOP rc=0`; repeat stop `-9`; worker exited |
| explicit probe occupied-slot race/leak | `ethercore_init` and `ethercore_probe_at` serialized by `coreqlock`; no probe of an occupied slot, so no partial controller is freed | source review; E7.1 `INIT idempotent=1` |
| E7.1 full-queue test swapped live `e->oq` | replaced by isolated `qpasstry` on a private Queue; real VirtIO TX/RX correlation retained | `queue-unit`, `queue-full`, `queue-closed`; E7.1 fixture |

## 6. Proof constraints and negatives

Positive evidence is host-verified bytes, not a log grep alone:

- valid ICMPv6 NS (Hop Limit 255, SLLA) -> NA with target/guest MAC/flags and
  valid pseudoheader checksum;
- valid Echo Request (unique ID/seq/payload) -> Echo Reply with matching
  fields and valid checksum;
- guest `POSITIVE rx=2 tx=2`, `CHAN-NATIVE ... clean=1`.

Negative cases exercised:

- no NIC: `NODEV n=0`, no panic;
- EtherType `0x0800` not consumed by native IPv6 (`other=1`);
- L2-truncated frame rejected by the native sink (`bad=1`);
- bad ICMPv6 checksum, bad NDP Hop Limit, bad IPv6 version, bad IPv6 payload
  length and non-local destination produce no NA/Echo Reply;
- native RX queue saturation (`drop=127`);
- TX link down (`TXDOWN n=1`); TX full/closed via `qpasstry` (`-2`/`-1`);
- repeat start (`-7`) and repeated stop (`-9`); worker exits (`worker_exited=1`).

## 7. Later cutover dependencies (not E7.2)

1. Native IPv6-only IP core with complete ICMPv6/NDP and an IPv4-negative
   connection test.
2. Native UDP6/TCP6 connection management with explicit `Stream` vs
   datagram `Message` semantics; userspace ABI remains `OPEN`.
3. Native WireGuard with IPv6-only outer UDP and inner IPv6 packets.
4. An O-only configuration removing `etherdevtab`, `ipdevtab` and `wgdevtab`.
5. Executable IPv4/ARP exclusion without breaking shared IP-version-neutral C
   code.
6. Removal of the `etherlegacyrx` compatibility call and the legacy
   `netifinit` allocation only after legacy `#l` acceptance is retired.
