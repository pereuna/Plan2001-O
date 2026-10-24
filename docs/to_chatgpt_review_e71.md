# E7.1 completion report — native Ethernet kernel C boundary

E7.1 VERDICT: APPROVE

BRANCH / UPSTREAM / BASE / FINAL COMMIT(S):
- repository: `pereuna/Plan2001-O`
- branch: `design/ipv6-only-native-20261024`
- upstream: `origin/design/ipv6-only-native-20261024`
- merge base with `origin/main`: `1c61dd175c0757e5eaed016c1a7305f7ccad5c91`
- checked-out base at start: `a7457b7b3c1915e77df34a9a20defde24681f4c9`
- subcommits: `f942e0e` (E7.1.0 audit), `152b764` (E7.1.1/E7.1.2 native core + adapter), `3035a57` (E7.1.3 VirtIO probe/fixture), plus this E7.1.4 report commit.
- `main` was not checked out, merged, committed to or pushed. Draft PR #1 was not merged.

SOURCE MAP: exact symbols, owners, IRQ/call context and Chan/Netfile edges

The single maintained map is [ETHER-MIGRATION.md](ETHER-MIGRATION.md). Its
table covers the required symbols and adds the E7.2+ dependency graph. Key
facts confirmed by re-reading current C:

- `port/ethercore.c` now owns `addethercard`, `cards[]`, `etherxx[]`,
  `etherprobe`, `ethercore_init`, stable lookup, `ethercore_attach`,
  `ethercore_tx`, RX registration and `etheriq`.
- `port/devether.c` is the retained legacy `#l` adapter: `etherattach`,
  `etherdevtab`, `ethermux`, `etheroq`, `etherwrite`/`etherbwrite`,
  `etherlegacyrx`, `netconsole`, `dmatproxy`, `ethersetlink/speed`.
- `port/netif.c` remains the `Chan`/`Qid`/`Netfile` file and policy layer.
  `netifinit` is still called by the core probe to allocate the embedded
  `Netif`, but no native frame operation calls `netifwalk/open/read/write/
  bread/close/wstat/stat`.
- `etheriq` call sites: VirtIO `rxproc` (`ethervirtio10.c:311`, worker
  context), `rtl8169` (`ether8169.c:1037`, interrupt), `i82563`
  (`ether82563.c:1102`, interrupt), `i225` (`etheri225.c:884`, interrupt),
  iwl. The native sink contract is therefore interrupt-safe.
- The only RX sink in E7.1 is the single explicit
  `ethercore_rxregister()` callback; the original frame always continues to
  `etherlegacyrx` -> `ethermux` -> `Netfile.f[].in`. The legacy dependency is
  named, not hidden.
- `#I`/UDP/TCP/WG edges are audited only in `docs/ETHER-MIGRATION.md`;
  `ip/*` was not modified.

NATIVE ETHER CORE: actual functions, files, init and lookup contracts

Files:
- `sys/src/9/port/ethercore.c` (new)
- `sys/src/9/port/etherif.h` (contract/prototypes)
- `sys/src/9/port/devether.c` (legacy adapter delegation)

Functions:
- `ethercore_init()`: bulk probe/reset; idempotent; returns controller count
  or `EtherErrPreinit` if no driver registered. A second call does not run
  `cards[].reset` again.
- `ethercore_lookup(ctlrno)`, `ethercore_byindex(i)`, `ethercore_byname(name)`:
  stable in-memory lookup, no path/Qid/OID/userspace handle encoding.
- `ethercore_probe_at(ctlrno, conf)`: legacy explicit `#lN:conf` extension.
- `ethercore_attach(Ether*)`: exactly one attach per controller, process
  context only. It is called by the native probe or by legacy `#l` attach.
- `ethercore_tx(Ether*, Block*)`: direct frame TX.
- `ethercore_rxregister/rxunregister`: one fixed-purpose RX sink per
  controller.
- `etheriq`: driver RX entry, native copy + legacy preservation.
- `ethercore_shutdown`: central controller shutdown loop.

Sequencing:
- `links()` registers all card drivers via `addethercard` before
  `chandevreset`.
