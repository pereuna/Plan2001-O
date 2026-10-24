# E7.3.1 report — UDP6 API concurrency, lifecycle and ownership hardening

VERDICT: APPROVE

BRANCH/BASE/COMMITS:
- repo: `pereuna/Plan2001-O`
- branch: `design/ipv6-only-native-20261024`
- upstream: `origin/design/ipv6-only-native-20261024`
- E7.3.1 work started at `aa5bd0e` (after restoring the shared general review file in `781a654`).
- commits: `9b59a66` (E7.3.1a audit/contract), `1285a52` (E7.3.1b-d receive, close/destroy, send hardening), `58e01cb` (E7.3.1e regression fixtures), plus this report commit.
- `main`, PR #1, E6/E8/E9 and the mistaken `design/e72-native-ipv6-20261024` branch were not touched.

REPRODUCED BEFORE / FIXED AFTER:
- **Atomic receive:** old `udp6_recv` used `qcanread()` then blocking `qbread()`. Two receivers could both observe ready; one removed the datagram and the other blocked past `timeout_ms`. Replaced with atomic nonblocking `qget()` plus a bounded timeout loop. A first hardening attempt using one shared `Rendez` was rejected by the kernel's single-waiter “double sleep” check; the final implementation uses one `Udp6Wait` Rendez per receiver.
- **Close/Conv reuse:** old `udp6_close` called `closeconv()` before waiting for `recvactive==0`, allowing a receiver to touch a Conv slot eligible for `Fsprotoclone` reuse. Replaced with `U6Open -> U6Closing -> U6Closed -> U6Destroyed`, quiescence counting and `closeconv` only after all send/recv/aux users are out.
- **Endpoint memory:** old API never freed the `Udp6Endpoint` wrapper. Added owner-only `udp6_destroy(&ep)` requiring `U6Closed` and zero active users; `udp6_close` remains the logical shutdown and repeat close still returns `Udp6ErrClosed`.
- **Send errors/exceptions:** old `udp6_sendto` held `sendlk` across `qbwrite(qbypass)` with no `waserror` unwind and never incremented `txerrors`. Added `waserror` cleanup, sendactive accounting, synchronous route rejection, error counters, and explicit accepted/uncertain semantics for the private envelope Block.

STATE & LOCK PROTOCOL:
- States: `U6Open -> U6Closing -> U6Closed -> U6Destroyed`; no other transitions.
- `st` (`Lock`) protects state, `recvactive`, `sendactive`, `auxactive`, counters and the waiter list. `sendlk` (`QLock`) serializes sends. `net->udplock` protects `udp6active` versus `ipv6native_stop`.
- Receive: process context only; `recvactive++` under `st`; atomic `qget`; one stack `Udp6Wait` per receiver; close sets `U6Closing` and wakes every waiter; `recvactive--` on every return path.
- Close: first closer sets `U6Closing`/`closer`, wakes waiters, polls quiescence with `up->sleep` (10 ms), then calls `closeconv`. A timeout returns `Udp6ErrBusy` and leaves a resumable `U6Closing`. Second close on `U6Closed` returns `Udp6ErrClosed`; a concurrent closer gets Busy.
- Send: `sendlk` then `sendactive++`; close waits for it. No new send/recv/stats Conv access starts after `U6Closing`. On `waserror`, `sendactive--`, `txerrors++`, `txuncertain++`, `sendlk` unlocked, caller payload retained.
- Destroy: owner-only after `U6Closed`, zero active users. It frees only the wrapper; the inherited UDP Proto owns the Conv/queues. Stale aliases after destroy are invalid by contract; tests use the cleared owner pointer and never call via a freed alias.
- Stats: Open snapshots may read the Conv under `auxactive`; Closing/Closed stats never dereference a recycled Conv. Pending/setlimit require Open.
- No function in this API may be called from interrupt context.

RECEIVE TIMEOUT EVIDENCE:
- `RACE1` was repeated 10 times on one endpoint. Both receivers were confirmed inside `udp6_recv` (`recvactive>=2`) before the host sent one real VirtIO UDP6 datagram. Every round produced exactly one success and one timeout:
  `CHECK race1 rounds=10 ok=10 timeout=10 max_timeout=600`.
