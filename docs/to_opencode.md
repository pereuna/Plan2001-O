# E7.1 — OpenCode: native Ethernet kernel C boundary (parallel to E6)

**ACTIVE TASK FOR THIS BRANCH ONLY. Implement E7.1, verify what you actually changed, commit/push verified checkpoints, and write an agent-readable completion report.** Do not implement the whole E7 networking stack, an IPv6-only runtime claim, or E6's disk migration in this task.

## Repository, branch and parallel-work rules — read first

- **Repository:** `pereuna/Plan2001-O`
- **Required branch / push destination:** `design/ipv6-only-native-20261024`. This branch already carries the accepted IPv6-only **target decision** in `docs/GENERAL-SOFTWARE-SPECIFICATION.md`. The branch originally forked from `1c61dd175c0757e5eaed016c1a7305f7ccad5c91` and has a later specification commit `d71d9794d72ff7b91a3da7d9d553f09c64035e0b`. Verify current HEAD/merge base yourself.
- **E6 agent is concurrently editing/pushing `main`.** NEVER check out, merge, rebase onto, commit to, or push `main` from this E7.1 run. Never overwrite or update `docs/to_opencode.md` on `main`. Do not merge this branch's draft PR #1.
- **Use a separate physical Git worktree or clone.** Running a second OpenCode session in the same worktree as the E6 agent is NOT safe, even on different branches. Before touching code, check `git status --short`, `git branch --show-current`, `git remote -v` and `git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'`. Abort if the local branch/upstream is not the required E7.1 branch or if another task's uncommitted files are present. If E6 shares the working tree, create a **separate clone** of the exact E7.1 branch, run OpenCode there, and leave E6's checkout untouched.
- **Hooks:** the existing OpenCode JS automation may run `git add .`, commit, and `git push`. It MUST publish ONLY to `origin/design/ipv6-only-native-20261024`. If a hook uses explicit `origin main` or automatically pulls/merges `main`, do not allow the hook to run with that configuration; isolate/disable that hook in the E7.1 worktree before execution. Never force-push. Perform a final branch/upstream check before the automatic push.
- **Merge policy:** E7.1 is a branch-local implementation. Integration with E6's eventual combined O-only kernel is **E7.2+**, after E6 is approved. Do not alter E6's acceptance results.

**Authoritative context:** `AGENTS.md`, `docs/KERNEL-API-ABI.md` (canonical vocabulary), `docs/GENERAL-SOFTWARE-SPECIFICATION.md` (new IPv6-only target), `docs/STATUS.md` (what is actually proven), `docs/KERNEL-OPMAP-NOTES.md` (historical hints; verify source), `docs/CONS-MIGRATION.md` (E5 pattern). Read the entire current Ethernet sources before editing.

## Goal and explicitly limited scope

**E7.1 GOAL:** extract and **actually execute** a direct, narrow, native **kernel C Ethernet lifecycle + frame data interface** beneath the existing `#l` legacy adapter. Reuse `Ether`, `Netif`, `Block`, `Queue`, controller-specific operations and registration callbacks when their semantics are correct. Do NOT replace them with a new file abstraction or artificial `NativeDev.open/read/write/close`. Keep the legacy `etherdevtab` fully functioning in existing builds.

Specifically demonstrate:
1. A native, independently callable controller discovery/initialization and lookup path, not just `etherdevtab.reset` renamed. Single initialization per controller, correctly sequenced after PCI/IRQ/memory requirements. No premature device attach in interrupt/`up == nil` contexts.
2. Native **Ethernet frame receive and transmit** boundaries that take/produce concrete `Block` payloads, have documented ownership, valid frame length/EtherType behavior, and do **not** require `Chan`/`Qid`/`Dirtab`/`Netfile` **in the native public C API** or their executed native callback/dispatch chain. Preserve the legacy `Netfile` multiplex/bridge/filter path separately; do not silently disable it.
3. A bounded real QEMU **VirtIO Ethernet** probe covering controller initialization and at least a genuine hardware TX/RX path if an isolated fixture can safely stimulate both directions. Separate hardware evidence from any injected `Block` unit test; do not label a fabricated ingress as NIC RX.
4. An exact dependency map of the next boundaries (`#I` IP, UDP/TCP, `#W` WireGuard), identifying what still uses `Chan`. NO functional rewrite of these protocols in E7.1.

