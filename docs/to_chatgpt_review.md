**VERDICT: APPROVE** (documented queue-boundary limitation in the report).

- Fixed `nativeinh6.c` lifecycle: REGISTERED → DRAINING → UNREGISTERED, stable callback pair captured at admission, Busy keeps DRAINING latched, retry finalizes, concurrent unregister returns Busy, and `wlock(ifc)` quiesces stale native demux lookups.
- Added deterministic E743 regression: red before `E743IP: BUSY ... draining=0`, green after with Busy/re-register rejection/drain/retry/rearm and five fresh-payload cycles.
- All gates passed: E74, E76, E77, E73, E72, E71, default `test-qemu`, E5 console. Logs in `build/verification/e743/`; report in `docs/to_chatgpt_review_e743.md`.
- Pushed only `origin/design/ipv6-only-native-20261024` at `268d444` (fix `6fdd4c4`). No merge, `main`, E7.5, or SEALED work.
