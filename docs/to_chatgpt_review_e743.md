# E7.4.3 review: native IPv6 Next Header unregister/re-register race

**VERDICT: APPROVE** for the registration/callback race, with the explicit
queue-boundary limitation in section 6.
**Branch:** `design/ipv6-only-native-20261024`.
**Old commit:** `e4735aa` (the red test was run against this code).
**Fix/regression commit:** the commit adding this report.
**NO MERGE.** No `main`, PR, E7.5, SEALED, WireGuard, crypto, `ipmux`,
userspace ABI, TCP6 or O-disk change was made.

## 1. Exact bug and root cause

The old `nativeip6_unregister()` did this after its 5 s wait:

```c
ilock(&c->lk);
active = c->active;
c->unregistering = 0;          /* unconditional, even when active != 0 */
iunlock(&c->lk);
return active == 0 ? NativeIp6Ok : NativeIp6ErrBusy;
```

and `nativeip6_rcv()` did this after its admission check:

```c
c->active++;
delay = c->delayms;
iunlock(&c->lk);
tsleep(... delay ...);
rc = c->rx(c->arg, &m);        /* mutable pair read after the sleep */
```

Consequences:

- A Busy unregister cleared `unregistering`, so `nativeip6_register()`
  accepted a new callback/arg while the old callback was still admitted.
- The old callback then read the new `c->rx`/`c->arg`, invoking callback B
  on a packet admitted by registration A.
- `nativeip6_unregister()` could not be retried: `registered` was already
  0, so the retry returned `NotReg` instead of eventually completing.
- The retained `Proto` was unlinked from `t2p[253]`, but a dispatch that
  had already obtained the Proto pointer was not quiesced before the old
  registration could be replaced.

The old red test observed:

```text
FAIL: E743 Busy did not latch DRAINING: E743IP: BUSY rc=-3 registered=0 draining=0 active=1
```

This is the actual before-fix failure (`build/verification/e743/before.log`).

## 2. Fixed lifecycle and ownership proof

`NativeIp6` now has an explicit state:

```text
UNREGISTERED (NipUnreg) -> REGISTERED (NipRegistered)
      ^                         |
      |                    unregister
      |                         v
      +---- finalize ---- DRAINING (NipDraining)
                                  |
                                  +-- Busy: stay DRAINING
```

Invariants implemented in `nativeinh6.c`:

1. **Stable callback admission.** `nativeip6_rcv()` validates the packet,
   takes `c->lk`, requires `NipRegistered`, copies `c->rx` and `c->arg` to
   locals, increments `c->active`, and releases the lock. The callback call
   uses only those locals. An admitted call can never see a later
   registration's callback or argument.
2. **Busy latches DRAINING.** The first unregister sets `NipDraining`,
   unlinks `t2p[253]`, and sets `drainwait=1`. On timeout with `active>0`
   it clears only `drainwait`; the state remains `NipDraining`. A
   `Busy` return therefore does **not** authorize freeing the old arg or
   re-registering.
3. **Retry/finalization.** A later `nativeip6_unregister(net)` may become
   the finalizer. It sets `drainwait=1`, waits for `active==0`, then
   transitions to `NipUnreg` and returns `Ok`. A completed unregister
   returns `NotReg` on a further call.
4. **Concurrent unregister.** While `drainwait=1`, another unregister
   returns `Busy` rather than finalizing behind the owner. After a Busy
   timeout `drainwait=0`, exactly one later caller can become the
   finalizer. This is deterministic and is exercised by the E743 fixture.
5. **Registration gate.** `nativeip6_register()` returns `Busy` for
   `NipRegistered` and `NipDraining`; only `NipUnreg` can publish a new
   callback. It sets the callback pair and state under `c->lk` after the
   Proto is linked.
6. **Send/stats/registered.** `nativeip6_send()` and
   `nativeip6_registered()` read `c->state` under `c->lk`; send returns
   `NotReg` throughout DRAINING. Stats report `registered=0`,
   `draining=1`.
7. **Callback error balance.** The callback call is wrapped in
   `waserror()`/`poperror()`; a raised callback decrements `active` and
   wakes the unregister waiter before propagating. The callback still owns
   `bp` on entry; a callback that raises after taking ownership must not
   leak it (the existing callback contract).

Lock order:

```text
natlk -> c->lk          (registration/send/stats metadata)
natlk -> c->lk          (unregister start/finalize)
natlk released          (during the active wait; callback may call send)
ifc wlock               (only after active==0, with no natlk/c->lk held)
natlk -> c->lk          (revalidate state, then finalize)
```