- `RACE2`: two receivers inside `udp6_recv`, two distinct real datagrams, both delivered once: `CHECK race2 ok=2`.
- Timeout is enforced with a wrap-safe `(NOW-start) >= timeout_ms` check and a 10 ms bounded observation interval. `timeout_ms=0` is a poll; `~0UL` waits until data/close. The measured 600 ms losing-receiver maximum was 600 ms; this is scheduling resolution, not a hard real-time guarantee.
- `CLOSEWAIT`: a blocked receiver was woken by close; `CHECK close-wake rc=0`, receiver status `Udp6ErrClosed`.

CONV CLOSE/REOPEN EVIDENCE:
- Close waits for in-flight users before `closeconv`; queued old datagrams are discarded by `qclose`.
- Same IPv6 address/port rebind after close/destroy succeeded and echoed a real host datagram: `CHECK rebind-open rc=0`, `CHECK rebind rx=1 tx=1`.
- 200 sequential open/close/destroy cycles on four ports: `CONV-SLOTS before=2 after=2 ac_before=2 ac_after=2`; no Conv slot growth.
- `ipv6native_stop` refuses teardown while an endpoint is live: `CHECK stop-live rc=-7`; stop succeeds only after all endpoints close/destroy: `STOP rc=0`, repeat stop `-9`, restart after stop `-7`.

MEMORY ALLOCATION/RELEASE COUNTERS:
- Focused wrapper counters: `CHECK loop-alloc opens=200 closes=200 destroys=200 live_delta=0`.
- Final after all endpoints: `ALLOC-FINAL opens=207 closes=207 destroys=207 live=0 peak=2`.
- The 200-loop includes periodic zero-timeout polls and a synthetic queued envelope on every 50th iteration to exercise close-with-pending-message; qclose discards queued Blocks. This is synthetic queue evidence, not NIC RX.
- Open failure paths call `closeconv` where a Conv was created; no successful Conv is leaked on later failure.

SEND ERROR/Block OWNERSHIP:
- `udp6_sendto` returns `Udp6ErrNoRoute` for a deliberately unroutable IPv6 peer: `CHECK send-noroute rc=-13`; the caller payload remains caller-owned. A subsequent real host datagram was echoed: `SENDFAIL-ALIVE`.
- Private-queue exception injection (`testkick` frees the envelope then raises) exercises real `waserror` unwinding: `CHECK fake-exc rc=-14`, `CHECK fake-unlock=1`, then a successful second send `CHECK fake-ok rc=0`. This is not NIC evidence.
- `txerrors` increments on argument/closed/route/MTU/exception/queue-return failures; `txuncertain` marks the private-envelope outcome when `qbypass`/`udpkick` has already accepted it. The caller payload is never freed on a returned error.
- Close-versus-send race: a live sender produced many rejected no-route/Closed sends while close completed: `CHECK close-send rc=0`, `CHECK close-send-results done=1 ok=0 err>0`; no stuck `QLock`.
- Link down remains a real medium-level drop after API acceptance (`TXDOWN txdown=1`, host saw no echo), distinguished from a synchronous API error.

REAL VIRTIO DATAGRAM EVIDENCE:
- Real VirtIO/IPv6/UDP6 echo with payload lengths `0, 1, 17, 1452` and paired messages from multiple source ports; host validated Ethernet/IPv6/UDP headers, source port `20001`, destination host port, UDP length, nonzero UDP6 pseudoheader checksum and unchanged payload.
- Guest: `POSITIVE rx=6 tx=6 bytes=1486`; `UDPSTATS ... OutDatagrams=8`.
- Negative packets remained dropped: zero/bad UDP6 checksum, malformed UDP length, IPv4 EtherType, unbound port (validated ICMPv6 Port Unreachable), RX queue saturation (`DropFull=14`), link down.
- `CHAN-NATIVE` and `CHAN-HARDEN` both:
  `namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1`.
  The native path uses no `Chan`, `namec`, `walk`, `devwalk`, `mount` or legacy exec.

