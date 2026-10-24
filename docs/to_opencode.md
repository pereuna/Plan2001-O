# E7.4.3 — FIX native IPv6 Next Header unregister / re-register race ONLY

**ACTIVE ONE-SHOT CORRECTION ON EXISTING E7 BRANCH. NO MERGE.**

Repository: `pereuna/Plan2001-O`
Branch: **`design/ipv6-only-native-20261024`**, the *same* branch that completed E7.1–E7.8.
This task supersedes the finished E7.4–E7.8 agent plan previously in `docs/to_opencode.md`, but does not authorize any new project phase, branch, integration, or merge.

## 0. Git/scope rules

- Before edits: `git branch --show-current` (MUST equal `design/ipv6-only-native-20261024`), `git status --short`, `git rev-parse HEAD`, `git remote -v` and upstream. Work on this existing branch; if other agents use the checkout, coordinate or use a safe dedicated worktree without creating a branch. Commit and push **only** `origin/design/ipv6-only-native-20261024`. Do NOT checkout, rebase, merge, reset, cherry-pick, open PR or push `main`. Do not run `git merge-tree` as part of this task. Never force-push. Do not touch E6/E8/E9 or the unrelated E7.2 branch.
- Scope is limited to `sys/src/9/ip/nativeinh6.c` and, if justified, `nativeinh6.h`; focused E7.4 probe/tests (`sys/src/9/pc64/e74nhprobe.c`, `tools/test_e74_ipproto.py` and corresponding E74/E76/E77 runners); and a **new** `docs/to_chatgpt_review_e743.md` report. The old E7.4/E7.6/E7.7/E7.8 reports are historical evidence; do not overwrite or retroactively change their verdicts. Do not alter `docs/E7-MERGE-READINESS.md`, `docs/STATUS.md` or `docs/to_chatgpt_review.md`, and do not edit old architecture specs merely to rationalize a behavior.
- Keep current `NORMAL`-only networking, real VirtIO IPv6/NDP, UDP6, Next Header 253 test endpoint, E7.6 no-network-Dev profile and E7.7 IPv6-only profile. **SEALED NOT IMPLEMENTED.** E7.5 userspace tunnel remains deferred. No WireGuard, cryptography, generic `ipmux`, new userspace ABI, IPv4 reintroduction, TCP6 or O-disk changes.

## 1. Precisely reproduced bug (current source)

Inspect exact current code and locks in `nativeinh6.c`, especially:
- `nativeip6_rcv()` validates the packet, acquires `c->lk`, checks `c->registered` and `c->rx`, increments `c->active`, releases the lock, optionally sleeps using `c->delayms`, and *only after sleeping* invokes `c->rx(c->arg, &m)`.
- `nativeip6_unregister()` sets `registered=0` and `unregistering=1`, removes `t2p[253]`, waits up to about 500*10 ms for `activezero(c)`, then **unconditionally assigns `c->unregistering=0`** even if `active>0` and returns `NativeIp6ErrBusy`.
- `nativeip6_register()` rejects `registered || unregistering`, but after the incomplete `unregister` clears `unregistering` it can install a **new callback and argument** while the previous callback is still in-flight. The old callback's eventual `c->rx(c->arg, ...)` may invoke the **new** callback/argument on a packet accepted by the previous registration; the old callback owner also cannot safely release resources and `unregister` cannot be retried while `registered==0` (returns NotReg). This is a specific race; fix it rather than masking it by extending the wait timeout or making test callbacks faster.
- The `Proto` is deliberately retained across unregister to avoid freeing a referenced `Fsrcvpcol` lookup pointer; account for a dispatch that obtains this Proto just before unlinking `t2p[253]` and enters `nativeip6_rcv` after the unregister decision. Audit this boundary, not only `active` callbacks already running. Preserve the single-consumer/single-Fs constraints.
- Verify `ipv6native_stop()` ordering with raw-protocol consumers, and inspect concurrent `nativeip6_send`/`stats` behavior. Fix only concrete race edges needed for correct registration lifecycle.

## 2. Required correct contract

Implement an explicit, reviewable lifecycle such as:

```text
UNREGISTERED -> REGISTERED -> DRAINING -> UNREGISTERED
                     |             |
                     +--unregister--+--(BUSY: STAY DRAINING)
```

