# E7.2 — OpenCode: first real native IPv6 receive and response path

**ACTIVE assignment. Execute in `design/e72-native-ipv6-20261024` only.**
This branch starts from the completed E7.1 branch `design/ipv6-only-native-20261024`. E7.1 proved real VirtIO L2 TX/RX via `ethercore`; it did NOT prove IPv6, ICMPv6, Neighbor Discovery, or native IP initialization. E7.2 must produce the first **real IPv6 packet-processing vertical slice**, reusing the existing Plan 9/9front IPv6 implementation rather than implementing a second IP stack.

**Concurrency and branch safety are mandatory.** E6 is completed on `main`; E8 is actively pruning unrelated legacy Dev registrations on `main`. Never check out, merge into, rebase, reset, commit to, or push `main`. Do not update E7.1's completed branch or PR #1. Use a dedicated clone/worktree; verify `git status --short`, `git branch --show-current`, `git remote -v`, `git rev-parse HEAD` and upstream before writing. An OpenCode automation that stages/commits/pushes must affect **this branch only**; disable or isolate a hook if it targets `main` or silently pulls another branch. No force-push. If any unrelated worktree modification is present, stop before overwriting it.

**Integration rule:** Do NOT merge E6/E8 into this implementation branch while E8 is active. The final integration into the approved O-only server kernel is a separate, later review gate. The agent must record concrete E6/E8 merge conflicts and an integration test plan, not pretend this isolated branch already proves `pc64onativedisk` or E8's pruned configuration. Preserve E7.1's default/legacy kernels. Do not alter `docs/to_chatgpt_review.md` (E6/E8 ownership) or global `docs/STATUS.md`. Write the E7.2 report separately to `docs/to_chatgpt_review_e72.md`.

## Objective and exact evidence boundary

Prove this *real* incoming and outgoing hardware-driven path in an opt-in amd64 test profile:

```text
QEMU VirtIO NIC real RX
  -> driver RX / etheriq(Ether*, Block*)
  -> E7.1 EtherRxSink (IRQ-safe, bounded handoff)
  -> process-context native IPv6 worker
  -> existing IPv6/ICMPv6/NDP implementation (Fs / Ipifc / ipiput6)
  -> existing IPv6 output, route and neighbor resolution where needed
  -> native Ethernet framing + ethercore_tx(Ether*, Block*)
  -> VirtIO NIC real TX, observed by host
```

**Acceptance requires an observed ICMPv6 Echo Reply AND an observed NDP Neighbor Advertisement (NA) to valid host-originated packets through real VirtIO RX/TX.** Sending/receiving only EtherType `0x86DD` is NOT proof. A synthetic Block/unit fixture is supplemental evidence only. Use deterministic link-local addressing in an isolated QEMU L2 fixture (no tap/bridge, no root privileges) and host-side byte/checksum verification. If genuine reuse of the existing IPv6 core cannot be made safe within the scope below, report **PARTIAL-HOLD**, preserve tested work and explain the smallest missing dependency. Do NOT claim success by inserting a trivial custom echo/NA packet generator that bypasses the existing IP/ICMPv6 stack.

This stage is intentionally **TRANSITIONAL**: legacy `#l`, `#I`, `#W`, IPv4, ARP, UDP and TCP may still be linked in ordinary profiles. Neither “native IPv6-only kernel” nor “all network Dev removed” is an E7.2 completion claim.

## Required source inspection before coding (E7.2.0)

Read `AGENTS.md`, `docs/KERNEL-API-ABI.md`, `docs/GENERAL-SOFTWARE-SPECIFICATION.md`, `docs/ETHER-MIGRATION.md`, `docs/to_chatgpt_review_e71.md`, `docs/CONS-MIGRATION.md` and the CURRENT code. Do not rely on historical line numbers. Inspect at least:

