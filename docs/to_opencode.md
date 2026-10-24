# E7.4–E7.8 — Finish the native IPv6 networking branch; NO merge

**ACTIVE AGENT PLAN — same branch only:** `design/ipv6-only-native-20261024` in `pereuna/Plan2001-O`. E7.1/E7.2/E7.3 and E7.3.1 are already agent-reported APPROVE. Start from their current committed head, not from old code. This replaces the *completed* E7.3.1 assignment in this file. Work through E7.4, E7.6, E7.7 and E7.8 in order, committing and reporting each independently. **E7.5 is intentionally deferred to a future USERSPACE tunnel project.** **E7.8 is verification/merge readiness ONLY. Merging happens in another ChatGPT session.**

## Non-negotiable branch, safety and scope

1. Verify `git branch --show-current` is exactly `design/ipv6-only-native-20261024`; check `git status --short`, `git rev-parse HEAD`, upstream and `git remote -v`. If the working tree has other tasks, use a dedicated worktree on the **same branch** without overlapping commits; coordinate safely. Push only `origin/design/ipv6-only-native-20261024` and verify remote. Do not create a branch, check out/rebase/merge/reset/cherry-pick `main`, open/merge PRs, force-push, touch PR #1 or the mistaken E7.2 branch. Do not modify E6/E8/E9 files on `main`. No automatic merge via hooks.
2. Read: `AGENTS.md`; `docs/GENERAL-SOFTWARE-SPECIFICATION.md` (IPv6-only section); `docs/KERNEL-API-ABI.md`; `docs/ETHER-MIGRATION.md`, `IPV6-NATIVE-MIGRATION.md` and `UDP6-NATIVE-MIGRATION.md`; `docs/to_chatgpt_review_e731.md`; current `pc64e71/e72/e73`, `tools/build.sh`, `sys/src/9/ip/{nativev6.c,nativeudp6.c,ipmux.c,ipv6.c,udp.c,icmp6.c,devip.c,ip.h}`, `sys/src/9/port/{ethercore.c,devether.c}`, existing configurations and kernel generators. Inspect actual code and compile outputs before recommending a change.
3. **Core architectural decision:** The physical network interface will *eventually* have exactly two mutually exclusive modes: `NORMAL` = the conventional IPv6 stack and its enabled services; `SEALED` = **only a dedicated authenticated encrypted direct-IPv6-IP transport plus the minimum required IPv6 link-control traffic**. Both input and output must be gated in a future implementation. External normal services will then see the normal network as unavailable although the physical NIC stays UP. Switching may someday be scheduled, but **DO NOT IMPLEMENT SEALED, an on/off switch, scheduler, classifier, encryption, cryptographic keys, or stealth claims in this E7 task**. The E7 kernel runs **NORMAL ONLY**; do not introduce a mode that can be activated prematurely. Future mode concepts may appear in design documentation or private internal naming only; if any placeholder is compiled, it must be inoperative, safe, and not add a fake security boundary. No production “sealed” success claim.
4. **No `ipmux` and no multiplexer framework.** The existing `ipmux.c` is a useful source reference for native packet delivery but NOT a requirement or the security gate. Current `pc64e73` does not link an ipmux Proto; do not add a generic decision tree, filter language, per-user routing graph or hierarchical device namespace. Minimal fixed-protocol dispatch should reuse the existing kernel IPv6 demultiplexing where possible.
5. **No WireGuard work at all here.** Do not write/migrate `devwg.c` crypto or handshakes; no userspace WG daemon, `wireguard-go`, WireGuard TUN adapter or wire format; no MicroPython `socket`, Lua/Go runtime or new filesystem. E7.5 (tunnel/authentication/key management/config/userspace transport) is a future independent project and has **NO code or acceptance gate in E7**. This work is networking infrastructure only.
6. Preserve the old legacy configurations `9pc64`, `9pc64mp`, E7.1/E7.2/E7.3 tests, E5 console, and their existing `#l/#I/#W`/IPv4 features. **Remove old functionality only from a dedicated new opt-in E7-native kernel configuration**, never globally until known callers and all regressions have been audited. Scope firewall/packet semantics to this kernel profile; no silent global weakening.

## High-level target and future SEALED seam

