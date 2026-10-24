# Ethernet migration map (E7.1)

**Status:** E7.1 source-backed operation map and design record.
**Branch:** `design/ipv6-only-native-20261024`.
**Scope:** the inherited `#l` Ethernet adapter, the new native Ethernet C core,
and the exact remaining `#I`/UDP/TCP/`#W` boundaries. This document does
**not** claim that the running kernel is IPv6-only. The current kernels are
**TRANSITIONAL**: they still link `etherdevtab`, `ipdevtab`, `wgdevtab`,
IPv4 packet code and ARP.

**Status vocabulary:** `EXISTING` = inherited source inspected here;
`NATIVE(E7.1)` = added/verified in this task; `LEGACY` = retained for
compatibility, not the native boundary; `OPEN` = unresolved, not implemented.

## 1. Audit gate: four things that must not be conflated

| Class | E7.1 treatment |
| --- | --- |
| (a) concrete native frame operations | `ethercore.c`: controller registry/init, lookup, attach, `Block` TX, RX sink dispatch. No `Chan`/`Qid`/`Dirtab`/`Netfile` in the executed native path. |
| (b) legacy multiplexer policy | `devether.c`/`netif.c`: `ethermux`, `Netfile.f[]`, promiscuous/multicast/bridge/bypass, `etherwrite`/`etherbwrite`, `netif*` file operations. Preserved unchanged in behaviour. |
| (c) IP-specific processing | `sys/src/9/ip/*`: IPv4/IPv6/ARP/NDP/UDP/TCP and `ethermedium.c`. Audited only; not rewritten in E7.1. |
| (d) hardware controller operations | `ether->attach/transmit/ctl/shutdown`, driver reset/probe callbacks, DMA rings, IRQs. Reused through their existing function-pointer semantics. |

A function whose signature has no `Chan*` is not automatically native. For
example `ethermux(Ether*, Block*, Netfile**)` is legacy policy, and
`etheroq` still carries a `Netfile` identity. Conversely `etheriq` is a
hardware RX entry but reaches `Netfile` through the retained adapter; E7.1
adds a separate native sink before that legacy delivery.

## 2. Operation map

`Chan_or_Netfile_edge` is `none` only when the *executed* function body and
its callees in that path contain no `Chan`, `Qid`, `Dirtab`, `Netfile`, `walk`,
`namec` or `Dev` file dispatch. A `Netif` field embedded in `Ether` is not by
itself a `Chan` edge; the file helpers in `netif.c` are.