Alternative names/state encoding are fine, but prove these invariants:

1. Once unregister starts, prevent all new callbacks from entering the retired registration. Any already admitted callback must finish against **the callback function and arg belonging to that admission**; capture a stable pair under the same lock that increments the in-flight reference, and do not read mutable `c->rx`/`c->arg` after releasing it. Document when the caller may free the old callback `arg` (only after **successful** unregister/quiescence, never after `Busy`).
2. If timeout occurs with `active>0`, return `NativeIp6ErrBusy` **and keep DRAINING latched**. No re-register and no overwriting old `rx`/`arg` until all old callbacks have completed and teardown has been finalized. No automatic success merely because the first unregister timed out.
3. Define a retry/finalization path using `nativeip6_unregister(net)` (prefer no new API). An owner can retry after `Busy` and get `NativeIp6Ok` once drained; only then may `nativeip6_register` return success. A concurrent unregister during ongoing teardown must have a documented, deterministic result (Busy or another existing typed error) and must never complete/clear the state behind the original owner's back. `NotReg` remains the outcome for an already COMPLETED unregistration. Do not add a new public Handle/framework for this fix.
4. Lock ordering must be explicit for `natlk`, `c->lk`, `Fs.t2p` and callback work. Don't hold a QLock/SpinLock while sleeping, while calling arbitrary callbacks, or waiting for worker progress that needs that lock. Avoid deadlock with callback -> `nativeip6_send`. No mutable callback metadata visible to old callbacks. Correctly balance `active++/--` through every normal and error path; inspect `waserror` if the callback can raise. Do not dereference freed `arg`/Block after owner releases it.
5. Consider and close the race of stale `Proto` demux lookups not yet counted as `active` when unregister succeeds and a new registration is published. If safe rearm requires a worker-entry generation, dispatch quiescence, or a narrower documented admission linearization point, implement the *smallest reliable mechanism*, with direct proof/tests. It is **not sufficient** to check `active==0` and then immediately reuse the same mutable callback when an old lookup could still invoke it. Do not make unsupported “all in-flight packets drained” claims.
6. On a completed unregister, `t2p[253]` no longer routes new packets to the endpoint. During DRAINING, `nativeip6_registered` reports false; `nativeip6_send` returns `NotReg` as today (unless source-backed semantics require a narrower change). Preserve the bounded retained Proto memory strategy: no per-rearm leak or unbounded allocation.
7. Compatibility: successful normal unregister, repeated completed unregister, and register/unregister/rearm cycles must retain the **existing** externally tested behavior. The new `Busy` recovery is the sole intentional contract extension, with clear documentation.

## 3. Deterministic regression reproducing the actual >5s race

Implement a controlled test in `e74nhprobe.c`, driven by the real host VirtIO `tools/test_e74_ipproto.py`. Reuse the E74 mechanism (currently `nativeip6_setdelay(net, 400)`) only if it can establish deterministic ordering. Prefer an explicit **test-only callback admission barrier** (callback entered/admitted, then block until test releases) over timing guesses. The test must verify:

A. Register callback **A** with a distinct non-null context `argA` and magic/generation. Send one genuine Ethernet/IPv6 Next Header 253 packet from the host. Confirm *in guest* `active>=1` and that callback A's admitted invocation is held **before invocation/finish** at the race point (not just a packet queued in the NIC). Strictly bound the barrier so the fixture cannot hang forever.
B. Invoke `nativeip6_unregister(net)` while A is still active. Force the timeout (use actual roughly 5s deadline, or a test-only injectable reduced timeout **without modifying production default semantics**). Expect **`NativeIp6ErrBusy`**, `registered=0` and `DRAINING`. The guest must print an unambiguous marker, and the host must assert it.
C. While A is still held and after Busy, attempt `nativeip6_register(net, callbackB, argB)`: MUST return `NativeIp6ErrBusy`. Send another host Next Header 253 packet and show it is not delivered to B and does not produce an authenticated-looking reply. The busy/unregistered state must not leak old packets into a new callback.
D. Release A; prove that only A(argA) was called for the original packet, exactly once, and B(argB) never consumed that original packet. If the original A implementation echoes via `nativeip6_send`, `NotReg` is the correct result during drain; free the `Block` exactly once. Verify the callback exited (`active==0`), no stale pointer usage and no stuck kernel worker.
E. Retry `nativeip6_unregister(net)`: expect `NativeIp6Ok`; a subsequent already-completed unregister returns `NativeIp6ErrNotReg` as documented. Then register B(argB) and send a **fresh real host packet**: B must receive exactly that fresh payload with correct IPv6 metadata. Confirm callback A is not called for B's packet. Unregister B successfully and safely retire both contexts. Repeat enough cycles to find lock/state leaks.
F. Negative concurrency interleavings: two concurrent unregister callers (deterministic result without rearming during teardown), re-register attempted immediately on draining, callback plus `nativeip6_send` and teardown, and a late `Proto` dispatch across unlink/rearm boundary if reproducible. Confirm registration record count bounded and the existing no-`Chan` counters remain zero.
G. Check host packet contents (original A payload versus fresh B payload), IPv6 version/Next Header 253, addresses, no duplicate or unexpectedly delivered packet, and actual callback-specific counters/markers. Make the test fail on mismatch, missing markers, timed-out guest phase, panic or hung QEMU. Pure serial “PASS” markers alone are not evidence of real NIC traffic.
H. Do not use a sleep-only race that passes whether or not concurrent operations truly overlapped. Use an admission/active barrier and direct state/callback identity assertions. If an entirely deterministic late-demux lookup is impractical, provide a source-backed correctness argument plus controlled stress or injection; describe that test limitation explicitly.

**BEFORE fix:** Demonstrate the old implementation permits an illegal re-register or fails the Busy-retry behavior, without executing a deliberate use-after-free that can destabilize the guest. Record before/after evidence and commit the focused regression with the fix. Do not fabricate a red test that was never run.

## 4. Regression matrix (after fix)

Run real build+test and preserve actual results/log paths:

```sh
E74_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e74-ipproto.sh

E76_NATIVE=1 WHAT=kernel tools/build.sh
tools/test-e76-network.sh

E77_NATIVE=1 WHAT=kernel tools/build.sh
tools/test-e77-ipv6-only.sh

UDP6_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e73-udp6.sh

IPV6_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e72-ipv6.sh

ETHER_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e71-ether.sh

WHAT=kernel tools/build.sh
tools/test-qemu.sh

OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole --devc build/amd64/pc64oconsole.devc.c
```

Rerun genuine E74/E76/E77 VirtIO UDP6/ICMPv6/NDP/Next Header 253 positives and negatives, including IPv4 EtherType rejection in E77. Verify no new `#l/#I/#W` or IPv4 executable symbols in the E76/E77 artifacts; reused E76/E77 test scripts already check these. No physical NIC and no O-boot regression claim. Keep test logs local under `build/verification/e743/` or their dedicated existing stage dirs; list real paths in the report. If system lacks KVM/build prerequisites, label `NOT RUN`, not PASS.

## 5. Deliverables and STOP condition

- Small and justified production fix in `nativeinh6.c`; if `nativeinh6.h` changes, document exact contract and why.
- Focused deterministic callback-admission/Busy/retry/rearm regression that **fails on the original bug** and passes afterward; host-observed real IPv6 253 frames. Minimize other source edits; do not change shared UDP/IPv6/ethercore implementations.
- New report: **`docs/to_chatgpt_review_e743.md`**, sections: `VERDICT: APPROVE / PARTIAL-HOLD / REJECT`, branch + old/new commit, exact bug/root cause, state/lock/ownership proof, before/after race markers, Busy behavior, retry and rearm, stale-dispatch assessment, test commands and actual results/logs, E7.1–E7.7 regressions, limitations, `NO MERGE`.
- Stage as one or two small reviewable commits; push **ONLY** `origin/design/ipv6-only-native-20261024` and verify that branch HEAD. Do NOT merge any branch or prepare a merge commit. Do not alter `main`, merge-readiness file, or previously delivered stage reports.

**APPROVE** only if a Busy unregister cannot expose re-registration or changed callback/arg to any older active call, the original callback drains, unregister retry succeeds, a genuinely new callback receives only new packets after successful rearm, and all earlier E7 native/legacy gates actually pass. Otherwise report `PARTIAL-HOLD` with the exact missing invariant; don't hide uncertainty or continue into unrelated cleanup.