- `sys/src/9/port/ethercore.c`, `devether.c`, `etherif.h`, `netif.c`, `qio.c` and VirtIO `ethervirtio10.c`; identify precisely where hardware reset, attach, IRQ, RX copy, legacy mux, TX queue, wakeup and shutdown occur.
- `sys/src/9/ip/devip.c`: `ipattach` currently initializes `Fs`, `ip_init`, `arpinit`, `netloginit` and `ipprotoinit[]` behind a `Chan` entrypoint. Identify which initialized structures are indispensable for IPv6 and which are genuinely only file-interface policy.
- `sys/src/9/ip/ethermedium.c`: `etherbind` uses `namec/chandial` and opens IPv4, IPv6, ARP `Chan`; `etherread6` strips L2 then invokes `ipiput6`; `etherbwrite` resolves neighbors and transmits via `devtab[Chan]->bwrite`. These are the concrete ingress/egress legacy boundaries; do not call them from the native slice.
- `sys/src/9/ip/ipv6.c` `ipiput6/ipoput6`, `icmp6.c` including NS/NA and Echo handling, `ipifc.c` including `ipifcinit/ipifcadd/ipforme`, `ip.h` `Fs/Proto/Conv/Ipifc/Medium`, IPv6 routing and neighbor-cache code. Inspect address initialization, multicast, NDP hop-limit and checksum validation, lock/context requirements, packet ownership, and the `Proto` receive path.

Produce `docs/IPV6-NATIVE-MIGRATION.md`: a machine-readable, source-backed table with columns
`symbol | source | callers | required_state | init_owner | call_context/locking | Block_ownership | Chan_or_Netfile_edge | native_reuse | test_evidence`.
Include an RX/TX call graph, clear separation of reusable IP packet logic from `#I` filesystem policy, and exact dependencies on legacy `netifinit` and `etherlegacyrx`. Mark unresolved work `OPEN`; do not rewrite code to make a misleading diagram appear clean.

## E7.2.1 — correct E7.1 issues before attaching a native protocol consumer

Bounded corrections, without redesigning controllers or inventing abstractions:

1. `ethercore_attach` currently publishes `attached=1` before `Ether.attach` completes. Ensure that a concurrent caller cannot observe “ready” while driver rings/workers are still initializing. Define a minimal synchronized detached/attaching/attached lifecycle and failure rollback; respect process vs interrupt context. Verify exactly-once attach in a repeated/concurrent test.
2. `ethercore_tx` checks `qfull` separately from `qpassnolim`, which is not an atomic capacity check. Define and implement an enforceable nonblocking backpressure/ownership contract under concurrent producers, including queue closed and link-down cases. No leaking Blocks, double free or unbounded spin. Inspect actual `qio.c` semantics; do not simply rename an unsafe check.
3. `ethercore_rxunregister` may race an in-flight sink invocation after the lock is dropped. Either provide safe lifetime synchronization, or strictly enforce a mechanically verified quiesced-only unregister and prevent callback/context use-after-free in the E7.2 consumer. Do not block in the driver IRQ path.
4. `ethercore_probe_at` has a possible occupied-slot race and resource leak. Serialize the registry transition, or explicitly isolate/disable unsafe concurrent explicit probes and test the permitted lifecycle. Do not free a partially initialized controller by merely freeing its `Ether*` after driver resources were allocated.
5. E7.1's negative queue test temporarily replaces a live VirtIO controller's `e->oq` pointer while its TX worker can read it. Replace this with an isolated, race-free queue/backpressure unit path. Preserve the real VirtIO TX/RX correlation test.

Keep `#l` working throughout these repairs. Record what was changed, what could not safely be changed, and evidence; no unrelated global `qio` refactor.

## E7.2.2 — native Fs/IPv6 initialization without a file attach

Extract or reuse the existing `Fs`/IPv6 initialization logic behind a **direct kernel C entrypoint**, callable in process context, without `namec`, `Chan`, `Qid`, `Dirtab`, `devattach` or `ipdevtab.attach`. Keep `ipattach` as a thin legacy entrypoint that delegates to the same idempotent initialization where possible. Preserve IPv6 `Proto` registration, ICMPv6, `Ipifc`, routing/self/neighbor state and all invariants required by `ipiput6` and `ipoput6`.

Use existing `Fs`, `Proto`, `Ipifc`, `Medium`, `Block` and `Queue` semantics; do **not** introduce a parallel “native IPv6” protocol stack, generic object/device framework, fake process namespace, synthetic `Chan` wrapper, new OID/Space layout, or userspace ABI. A few narrowly scoped functions and structs are acceptable. IP version-specific legacy code may remain linked for this transition, but the demonstrated native ingress and egress MUST NOT dispatch IPv4/ARP.