E7.1/E7.2/E7.3 REGRESSIONS:
- E7.3 hardware fixture: PASS on three consecutive runs after hardening.
- E7.2 NDP/ICMPv6 fixture: PASS.
- E7.1 VirtIO L2/legacy `#l` fixture: PASS.
- default `9pc64` + `9pc64mp` build and `tools/test-qemu.sh`: PASS.
- E5 `9pc64oconsole` build and cons check: PASS, 23 Qids, no `consdevtab`.
- Legacy `#I` UDP4/UDP6, headers=0 child Convs, TCP, IPv4/ARP, `#l` and `#W` remain linked and are not replaced by this API.

COMMANDS/ACTUAL LOGS:
```sh
UDP6_PROBE=1 WHAT=kernel tools/build.sh        # BUILD-DONE, 9pc64e73
tools/test-e73-udp6.sh                         # PASS (3 consecutive runs)
IPV6_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e72-ipv6.sh                         # PASS
ETHER_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e71-ether.sh                        # PASS
WHAT=kernel tools/build.sh
tools/test-qemu.sh                             # PASS
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py \
  --kernel build/amd64/9pc64oconsole \
  --devc build/amd64/pc64oconsole.devc.c        # PASS
```
Observed hardening markers:
`RACE1 rounds=10 ok=10 timeout=10 max_timeout=600`,
`RACE2 ok=2`, `close-wake rc=0`, `close-send err>0`,
`fake-exc=-14`, `fake-unlock=1`, `fake-ok=0`,
`send-noroute=-13`, `loop-alloc 200/200/200 live_delta=0`,
`conv-slots 2->2`, `closed-stats state=2`, `closed-aux -1/-7`,
`destroy rc=0 nil=1`, `rebind rx=1 tx=1`, `ALLOC-FINAL live=0`,
`CHAN-NATIVE/CHAN-HARDEN clean=1`, `DONE pass=1 fails=0`.

LOCAL LOG PATHS (ignored, not in Git):
- `build/verification/e731/build-e73.log`, `test-e73-1.log`, `test-e73-2.log`, `test-e73-3.log`
- `build/verification/e731/boot-virtio-final.log`, `serial-virtio-final.log`, `boot-nonic-final.log`
- `build/verification/e731/build-e72.log`, `test-e72.log`
- `build/verification/e731/build-e71.log`, `test-e71.log`
- `build/verification/e731/build-default.log`, `test-default.log`
- `build/verification/e731/build-oconsole.log`, `test-oconsole.log`

NOT RUN/OPEN:
- No E6/E8/E9 integration or `main` merge; no final `#I/#l/#W`/IPv4 removal or IPv6-only linkage.
- No userspace socket/fd/Handle, MicroPython networking, TCP6, WireGuard, TLS, DNS/DHCPv6 or routing daemon.
- `ipv6native` remains a one-shot object if its inherited Fs workers cannot be destroyed; `udp6_destroy` reclaims only endpoint wrappers, not the Fs.
- Exception injection uses a private `qbypass` Queue; it proves `udp6_sendto` unwind and lock release, not an arbitrary `udpkick` fault on the real NIC.
- No hard real-time timeout claim; 10 ms observation resolution.
- Promiscuous reception is still enabled by the test NATIVE medium; production multicast filtering is open.
- Stale raw pointers after `udp6_destroy` are invalid by contract; no refcounted handle layer was added.

LATER E7.4 DEPENDENCIES:
- WireGuard outer UDP6 can use this endpoint shape only after it accepts the documented process-context/owner/destroy contract and does not retain stale aliases.
- E7.4 should keep `Udp6Msg` datagram boundaries, peer metadata and the inherited `udpiput`/`udpkick` path; WireGuard inner IPv6 and cryptographic work remain separate.
- Integration with E6/E8/E9 must reconcile the `main.c` handoff chain, `pc64/mkfile` `CONFLIST`, `tools/build.sh` profile dispatch and the pruned O-only configuration in a later clean gate.