| symbol | source | current_callers | semantic_owner | input/output | allocation_ownership | call_context/locking | Chan_or_Netfile_edge | E7.1_target | legacy_compatibility | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `addethercard` | `port/ethercore.c` | generated `links()` via `ether*link()` | core controller registry | `(type, reset fn)` -> `cards[]` | static table, strings owned by drivers | boot, single-threaded before `chandevreset` | none | NATIVE(E7.1): owns registry | unchanged registration calls | `9pc64`/`9pc64e71` link; `NODEV` boot |
| `cards[]`, `etherxx[]` | `port/ethercore.c` | core only | core registry | static arrays | `Ether` allocated by `etherprobe`, never freed in E7.1 | core `Lock` around init/table writes; lookups read | none | NATIVE(E7.1): stable lookup by ctlrno/index/name | no external users | `ethercore_lookup/byindex/byname` |
| `etherprobe` | `port/ethercore.c` | `ethercore_init`, `ethercore_probe_at` | core controller discovery | config/conf -> `Ether*`; calls `cards[].reset`; allocates `oq`, `Netif` | `malloc(sizeof(Ether))`; output queue `qopen`; `netifinit` allocates `Netif.f` | boot or legacy explicit attach; no attach here | none at probe; `netifinit` allocates legacy state but does not use `Chan` | NATIVE(E7.1): single probe/reset per controller | same card reset semantics, print format, `ea=`, `*noetherprobe` | `INIT probes=90`, `idempotent=1` |
| `ethercore_init` | `port/ethercore.c:199` | `etherreset` (boot); E7.1 probe | core lifecycle | `()` -> controller count or negative error | none directly; calls `etherprobe` | boot `chandevreset`, single-threaded; probe re-call is a no-op | none | NATIVE(E7.1): exactly-once reset/probe | replaces old `etherreset` scan body | `INIT inits=2 probes=90 idempotent=1` |
| `ethercore_probe_at` | `port/ethercore.c` | `etherattach` spec `N:conf` | core registry extension | `(ctlrno, conf)` -> `Ether*`/nil | same as `etherprobe` | process context, privileged legacy attach | none | NATIVE(E7.1): explicit error on occupied/invalid slot | preserves `iseve`/`Einuse` checks in adapter | source review |
| `etherattach` | `port/devether.c:43` | `namec("#l...")` legacy only | legacy `#l` adapter | spec -> `Chan*`; calls lookup + `ethercore_attach` | `devattach` Chan | process context | Chan/Qid/Dev attach | LEGACY: retained, delegates hardware to core | same spec parsing, permissions, `Einuse`, `devattach` | legacy `#l` RX test |
| `Ether.attach` | driver (`ethervirtio10.c:398`, `ether8169.c:828`, `ether82563.c:1501`, `etheri225.c:1075`, `etheriwl.c:4066`, `ethersink.c:35`) | `ethercore_attach` | hardware controller | `Ether*` -> void; enables rings/queues/IRQ workers | driver-owned DMA/ring memory | process context; VirtIO starts `kproc`s | none | NATIVE(E7.1): exactly once, after scheduler/`up` | drivers idempotent; legacy attach now routes through core | `ATTACH rc=0`; `#l` test |
| `Ether.transmit` | drivers; installed by card reset | `qopen(Qkick)`; `ethercore_tx` explicit kick | hardware TX kick | `(void*)Ether*` -> void; drains `oq` to hardware | consumes `Block`s from `oq` | process/soft context; driver-specific | none | NATIVE(E7.1): native TX kicks it; VirtIO has nil and relies on `txproc` | unchanged | host UDP frame with `E71TXTX` |
| `Ether.ctl` | drivers / `ethersink.c` | `etherwrite` non-data branch | hardware/controller control | `(Ether*, void*, long)` -> long | caller buffer | process context | legacy `#l` ctl only | LEGACY: not exposed by native API | unchanged `etherwrite` ctl path | source review |
| `Ether.shutdown` | drivers; `ethercore_shutdown` | `ethershutdown` (Dev) | hardware power/shutdown | `Ether*` -> void | none | shutdown path | none | NATIVE(E7.1): central loop | same "no shutdown function" print | source review |
| controller probe/reset callbacks (`virtio10 reset`, `rtl8169pnp`, `i82563pnp`/..., `i225pnp`, `iwlpnp`, `sink reset`) | `port/ethervirtio10.c:662`, `pc/ether8169.c`, `pc/ether82563.c`, `pc/etheri225.c`, `port/etheriwl.c`, `port/ethersink.c:53` | `etherprobe` via `cards[].reset` | hardware controller discovery | config `Ether*` -> 0/-1; PCI/DMA/IRQ/firmware setup | controller-owned | boot `chandevreset` (pre-scheduler) | none | NATIVE(E7.1): registry owns call; reset body unchanged | unchanged | `#l0: virtio10 ...` boot line |
| `netconsole` | `port/devether.c:533` | `etherreset(on=1)`, `ethershutdown(on=0)` | legacy IPv4 UDP console | `on` -> installs/removes `consuart` | `Netconsole`, `netcons->buf` | boot/shutdown; `putc` uses `ilock` | legacy `#l` output queue; IPv4 literals | LEGACY-ONLY; not moved to native core | unchanged; `print`/`panic` paths preserved | source review; E5 console build passes |
| `etheriq` | `port/ethercore.c:497` | VirtIO `rxproc` (`ethervirtio10.c:311`), `rtl8169` (`:1037`), `i82563` (`:1102`), `i225` (`:884`), iwl | core RX dispatch | `(Ether*, Block*)`; takes ownership | copy to native sink; original to legacy | **RX context**: VirtIO worker, other drivers may be IRQ; sink must not sleep | none in native dispatch; calls legacy adapter for same frame | NATIVE(E7.1): explicit single sink + legacy preservation | legacy receives every frame unchanged | `RX len=64 type=0x88b5 match=1` |
| `ethercore_rxregister/rxunregister` | `port/ethercore.c:429,450` | E7.1 probe / future native IP6 | core RX subscription | `(Ether*, sink, arg)` -> error code | caller owns `arg` lifetime; must quiesce RX before unregister | process context; `ilock` only | none | NATIVE(E7.1): exactly one fixed-purpose sink | none | `NEG rxregister-busy`, `NEG rxunregister-twice` |
| `etherlegacyrx` | `port/devether.c:275` | `etheriq` | legacy RX policy | `(Ether*, Block*)`; consumes or forwards | existing `ethermux` rules | RX context (IRQ for some drivers) | uses `Netfile.f[]` via `ethermux` | LEGACY: retained as the only mux sink | identical old `etheriq` body | legacy `#l` RX test |
| `ethermux` | `port/devether.c:182` | `etherlegacyrx`, `etheroq` | legacy demultiplex/bridge/filter | `(Ether*, Block*, Netfile**)` -> `Block*`/nil | pass-to-one or copy-to-many; frees on drop | RX/TX process or IRQ; no qlock | `Netfile.f[]`, `Netfile.bridge/bypass/promisc`, `mactab` | LEGACY: policy stays in adapter | unchanged | source review; `#l` type-0x86dd delivery |
| `etheroq` | `port/devether.c:288` | `etherwrite`, `etherbwrite` | legacy channel TX policy | `(Ether*, Block*, Netfile**)`; rewrites source MAC, bypass/DMAT, mux | consumes `bp`, copies for mux recipients, `qbwrite` | process context (Chan write) | `Netfile` identity required | LEGACY: not the native TX entry | unchanged | source review |
| `etherwrite` | `port/devether.c:309` | Dev `write` | legacy data/ctl adapter | `(Chan*, buf, n)` -> long | allocates/copies `Block` | process context | Chan/Qid | LEGACY | same length checks `Etoobig`/`Etoosmall`, ctl behaviour | source review |
| `etherbwrite` | `port/devether.c:362` | Dev `bwrite` | legacy block write | `(Chan*, Block*, ulong)` -> long | consumes on data path; frees on error | process context | Chan/Qid/Netfile | LEGACY | unchanged | source review |
| `ethercore_tx` | `port/ethercore.c:379` | E7.1 probe / future native IPv6 | native frame TX | `(Ether*, Block*)` -> `EtherErr*` | success consumes `bp`; failure leaves `bp` to caller; internal copy owned by `oq` | **process context only**; non-blocking `qpassnolim`; explicit kick | none | NATIVE(E7.1): direct `Block` TX, link/MTU/queue checks | legacy path unchanged | host `E71TXTX` frame; `TX rc=0` |
| `qopen(Qmsg|Qkick)` / `oq` | `port/qio.c`; created in `etherprobe` | core, legacy `etheroq` | TX buffering/backpressure | `Queue*` of `Block` messages | queue owns queued blocks | `ilock` inside qio; Qkick callback | none by itself | NATIVE(E7.1): same queue, explicit native kick | same queue used by legacy | `STATS tx=1`; host frame |
| `Netif`, `Netfile` | `port/netif.h` | embedded in `Ether`; `Netfile.f[]` per controller | legacy multiplex state | fields + per-open `in` queue | `Netif.f` allocated by `netifinit`; `Netfile` by `openfile` | `QLock(Netif)` in file helpers | yes, by definition | LEGACY: retained; native path does not read `f[]` | unchanged | `CHAN-NATIVE ... clean=1` |
| `netifinit` | `port/netif.c:19` | `etherprobe` | legacy state allocation (also reached from core probe) | name/nfile/limit -> fills `Netif` | `xalloc` for `f[]` | boot/probe | no `Chan` in body | EXISTING: called by core, but not a native frame op | unchanged | `#l` test |
| `netifopen/close/read/write/bread/wstat/stat` | `port/netif.c:159,415,190,298,264,371,409` | Dev `walk/open/read/write/bread/wstat/stat` | legacy file/Netfile policy | `Chan*` + buffers | per-`Netfile`, queue blocks | `QLock(Netif)`; can sleep | `Chan`, `Qid`, `Dirtab` | LEGACY: untouched | access checks, modes, bridge/bypass, multicast close preserved | legacy `#l` attach/ctl/read test |
| `activemulti`, `macent`, multicast/promisc/bypass/bridge | `port/netif.c`, `port/devether.c` | legacy `ethermux`, `netifwrite`, `netifclose` | legacy filtering policy | addresses/state -> delivery decisions | `Netaddr` allocations | `QLock(Netif)` / RX context reads | `Netfile` fields | LEGACY: not moved to native sink | unchanged | source review |
| `dmatproxy` | `port/devether.c:642` | `etherlegacyrx`, `etheroq` | legacy Wi-Fi MAC translation | `Block*`, direction, proxy MAC -> mutates frame | no new block | RX/TX context | none by itself but part of legacy policy | LEGACY: not applied to native raw TX/RX | unchanged | source review |
| frame copying | `ethermux` (`devether.c`), `etheriq` (`ethercore.c`) | both RX paths | ownership isolation | `Block` -> new `Block` | native: `iallocb` copy for sink; legacy: `iallocb` copies for extra recipients; TX: `allocb` copy | RX copy is interrupt-safe | none added | NATIVE(E7.1): one owner per `Block` | legacy copy rules unchanged | `STATS drop=0`; source review |
| NIC IRQ RX / enable ordering | drivers + `ethercore_attach` | driver interrupt/worker | hardware RX | IRQ -> `etheriq` | driver ring blocks | IRQ for 8169/82563/i225/iwl; worker for VirtIO | native sink contract is IRQ-safe | NATIVE(E7.1): documented context, no sleeping in sink | drivers unchanged | VirtIO RX marker |
| drop/overflow accounting | `Ether` (`Netif.inpackets/outpackets/soverflows`), core `rxdropped` | legacy mux and native sink | stats | counters | none | counters not locked (existing style) | legacy counters in `netifread` stats | NATIVE(E7.1): `rxdropped` for native copy failure | existing `soverflows` unchanged | `STATS drop=0` |
| `ethersetlink` / `ethersetspeed` | `port/devether.c:403,392` | drivers (link change, speed) | hardware state + legacy queue sizing | `(Ether*, value)` | none | driver process/IRQ; prints only when `up` and `islo()` | reads `ether->f` to decide legacy actions | LEGACY/EXISTING: retained | same link print and `qsetbypass` drop | source review |
| `etherdevtab` | `port/devether.c` (Dev table) | generated `devtab[]` from `pc64*` configs | legacy `#l` registration | Dev callbacks | none | boot registration | Chan/Qid | LEGACY: kept registered in all pc64 profiles | unchanged | `strings 9pc64`; build |
| `ipdevtab` | `ip/devip.c` (`ipattach` at `:299`) | `#I` attach via `namec` | legacy IP file namespace | Chan/Qid; `Fs` init | `Fs`, `Conv` | process context, `QLock` | Chan/Qid/`namec` | AUDIT ONLY (E7.2+) | unchanged | source review |
| `wgdevtab` | `ip/devwg.c` | `#W` attach/write | legacy WireGuard file interface | Chan/Qid; `Wg` | `Wg`, `Chan` | process context | Chan/Qid | AUDIT ONLY (E7.2+) | unchanged | source review |
| `etherbind` / `etherbwrite` / `etherread4` / `etherread6` | `ip/ethermedium.c:113,255,321,361` | `ipifc` bind and medium callbacks | legacy IP-to-Ethernet | `Ipifc`, `Block`, version -> `Chan`/`devtab` | existing `Etherrock`, queues | kprocs | `namec`, `chandial`, `devtab[..]->bread/bwrite` | AUDIT ONLY (E7.2+) | unchanged | source review |
| `wglisten` / `wgreader` | `ip/devwg.c:1698,1211` | `#W` write / kproc | legacy WG outer UDP | `namec("/net/udp/clone")`, `Chan*`, `Block` | `Chan`, `Wg` | process/kproc | `Chan` | AUDIT ONLY (E7.2+) | unchanged | source review |
| loopback/null/pkt media, `ipoput4/6`, `ipiput4/6`, `SDifc` | `ip/*`, `port/sd*` | IP stack, storage | context only | packets/blocks | existing | existing | some Chan edges in file media | AUDIT ONLY; not modified | unchanged | source review |

