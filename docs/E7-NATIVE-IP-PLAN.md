# E7.4 native IPv6 packet boundary: source map and design

**Status:** E7.4.0 design, implemented in `sys/src/9/ip/nativeinh6.c` (C API
prefix `nativeip6_`) and tested by `tools/test-e74-ipproto.sh`.
**Branch:** `design/ipv6-only-native-20261024`.
**Scope:** one opt-in experimental IPv6 Next Header consumer on the NORMAL
IPv6 path. This is the integration seam a future userspace tunnel may use; it
is **not** a tunnel, encryption, authentication or SEALED implementation.

Vocabulary follows `docs/KERNEL-API-ABI.md`. `Proto`, `Conv`, `Fs`, `Ipifc`,
`Block` and `Queue` are existing kernel C structures, not userspace handles.
The E7.4 consumer is kernel C only; there is no raw-packet or socket ABI.

## 1. Exact receive path (NORMAL, current code)

```text
VirtIO TX/RX rings (port/ethervirtio10.c)
  rxproc
    -> etheriq(Ether*, Block*)                     port/ethercore.c
       -> EtherRxSink copy (IRQ/driver-worker safe) qpass(rxq)
       -> etherlegacyrx(original)                  port/devether.c (legacy, parallel)
  ipv6native worker (kproc, process context)       ip/nativev6.c
    -> strip 14-byte Ethernet header
    -> rlock(ifc); ipiput6(f, ifc, Block*)          ip/ipv6.c
       -> version / payload-length validation (trimblock)
       -> ipforme / forwarding decision
       -> procxtns(ip, bp, 1)                      extension-header walk + reassembly
       -> h = bp->rp; p = Fsrcvpcol(f, h->proto)    ip/devip.c
          -> Fsrcvpcol returns f->ipmux if set, else f->t2p[proto]
       -> (*p->rcv)(p, ifc, bp)                    e.g. icmpiput6, udpiput
    -> runlock(ifc)
```

`Fsrcvpcol` (`sys/src/9/ip/devip.c:1490`) is the existing protocol
demultiplexer. `Fsproto` (`devip.c:1339`) installs a `Proto` in both `f->p[]`
and `f->t2p[ipproto]`, rejecting a duplicate protocol number. The E7.4
consumer uses exactly that table entry for experimental Next Header **253**;
it does not allocate a new `Fs`, `Conv` array, path or `Dev`.

`ipmux` would intercept at `Fsrcvpcol` because that function prefers
`f->ipmux` over `t2p[proto]`. E7.4 does not set `f->ipmux`, does not link an
ipmux `Proto`, and does not add a decision tree, filter language or per-user
routing graph. The security boundary a future SEALED mode needs is a
per-physical-interface ingress/egress policy, not a better multiplexer.

## 2. Exact transmit path (NORMAL, current code)

```text
nativeip6_send / icmp6 / udpkick
  -> ipoput6(f, bp, nil, ttl, tos, rh)             ip/ipv6.c
     -> v6lookup (route, on-link neighbor)
     -> ipifcoput(ifc, bp, V6, gate, rh)           ip/ipifc.c
        -> ifc->m->bwrite                          ip/nativev6.c nativebwrite
           -> ethermediumframe                     ip/ethermedium.c (NDP/pad)
           -> ethercore_tx(Block*)                 port/ethercore.c
              -> qpasstry(Ether.oq) -> VirtIO txproc -> physical frame
```

The E7.4 sender only builds an IPv6 header plus one **253** payload. It has
no generic raw-IP entry, no userspace path and no way to inject an apparently
authenticated inner IPv6 packet.

## 3. Registration, ownership and lifecycle

| Item | E7.4 contract |
| --- | --- |
| Wire selector | IPv6 Next Header 253, explicitly experimental (RFC 3692 test range; not a permanent IANA assignment, not WireGuard). |
| Registration | One `Proto` named `e74ip6` with `ipproto=253`, installed with `Fsproto`. Exactly one consumer globally; a second registration returns `NativeIp6ErrBusy`. |
| Duplicate protocol | `Fsproto` rejects an already occupied `t2p[253]`; the wrapper also refuses a second consumer. |
| Unregister | Clears `f->t2p[253]`, marks the consumer disabled, waits for an in-flight callback to return, and never frees the `Proto`/consumer while the worker could still hold the pointer. The one-shot `Fs` is retained as in E7.3, so the bounded allocation is not a per-packet leak. |
| Re-register | Re-publishes the same `Proto` entry; no duplicate `f->p[]` entry and no second stack. |
| Callback context | The native IPv6 worker (process context, after `rlock(ifc)`). It may block briefly but must not sleep forever; the NIC sink/IRQ path never invokes it. |
| Block ownership | The callback receives one `Block` whose `rp` is the first payload byte. It owns the `Block`; returning non-zero rejects/drops it. `nativeip6_send` consumes it on success and leaves it to the caller on failure. |
| Validation before dispatch | Single concatenated Block; `BLEN >= IP6HDR`; version 6; declared payload length equals delivered IPv6 payload; payload fits the IPv6 maximum. `ipiput6` already trims the packet to the declared length and rejects bad versions/lengths before the `Proto` is called. |
| Extension headers | Inherited `procxtns`/`ipfragreassemble6` are unchanged. A bare 253 or a reassembled fragment reaches the consumer. Hop-by-hop/routing-header combinations are not re-demultiplexed by inherited code; they are safely dropped as an unknown protocol (h->proto is still the extension-header number). No new extension-header parser was added. |
| Counters | `rxframes`, `rxbytes`, `rxreject`, `rxbad`, `txaccepted`, `txerrors`, `txbytes`, `active`, `registered`. The bounded native RX `Queue` additionally exposes `ipv6native` `rxdrop` on saturation. |
| Stop | The probe unregisters before `ipv6native_stop`; stop tears down the sink, closes the RX queue and waits for the worker to exit. A pending callback is either completed or rejected by the `registered` flag. |