**Out of scope:** unregistration/removal of `etherdevtab`, `ipdevtab` or `wgdevtab`; elimination of IPv4 symbols; new TCP/UDP socket or Handle ABI; IPv6 routing/NDP complete test; WireGuard cryptographic changes; changing D2b persistence or E6 SD core; physical NIC validation. At E7.1 completion the default and opt-in kernels may still link legacy IPv4, ARP and three network `Dev` tables: name this status **TRANSITIONAL**, never IPv6-only implemented.

## Exact source observations to confirm, not hand-wave

All observations below are from the pre-E7.1 branch; re-evaluate current C before assuming unchanged.

- `sys/src/9/port/devether.c` (~950 lines) combines `etherdevtab`, `etherreset()`, `etherprobe()`, `addethercard()`, `etheriq()`, `etheroq()`, `ethermux()` and IPv4-only `netconsole()`. `etherreset` currently probes cards via `cards[].reset`, installs `Ether.oq = qopen(... Qmsg|Qkick ..., ether->transmit, ether)`, calls `netifinit` and enables legacy IPv4 `netconsole(1)`. Do not assume controller reset and IP configuration are the same event.
- `Ether` in `sys/src/9/port/etherif.h` contains concrete hardware operations (`attach`, `transmit`, `ctl`, `shutdown`), MAC/MTU/link, `Queue *oq`, and an embedded `Netif`. Distinguish its physical controller state from a legacy `Netfile` subscription. The output `Queue` is a buffer; an Ethernet **frame** is a length-delimited `Message`; neither is a TCP `Stream`.
- The RX driver entry `etheriq(Ether*, Block*)` calls filtering/DMAT and `ethermux`; `ethermux` currently selects and delivers to legacy `Netfile.f[].in` subscriptions. This is a **real legacy dependency**, even though `etheriq` itself takes no `Chan*`. Do not claim a fully independent native RX datapath while its only sink is `Netfile`.
- `etheroq` and `etherwrite` send via `ethermux` and `qbwrite(ether->oq, bp)`. The `Qkick` transmit callback is installed by `etherprobe`, so a successful enqueue is not by itself a proven NIC transmit. Preserve frame ownership on rejection, copy-on-write, queue backpressure and link state; avoid unbounded spinning or use-after-free.
- `sys/src/9/port/netif.c` (~738 lines) combines `Netfile` state/permission/multicast control with ``netifwalk/open/read/write/close` using `Chan`/`Qid`. A native consumer must not call these legacy file helpers. Keep legacy rights/modes, exclusivity, bridge, bypass, promisc, multicast and queue close behavior intact.
- `sys/src/9/pc/ether8169.c`, `ether82563.c`, `etheri225.c`, `sys/src/9/port/ethervirtio10.c` and `etheriwl.c` register via `addethercard(...)` and invoke `etheriq` on receive. Keep their controller firmware/DMA/IRQ behavior unchanged unless a narrowly justified fix is required. Intel Wi-Fi firmware may use inherited file lookups, so **do not** claim Wi-Fi works without a filesystem in O-only. QEMU VirtIO is the only required real NIC for this stage.
- `devether.c`'s `netconsole()` is an IPv4 UDP utility. **Classify it LEGACY-ONLY** and keep it operational in old builds; do not transfer it to native IPv6-only API, confuse it with E5's UART diagnostics, or break `print/iprint/panic`.
- `sys/src/9/ip/devip.c` initializes `Fs` through `ipattach`; `sys/src/9/ip/ethermedium.c` opens `#l` paths via `namec`/`chandial` and uses legacy `devtab[]->bread/bwrite`. `sys/src/9/ip/devwg.c` calls `namec("/net/udp/clone",...)` and reads via `Chan`. This is E7.2+ work, **audit only**. `ip.h` has `Fs`/`Proto`/`Conv`/`Medium` and existing `Queue` data paths. Do not replace working protocol machinery or use IPv4-specific conversion in the native API.
- Current D2b server test normally boots with `-nic none`. A successful D2b storage boot does NOT prove networking. `tools/wgtest.sh` labels itself a historical legacy CPU-server test with unavailable old root, not a native O-only WG regression.