## 3. Native E7.1 contracts

### 3.1 Lifecycle and lookup

- `ethercore_init()` is the only bulk probe/reset entry. It is idempotent:
  a second call returns the existing controller count and does not call
  `cards[].reset` again. It returns `EtherErrPreinit` if no card driver has
  registered.
- `ethercore_lookup(ctlrno)`, `byindex(i)` and `byname(name)` provide stable
  in-memory lookup. Invalid indices return `nil`; there is no path/Qid/OID
  encoding and no global userspace handle.
- Controller reset (`cards[].reset`) still runs at boot from
  `etherdevtab.reset` -> `ethercore_init()`, after PCI configuration and
  before `pageinit`/scheduler, exactly as the inherited driver constraints
  require. It performs PCI discovery, DMA/ring allocation and IRQ enable.
- `attach` (ring/queue enable, worker startup) is separate and runs from
  `ethercore_attach()` in process context after the scheduler exists:
  the E7.1 probe calls it, or a legacy `#l` open calls it. It is never called
  from `etheriq`, from an interrupt, or with `up == nil` in E7.1.
- Legacy `etherattach` delegates to `ethercore_lookup` and
  `ethercore_attach`; it does not call `etherdevtab.reset` or a controller
  reset callback from the native entry.

### 3.2 Frame TX