## 4. Why not a direct callback outside `Proto`?

A second dispatch hook would duplicate the existing `t2p[]` lookup, require
an additional calling convention and create an alternative receive path that
UDP6/ICMPv6 do not exercise. The fixed `Proto` entry reuses:

- `ipiput6` version/length validation and route/forward logic;
- `procxtns` extension-header and fragment handling;
- `Fsproto` protocol-number collision checks;
- the existing worker/BLock ownership model.

The only new code is a tiny `rcv` function, a statically bounded consumer
record and a single-purpose sender.

## 5. Future NORMAL / SEALED seam (DESIGN ONLY, **NOT IMPLEMENTED**)

The following is documentation for a later project. **No mode switch,
scheduler, classifier, encryption, key management, SEALED ingress/egress
filter or userspace tunnel exists in E7.4.** The E7 kernel is NORMAL ONLY.

A later SEALED mode should place two decisions at explicit existing points:

| Boundary | Current NORMAL function | Future SEALED decision (NOT IMPLEMENTED) |
| --- | --- | --- |
| Physical ingress, before IP/ICMP processing | `etheriq` / `ipv6native_etherinput` / `ipiput6` | Per-`Ether` mode check **before** `ipiput6` and before ICMPv6 error generation; allow only explicitly specified NDP/PMTU control and the dedicated transport. |
| Physical egress, before NIC queue admission | `nativebwrite` / `ethermediumframe` / `ethercore_tx` | Per-`Ether` mode check before `qpasstry` into `Ether.oq`, including queued/stale frames across a transition; ordinary IPv6 TX must fail explicitly. |
| Forwarding | `ipiput6` non-local branch | Drop ordinary forwarding; outer tunnel packets are handled by the future service, not forwarded as normal IPv6. |
| Multiple NICs | each `Ether`/`Ipifc` pair | Mode is per physical interface; no single accidental global switch. |
| Link state | `ether->link`, `nativebwrite` link-down branch | SEALED keeps the physical link UP; “logically unavailable” must be distinguishable from link-down. |
| Queue invalidation | `Ether.oq`, `ipv6native` `rxq` | A future atomic mode/generation publication must invalidate stale queued frames in both directions. |
| Failure/recovery | process lifecycle | Fail closed: a crashed userspace tunnel must not reopen NORMAL automatically; boot/operator recovery needs a separate design. |

Trust boundary for the future tunnel (NOT IMPLEMENTED): authenticate before
inner IPv6 injection; separate outer and verified inner packets; anti-replay;
peer/allowed-prefix checks; loop avoidance; bounded queues; full IPv6
length/extension validation; PMTU and rate limits. E7.4's experimental
plaintext 253 payload **must never** be treated as authenticated inner IP.

## 6. Deliberately absent

- No SEALED runtime, mode flag, scheduler, classifier or cryptographic code.
- No `ipmux`, no `f->ipmux`, no filter language.
- No WireGuard code, userspace daemon, TUN adapter or wire format.
- No new `Dev`, `Chan` path, syscall, socket, fd or userspace raw-packet API.
- No generic IPv6 packet injector; `nativeip6_send` is fixed to Next Header
  253 and requires a running NORMAL consumer.
- No change to ordinary `9pc64`, `9pc64mp`, E7.1/E7.2/E7.3 or E5 profiles.

### 6.1 Build-name note

The inherited `port/mkdevc` strips indentation from `misc` entry names and
then re-tests the stripped line as a section header. A `misc` token whose
name contains `dev`, `ip`, `link`, `misc` or `port` therefore ends `misc`
collection and silently drops the following device/architecture entries.
The E7.4 source files are consequently named `nativeinh6.c` and
`e74nhprobe.c` (no such substring), although the kernel C symbols remain
`nativeip6_*` and `e74ipprobe_start`. This is a build-tool naming constraint,
not an API rename.