## E7.1.0 — baseline audit and proof obligations

Before code edits, create `docs/ETHER-MIGRATION.md` as a **single agent-readable operation map**, with source/function/consumer/ownership/lifetime and a status per entry. Include at least:

- `etherreset/etherprobe/addethercard`, registry `etherxx[]` and `cards[]`, `etherattach`, `Ether.attach/transmit/ctl/shutdown`, all active controller reset/probe callbacks, netconsole-on-reset, controller shutdown;
- `etheriq`, `ethermux`, `etheroq`, `etherwrite/etherbwrite`, `Netif/Netfile`, `netifinit/open/close/read/write`, `qopen(Qmsg|Qkick)` and TX ownership;
- `dmatproxy`, multicast/promisc/bypass/bridge, frame copying, NIC IRQ RX, enable/attach ordering and drop accounting;
- the three legacy `Dev` tables (`etherdevtab`, `ipdevtab`, `wgdevtab`) and exactly where the IP-to-Ethernet and WG-to-UDP paths traverse `namec/chandial/devtab/Chan`;
- nonlegacy or unrelated network paths (loopback medium, native `ipoput4/6` packet processing, existing `SDifc` etc.) as context only.

Use a table with columns:
`symbol | source | current_callers | semantic_owner | input/output | allocation_ownership | call_context/locking | Chan_or_Netfile_edge | E7.1_target | legacy_compatibility | evidence`.

**Audit gate:** distinguish (a) concrete native frame operations, (b) legacy multiplexer policy, (c) IP-specific processing, and (d) hardware controller operations. Do not assume that a function is Chan-free just because its signature omits `Chan*`. Mark unresolved ownership/callback choices as OPEN, not "implemented."

## E7.1.1 — introduce the direct Ethernet C core

Separate independent hardware/controller registry/lifecycle from `etherdevtab`. A small `ethercore.c` next to `devether.c` is a reasonable outcome, but code ownership may differ if the existing implementation reveals unavoidable coupling. Prefer an **actual independent compiled core** rather than a new generic object framework, large generated wrappers or unrelated code movement.

Core must own or directly implement:
- controller registration/probe, stable in-memory `Ether*` lookup for the native kernel, and exactly-once initialization; explicit errors for absent devices, preinit calls and invalid indices;
- controller-specific `reset/attach/transmit/shutdown` using the existing function pointer semantics;
- MAC, MTU, link, output `Queue` and core stats in their real structures;
- direct frame TX using `Block` with a documented transfer-of-ownership rule, actual queue/backpressure and eventual `Ether.transmit` kick, independent of a legacy `Chan` endpoint;
- direct frame RX dispatch, clearly separating **native frame subscriber/delivery** from legacy `Netfile` demultiplexing.

For the E7.1 native RX path use the smallest **explicit, fixed-purpose** mechanism suitable for one kernel networking consumer (e.g., an Ether RX callback with strictly defined registration/ownership/IRQ behavior), **not** a universal class, automatic copy for every network protocol, unbounded publisher/subscriber bus, global user-visible Handle scheme, or callback accepting a `Chan*`. Specify whether RX is IRQ context or worker context. Do not take sleeping locks or allocate unsafe memory in IRQ; copying or deferring into a `Queue` may be necessary if the actual driver invokes `etheriq` under interrupt constraints. If the existing driver path cannot safely meet a direct callback's lifetime contract, implement a bounded deferred path and document it.

**Ownership invariants required:** exactly one owner of every ingress/egress `Block`; precise behavior when RX delivery is absent/full, TX length invalid, carrier is down, queue full, driver not enabled, and shutdown/unbind races. Preserve EtpType and L2 framing; ensure IPv6 EtherType 0x86DD is not silently interpreted as an IPv4 address or converted. At E7.1 a raw Ethernet frame being accepted is **not** proof that the IPv6 stack accepted the packet; likewise legacy receiving IPv4 remains transitional, not a policy violation in this development build.

If full datapath extraction would require reimplementing `Netfile` bridging semantics, leave those policies in the adapter and add the minimal explicit compatibility dispatch needed to retain them. Demonstrate the **native path** not touching `Chan`/`Qid`/`Netfile`; do not claim all legacy code was removed from the resulting binary.