```text
                              E7 normal runtime (IMPLEMENT)
VirtIO / Ethernet
  -> native ethercore sink / native IPv6 packet validation
  -> ordinary ICMPv6 + Neighbor Discovery; UDP6 via Proto/Conv
  -> direct experimental IPv6 Next Header consumer (E7.4, fixed small API)
  -> ordinary native IPv6 TX -> physical Ether
  [No ipmux, no Chan or 9P in these native paths]

                              Future encrypted tunnel (DESIGN ONLY)
physical Ether in NORMAL <future atomic mode transition> SEALED
 ingress/egress policy at a physical-interface boundary (not ipmux)
     allow essential local-link NDP/PMTU controls as explicitly specified
     allow ONLY the dedicated raw encrypted IP transport
     DROP normal IPv6 traffic both directions; no ping/TCP/UDP leak
 outer encrypted packet -> future userspace authenticated service
 verified inner IPv6 packet -> future virtual IPv6 interface (not today)
 physical NIC stays UP; normal network logically unavailable
```

**Important distinction:** No UDP port is present when the **future** encrypted transport uses a dedicated IPv6 Next Header protocol directly, but this does NOT hide the host's IPv6 address, MAC/ND presence, packet timings or any visible header. No encrypted/authenticated transport exists in E7.4; E7.4 experimental packets are plaintext TEST VECTORS and MUST NEVER be passed to the production IP stack as “authenticated inner IP.” Ordinary `NORMAL` pings and UDP6 are expected to work in current E7 tests.

**Future design constraints to document, not implement:**
- Per-physical-interface mode scope, not a single accidental global switch; ingress decision before regular protocol handlers and ICMP errors, egress decision before actual NIC queue acceptance (including queued/stale packets across transitions). Both directions needed, with atomically published mode and generation / queue invalidation eventually.
- Physical link remains UP in SEALED; ordinary service network operations will eventually get explicit unavailability semantics, not silently time out; distinguish link-down vs logical network-disabled.
- NDP/Neighbor Solicitation/Advertisement remain necessary for an on-link IPv6 peer/router. Router Advertisement acceptance, multicast behavior, ICMPv6 Packet Too Big, destination unreachable and rate limiting need a threat/availability decision; do not casually allow “all ICMPv6” or drop all ICMPv6. External IPv6 observers can still see ND at L2.
- Fail closed on crash/restart of the **future** userspace tunnel service: never reopen NORMAL automatically. Boot default and authorized operator control need a separate later design and recovery mechanism.
- A future tunnel needs separation of outer packets vs verified inner packets, anti-replay, peer-to-allowed-prefix checks, routing-loop avoidance, bounded input queues, authenticating BEFORE inner IPv6 injection, packet length/extension-header validation, PMTU and rate limits. Keep this as a documented trust boundary, not a stub that bypasses checks.
- No guarantee unknown IP protocols pass through the Internet; experimental protocol numbers `253/254` are only for test deployments and are not permanent global assignments (IANA protocol registry / RFC 3692). One selected number in a controlled QEMU/LAN test is allowed. Do not create a new IPv6 extension-header parser or break existing extension-header semantics; distinguish Next Header upper-layer demux from extension-header processing.

## E7.4 — Native IPv6 packet boundary in NORMAL mode

**Goal:** Provide a small, verifiable kernel C ingress/egress point for a dedicated **direct IPv6 next-header payload** while preserving conventional IPv6/UDP6/ICMPv6 behavior. This becomes a later userspace tunnel's integration point, NOT its implementation. Avoid a speculative userspace ABI, routing framework or firewall.

