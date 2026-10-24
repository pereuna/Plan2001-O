E7.3 toteutettu, verifioitu ja pushattu branchille `design/ipv6-only-native-20261024`.

- **Verdict:** APPROVE
- **Commitit:** `c3edcc5` (map), `3c1f88b` (lifecycle/hardening), `936ca55` (UDP6 API), `a55c5b5` (VirtIO/UDP6 fixture), `9503802` (report)
- **Oikea VirtIO UDP6:** hostin datagrammit kahdesta lähdeportista pituuksilla `0/1/17/1452`; guest palautti ne oikeille IP/portti-yhdistelmille muuttumattomalla payloadilla ja validilla UDP6-checksumilla.
- **Guest evidence:** `POSITIVE rx=6 tx=6 bytes=1486`, `COUNTERS in=34 out=8 noports=1 inerrors=5`, `CHAN-NATIVE ... clean=1`.
- **Negatiivit:** väärä/zero-checksum, väärät UDP-pituudet, truncation, IPv4-frame, unbound-port (ICMPv6 Port Unreachable), duplicate bind, IPv4-mapped bind, queue saturation (`DropFull=14`), link down, close/repeat-close/post-close, stop/repeat-stop/restart-after-stop.
- **Regressiot:** E7.2, E7.1, default `9pc64`/`9pc64mp` ja E5 `9pc64oconsole` kaikki PASS.
- **Raportit:** `docs/UDP6-NATIVE-MIGRATION.md`, `docs/to_chatgpt_review_e73.md`; logit `build/verification/e73/`.
- `main`iin, PR #1:een, E6/E8/E9-työhön tai aiempiin E7-raportteihin ei koskettu. Status pysyy **TRANSITIONAL**-tilassa.