- `chandevreset` -> `etherdevtab.reset` -> `ethercore_init` performs PCI,
  reset callbacks, IRQ enable, output queue and `Netif` allocation before
  `pageinit`/scheduler, matching the inherited driver requirements.
- `attach` is not part of reset. It runs later in process context after
  `schedinit` (E7.1 probe) or on a legacy `#l` open. No attach occurs in
  `etheriq`, in an interrupt, or with `up == nil`.
- The native probe calls `ethercore_init()` again and observes
  `probes` unchanged (`idempotent=1`); it never calls `etherdevtab.reset`.

FRAME RX/TX: ownership, link/MTU, backpressure and Qkick evidence

TX contract (documented in `ethercore.c` and `etherif.h`):
- complete L2 `Block`; EtherType is preserved, never interpreted as IPv4/IPv6;
- process context only;
- success consumes the caller's `Block`; every failure leaves it to the
  caller;
- length must be `minmtu..maxmtu`, controller must be attached, queue open,
  link not down;
- full queue is reported as `EtherErrQueue` (non-blocking `qpassnolim`);
- the core copies the frame into a queue-owned `Block`, then calls
  `Ether.transmit(e)` or lets qio wake a blocked reader. VirtIO has no
  `transmit` callback and uses its `txproc`; the explicit kick/wakeup path is
  therefore covered for both driver styles;
- `outpackets` is incremented only after a successful enqueue.

RX contract:
- sink receives one private `iallocb` copy and owns it;
- original `Block` goes to the legacy path exactly once;
- allocation failure increments `rxdropped` and does not block legacy;
- sink runs in the driver's RX context and must be interrupt-safe (no sleep,
  no blocking `QLock`, no sleeping allocation); the test sink uses `qpass`
  and `wakeup`;
- unregister must only run when no RX is in flight (documented; E7.1 test
  quiesces first).

Observed hardware evidence:
- host -> guest: `host-rx.hex` starts
  `525400123456 020000000001 88b5 45373152585258...`
  (`E71RXRX`); guest marker `E71ETHER: RX len=64 type=0x88b5 match=1`;
- guest -> host: `host-tx.hex` starts
  `ffffffffffff 525400123456 88b6 45373154585458...`
  (`E71TXTX`); guest marker `E71ETHER: TX rc=0 ... ok=1`;
- `E71ETHER: STATS tx=1 rx=1 drop=0 attached=1 registered=1`;
- native Chan counters around attach/register/TX/RX:
  `namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1`.

LEGACY #l: Dev registration and representative behavior tests

- `etherdevtab` is still registered in `pc64`, `pc64mp`, `pc64native`,
  `pc64oconsole` and the new opt-in `pc64e71`.
- `etherattach` parses the same spec, enforces `iseve`, `Ebadspec`,
  `Einuse`, `Enodev`, calls `devattach`, and delegates controller enabling
  to `ethercore_attach`.
- `netif.c` access checks, per-`Netfile` state, queue reopen/close, offsets,
  `Qmsg` framing, bridge/bypass/promiscuous/multicast/headersonly and
  `netconsole` are unchanged.
- A real QEMU VirtIO test opened `#l0/ether0/clone`, wrote
  `connect 0x86dd`, opened `#l0/ether0/0/data`, received a host frame and
  reported `E71ETHER: LEGACY len=64 type=0x86dd match=1`.
- Default kernel boot (no probe) passed `tools/test-qemu.sh`.

VIRTIO QEMU: exact build/boot/network commands, correlated RX and TX observations, log paths

```sh
# opt-in kernel + fixture
ETHER_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e71-ether.sh

# default and E5 preservation
WHAT=kernel tools/build.sh
tools/test-qemu.sh
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py --kernel build/amd64/9pc64oconsole \
  --devc build/amd64/pc64oconsole.devc.c
```

The fixture boots `9pc64e71` through `bootx64.efi` with QEMU/KVM, q35,
2048 MB, no disk, and a raw L2 UDP (`-netdev dgram`) peer:

```text
-netdev dgram,id=n0,local.type=inet,local.host=127.0.0.1,
        local.port=P1,remote.type=inet,remote.host=127.0.0.1,remote.port=P2
-device virtio-net-pci-non-transitional,netdev=n0,mac=52:54:00:12:34:56
```