`int ethercore_tx(Ether *e, Block *bp)`:

- Input is one complete L2 frame in a `Block`; EtherType bytes are preserved.
  There is no IPv4/IPv6 interpretation in this function.
- Rejects, without consuming `bp`: `bp == nil` (`EtherErrBadArg`), unknown
  controller (`EtherErrNoDevice`), length outside `e->minmtu..e->maxmtu`
  (`EtherErrBadLen`), not attached/no queue (`EtherErrNotReady`), `link == 0`
  (`EtherErrDown`), closed queue (`EtherErrClosed`), full queue
  (`EtherErrQueue`), allocation failure (`EtherErrNoMem`).
- On `EtherErrOk` the core has consumed `bp`. Internally it copies the frame
  into a queue-owned `Block` so a queue-close race cannot free the caller's
  block. The copy is enqueued with `qpassnolim` (non-blocking, no implicit
  kick) and then `Ether.transmit(e)` is called, or the queue's starved reader
  (VirtIO `txproc`) is woken by qio. Success increments `outpackets`.
- Legacy `#l` writes still use `etheroq` -> `ethermux` -> `qbwrite`; they are
  not equated with the trusted native entry and keep `Netfile` identity.

### 3.3 Frame RX

`void etheriq(Ether *e, Block *bp)` is the driver RX entry.

