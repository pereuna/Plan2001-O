# E7.3.1 — OpenCode: UDP6 API hardening (same E7 branch)

**ACTIVE implementation task, not another branch.** Continue **only** in `design/ipv6-only-native-20261024`. The E7.3 native UDP6 functional PoC has been delivered; this is a narrowly scoped post-review correction before E7.4/WireGuard. Preserve its proven hardware path, tests and ordinary legacy kernels. This assignment supersedes the completed E7.3 assignment in this file. Its name “E7.3.1” denotes the **new UDP6 API hardening stage**; do not confuse it with the previous E7.3.1 lifecycle checkpoint already listed in the E7.3 report.

**Before editing:** check `git branch --show-current`, `git status --short`, `git rev-parse HEAD`, upstream, and `git remote -v`. If the working tree has other changes, reconcile without overwriting. Commit/push only `origin/design/ipv6-only-native-20261024` with no force-push. Do **not** create branches or switch to, reset, rebase, cherry-pick or merge `main`; E6/E8/E9 work is separate. Do not touch PR #1 or the mistakenly created `design/e72-native-ipv6-20261024` branch. Agent hooks must not update `main` or replace `docs/to_chatgpt_review.md`.

**Read first:** `AGENTS.md`, `docs/KERNEL-API-ABI.md`, `docs/GENERAL-SOFTWARE-SPECIFICATION.md`, `docs/UDP6-NATIVE-MIGRATION.md`, `docs/IPV6-NATIVE-MIGRATION.md`, `docs/to_chatgpt_review_e73.md`, `docs/to_chatgpt_review_e72.md` and actual current sources. Use the code, not estimated line numbers, for final contracts.

## Goal

Make the **existing** `Udp6Endpoint` kernel C API safe for concurrent datagram receivers, close versus send/recv, bounded reusable endpoint lifetimes and synchronous transmit error handling. The final native path remains:

```text
VirtIO NIC -> etheriq -> native IPv6 worker -> inherited udpiput
  -> inherited UDP Proto/Conv (headers=7, Qmsg receive)
  -> udp6_recv / udp6_sendto
  -> inherited udpkick -> ipoput6 -> native medium -> ethercore_tx
```

**No new UDP stack or file-shaped interface.** Keep `udpinit`, `udpiput`, `udpkick`, `Proto`, `Conv` and existing 52-byte UDP headers=7 envelope; `Udp6Msg` remains one complete Message/datagram (including a zero-length payload) plus peer/local IPv6/port metadata. Do not add socket/fd/`Chan`/`Qid`/`walk`/`Netfile` API, userspace ABI or WireGuard. Maintain native IPv6-only handling and ordinary legacy `#I` UDP4/UDP6 behavior. Do not run E6/E8/E9 integration here.

## 0. Mandatory audit and invariants

Inspect:
- `sys/src/9/ip/nativeudp6.c` and `nativeudp6.h` in full (`udp6_open`, `udp6_recv`, `udp6_sendto`, `udp6_close`, `udp6_stats`, `udp6_setlimit`, `udp6_pending`);
- `sys/src/9/ip/udp.c`: `udpiput`, `udpannounce`, `udpcreate`, `udpclose`, `udpkick`, hash lookup and `Qmsg` ownership;
- `sys/src/9/ip/devip.c`: `Fsprotoclone`, `closeconv`, `setluniqueport` and how `Conv` slots are reused by later `Fsprotoclone`;
- `sys/src/9/port/qio.c`: `qget` is an **atomic nonblocking dequeue** under the Queue lock; `qbread` can wait indefinitely for data; `qcanread` is only an observation, not an atomic read reservation; `qclose` discards queued Blocks; `qpass` consumes or frees its Block, and `qbwrite(qbypass)` invokes the callback synchronously;
- `sys/src/9/ip/nativev6.c` start/stop state machine and its current one-shot lifetime contract;
- `sys/src/9/pc64/e73udpprobe.c` and `tools/test_e73_udp6.py`.

Write a small lifecycle/ownership table into `docs/UDP6-NATIVE-MIGRATION.md` with columns `operation | permitted_state | locks / wait context | owns_on_success | owns_on_error | close/destroy race behavior | evidence`.

Specify whether functions may be called from the interrupt path (they should not), and whether concurrent calls on a *live, not yet destroyed* endpoint are supported. Explicitly distinguish an endpoint's logical CLOSE from memory RELEASE/DESTROY. A closed pointer is valid only until destroy. Access after destroy is invalid and MUST NOT be tested as repeat-close.

