# E7.2 completion report — first real native IPv6 receive/response path

VERDICT (APPROVE / PARTIAL-HOLD / REJECT): **APPROVE**

BRANCH / BASE / COMMITS:
- repo: `pereuna/Plan2001-O`
- branch: `design/ipv6-only-native-20261024`
- upstream: `origin/design/ipv6-only-native-20261024`
- base at start of E7.2 work: `7802079` (E7.1 completed on the same branch; original fork base `1c61dd17`)
- E7.2 commits: `35ea815` (E7.2.0 audit), `bb48ffd` (E7.2.1 hardening), `d56db5b` (E7.2.2 Fs init), `6bf0961` (E7.2.3 native medium/worker), `6aae8c4` (E7.2.4 fixture), plus this report commit.
- `main` was not checked out, merged, rebased, committed to or pushed. PR #1 was not merged. The mistaken `design/e72-native-ipv6-20261024` branch was not touched.

E7.1 HARDENING:
- `ethercore_attach`: per-controller `QLock`; `attached=1` is published only after `Ether.attach` returns. A concurrent caller waits, then observes ready. Failure leaves the controller detached and retryable.
- `ethercore_tx`: new `qpasstry()` in `qio.c` checks capacity and inserts under the same Queue lock. Returns `-1` closed / `-2` full without freeing; native TX frees only its private copy. No qfull/qpass race.
- `ethercore_rxunregister`: `rxactive`/`rxunregistering` plus a `Rendez`; the sink callback increments/decrements around delivery, and unregister waits in process context until no callback is in flight. IRQ code never sleeps.
- `ethercore_probe_at`/`ethercore_init`: serialized by `coreqlock`; an occupied slot is never probed and then freed. This avoids leaking a controller whose PCI/IRQ/DMA reset already ran.
- E7.1's live `e->oq` swap in the negative test was removed. Full/closed backpressure is tested on a private Queue with the real `qpasstry` primitive; the real VirtIO TX/RX correlation test is retained.
- Evidence: E7.1 fixture still PASS after these changes.

Fs INITIALIZATION:
- `ip/devip.c`: `ipfsinit(Fs*, int)` now owns `ip_init` + `arpinit` + `netloginit` + `ipprotoinit[]`. `ipattach` is a thin legacy wrapper that allocates an Fs and delegates.
- `ip/nativev6.c`: `ipv6native_start` allocates one `Fs`, calls `ipfsinit`, `Fsprotoclone(f->ipifc)` and `ipifcadd` for a deterministic link-local address. It does not call `namec`, `Chan`, `Qid`, `devattach`, `ipattach`, `etherbind` or `chandial`.
- Repeat start returns `EtherErrBusy`; no second `Fs`/`Proto` registration. The probe also repeats `ethercore_attach` (`rc=0`).
- One IPv6 `Ipifc` is bound to the existing `Ether*` through a native `Medium` with `maclen=6`, `hsize=14`, `maxtu=1514`. Test-only link-local: `fe80::5054:ff:fe12:3456` for MAC `52:54:00:12:34:56`.

NATIVE RX/TX OWNERSHIP:
- RX sink (`ipv6native_etherinput`): driver RX context; accepts only `0x86DD`, minimum `ETHERHDRSIZE+IP6HDR`, own unicast or IPv6 multicast MAC; `qpass` into a bounded 64 KiB `Qmsg` queue; on full/closed the Block is released by qpass and `rxdrop` increments. No `ipiput6`, sleeping lock or path lookup in the callback.
- Worker: process context, `qbread`, strips Ethernet header exactly once, takes `rlock(ifc)`, calls the canonical `ipiput6`, then `runlock`. `ipiput6` owns the Block afterwards.
- Output: `ipoput6` -> native `Medium.bwrite` -> shared `ethermediumframe` (ARP/NDP, pad, EtherType `0x86DD`) -> `ethercore_tx`. Success consumes the frame; failure leaves it to the medium, which frees it and increments `txerrs`. No `devtab[Chan]->bwrite`, `etherwrite` or `Netfile`.
- `ifc->speed` is forced to 0 for the native test medium. The first run exposed that a nonzero speed with zero `burst` made `ipifcoput` drop the second packet unless timing delayed it; disabling shaping fixed the real protocol path rather than the test.
- The E7.1 compatibility path still receives the original frame (via `etherlegacyrx`) and remains linked; `ethercore` is not claimed independent of `devether.c`/`netifinit`.

ICMPv6/NDP REAL HARDWARE EVIDENCE:
Host raw-L2 dgram peer -> real VirtIO device -> guest `rxproc` -> `etheriq` -> native sink/worker -> existing `ipiput6` -> existing `icmpna6`/`mkechoreply6` -> existing `ipoput6` -> native medium -> `ethercore_tx` -> real VirtIO TX -> host.

Observed on the same QEMU guest:
- host NS (Hop Limit 255, SLLA) -> guest NA: `NA: flags=0x60`, EtherType `0x86DD`, target `fe80::5054:ff:fe12:3456`, TLLA guest MAC, valid ICMPv6 pseudoheader checksum;
- host Echo Request id `0x1234` seq `1` payload `e72-echo` -> guest Echo Reply with matching id/seq/payload, source/destination `fe80::5054:ff:fe12:3456` -> `fe80::2`, valid checksum;
- guest markers: `POSITIVE rx=2 tx=2`, `CHAN-NATIVE ... clean=1`;
- guest NA and Echo replies were observed by the host only after passing through the real VirtIO TX path; this is not a log-only claim.