## E7.1.2 — retain exact legacy `#l` functionality

Keep `etherdevtab` registered for all existing kernel profiles in E7.1. Legacy `etherattach`, `etherwalk/stat/open/read/write/bread/bwrite/close/wstat` and `netif.c` must keep access checks, per-`Netfile` state, buffer/polling/offset semantics and closed subscription behavior. Wrap/delegate to the same new hardware/core operations where semantically equivalent, but **do not equate** a legacy `Chan` write (which carries `Netfile` identity and policy) with direct core TX from a trusted kernel caller.

Controller registry and resetting must not occur twice when normal boot calls `chandevreset`. Use the actual boot constraints in `pc64/main.c`. Retain status/formatting, link notifications, `netconsole` legacy option, and power/shutdown logic. If `devether.c` is split, keep old linker source assignments coherent and preserve `netif.c` behavior in legacy; monitor same-name symbols and init races.

**A legacy-compatible kernel must still link, boot and receive/transmit using its previous device mechanism.** If preserving an edge requires a specific `Netfile` compatibility callback, document it clearly; no conversion of existing controller driver's RX `Block` into raw bytes then back purely for cosmetic API shape.

## E7.1.3 — focused verification with actual VirtIO NIC

Use a *separate disposable* QEMU fixture with `virtio-net-pci` (or the repo's already supported VirtIO Ethernet device) and serial output; the existing D2b storage fixture disables NIC so **it is not sufficient**. Do not interact with physical NICs or users' running servers. Do not require old CPU-server `wgtest.sh` infrastructure.

Verify, in the same coherent E7.1 build:
- compile/link the actual new core and existing `etherdevtab` on amd64; preserve default kernel and E5 (E6 is running elsewhere);
- controller discovery, MAC address, init exactly once, ring/queue setup and relevant DMA/IRQ attachment by observing *actual* NIC driver; do not call `etherdevtab.reset` from the native C entry;
- a trusted native caller uses the direct TX frame function, with a host-observable transmitted test Ethernet frame or a driver/hardware completion counter proven to correspond to that frame, **not** merely `qbwrite` success;
- a host-generated Ethernet frame reaches the **real VirtIO RX handler** and the direct native receive sink. A synthetic injected `Block` is useful for isolated ownership/negative tests, but it does not satisfy this hardware-RX criterion;
- negative cases: absent/no controller, invalid frame lengths, full/down queue, and failed native RX registration or rejected/unbound sink; verify bounds and cleanup with actual assertions/markers;
- a minimal legacy `#l` control test (e.g. existing `ether` attach/read with a QEMU card) confirms native refactor did not sever `Netfile` semantics. If an IPv4 legacy test is used, do not present that as IPv6-only evidence.

A small new `tools/test-e71-ether.sh` / `tools/test_e71_ether.py` and opt-in native probe are acceptable; keep tests deterministic with serial markers and fail closed. **Do not introduce a general-purpose Python build system or tool dependency.** Existing `tools/build.sh` may need a small config/build profile addition for an opt-in test, but do not overwrite E6's simultaneous modifications in `main`. Retain a branch-local diff and explain exactly which shared files will need careful merge later. Prefer untouched `tools/test-oboot-server.sh`, `tools/build.rc`, kernel disk configs, `docs/STATUS.md` and `docs/to_chatgpt_review.md` if unrelated to E7.1; these are under E6's active ownership.

Run at least an actual kernel build plus focused QEMU evidence. If host injection/packet capture cannot be made reliable or QEMU unavailable, report `PARTIAL-HOLD` and exact missing gate; do not fake a test PASS. A timeout, test code presence or log grep without a correlated RX/TX marker is not proof of data movement. Keep logs under ignored `build/verification/e71/` and name the exact commands.

## E7.1.4 — IP/UDP/TCP/WireGuard boundary audit ONLY

Without changing `sys/src/9/ip/*` implementation, append to `docs/ETHER-MIGRATION.md` a brief **E7.2+ dependency graph**:

```text
NIC driver -> Ether RX -> legacy Netfile OR native frame sink (E7.1)
IPv6 native candidate: frame sink -> IP6/ICMPv6/NDP -> TCP6/UDP6 (future)
Current legacy: #l -> ethermedium.c namec/chandial/Chan -> ipiput4/6
Current WG: #W -> wglisten("/net/udp/clone") -> Chan -> UDP
```

Show concrete source edges for `ipattach/Fs` init, `etherbind`, `etherread4/6`, `Proto/Conv`, `udpinit`/`tcpinit` and `wglisten/wgreader`. Separate packet-processing reuse from file-namespace initialization. State exact later acceptance conditions:
- native IPv6-only IP core (with working ICMPv6/NDP);
- native UDP6/TCP6 connection management with appropriate `Stream` vs datagram `Message` semantics;
- native WG outer/inner IPv6-only routing;
- eventual new O-only config removing `etherdevtab`, `ipdevtab` and `wgdevtab`;
- eventual exclusion of executable IPv4/ARP from the final kernel **without breaking legitimate shared C code**.

These are **NOT** E7.1 coding or runtime requirements. If proposing a future userspace ABI, mark `OPEN`; do not add syscalls or conflate `OID`, kernel `Ether*` and userspace `Handle`.

## Acceptance gates and reporting

**E7.1 APPROVE** requires:
1. Actual source-backed operation/ownership map covering the above registry, datapath, Netif and three-Dev dependencies;
2. Independent compiled/linked native Ethernet C lifecycle + RX/TX data interface, no synthetic Qid selector, no `Chan`/`Netfile` in its *executed native path*, precisely documented buffering and IRQ/ownership rules;
3. Legacy `#l` behavior preserved in a built and relevant tested standard kernel; E5 no-`#c` profile build preserved when affected;
4. A real VirtIO NIC probe and **observed native TX and RX** in disposable QEMU, with negative cases;
5. No change to the new IPv6-only **target** and no false claim that runtime is already IPv6-only;
6. All commits pushed **ONLY to the E7.1 branch**, without updating `main` or merging PR #1.

If one gate is unresolved, use `PARTIAL-HOLD`, push only stable verified checkpoints and identify exact missing evidence. Do not delete tests, weaken assertions, or label a mock NIC a real NIC to obtain APPROVE.

**Deliverables:** `docs/ETHER-MIGRATION.md` (single agent-friendly map, design and evidence), new or altered C source/header only where necessary, small focused test scripts, and `docs/to_chatgpt_review_e71.md` (dedicated E7.1 report; do not overwrite E6's `docs/to_chatgpt_review.md` in `main`). When editing `docs/KERNEL-API-ABI.md` is necessary, add evidence-backed notes without changing unrelated canonical terminology or binding hypothetical C prototypes as facts. Do not update global `docs/STATUS.md` concurrently with E6; reference exact E7.1 report in the branch and reconcile STATUS only at merge review.

**Final report exact headings:**

```text
E7.1 VERDICT: APPROVE / PARTIAL-HOLD / REJECT
BRANCH / UPSTREAM / BASE / FINAL COMMIT(S):
SOURCE MAP: exact symbols, owners, IRQ/call context and Chan/Netfile edges
NATIVE ETHER CORE: actual functions, files, init and lookup contracts
FRAME RX/TX: ownership, link/MTU, backpressure and Qkick evidence
LEGACY #l: Dev registration and representative behavior tests
VIRTIO QEMU: exact build/boot/network commands, correlated RX and TX observations, log paths
NEGATIVES: rejected bad length, absent/down interface, RX sink/queue error, results
IP/UDP/WG FOLLOW-UP: audited concrete source edges only, not modified behavior
IPV6-ONLY STATUS: architecture target ACCEPTED; implementation still TRANSITIONAL
SHARED E6 FILES / MERGE RISK: list exact paths; no E6 edits on main
TESTS ACTUALLY RUN: PASS / FAIL / NOT RUN with source logs
UNRESOLVED: precise blockers and next bounded action
```

**Commit discipline:** reviewable E7.1 subcommits (`E7.1.0 audit`, `E7.1.1 native core`, `E7.1.2 adapter`, `E7.1.3 QEMU`, `E7.1.4 report`) without deliberately breaking the checked-out kernel. Push to the E7.1 branch only. **No PR merge, no main push, no E6 code change.**