No tap/bridge/privilege is used. The second boot uses `-nic none`.

Correlation is fail-closed: the host waits for `E71ETHER: READY`, injects the
`0x88b5` frame, reads the guest `0x88b6` frame from the host UDP socket,
checks both EtherType and magic, then checks the guest RX/TX markers. A
synthetic Block alone is never presented as NIC RX.

Logs (ignored by Git, local evidence):
- `build/verification/e71/build-e71.log`
- `build/verification/e71/test-e71.log`
- `build/verification/e71/boot-virtio.log`
- `build/verification/e71/boot-nonic.log`
- `build/verification/e71/serial-virtio.log`, `serial-nonic.log`
- `build/verification/e71/host-tx.hex`, `host-rx.hex`, `host-legacy.hex`
- `build/verification/e71/build-default.log`,
  `test-default-boot.log`, `build-oconsole.log`, `test-oconsole-check.log`

NEGATIVES: rejected bad length, absent/down interface, RX sink/queue error, results

All observed PASS:
- pre-attach TX: `CHECK preattach rc=-2` (`EtherErrNotReady`);
- short frame: `NEG shortlen rc=-4` (`EtherErrBadLen`);
- over-MTU frame: `NEG longlen rc=-4`;
- second RX sink: `NEG rxregister-busy rc=-7` (`EtherErrBusy`);
- mismatched/nil RX unregister or nil sink:
  `NEG rxunregister-mismatch rc=-9`, `NEG rxregister-nil rc=-9`;
- link down: `CHECK down rc=-5` (`EtherErrDown`), original Block retained and
  freed by the test;
- full output queue: `CHECK queue-full rc=-6` (`EtherErrQueue`). This is an
  isolated core backpressure test using a private limit-0 Queue with no
  kick; it is explicitly **not** hardware TX evidence;
- unbound sink: `RXUNREGISTER rc=0`, then
  `NEG rxunregister-twice rc=-9`; the subsequent legacy `#l` read proves the
  legacy path still receives after native unbind;
- absent controller: second boot with `-nic none` reports
  `E71ETHER: NODEV n=0`, `DONE pass=1`, no panic/fault.

IP/UDP/WG FOLLOW-UP: audited concrete source edges only, not modified behavior

Detailed in `docs/ETHER-MIGRATION.md` section 5. Summary:

```text
NIC driver -> etheriq -> native sink OR etherlegacyrx/ethermux/Netfile     [E7.1]
future: native sink -> IP6/ICMPv6/NDP -> TCP6/UDP6                         [E7.2+]
current #I: ipattach -> namec/chandial -> devtab[Chan]->bread/bwrite        [audit]
current #W: wglisten -> namec("/net/udp/clone") -> Chan -> wgreader        [audit]
```

Concrete edges: `ipattach` (`ip/devip.c:299`), `etherbind`
(`ip/ethermedium.c:113`), `etherbwrite` (`:255`), `etherread4/6`
(`:321,361`), `udpinit` (`ip/udp.c:678`), `tcpinit` (`ip/tcp.c:3190`),
`icmp6init` (`ip/icmp6.c:820`), `wglisten` (`ip/devwg.c:1698`), `wgreader`
(`:1211`). No `ip/*` file was modified. Later acceptance requires native
IPv6/ICMPv6/NDP, native UDP6/TCP6 semantics, native IPv6-only WG, removal of
the three Dev registrations, and exclusion of executable IPv4/ARP without
breaking shared C code. Any userspace ABI remains `OPEN`.

IPV6-ONLY STATUS: architecture target ACCEPTED; implementation still TRANSITIONAL

The IPv6-only target in `docs/GENERAL-SOFTWARE-SPECIFICATION.md` was not
changed. The current kernels still link `etherdevtab`, `ipdevtab`,
`wgdevtab`, IPv4 packet code and ARP. E7.1 does not claim an IPv6-only
runtime; acceptance of an `0x86DD` frame only proves L2 delivery.

SHARED E6 FILES / MERGE RISK: list exact paths; no E6 edits on main

