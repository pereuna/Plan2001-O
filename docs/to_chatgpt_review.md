Implemented and pushed local native OID registration.

- Added `space.oregister([data])` backed by native `ospacecreate`, with allocator state in the existing Space header transaction.
- Added collision-safe high-water allocation, corruption rejection, concurrent-create serialization, `ohandle -reg`, and `tools/test-o-register.sh`.
- Scope is explicitly one active native O volume/Space; no machine-wide or remote identity.

Commits: `a9c3247`, `077ba29`, `09cb651`, `4644d1a`. Pushed to `main`.

All gates passed: the new registration gate plus `test-o-bytefile` and the nine existing O-only gates. Evidence: `build/verification/*-register.log`, `build/verification/test-o-register-final.log`, and `docs/to_chatgpt_review.md`.
