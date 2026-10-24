E7.1 completed and pushed to `origin/design/ipv6-only-native-20261024`.

- **Verdict:** APPROVE
- **Commits:** `f942e0e` audit, `152b764` native core + legacy adapter, `3035a57` VirtIO probe/fixture, `4e46415` report
- **Verified:** `9pc64` + `9pc64mp` build/boot, `9pc64oconsole` build + E5 check, `9pc64e71` real VirtIO native TX/RX, legacy `#l` RX, no-NIC and negative cases.
- **Reports:** `docs/ETHER-MIGRATION.md`, `docs/to_chatgpt_review_e71.md`; logs under `build/verification/e71/`.
- `main` was untouched; PR #1 was not merged. Current status remains **TRANSITIONAL**, not IPv6-only runtime.