### E7.4.0 — Source map and design
- Produce `docs/E7-NATIVE-IP-PLAN.md`: exact path `VirtIO RX -> etheriq -> sink/worker -> ipiput6 -> procxtns -> Fsrcvpcol -> Proto`, plus TX back through `ipoput6`, Medium, `ethercore_tx`. Show where `ipmux` would intercept, why it is NOT required. Trace `Fsproto`/`t2p[]` registration, protocol numbers, neighbor discovery, control-traffic handling, ownership, synchronization and route/MTU.
- Map the future ingress + egress NORMAL/SEALED seam to explicit existing functions and link boundaries, without modifying behavior for SEALED. Identify where forwarding, local packets, ICMPv6 error generation, queued output and multiple NICs cross those boundaries. Explicitly mark `NOT IMPLEMENTED` for SEALED.
- Choose either a fixed kernel-native protocol registration via the **existing** Proto demux, or an even smaller direct registered callback; justify how collisions, ABI creep, buffer lifetimes, close/unregister and fault/race handling are prevented. Do not allocate a new `Fs` or implement a parallel IP stack. Prefer reusing ``sys/src/9/ip/ipv6.c` / `Fsrcvpcol` and one small fixed-transport endpoint rather than inventing `ipmux2`.
- A test-only fixed Next Header protocol (e.g. `253`) must be marked experimental and optional. Never claim its wire payload is WireGuard or a secure tunnel.

### E7.4.1 — Minimal C implementation + opt-in test
- Implement only the minimum C API that can register/receive raw IPv6 Next Header datagrams of the chosen experimental type (one complete bounded packet or payload, explicit source/destination/interface/protocol metadata and documented ownership) and send back native IPv6 packets of that same type through the inherited IPv6 TX path. Packet lengths and malformed IPv6 headers must be validated BEFORE callback dispatch. Exactly one consumer, deterministic already-registered / unregister / stop / no-controller statuses.
- Keep NIC/IPv6 startup order, NDP, route & IPv6 MTU, no use-after-free across unregister and stop. A pending receive must be cancellable; a producer in NIC/IRQ context must not sleep or allocate blocking resources. Qmsg/full drop and ownership counters observable.
- If IPv6 Next Header extension chains/fragments are unsupported by this experimental consumer, **fail closed for that test protocol**, document the exact limitation, and test negatives; DO NOT break NDP/UDP6 existing extension handling. Any callback must execute in a safe context with explicit ownership.
- No ability to inject unauthenticated arbitrary inner IPv6 packets into a normal receiving interface. Document the future trusted injection function requirements, but do **not** expose a dangerous callable bypass or any userspace/raw packet API yet.
- Give this a separate opt-in `pc64e74` (or similarly unambiguous) test profile, `E74_PROBE=1` build selector and `tools/test-e74-ipproto.sh` host fixture. Don't silently repurpose `pc64e73` or change default builds.

### E7.4.2 — Host-verified QEMU tests
- Send/receive actual Ethernet/IPv6 packets over the same isolated VirtIO host datagram transport as E7.3. Host verifies selected experimental Next Header, IPv6 version, src/dst, complete payload and length; no ghost/duplicate replies, valid link-layer behavior and real TX from guest.
- Send NS -> expect NA, ICMPv6 Echo -> Echo Reply and UDP6 -> UDP6 Echo in **NORMAL** mode. Demonstrate that adding the raw IP consumer does NOT hijack UDP6, NDP or ordinary ICMPv6.
- Negative: bad IPv6 version/length, truncated packet, bad or duplicate consumer registration, unhandled Next Header, invalid interface, queue-full, unregister with in-flight receive, no NIC, and MTU rejection. For unsupported extension combinations, assert safe reject. Check `namec/newchan/walk/devwalk/mount/exec==0` on native protocol path.
- Put logs under `build/verification/e74/`; put report into `docs/to_chatgpt_review_e74.md` (PASS/PARTIAL-HOLD and exact actual evidence). Keep former stage reports untouched.

**E7.4 gate:** source-backed native direct IP Next Header exchange, real host packet checks, harmless coexistence with UDP6/ICMPv6, no `ipmux`, no `Chan` in native path, no SEALED implementation, all E7.1/2/3/3.1 regressions intact. If this gate fails, report `PARTIAL-HOLD` and **stop** before E7.6.

## E7.5 — Deferred to a SEPARATE userspace project

**NO implementation, no scaffold, no tests, no dependency introduced here.** It will ultimately own encryption/authentication, key/session management, tunnel service state, peer/allowed-prefix policy, IPv6 inner packet forwarding, configuration and interaction with the E7.4 C boundary through a future reviewed process ABI. It might use WG's protocol concepts but is **not** an E7 kernel prerequisite. SEALED operation may only be claimed after that later authenticated service, policy enforcement and recovery mechanisms exist.

## E7.6 — Extract/remove legacy networking adapters from an E7-only build profile

**Goal:** Create a new **isolated** `pc64e7native` (name can vary if conflicts) representing **NORMAL IPv6 networking without legacy device-file registration**, preserving E7.4 native protocol test path and E7.3 hardened UDP6. This is *not* the merged `pc64onativedisk` profile; do not touch its implementation on `main`.

1. Machine-audit native versus legacy edges of `etherdevtab (#l)`, `ipdevtab (#I)`, `wgdevtab (#W)`, `devether.c`, `devip.c`, `devwg.c`, `etherlegacyrx`, `netifinit/Netfile`, `ethermedium.c` and `chandial/namec`. Include dependency and symbol lists in `docs/E7-NETWORK-CUTOVER.md`. A single usage of `Fs`/`Proto`/`Conv` *as native C structs* does not equal use of `Chan`; distinguish structural types, linked code and executed operations.
2. Split **native IP core initializers/helpers** currently co-located in `devip.c` away from `Dev ipdevtab`/file namespace as necessary. Let legacy adapter delegate to shared native core where feasible; no duplicate IP stack or fake `Dev`.
3. Remove `#l/#I/#W` registrations and their required namespace adapters from the new test-only E7 native profile; don't remove from ordinary `9pc64`/E7.1/E7.2/E7.3. Rework NIC initialization/legacy RX calls for this profile so it has no legacy sink and does not depend on the `Netfile` file-based fanout. Keep low-level driver registers, boot, NDP and actual TX/RX.
4. Avoid compile/linking legacy adapter functions in the target profile, not just making them unreachable through runtime flags. Where `Netif` contains version-neutral hardware counters or MAC state, identify and preserve necessary data without silently retaining full legacy allocation. If technical debt cannot be severed safely, document explicit hold instead of deleting needed code.
5. Verify generated Dev tables/OMAP/linked symbols from the exact E7 target. Demonstrate absent `etherdevtab`/`ipdevtab`/`wgdevtab` and no runtime `namec`/`Chan` dispatch in the E7 target, with the original profiles remaining valid. Check no NIC and real VirtIO; hardware and error-path regression must be real.
6. Add `E76_NATIVE=1 WHAT=kernel tools/build.sh` (or equivalent) and `tools/test-e76-network.sh`; run original E7.1/E7.2/E7.3/E7.4 and default/E5 tests. `docs/to_chatgpt_review_e76.md` with PASS/HOLD and actual emitted configs/symbol evidence.

**E7.6 gate:** no `#l/#I/#W` device registrations/legacy path reachable from the dedicated native target, real IPv6 NDP + UDP6 + direct raw-protocol tests still working, ordinary builds unaffected. If unmet, report `PARTIAL-HOLD` and **stop** before E7.7.

## E7.7 — Executable IPv4 / ARP removal from the E7 native target ONLY

**Goal:** Produce a truly IPv6-only linked **E7-native NORMAL profile**, not merely an IPv6-only configuration string.

1. Audit all live/linked IPv4 and IPv6-compatibility implementations, protocol init, IPv4 route paths, `ipiput4`/`ipoput4`, `icmpiput4`/`udpiput`'s V4 branch, TCP IPv4, multicast, ARP and shared `Fs` helpers. Explicitly separate **IPv4 ARP** from IPv6 Neighbor Discovery and any legitimately shared address-resolution implementation. Do NOT break NDP by mechanically deleting every name or symbol containing “arp”.
2. Remove executable IPv4 parsing/forwarding/routing/ARP from the **new native E7 configuration** using maintainable source separation/conditional compilation and targeted link rules. Preserve a reasonable legacy dual-stack build. Do not introduce mapped IPv4 fallback, NAT64 or fake IPv4 packet translations into native C API.
3. Accept genuinely version-neutral/common helpers only if they do NOT enable an executable IPv4 packet path. Provide reproducible object/link-map/symbol evidence, not only greps or lack of a `#I` namespace. If a static symbol is optimized out, explain which exact binary/map is authoritative.
4. Test IPv4 Ethernet EtherType drop and **no IPv4 side effect** (no UDP/ICMP reply, no IPv4 packet processing), plus IPv4-mapped address API rejection. Test both incoming and outgoing attempted IPv4 paths, including unbound protocol/unknown Next Header handling. Preserve IPv6 ICMPv6 ND, direct experimental IP protocol and UDP6 positive/negative checks; use real QEMU VirtIO frames. Test link-down, no NIC, malformed packets and needed IPv6 control traffic.
5. Do not claim a general native TCP6 stream API exists: inherited TCP6 may or may not be retained; source/documentation MUST identify what is truly available in this profile. TCP6, application services, DNS, DHCPv6 and userspace networking ABI are not authorized new implementations in this task. `NORMAL` means the conventional IPv6 stack **only for implemented/linked protocols**, not an imaginary full desktop networking stack.
6. Write `docs/to_chatgpt_review_e77.md` and rerunnable `tools/test-e77-ipv6-only.sh` (or extend E76 fixture), with source + linked evidence and host traffic results.

**E7.7 gate:** executable IPv4/ARP absent from selected E7 target; all IPv6 capabilities demonstrated; default legacy stack still builds/tests. If substantial source-level refactoring is required and cannot be completed without breaking shared code, report `PARTIAL-HOLD`, preserve successful earlier stages, and **do not attempt main merge**.

## E7.8 — Final verification and handoff, **NOT MERGE**

At end of E7.7 (or earlier HOLD), the agent shall perform a single **read-only integration readiness review**. Do NOT integrate into `main` or change E6/E8/E9. This is a gate for a separate future merge session.

Create:
- `docs/E7-MERGE-READINESS.md`: commits, resulting branch HEAD, delivered/held stages, compiler configurations and external test evidence; an explicit `NORMAL only / SEALED NOT IMPLEMENTED / E7.5 USERSPACE DEFERRED` status; remaining threat model and physical NIC limitations.
- A **conflict map** versus current `origin/main` (fetch/read/compare is allowed; no merge/rebase/cherry-pick). Enumerate conflicts expected for `sys/src/9/pc64/main.c`, `mkfile`/`CONFLIST`, `tools/build.sh`, generated Dev/OMAP tables, E6 `pc64onativedisk`, E8 pruned drivers and E9 boot changes. Provide safe suggested resolution order **only as documentation**, and the exact future E6/O-disk/MicroPython/E8/E9/E7 regressions needed.
- `docs/to_chatgpt_review_e78.md`: `VERDICT: READY-FOR-SEPARATE-MERGE / PARTIAL-HOLD / REJECT`; supported exact evidence; binary symbol audit; real packet bytes; E7.1/E7.2/E7.3/E7.3.1/E7.4/E7.6/E7.7/default/E5 outcomes; no-NIC and malformed negatives; actual builds/logs; explicitly untested physical NIC scenarios; known bugs.

**Required final regression matrix:**
```text
E7.1: physical layer VirtIO L2 real RX/TX + negative tests
E7.2: IPv6 + NDP NA + ICMPv6 Echo real host frames
E7.3: native UDP6: 0/1/17/1452-byte payload, checksums,
      concurrent receivers, close/destroy/rebind, malformed/queue/link down
E7.4: dedicated experimental Next Header C API, real RX/TX,
      no interference with NDP/UDP6/ICMPv6
E7.6: no #l/#I/#W/Chan adapter in E7-native linked target
E7.7: no executable IPv4 or IPv4-ARP in E7-native target,
      IPv4 drop in RX + no IPv4 TX, IPv6 NDP still works
Legacy: ordinary 9pc64/9pc64mp + QEMU, E5 9pc64oconsole,
        original E7.1/2/3 opt-in profiles still pass
E6/E8/E9/main: NOT INTEGRATED — document later regression commands,
              do not claim this branch verified merged O-only boot.
SEALED: NOT IMPLEMENTED — no sealed-mode packet filtering/security tests.
E7.5 tunnel: NOT IMPLEMENTED — no encryption, userspace bridge or WG.
```

You may run existing scripts like:
```sh
ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh
IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh
UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh
WHAT=kernel tools/build.sh && tools/test-qemu.sh
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
```
Run and document the **actual new** E74/E76/E77 commands decided above; do not report PASS for missing/unrun tests. Use logs under `build/verification/e78/`. Verify exact target binary symbols; no fabricated counts. Validate response behavior and metadata using the host, not guest “PASS” markers alone.

## Agent checkpoints and reporting discipline

- Work sequentially `E7.4.0 -> E7.4.1 -> E7.4.2 -> E7.6 -> E7.7 -> E7.8`, with small reviewable commits. At each stage produce named report and run the corresponding tests; if its acceptance gate fails, stop, report exact blockers and do NOT proceed with speculative cleanup.
- Update the existing networking architecture docs where the facts change; keep earlier `docs/to_chatgpt_review_e7*.md` reports intact. Don't overwrite generic `docs/to_chatgpt_review.md` or unrelated `docs/STATUS.md`; if automation changes those, preserve the original shared content as agreed in prior runs.
- Do not touch `main` or other branches, including via scripts or hooks. Do not perform **any merge** even when all stage gates pass. The sole requested final handoff is tested E7 branch HEAD + read-only readiness evidence for a **different ChatGPT conversation**.
- On successful completion push ONLY `origin/design/ipv6-only-native-20261024` and verify the remote head. Final response to the human should include concise stage verdicts, commits, actual test results, and links to `docs/to_chatgpt_review_e78.md` + `docs/E7-MERGE-READINESS.md`.

**Ruling:** This plan authorizes native network infrastructure and removal from an **isolated E7 test kernel** only. It does **not** authorize SEALED runtime, encrypted tunnel cryptography, userspace tunneling, production network invisibility, full O-only integration or any merge.