- If an E7.1 sink is registered, the core makes one interrupt-safe `iallocb`
  copy and calls `sink(arg, e, copy)`. The sink owns that copy.
- The original `bp` is always passed to `etherlegacyrx` (the old `etheriq`
  body) so `Netfile`, bypass, DMAT and `ethermux` behaviour is preserved.
- If the copy allocation fails, `rxdropped` is incremented and legacy still
  receives the original.
- The sink runs in the driver's RX context. VirtIO calls from `rxproc`
  (worker); `rtl8169`, `i82563`, `i225` and iwl may call from interrupt.
  Therefore the sink must not sleep, take a blocking `QLock`, or allocate
  with a sleeping allocator. The E7.1 test sink uses `qpass` + `wakeup`,
  both interrupt-safe. Registration/unregistration are process-context
  operations; the caller must quiesce in-flight RX before unregistering.
- Exactly one sink per controller exists in E7.1. This is deliberately not
  a publish/subscribe bus or a universal protocol registry.

### 3.4 IPv6 EtherType

`ETIP6`/`0x86DD` is never converted to an IPv4 address in the native core.
The E7.1 hardware test uses experimental EtherTypes `0x88B5`/`0x88B6`; the
legacy test uses `0x86DD` to prove L2 delivery and EtherType preservation.
Acceptance of a raw Ethernet frame by the native sink is **not** evidence
that the IPv6 stack accepted it. No IPv6/NDP datapath is implemented here.