## 1. Fix atomic UDP Message receive and timeout semantics

**Source-backed bug:** `udp6_recv()` does `qcanread(ep->conv->rq)` then `qbread()`. Two receivers can both observe ready; the first removes the only Message and the second blocks indefinitely in `qbread`, ignoring `timeout_ms` and preventing clean shutdown.

Requirements:
1. Replace that check-then-blocking-read operation with an **atomic nonblocking dequeue**, preferentially the existing `qget()`. No `qbread` following `qcanread`. The Queue lock must make the dequeue linearizable between two readers.
2. Wait only in process context while no item exists; use a bounded sleep or proper producer notification so a specified timeout is enforced. Avoid spin loops; use a monotonic wrap-safe deadline, document how `timeout_ms=0` and `timeout_ms=~0UL` are interpreted. If a precise deadline cannot be implemented from current kernel clocks, show the actual resolution/guarantee; do not claim a strict timeout with an unbounded blocking primitive.
3. Preserve one full `Qmsg` record per successful return; retain 52-byte envelope metadata, IPv6 addresses, source/destination ports, correct Block ownership, **zero-length payload** as valid, and out-of-order arrival when multiple readers dequeue different packets. Exactly one receiver may own each Message.
4. Make `close` wake receivers and cause a deterministic `Udp6ErrClosed` (not spurious timeout or forever sleep); no read of a recycled `Conv` slot, freed Queue or endpoint storage. Correctly maintain `recvactive` on all error paths, including `waserror`/`nexterror` cases where inherited queue helpers can raise.
5. Test two+ simultaneous receivers and a single available datagram; the losing receiver must time out (or report closed when explicitly closed) without hanging. Test two simultaneous receivers and two distinct datagrams: each is received exactly once. Include `0`-length data, poll, short timeout, long timeout, close-during-wait, and repeated negative/positive cycles.

## 2. Make close linearizable and safely reusable

**Source-backed bug:** `udp6_close()` currently sets `closed` then calls `closeconv()` **before** waiting for `recvactive==0`. `closeconv` resets `Conv` and makes its slot eligible for reuse while a previous receiver may still access `ep->conv->rq`. This is a race against later `Fsprotoclone`.

Requirements:
1. Establish an explicit state transition (e.g. OPEN -> CLOSING -> CLOSED -> DESTROYED; different names acceptable). Under a documented lock/atomic discipline: reject new operations once CLOSING starts, quiesce in-flight sends and receives, wake waiters, and do not call `closeconv` / recycle `Conv` until **all old users are out**. Avoid holding a `QLock` across a callback or waiting operation that needs it to exit.
2. Closing must be idempotent in effect. The **existing logical API's** second `udp6_close` on a still-allocated CLOSED endpoint must return `Udp6ErrClosed` (retain earlier E7.3 regression expectation). If shutdown times out before quiescence, return `Udp6ErrBusy` and retain a recoverable CLOSING state; a later close must be able to finish, not incorrectly treat CLOSING as fully CLOSED.
3. Serialize against `udp6_sendto` including its pre-lock reads of `ep->net`, `ep->conv` and interface MTU; against `udp6_recv` including queue pointer access; and against `udp6_stats/pending/setlimit`. Never dereference a `Conv` that may already have been reassigned.
4. Record explicitly which party owns the last reference to an endpoint. The echo-worker owner must stop and join workers before destroying; do not create impossible “safe access after free” semantics for arbitrary stale C pointers.
5. Demonstrate that a new endpoint can immediately rebind the **same** IPv6 address/port after the old close completes and receive/send normally with a reusable inherited `Conv`. No stale packet from a previous endpoint may enter the new endpoint; permit discard of queued old datagrams at close.
6. `ipv6native_stop` must refuse or defer teardown while live UDP6 endpoint operations can still reach the same `Fs`/`Ipifc`. The E7.3 fixture normally closes UDP endpoints before IPv6 stop; make that ordering mechanically enforced or explicitly documented with a safe guard, not merely a test comment.

## 3. Reclaim Udp6Endpoint memory without stale-pointer tricks

**Source-backed bug:** `udp6_open` allocates an `Udp6Endpoint` with `smalloc` and the current `udp6_close` never frees it. Repeated service restarts cause unbounded endpoint allocations even if `Conv` slots are reused.