Neither `natlk` nor `c->lk` is held while sleeping, while invoking the
callback, or while waiting for the worker. The callback may call
`nativeip6_send()`: the send path takes `natlk`, sees DRAINING during
teardown, and returns `NotReg` before `ipoput6` (so it cannot queue behind
the finalizer's `wlock`). The E743 A callback exercises this path and
observes `A-SEND rc=-4`.

## 3. Stale Proto / demux assessment

The `Proto` remains retained, as before. The endpoint is now explicitly
bound to `net->ifc`:

```c
if(ifc != c->net->ifc) { freeblist(bp); return; }
```

`t2p[NativeIp6Proto]` is unlinked at the start of DRAINING. After
`active==0`, the finalizer takes `wlock(net->ifc)`. Every native-medium
`ipiput6` call holds `rlock(net->ifc)` for the whole dispatch, including
`p->rcv`; after the writer is acquired, no old `ipiput6` dispatch/lookup is
still inside the native medium. A retained stale Proto pointer that calls
`nativeip6_rcv` during DRAINING sees `state != NipRegistered` and drops
before callback admission. This closes the late-demux lookup that
`active==0` alone did not cover.

**Queue boundary (not claimed as drained):** a frame still sitting in
`net->rxq` has not entered `ipiput6` and was never admitted to the old
registration. It is dropped if demuxed before rearm because `t2p` is nil;
if it is demuxed after rearm, it is new input to the new registration.
There is no queue-wide drain/barrier in this fix. The E743 fixture sends
the stale C frame during DRAINING, waits for it to be demuxed and dropped
(`C-DRAINED delivered=2`) before retry/rearm, and then verifies that B
receives only the fresh D payloads. This is a deliberate admission
linearization point, not a claim that every pre-rearm frame is dropped.

## 4. Before/after evidence

Before (`build/verification/e743/before.log`, old code):

```text
FAIL: E743 Busy did not latch DRAINING: E743IP: BUSY rc=-3 registered=0 draining=0 active=1
```

After (`build/verification/e743/final-e74-boot-virtio.log`, E74):

```text
E743IP: A-REG rc=0
E743IP: A-READY
E743IP: A-ADMITTED active=1 registered=1
E743IP: BUSY rc=-3 registered=0 draining=1 active=1
E743IP: CONCUR-OWNER rc=-3 done=1
E743IP: REG-B rc=-3
E743IP: C-READY
E743IP: A-DONE callsA=1 callsB=0 active=0
E743IP: A-SEND rc=-4
E743IP: C-DRAINED delivered=2
E743IP: RETRY rc=0
E743IP: NOTREG rc=-4
E743IP: CYCLE 0 REG rc=0
E743IP: CYCLE 0 READY
E743IP: CYCLE 0 GOT callsB=1 len=8
E743IP: CYCLE 0 UNREG rc=0
...
E743IP: CYCLE 4 GOT callsB=1 len=8
E743IP: CYCLE 4 UNREG rc=0
E743IP: DONE callsA=1 callsB=1
```

The same E743 markers appear in the E76 and E77 serial logs
(`build/verification/e743/final-e76-boot-virtio.log`,
`final-e77-boot-virtio.log`).

The regression is driven by real host VirtIO Ethernet/IPv6 frames:
`A-ORIGINAL` is the admitted A packet, `C-STALE` is sent while A is held
and B is blocked, and five `D-0..D-4` frames are sent only after each
successful rearm. The host asserts payload, IPv6 version/Next Header 253,
absence of A/C echoes, absence of B delivery of A/C, and the exact
callback counters. Pure serial `PASS` text is not the evidence: the guest
counters and host frame contents are checked.

## 5. Tests actually run (all PASS)

Build/test commands and logs under `build/verification/e743/`:

| Gate | Command | Result / log |
| --- | --- | --- |
| E7.4.3 E74 | `E74_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e74-ipproto.sh` | PASS; `final-e74.log`, `final-e74-boot-virtio.log` |
| E7.6 | `E76_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e76-network.sh` | PASS; `final-e76.log`, `final-e76-boot-virtio.log` |
| E7.7 | `E77_NATIVE=1 WHAT=kernel tools/build.sh && tools/test-e77-ipv6-only.sh` | PASS; `final-e77.log`, `final-e77-boot-virtio.log` |
| E7.3 | `UDP6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e73-udp6.sh` | PASS; `final-e73.log` |
| E7.2 | `IPV6_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e72-ipv6.sh` | PASS; `final-e72.log` |
| E7.1 | `ETHER_PROBE=1 WHAT=kernel tools/build.sh && tools/test-e71-ether.sh` | PASS; `final-e71.log` |
| Default | `WHAT=kernel tools/build.sh && tools/test-qemu.sh` | PASS; `final-default-qemu.log` |
| E5 console | `OCONSOLE=1 WHAT=kernel tools/build.sh` + `python3 tools/cons_migration_check.py ...` | PASS; `final-e5-cons.log` |

E76/E77 static artifacts:

```text
9pc64e7native  1822131 bytes  md5 f1402c94b4255b037203e99b9fd81fd4
9pc64e7v6only  1742012 bytes  md5 91a1c56a89dd24de980616470ea8cfc8
generated devtab: no etherdevtab/ipdevtab/wgdevtab
```

`tools/test-e76-network.sh` and `tools/test-e77-ipv6-only.sh` retain their
linked-symbol and generated-Dev checks; E77 still rejects the IPv4
EtherType frame and IPv4-mapped UDP6 open. `E7.5` remains deferred and
`SEALED` is not implemented.

## 6. Limitations / non-claims

- The queue-boundary limitation in section 3 is deliberate: no claim is
  made that a frame queued but not yet demuxed at rearm is dropped. The
  tested stale C frame is drained before retry.
- `ipv6native_stop()` ordering is unchanged. Callers should unregister the
  raw consumer before stopping the IPv6 instance; a stop during an active
  callback can still return its existing `EtherErrBusy`. No new stop
  contract is claimed.
- A callback that raises after taking `bp` ownership can still leak that
  Block; the pre-existing callback contract remains "consume or free".
- No physical NIC and no O-boot regression was run. Physical hardware,
  fragmentation/extension-header fuzzing, and full merged-tree O boot
  remain NOT RUN.
- `natip`/`Proto` remains one bounded retained record; re-registration
  does not allocate a new Proto or NativeIp6 record.