E7.1 touched these files that E6 may also touch on `main`:
- `sys/src/9/pc64/main.c` (one new handoff hook)
- `sys/src/9/pc64/mkfile` (`ethercore.o`, `pc64e71` in `CONFLIST`)
- `tools/build.sh` (`ETHER_PROBE=1` profile)
- `sys/src/9/port/portmkfile` (`ethercore.o` rule/dependency)
- `sys/src/9/arm64/mkfile` (`ethercore.o`; arm64 is planned/unbuilt)
- `sys/src/9/port/devether.c`, `sys/src/9/port/etherif.h`

New, low-conflict files:
- `sys/src/9/port/ethercore.c`
- `sys/src/9/pc64/e71etherprobe.c`
- `sys/src/9/pc64/pc64e71`
- `tools/test-e71-ether.sh`, `tools/test_e71_ether.py`
- `docs/ETHER-MIGRATION.md`, this report

Deliberately untouched (E6-owned): `tools/build.rc`,
`tools/test-oboot-server.sh`, `docs/STATUS.md`, `docs/to_chatgpt_review.md`,
kernel disk configs, and `main` itself. Merge review must reconcile the
`main.c` handoff branch and the `pc64/mkfile` `CONFLIST` list with E6's disk
core changes; no semantic conflict with `devether.c`/`ethercore.c` is
expected, but E6 acceptance results are unaffected by this branch.

TESTS ACTUALLY RUN: PASS / FAIL / NOT RUN with source logs

PASS (executed by this run):
1. `ETHER_PROBE=1 WHAT=kernel tools/build.sh` -> `9pc64e71`, BUILD-DONE
   (`build/verification/e71/build-e71.log`).
2. `tools/test-e71-ether.sh` -> `PASS: absent controller (NODEV)`;
   `PASS: VirtIO native TX/RX, legacy #l RX, negatives`;
   `PASS: E7.1 Ethernet fixture` (`test-e71.log`, `boot-*.log`,
   `host-*.hex`).
3. `WHAT=kernel tools/build.sh` -> `9pc64` and `9pc64mp`, BUILD-DONE
   (`build-default.log`).
4. `tools/test-qemu.sh` -> `PASS: kernel up to init0 (no root=)`
   (`test-default-boot.log`).
5. `OCONSOLE=1 WHAT=kernel tools/build.sh` -> `9pc64oconsole`, BUILD-DONE
   (`build-oconsole.log`).
6. `python3 tools/cons_migration_check.py ...` -> PASS, 23 Qids, 19 native,
   2 legacy-only, 2 intentionally unsupported, no `consdevtab`
   (`test-oconsole-check.log`).
7. `strings build/amd64/9pc64` shows `ethercore_init`, `ethercore_tx`,
   `etheriq`, `etherdevtab`, `etherlegacyrx`; `9pc64e71` also shows
   `e71etherprobe_start`.

NOT RUN / not required in E7.1:
- no physical NIC test; no IPv6/NDP/UDP6/TCP6 native runtime test; no
  WireGuard test; no E6 disk/O-only server regression (E6 owns it);
- no 9P adapter, no userspace networking ABI, no controller unregistration.

UNRESOLVED: precise blockers and next bounded action

- The native RX sink is still parallel to the legacy mux and every frame is
  copied once for the sink while the original continues through
  `ethermux`; a true native-only sink without the legacy copy/path requires
  the E7.2 IP6 consumer and eventual adapter removal.
- The full-queue negative is an isolated Queue test, not a forced real-NIC
  queue saturation. Forcing driver ring saturation deterministically is
  future test work, not a data-path claim.
- `ethercore_rxunregister` requires the caller to quiesce RX before
  unregistering; E7.1 has one fixed sink and no refcount/generation scheme.
- `ethercore_probe_at` has a narrow occupied-slot race that can leak a
  probed `Ether`; the normal boot path is single-threaded and legacy checks
  `Einuse` first. A later cleanup can add a proper registry lock/ownership
  rule.
- No native IPv6, UDP6/TCP6, NDP or WireGuard work was done; those remain
  E7.2+ and are named in `docs/ETHER-MIGRATION.md`.
- Next bounded action: integrate E7.1 with E6's approved kernel, then build
  the first native IPv6 RX consumer (Ether sink -> IPv6/ICMPv6) without
  removing legacy `#l` until its acceptance tests still pass.
