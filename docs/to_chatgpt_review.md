E7.2 toteutettu ja pushattu vain branchille `design/ipv6-only-native-20261024`.

- **Verdict:** APPROVE
- **Commitit:** `35ea815`, `bb48ffd`, `d56db5b`, `6bf0961`, `6aae8c4`, `703073f`
- **Oikea VirtIO-polku:** hostin NS → guest NA (`flags=0x60`) ja hostin Echo Request → guest Echo Reply, molemmat hostin tavu-/checksum-verifioinnilla.
- **Guest-evidence:** `POSITIVE rx=2 tx=2`, `CHAN-NATIVE ... clean=1`, `DONE pass=1 fails=0`.
- **Negatiivit:** ei NICiä, IPv4 EtherType, truncation, väärä checksum/hop limit/versio/pituus, queue saturation, TX down/full/closed, repeat init/attach/stop.
- **Regressiot:** E7.1-fixture, default `9pc64`/`9pc64mp` boot ja E5 `9pc64oconsole` kaikki PASS.
- **Raportit:** `docs/IPV6-NATIVE-MIGRATION.md`, `docs/to_chatgpt_review_e72.md`; logit `build/verification/e72/` ja `e71/`.
- `main`iin, PR #1:een tai E6/E8-työhön ei koskettu; status on edelleen **TRANSITIONAL**.