Keep the ability to call `udp6_close(ep)` twice while the endpoint is still allocated **and** reclaim memory safely. Preferred small solution: retain `udp6_close` as a logical shutdown and add an explicit owner-only `udp6_destroy(Udp6Endpoint **pep)` (or equivalent) that requires CLOSED/quiesced state, frees the wrapper once and sets the caller-owned pointer to `nil`. It must not free `Conv` or queues still managed by the inherited `Proto`; `closeconv` already owns that logical transition. An alternative is permissible if it is equally precise and tests retain meaningful repeat-close-before-dispose semantics.

- Precisely state who may call destroy, how concurrent users have exited, and what happens to stale aliases. If the kernel lacks reference-counted handles, **do not promise stale raw-pointer calls are safe after destroy**.
- Eliminate possible leaks on `udp6_open` partial-failure paths (e.g. clone/announce errors); use existing `closeconv` conventions where valid, and no accidental leaked successful `Conv` on later failure.
- Count successful endpoint allocations and releases (a focused test counter is sufficient; no broad allocator instrumentation). Prove bounded live endpoint count after **hundreds of sequential open/close/destroy/reopen** operations at one and multiple ports, and no accumulated active UDP `Conv`, Qmsg queues, callbacks or workers.
- Refresh `udp6_stats` contract: while CLOSED but not destroyed, return endpoint-owned counters safely without reading a recycled `Conv`. After destroy, access is invalid; tests use the cleared owner pointer.

## 4. Repair send error, exception and ownership semantics

**Source-backed bug:** `udp6_sendto` holds `ep->lk` and calls `qbwrite(ep->conv->wq, nb)` (where `wq` is `qbypass(udpkick, c)`). The inherited send path can raise a Plan 9 kernel `error`, long-jumping past `qunlock`. It may also consume `nb` during `udpkick`. Treat both locking and two-Block ownership explicitly.

Requirements:
1. Ensure **every** error/exception path releases all locks and does not leave a half-closed endpoint. Use `waserror/poperror/nexterror` correctly; inspect the actual `qbwrite` and `udpkick` Block ownership path and avoid both double-free and leak of the *private envelope Block*. The original caller `payload` must never be accidentally consumed on a reported failure.
2. Keep the contract that a successful call consumes the caller payload, while an ordinary returned error leaves it caller-owned. If errors can happen **after** the internal `qbypass` accepted ownership of the envelope, expose that as a clearly documented “accepted / outcome uncertain” category rather than incorrectly claiming the original payload was transmitted or falsely freeing a transferred Block. Do not conflate UDP encode/queue acceptance with NIC completion.
3. Implement observable error accounting: the existing `Udp6Stats.txerrors` must be incremented for appropriate unsuccessful API sends (it is currently never incremented). Distinguish rejected arguments, CLOSED, MTU overflow, no route, link down and downstream queue failures **to the extent they can be determined safely**; mark asynchronous delivery outcomes explicitly rather than fabricate them.
4. No global rewrite of `qbwrite`, `qio.c`, UDPv4 code or unrelated send paths. If a narrow helper in the inherited UDP code is necessary to turn a nonlocal error into a typed native result, it must reuse `udpkick`/`ipoput6` and preserve legacy `#I` behavior.
5. Prove a deliberately triggered synchronous error (e.g. controlled route failure or other source-backed `error` path) leaves the endpoint unlocked and usable for a subsequent successful send. Test close racing against send and no UAF, no lockup or lost ownership. Keep a real NIC link-down case separate: the existing API may report accepted even if native Ethernet later drops, and this distinction must be truthful in docs/tests.

## 5. New deterministic concurrency/regression fixtures

Extend the **same** opt-in `pc64e73` profile with focused C-side test workers and host-side `tools/test_e73_udp6.py` cases, or add a clearly named `tools/test-e731-udp6-hardening.sh` that invokes the same kernel/guest and host-L2 testing machinery. **No new branch** and no TAP/bridge/root requirement. Real VirtIO/IPv6/UDP6 response path must remain used for positives. Synthetic/private-queue checks may be used only to force concurrency/errors that cannot be reproduced deterministically on real NICs.

Required failing-on-error checks:

- **Two-reader single-message race:** both readers start together, one real incoming datagram, exactly one success and one timely timeout. Use a deterministic gate/barrier as far as practical, retry many times; log timeout maximum. A false PASS caused by never overlapping receivers is unacceptable.
- Two-reader two-datagram test with distinct payload and ports: each Message delivered exactly once, no length/metadata corruption.
- Close-during-blocked-recv: no infinite wait, no recycled-`Conv` access, one consistent close status, restart/rebind after close and subsequent host UDP echo still work.
- Close-while-send-active: use controlled scheduling, confirm the send is either accepted-before-close or rejected-after-close, never a half-consumed Block or stuck `QLock`. Injection/fault test must exercise *real* exception unwinding.
- Repeated endpoint create/bind/close/destroy/rebind (at least 200 iterations) with allocation/free counters balanced and peak live count bounded; include an occasional outstanding read and outstanding queued Message.
- Post-close `recv` and `sendto` return `Udp6ErrClosed` while wrapper remains allocated; second close returns `Udp6ErrClosed`; destroy sets owner pointer nil; **do not call via freed aliases**.
- UDP6 integrity remains: real VirtIO echo with payload lengths `0, 1, 17, 1452` and rapid distinct datagrams from multiple ports; NDP, valid IPv6/UDP checksums, no port cross-talk.
- Negative packets continue to be dropped: zero/bad UDP6 checksum, UDP length malformed, unbound port ICMPv6 behavior, IPv4 EtherType, RX queue saturation, link down.
- A failed/close-interrupted send must leave a subsequent valid send working; record exact result codes and ownership.
- Record native `namec/newchan/walk/devwalk/mount/exec` counter delta for bind/read/send/close: zero on demonstrated native path.

Add precise safety instrumentation (endpoint state, in-flight readers/senders, allocation/free counts, `Conv` identity/slot reuse and selected trace points). Host tests must assert outcomes and fail on guest panic, hang, wrong byte/checksum/port or missing evidence. Don't assert a false “memory leak fixed” based only on single-boot success.

**Run after hardening:**
```sh
UDP6_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e73-udp6.sh
IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh
ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh
WHAT=kernel tools/build.sh && tools/test-qemu.sh
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
```

An additional dedicated hardening script is acceptable, but may not replace the original E7.3 hardware fixture or E7.1/E7.2/legacy regression gates. Store ignored logs under `build/verification/e731/`. Include exact commands, environment, actual PASS/FAIL and distinguish rerun from earlier historical reports. The code review and report must not claim that KVM testing proves absence of all scheduling races; deterministic injection/stress increases confidence but does not replace explicit lock correctness.

## 6. Scope, delivery and acceptance

**Do not** add a userspace socket/MicroPython networking API, TCP6, WireGuard, TLS, IPv4 native support, networking device objects, path/namespace compatibility wrappers, full `Fs` destructors, E6/E8/E9 integration, or change OID/Space/kernel boot. `IPv6Native` remains a one-shot PoC if its inherited `Fs` workers cannot be safely destroyed; this does not excuse an unbounded per-endpoint leak.

Reviewable commits for:
1. `E7.3.1a` operation/ownership audit and tests that reproduce the races;
2. `E7.3.1b` receive and timeout fix;
3. `E7.3.1c` close/Conv quiescence, explicit destroy and lifecycle;
4. `E7.3.1d` send/error/ownership repair;
5. `E7.3.1e` hardware/concurrency regressions and report.

Update only the relevant sections of `docs/UDP6-NATIVE-MIGRATION.md`. Keep previous stage reports intact. Write **`docs/to_chatgpt_review_e731.md`** including:

`VERDICT: APPROVE / PARTIAL-HOLD / REJECT`; `BRANCH/BASE/COMMITS`; `REPRODUCED BEFORE / FIXED AFTER`; `STATE & LOCK PROTOCOL`; `RECEIVE TIMEOUT EVIDENCE`; `CONV CLOSE/REOPEN EVIDENCE`; `MEMORY ALLOCATION/RELEASE COUNTERS`; `SEND ERROR/Block OWNERSHIP`; `REAL VIRTIO DATAGRAM EVIDENCE`; `E7.1/E7.2/E7.3 REGRESSIONS`; `COMMANDS/ACTUAL LOGS`; `NOT RUN/OPEN` and `LATER E7.4 DEPENDENCIES`.

**APPROVE** only when all four source-backed E7.3 defects are addressed (atomic receive, close quiescence/Conv reuse, reclaimable endpoint memory, exception-safe send/error/Block ownership), concurrency tests assert their intended interleavings and complete, the real VirtIO UDP6 fixture still passes, and the earlier E7.1/E7.2/default gates stay green. Otherwise report **PARTIAL-HOLD** with precise blocker and do not propose the UDP6 API as a safe production WireGuard transport.

Finally verify current branch/upstream and commit/push **only** `origin/design/ipv6-only-native-20261024`. Never merge or push `main`.
