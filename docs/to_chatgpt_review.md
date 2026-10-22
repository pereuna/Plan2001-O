Both loader issues are fixed and the full suite was rerun from a **clean committed tree**.

**Commits**
- `cb7d4a1` — fix native O exec stack and BSS bounds
- `4678fad` — test: exercise the 4 GiB BSS boundary
- `9c211fe` — docs-only STATUS record

**Tested commit:** `4678fad0d66f83b310291320e57aba12068934d`  
**Final HEAD:** `9c211feab794db4dc2614d30b8f7a28e6afbfcd4` (docs-only)  
**Working tree:** clean

**Fix 1 — `Tos` reservation**
`execo()` now reserves `sizeof(Tos)` first and places `argv` and its strings below it, matching the ordinary exec layout. It also bounds-checks the new stack area.

The O target now asserts:
- `argc == 1`
- `argv[0]` starts with `oexec `
- `_tos` is present
- `cyclefreq != 0` and `pid != 0`
- profiling `pp`/`next`/`last`/`first` pointers and `prof.pid`/`prof.what` remain zero

**Fix 2 — BSS addresses**
`abss`/`ebss` remain `uintptr` through both `execparse()` and both loader paths. Only segment sizes remain narrower.

The boundary regression:
- Host seeding patches the target’s BSS header field to `0xffffffff`.
- `abss`/`ebss` therefore extend past 4 GiB.
- The target proves it can access a BSS page at `0x100000000`.
- With the old 32-bit narrowing, the BSS extent wraps and that page faults; with `uintptr` it works.
- The target prints exactly one `ohello: argv, Tos and BSS boundary PASS` marker.

**Verification — all PASS from clean `4678fad`**

| Gate | Result | Log |
| --- | --- | --- |
| Full amd64 build | PASS | `build/verification/build-bssboundary.log` |
| selfroot | PASS | `build/verification/selfroot-bssboundary.log` |
| `test-o-exec` | PASS | `build/verification/test-o-exec.log`, `build/amd64/oexecvm/serial.clean.log` |
| `test-o-handles` | PASS | `build/verification/test-o-handles.log` |
| `test-ge` | PASS | `build/verification/test-ge.log` |
| `test-o-volume` | PASS | `build/verification/test-o-volume.log` |
| `test-o-objects` | PASS | `build/verification/test-o-objects.log` |
| `test-o-space` | PASS | `build/verification/test-o-space.log` |
| `test-o-boot` | PASS | `build/verification/test-o-boot.log` |

`test-o-exec` again verified missing-OID/truncated-header rollback, handle preservation, successful child execution and close-on-exec behavior.

`docs/STATUS.md` now records the tested commit, clean-tree state, commands, results, timestamps and log paths. Remaining limitations are unchanged: no catalog, architecture selection, dynamic linking, permissions, or general executable-object format support.