Prove the init operation is idempotent: no double `Fs`, duplicated `Proto` registrations or leaked state after a second call. A test profile may opt in after scheduler startup; never run sleeping `attach`/IP setup from interrupt context or an early boot stage lacking `up`.

## E7.2.3 — native Ethernet-to-IPv6 medium and safe worker

Implement the minimum typed native adapter connecting E7.1's `EtherRxSink` to the existing IPv6 stack:

- The callback may execute under IRQ on inherited NIC drivers. Validate only cheap L2 properties and enqueue owned frames in a **bounded, IRQ-safe** queue; do not call `ipiput6`, sleeping locks, name service, or blocking allocators inside an IRQ callback. Count rejected/overfull frames accurately.
- The worker owns each dequeued `Block`; accept valid EtherType `0x86DD` only, check minimum lengths and Ethernet destination (own unicast / required IPv6 multicast), remove the Ethernet header exactly once, then hand ownership to the canonical `ipiput6(Fs*, Ipifc*, Block*)` in process context with its required locking. No duplicate/free-after-transfer.
- Build one native IPv6 `Ipifc` backed by the existing `Ether*`, with a deterministic test-only link-local address and appropriate multicast/neighbor state. Any production address policy or userspace interface is `OPEN`. Do not call the legacy `etherbind` `namec/chandial` path.
- IPv6 output must use a native medium callback that constructs a complete Ethernet frame and calls `ethercore_tx`. Reuse existing route/ND logic (including Neighbor Solicitation and Advertisement) rather than bypassing it with permanent fake neighbor entries. Preserve correct EtherType, MAC destination, MTU, checksums, and Block ownership on TX success/failure. Do not route replies through `devtab[Chan]->bwrite`, `etherwrite` or a `Netfile`.
- The E7.1 compatibility path still receives its own copy for legacy profiles. Avoid duplicating native/legacy IPv6 consumers in the E7.2 test configuration; report explicitly that the legacy adapter is still linked and called. Do not claim that `ethercore.c` is fully independent of `devether.c` or `netifinit` until that dependency is genuinely eliminated and tested.

Inspect NDP's real multicast join and routing calls; if they require a `Chan`-only helper, extract the actual concrete function rather than manufacturing a path-based device. A single fixed-purpose consumer is enough, not an extensible subscription framework.

## E7.2.4 — real QEMU VirtIO IPv6 + ICMPv6 + NDP fixture

Add an **opt-in** profile (for example `pc64e72` selected by `IPV6_PROBE=1`) and a narrow test `tools/test-e72-ipv6.sh` / `tools/test_e72_ipv6.py`. Extend E7.1's existing UDP dgram raw-L2/QEMU test approach; do not set up TAP, bridges, host network namespaces or require root. Use Python standard library for host packet generation/verification. Place ignored run logs under `build/verification/e72/`.

Minimum proof, all correlated to the **same actual VirtIO guest**:

1. Native Ethernet controller attached exactly once; native `Fs` and one IPv6 `Ipifc` initialized without a file attach. Record MAC, link-local address, native vs legacy registration and packet counters.
2. Host sends a valid ICMPv6 **Neighbor Solicitation** for the guest's link-local IPv6 address (proper IPv6 destination, multicast MAC, checksum, Hop Limit 255, SLLA option as appropriate); host observes a matching **Neighbor Advertisement** from the guest's real TX path and validates bytes, checksum, addresses, flags and target. Include any necessary host-side NDP state exchange for the reply.
3. Host sends a valid ICMPv6 **Echo Request** to the same guest IPv6 address with a unique identifier, sequence and payload; host observes an **Echo Reply** through VirtIO TX with matching ID/sequence/payload, valid checksum and IPv6 source/destination. Verify the host packet was seen in the native worker, not only legacy `#l`.
4. Prove a bounded native-path `namec/newchan/walk/devwalk/mount/exec` counter window remains unchanged during IP setup, ND and Echo and reply TX. Counters alone do not prove correctness: combine with hardware and IP-level evidence.
5. Negative cases must be **assertions that fail the harness**: no NIC; EtherType `0x0800` must not be consumed by native IPv6; truncated Ethernet/IPv6; bad IPv6 version/payload length; invalid ICMPv6 checksum and invalid NDP Hop Limit; destination not local or subscribed multicast; native RX queue saturation; RX unbind/shutdown safety; TX down/full/closed; repeat init/attach. For any case the existing stack intentionally handles differently, document the verified behavior and adapt the negative to the real protocol contract, never silently delete the check.
6. Retain and rerun the E7.1 real native TX/RX + legacy `#l` behavior and default kernel boot. Verify there is no panic, use-after-free or resource exhaustion. A fixture that only greps “PASS” log strings without cross-checking host bytes is insufficient.