NEGATIVE CASES:
- no NIC: `E72IPV6: NODEV n=0`, no panic (`build/verification/e72/boot-nonic.log`);
- IPv4 EtherType `0x0800`: not consumed by native IPv6 (`other=1`), no reply;
- L2-truncated `0x86DD`: native filter rejects (`bad=1`, `CHECK truncated-filter`);
- bad ICMPv6 checksum, bad NDP Hop Limit, bad IPv6 version, bad IPv6 payload length, and non-local destination: no NA/Echo Reply; a subsequent valid Echo gets a reply (`ALIVE`);
- native RX queue saturation: `CHECK queue-sat drop>0` (observed 126-127);
- TX link down: host Echo while `e->link=0` gets no reply; `TXDOWN n=1`;
- TX full/closed contract: `CHECK txq-full rc=-2`, `CHECK txq-closed rc=-1` (isolated `qpasstry`, not NIC evidence);
- RX stop/unbind: `STOP rc=0`, `CHECK repeat-stop rc=-9`, `FINAL worker_exited=1`;
- repeat init/attach: `CHECK repeat-start rc=-7`, `CHECK repeat-attach rc=0`;
- no panic/fault/suicide markers in either boot.

CHAN COUNTERS:
- Snapshot before native Fs/IPv6 start and after the NS/Echo positive window:
  `CHAN-NATIVE namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0 clean=1`.
- Counters are supplemental; the host-verified NA/Echo bytes and the guest `POSITIVE rx=2 tx=2` are the primary evidence.

LEGACY REGRESSIONS:
- E7.1 fixture re-run after E7.2 changes: PASS (`build/verification/e71/test-e71-e72changes.log`), including real native TX/RX, legacy `#l` `connect 0x86dd` + data read, and all E7.1 negatives.
- Default `9pc64` + `9pc64mp` build and `tools/test-qemu.sh` boot: PASS (`build/verification/e72/build-default-e72changes.log`, `test-default-boot-e72changes.log`).
- E5 `9pc64oconsole` build and cons check: PASS, 23 Qids (19 native, 2 legacy-only, 2 intentionally unsupported), no `consdevtab` (`build-oconsole-e72changes.log`, `test-oconsole-e72changes.log`).
- E7.2 test profile does not open a legacy `#l` IPv6 data subscription, so IPv6 is not duplicated through Netfile. Legacy `#l` is still linked and `etheriq` still calls `etherlegacyrx` for every frame.

TEST COMMANDS / LOG PATHS:
```sh
IPV6_PROBE=1 WHAT=kernel tools/build.sh        # 9pc64e72
tools/test-e72-ipv6.sh                         # NDP NA + Echo + negatives + no-NIC
ETHER_PROBE=1 WHAT=kernel tools/build.sh
tools/test-e71-ether.sh                        # E7.1 regression
WHAT=kernel tools/build.sh
tools/test-qemu.sh                             # default kernel boot
OCONSOLE=1 WHAT=kernel tools/build.sh
python3 tools/cons_migration_check.py \
  --kernel build/amd64/9pc64oconsole \
  --devc build/amd64/pc64oconsole.devc.c
```
Local ignored logs:
- `build/verification/e72/build-e72.log`
- `build/verification/e72/test-e72.log`
- `build/verification/e72/boot-virtio.log`, `serial-virtio.log`
- `build/verification/e72/boot-nonic.log`, `serial-nonic.log`
- `build/verification/e72/build-default-e72changes.log`,
  `test-default-boot-e72changes.log`,
  `build-oconsole-e72changes.log`, `test-oconsole-e72changes.log`
- `build/verification/e71/test-e71-e72changes.log`
These are local, ignored evidence, not published Git contents.

NOT RUN / OPEN:
- No merge/rebase with `main`; no E6/E8 integration test.
- No native UDP6/TCP6, WireGuard, routing daemon, DHCPv6/DNS, userspace socket/handle ABI, or IPv6-only link cutover.
- No physical NIC validation; QEMU VirtIO only.
- `ipv6native_start` failure after partial `Fs`/`Ipifc` allocation does not yet free all Fs state; successful repeat start is covered (`EtherErrBusy`). Failure cleanup is `OPEN`.
- `ethercore_rxunregister` waits indefinitely if a registered sink blocks despite its contract; E7.2's sink is non-blocking and IRQ-safe. A later consumer must preserve that contract.
- The native `Medium.addmulti` is a no-op because the test profile enables promiscuous reception. A production multicast-filter policy is `OPEN`.
- Legacy `#l`/`#I`/`#W` and IPv4/ARP remain linked. The runtime is **TRANSITIONAL**, not IPv6-only.

E6/E8 INTEGRATION RISKS AND LATER GATE:
- `origin/main` now contains E6/E8 work (`pc64onativedisk`, `sdcore`, Dev pruning, OMAP regeneration). Files changed on both sides include `sys/src/9/pc64/main.c`, `sys/src/9/pc64/mkfile`, `tools/build.sh`, `sys/src/9/port/mkdevc`, `docs/STATUS.md`, `docs/KERNEL-API-ABI.md`.
- Expected conflicts: the `main.c` handoff chain (`onativeprobe` / E7.1 / E7.2), `pc64/mkfile` `CONFLIST`, `tools/build.sh` opt-in profile dispatch, and generated Dev/OMAP files. E8 prunes Dev registrations in `pc64onativedisk`; E7.2 keeps the ordinary `pc64*` profiles intact.
- Do not merge while E8 is active. Later integration gate: a clean review branch, re-run E6 O-server, E8 pruned profile, default `pc64`/`pc64mp`, E5 `pc64oconsole`, E7.1 fixture and E7.2 fixture on the combined tree. Reconcile `docs/STATUS.md` and `docs/KERNEL-API-ABI.md` only at that gate.