## 4. Legacy `#l` preservation

- `etherdevtab` remains registered in `pc64`, `pc64mp`, `pc64native`,
  `pc64oconsole` and the opt-in `pc64e71`.
- `etherwalk/stat/open/read/write/bread/bwrite/wstat/close` and all
  `netif.c` file helpers are unchanged. Access checks (`netown`), per-open
  `Netfile` state, `qreopen/qclose`, offsets, `Qmsg` framing, bridge, bypass,
  promiscuous, multicast and `headersonly` remain in the adapter.
- `netconsole` remains legacy-only and IPv4; it was not moved into the
  native API or confused with the E5 UART console service.
- A generated `links()` still calls every `ether*link()` -> `addethercard`
  before `chandevreset`; the registry therefore sees the same drivers as
  before. `ethercore.o` is in the kernel `PORT` object list so all pc64
  profiles link the core even when the E7.1 probe is not present.

## 5. E7.2+ dependency graph (audit only)

```text
NIC driver -> etheriq(Ether*, Block*)                         [E7.1]
    |-> native sink copy (E7.1) -> future IPv6 packet processing
    |-> etherlegacyrx -> DMAT -> ethermux -> Netfile.f[].in -> netifbread

Current legacy IP:
  #I attach (ipdevtab, ipattach) -> Fs init -> ip_init/arpinit/
      ipprotoinit[] = { ipifcinit, icmpinit, icmp6init, udpinit,
                        tcpinit, ... }
  Ipifc medium bind (ethermedium.c:etherbind)
      -> namec(ifc "/addr") -> #l
      -> chandial(ifc "!0x800") / chandial(ifc "!0x86DD") / "!0x806"
      -> devtab[Chan]->write(Chan,"nonblocking")
  etherbwrite (Ipifc medium) -> arp/NDP -> padblock/adjustblock ->
      devtab[er->mchan4/6->type]->bwrite(Chan, Block)
  etherread4/6 kproc -> devtab[Chan]->bread() -> ipiput4/ipiput6

Current WireGuard:
  #W write -> wglisten -> namec("/net/udp/clone") -> Chan ctl
      -> devtab[Chan]->read/write (udp clone, announce, headers)
      -> namec("/net/udp/<n>/data") -> Chan udata
      -> wgreader kproc -> devtab[Chan]->bread() -> UDP payload
```

Concrete source edges:

- `ipattach` / `Fs` creation: `ip/devip.c:299`; `ip_init`, `arpinit`,
  `netloginit`, then `ipprotoinit[]` generated from the config `ip` section.
