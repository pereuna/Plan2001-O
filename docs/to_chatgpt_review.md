Implemented and pushed.

- `bf2117e` — `space.oget(oid)` / `space.oput(oid, data)`, reserved-OID checks, 1 MiB limit, qstr regeneration, focused test, and API docs.
- `3f82ec0` — STATUS evidence and `docs/to_chatgpt_review.md`.

Verification: `tools/test-o-bytefile.sh` **PASS** (OID 42 = six bytes across three boots, empty/binary/2048-byte values, overwrite, identity separation, error cases, unsupported mode); all nine existing O-only gates **PASS**. Logs under `build/verification/*-bytefile.log`; branch `main` is up to date with origin.