Use proper ICMPv6 pseudoheader checksum, not an ICMPv4 checksum. Use fixed local link-layer test addresses within this fixture only; do not accidentally require IPv4 on the Plan2001 guest because QEMU uses localhost UDP as the **host-side transport for Ethernet frames**.

## Strictly out of scope for E7.2

- No full native UDP6/TCP6 connection manager, listener/stream/message userspace API, socket compatibility layer, WireGuard migration, routing daemon, DNS, DHCPv6, router support or new network config language.
- No final removal of `etherdevtab`, `ipdevtab`, `wgdevtab`; no global deletion of IPv4 or ARP sources; no claim that the final O-only image is IPv6-only. That requires later isolated linkage and runtime proof.
- No changes to E6 disk `sdcore`, E8 Dev pruning, OID/Space persistence, MicroPython interpreter/ABI, kernel filesystems, or unrelated architectures. Do not break the ordinary `pc64`, `pc64mp`, `pc64native`, `pc64oconsole` or legacy `#I` behavior.
- No merge/rebase of an actively changing `main` during this task. Cross-branch integration with E6/E8 requires a separate clean review and complete O-server regression matrix after the parallel work finishes.

## Required delivery, test gates and report

Use reviewable commits for `E7.2.0` audit, `E7.2.1` lifecycle/ownership repairs, `E7.2.2` native IP initialization, `E7.2.3` native IPv6 medium, `E7.2.4` real QEMU fixture and final report. If a step is blocked, stop broadening the scope; keep only source-proven, runnable checkpoints. No fabricated success or unexplained test skips.

Deliver:
- `docs/IPV6-NATIVE-MIGRATION.md` containing the exact source/ownership/context map, native and legacy call graphs, proof constraints, failure cases, and later IPv6-only/UDP/WG cutover dependencies.
- Minimal kernel C/header and build changes in the E7.2 branch; opt-in test fixture; preserve E7.1 fixture.
- `docs/to_chatgpt_review_e72.md` with headings:
  `VERDICT (APPROVE / PARTIAL-HOLD / REJECT)`,
  `BRANCH / BASE / COMMITS`,
  `E7.1 HARDENING`,
  `Fs INITIALIZATION`,
  `NATIVE RX/TX OWNERSHIP`,
  `ICMPv6/NDP REAL HARDWARE EVIDENCE`,
  `NEGATIVE CASES`,
  `CHAN COUNTERS`,
  `LEGACY REGRESSIONS`,
  `TEST COMMANDS / LOG PATHS`,
  `NOT RUN / OPEN`,
  `E6/E8 INTEGRATION RISKS AND LATER GATE`.
- Commands and observed outputs for actual kernel build(s), real QEMU test(s) and original E7.1/default regressions. Explicitly distinguish test results **executed by the agent** from earlier E7.1 report results; ignored build logs are local, not published Git evidence.

**APPROVE** only if the branch demonstrably boots the test profile, sends real NDP NA and ICMPv6 Echo Reply from reused native IPv6 code over VirtIO with host verification, has no `Chan`/`Netfile` dispatch on the demonstrated native IP chain, passes negative tests, and preserves E7.1/default legacy behavior. If any mandatory proof is missing, use **PARTIAL-HOLD**; do not relabel raw Ethernet delivery as protocol support.

At the end, verify branch/upstream, commit and push **only** `origin/design/e72-native-ipv6-20261024` using the existing OpenCode automation as appropriate. Never merge PR #1 or write to `main`.