- `Proto` / `Conv`: `ip/ip.h` `struct Proto` (rcv/bind/connect/ctl/...) and
  `struct Conv` (`rq/wq/eq`, `Iphash`, `ptcl`, `Routehint`).
- `udpinit`: `ip/udp.c:678`; `tcpinit`: `ip/tcp.c:3190`; `icmp6init`:
  `ip/icmp6.c:820`; `ipifcinit`: `ip/ipifc.c:916`.
- `etherbind` / `etherbwrite` / `etherread4` / `etherread6`:
  `ip/ethermedium.c:113,255,321,361`; these use `namec`, `chandial`,
  `devtab[Chan]->bread/bwrite`.
- `wglisten` / `wgreader`: `ip/devwg.c:1698,1211`; `namec` of `/net/udp/clone`
  and `/net/udp/<n>/data`, then `Chan` bread/write.
- `ipiput4/ipiput6`, `ipoput4/ipoput6`: `ip/ip.h` declarations around
  `ip.h:767`; packet processing is separate from file-namespace `Fs` init.

Later acceptance conditions (not E7.1 work):

1. Native IPv6-only IP core with working ICMPv6/NDP and a tested negative
   path rejecting IPv4 frames/connections.
2. Native UDP6/TCP6 connection management with explicit datagram `Message`
   vs `Stream` semantics (no new socket handle ABI implied here; `OPEN`).
3. Native WireGuard with IPv6-only outer UDP and inner IPv6 packets.
4. An O-only configuration that no longer registers `etherdevtab`,
   `ipdevtab` and `wgdevtab`.
5. Exclusion of executable IPv4/ARP code from the final kernel without
   breaking genuinely version-independent shared C code.

Any userspace ABI for native networking remains `OPEN`; `OID`, a kernel
`Ether*` and a userspace `Handle` are distinct concepts.

## 6. Executed evidence (E7.1)

```sh
ETHER_PROBE=1 WHAT=kernel tools/build.sh      # 9pc64e71
tools/test-e71-ether.sh                       # VirtIO + no-NIC fixture
WHAT=kernel tools/build.sh                    # 9pc64 + 9pc64mp
tools/test-qemu.sh                            # default kernel boot
OCONSOLE=1 WHAT=kernel tools/build.sh         # 9pc64oconsole
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole \
  --devc build/amd64/pc64oconsole.devc.c
strings build/amd64/9pc64 | grep ethercore    # core linked in default
```

Observed (logs under ignored `build/verification/e71/`):

- `E71ETHER: INIT rc=1 inits=2 probes=90 idempotent=1`
- `E71ETHER: ATTACH rc=0`, `READY`
- native TX: host UDP frame `...88b6 45373154585458...` (`E71TXTX`);
  `E71ETHER: TX rc=0 ... ok=1`
- native RX: host-injected `...88b5 45373152585258...` (`E71RXRX`);
  `E71ETHER: RX len=64 type=0x88b5 match=1`
- native path Chan counters: `namec=0 newchan=0 walk=0 devwalk=0 mount=0
  exec=0 clean=1`
- negatives: preattach `-2`, short/long length `-4`, RX busy `-7`, mismatched
  RX unregister `-9`, nil sink `-9`, down `-5`, full queue `-6`
- legacy `#l`: `E71ETHER: LEGACY len=64 type=0x86dd match=1`
- no NIC: `E71ETHER: NODEV n=0`, no panic
- default kernel boot: `PASS: kernel up to init0 (no root=)`
- E5 profile: 23 Qids, 19 native, 2 legacy-only, 2 intentionally unsupported;
  no `consdevtab`

## 7. Status

The IPv6-only target in `docs/GENERAL-SOFTWARE-SPECIFICATION.md` remains
**accepted architecture**. The implementation in this branch is
**TRANSITIONAL**: E7.1 proves a native Ethernet lifecycle and frame boundary
with a real VirtIO NIC; it does not implement the IPv6-only IP/UDP/TCP or
WireGuard runtime.
