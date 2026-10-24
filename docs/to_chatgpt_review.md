E7.3.1 hardening completed and pushed to `origin/design/ipv6-only-native-20261024`.

- **Verdict:** APPROVE
- **Commits:** `9b59a66` audit/contract, `1285a52` receive/close/destroy/send hardening, `58e01cb` concurrency fixtures, `310fdad` Announced-state send guard, `1146d24` final report
- **Receive:** atomic `qget`, per-receiver waiter list (fixed single-waiter double-sleep), bounded `timeout_ms`; 10-round two-reader race: `ok=10 timeout=10 max_timeout=610`, two-datagram race `ok=2`
- **Lifecycle:** `U6Open→Closing→Closed→Destroyed`; close quiesces before `closeconv`; explicit `udp6_destroy`; 200-cycle reap test: `opens=200 closes=200 destroys=200 live_delta=0`, final `live=0`, Conv slots `2→2`
- **Send:** synchronous no-route rejection (`-13`), `waserror` unwind (`fake-exc=-14`, lock released), post-error send works, close-vs-send race passes; link-down remains a truthful accepted-then-dropped case
- **Real hardware:** VirtIO UDP6 echo with `0/1/17/1452`-byte payloads, multi-port checksums/ports/payloads, NDP, negatives, `CHAN` counters `clean=1`
- **Regressions:** E7.3 ×3, E7.2, E7.1, default `9pc64`/`9pc64mp`, E5 `9pc64oconsole` all PASS
- **Docs/logs:** `docs/UDP6-NATIVE-MIGRATION.md`, `docs/to_chatgpt_review_e731.md`; logs under `build/verification/e731/`
- `main`, PR #1, E6/E8/E9, and prior stage reports were not modified.
