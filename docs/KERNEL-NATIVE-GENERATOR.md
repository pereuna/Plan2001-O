# Kernel native-operation generator (E2–E4)

`tools/kernel_opmap.py` remains the one kernel analyser.  E1 added an opt-in
manifest/emitter; E2 generalises the emitter to one **source-verified readnum
rule** and proves the generated entries in a linked, booted `pc64native`
kernel.  The default `--write`, `--check`, `--stats` and OMAP artifacts are
still the tracked signal. E4 applies an independently reviewed E3 Qppid
extraction and executes it through the same E2 renderer.

## Status

**E4 APPROVE** for three bounded reads; [independent review](to_astra_review.md):

| Driver | Selector | Shared helper | Generated entry | Result |
| --- | --- | --- | --- | --- |
| `sys/src/9/pc/devrtc.c` | `Qrtc` read | `rtcqread` | `native_rtc_qrtc_read` | linked and executed |
| `sys/src/9/port/devcons.c` | `Qpid` read | `consqpidread` | `native_cons_qpid_read` | linked and executed |
| `sys/src/9/port/devcons.c` | `Qppid` read | `consread_qppid_read` | `native_cons_qppid_read` | independently reviewed, linked and executed |

All three use the same renderer/extractor.  No per-driver C body, `if driver ==`
branch or duplicate `render_rtc_source`/`render_cons_source` exists.

E5 moves the non-Dev console/time/random/proc/sysinfo services out of
`devcons.c` but leaves the E4 `consqpidread` and `consread_qppid_read` helper
text unchanged.  The devcons source pin is deliberately updated to
`7978565a...c7128375`; `--generate-native --check`, the 29 focused generator
tests and the real `pc64native` probe pass with the repinned source.

## E2 source identity (historical)

- E2 base revision: `7b4dfac4903e909dc2a00f37e9320335808029ac`.
- `sys/src/9/pc/devrtc.c`: SHA-256
  `6c2f2fd951f861b99323aa372ad902ffedf0f36124ef354be2f1f336c44cbe5d`.
- `sys/src/9/port/devcons.c`: SHA-256
  `068dca67758d90a60baed6d9250241c46ee23974b8f09ce45b06e7140e901896`.

The current RTC pin is unchanged; E4 replaces the devcons pin with
`5491d5a...dabf61`, and E5 re-pins the reviewed adapter split at
`7978565a44ab0ca4dc130276aeae09219567fe615094ee3c440666e9c7128375`.
The Qpid/Qppid helper text and source shape are unchanged; only the
surrounding core functions moved to `port/cons.c`, `port/procobs.c` and
`port/sysinfo.c`.
A source edit fails closed until reviewed and deliberately repinned.

## CLI and outputs

```sh
python3 tools/kernel_opmap.py --generate-native \
    --config pc64 --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --check \
    --config pc64 --out-dir build/generated/kernel-native
```

Outputs under `build/generated/kernel-native/` (Git-ignored):

| File | Contents |
| --- | --- |
| `kernel_native.h` | selector/size constants, helper and entry prototypes |
| `kernel_native.c` | thin generated bindings and per-driver selector dispatch |
| `native-decisions.json` | full `pc64` decision manifest and source mapping |

## The one generic rule

For a binding with `kind: readnum`, the extractor reads the named helper from
the existing tokenised `Analyzer` tree and requires a narrow shape:

- `long helper(void *buf, long n, vlong off)`, externally linked;
- optional `if(n <= 0) return n;` guard;
- optional `offset` local initialised from `off`;
- exactly one `readnum(offset, buf, n, value, size)` result, either
  `return readnum(...)` or `n = readnum(...); return n;`;
- offset is `off`, a cast of `off`, or the reviewed local;
- value calls only allow-listed symbols and identifiers;
- size is a literal or an allow-listed constant resolved from parsed enums;
- the selected `Dev` Qid case must `return helper(buf, n, off);`.

Refused without generation: other statements/control flow, `goto`, loops,
untracked locals, unreviewed calls or identifiers, macro/indirect values,
multiple readnum results, preprocessor-conditional helpers/handlers, stale
source hashes, missing helpers, and inconsistent binding data.  A partial token
match never produces executable C.

## Source changes and single implementation

The following are small, reviewed source edits, not automatic C-to-C
rewriting:

- `devrtc.c`: added `rtcqread(void*, long, vlong)` containing the existing
  Qrtc `readnum` body (assign-then-return).  `rtcread`'s `Qrtc` case delegates
  to it.  `off`/offset and `readnum` sizing are unchanged.
- `devcons.c`: added `consqpidread(void*, long, vlong)` with the existing
  `n <= 0` guard and `readnum((ulong)off, ..., up->pid, NUMSIZE)` direct
  return.  `consread`'s `Qpid` case delegates to it.

Both the inherited `Dev` branch and the generated native entry call the same
helper, so the algorithm has one implementation.  The helper source hashes are
pinned in the binding; any change fails closed until reviewed.

## Manifest decisions

- `Qrtc` read: `DIRECT`; value `(ulong) rtctime()`, size `12`, assign-return,
  no n guard.
- `Qpid` read: `DIRECT`; value `up->pid`, size `NUMSIZE` (resolved to `12`),
  direct-return, `n <= 0` guard also present before Qid dispatch.
- E1's separately reviewed RTC NVRAM read/write `DIRECT` claims are explicitly
  **downgraded to MANUAL** in E2: the generic rule is readnum-only and they are
  not silently retained or dropped.
- `devpipe` stays `MANUAL` (dynamic `Pipe`/`qref`/`c->aux` ownership).
- Other active drivers remain analysis-only `MANUAL`/`LEGACY`.

Authorization is explicit: both generated entries are **kernel-internal-only**.
The inherited `devopen`/Dirtab policy remains the user-facing policy
(`Qrtc` is `0664` with other-read set; `Qpid` is `0444`); the probe proves
`up->pid`, not a new public API.  No syscall, `/dev` adapter, fake Fgrp or OID kind was added.

## Opt-in build and probe

Normal `pc64`/`pc64mp` builds link `onativeprobe_stub.c`; the opt-in
`pc64native` config links `onativeprobe.c` and the staged generated C instead.
There is no bootdir in `pc64native`.

```sh
NATIVE_PROBE=1 WHAT=kernel tools/build.sh
tools/test-o-native-generator.sh
```

`tools/build.sh` regenerates the native artifacts, stages them under
`build/overlay/sys/src/9/pc64/`, and builds `9pc64native`.  `plan9.ini`
`onativeprobe=1` selects the probe independently of `oboot=server`.

The probe runs in a real `*onativeprobe*` kernel process after the scheduler.
It calls `rtcinit()` exactly once because `chandevinit()` does not run on this
path; it does not duplicate `chandevreset()`, PCI/clock setup or user
namespace creation.  It is read-only: no CMOS/NVRAM write or time set.

Observed on the disposable QEMU boot:

```text
ONATIVEPROBE: INIT rtcinit=done chandevinit=not-run
ONATIVEPROBE: BEGIN pid=1 namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
ONATIVEPROBE: RTC ... ret=12 value=1792789125
ONATIVEPROBE: RTC text=[ 1792789125 ] plausible=1
ONATIVEPROBE: RTC OFFSET fullret=12 partret=4 match=1
ONATIVEPROBE: PID ... ret=12 value=1 pid=1 match=1
ONATIVEPROBE: PID OFFSET fullret=12 partret=4 match=1
ONATIVEPROBE: rtc selector=101 caught=1 err=native rtc: unsupported selector
ONATIVEPROBE: cons selector=112 caught=1 err=native cons: unsupported selector
ONATIVEPROBE: END pid=1 namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0
ONATIVEPROBE: DONE
```

The measured window is from `BEGIN` to `END`; path counters stay zero.  The
test also checks size clamp, zero/negative `n` for Qpid, out-of-range offsets,
formatted text, exact return counts, absence of panic/fault, and the linked
symbols in `build/amd64/9pc64native`.  Logs are in
`build/verification/o-native-generator-{serial,boot}.log` (not committed).

## Evidence, limits and remaining Chan

- `python3 tools/test_kernel_opmap.py`: 21/21 PASS.
- Generated output is byte-for-byte reproducible; native `--check` PASS.
- `NATIVE_PROBE=1 WHAT=kernel tools/build.sh`: PASS, both generated symbols
  linked.
- `tools/test-o-native-generator.sh`: PASS (real RTC and PID).
- `WHAT=kernel tools/build.sh`: PASS (normal kernel unaffected).
- `tools/test-oboot-server.sh` (D2b): PASS; `tools/test-oboot-output.sh`: PASS;
  `tools/test-o-boot.sh`: PASS; `tools/test-o-pathless.sh`: PASS.
- Normal OMAP `--check` now PASS after a deliberate `--write`: the source
  fingerprint changed because of the reviewed helper edits, the new
  `onativeprobe`/stub/config files, and the `pc64native` config.  The
  `pc64native` report intentionally records generated `kernel_native` as an
  unresolved source object because that file is produced only under `build/`.

Limitations: this proves two read operations, not general driver conversion,
full legacy permission/lifecycle equivalence, or whole-kernel Chan
independence.  `Chan`, `Qid`, `Dirtab`, `Walk`, `Dev`, namespace/9P code,
pipe endpoints, GE/O volume discovery and all non-pilot driver paths remain.
The generated entries are kernel-internal-only and are not a userspace ABI.

## E3 source-to-source extraction proposals (opt-in)

E3 extends the same analyser with a **proposal-only** mode.  It never writes
tracked kernel sources and never activates a patch in a build.

```sh
# Pre-E2 historical input (disposable snapshot; not the worktree).
git archive 7b4dfac4903e909dc2a00f37e9320335808029ac |
    tar -x -C build/e3/pre-e2

python3 tools/kernel_opmap.py --propose-extraction --config pc64 \
    --source-tree build/e3/pre-e2 \
    --source-rev 7b4dfac4903e909dc2a00f37e9320335808029ac \
    --selectors rtc:read:Qrtc,cons:read:Qpid \
    --out-dir build/generated/e3-pre-e2

python3 tools/kernel_opmap.py --propose-extraction --config pc64 \
    --selectors cons:read:Qppid --out-dir build/generated/e3-head

# Determinism / tamper check; no writes.
python3 tools/kernel_opmap.py --propose-extraction ... --check
```

Accepted inputs are pinned by source SHA.  Historical and current hashes are
in `E3_PINNED_SHA`; a modified file or a different tree is refused.  Outputs
must stay under `build/generated/` and contain one deterministic
`<basename>.patch` per source file plus `extraction-decisions.json`.

| Candidate | Source SHA-256 | Result | Patch SHA-256 |
| --- | --- | --- | --- |
| pre-E2 RTC `Qrtc` read | `45722e4f...f1bcb` | `DIRECT-CANDIDATE`, helper `rtcread_qrtc_read` | `7b715be6...402b524` |
| pre-E2 cons `Qpid` read | `b6811757...1ece4` | `DIRECT-CANDIDATE`, helper `consread_qpid_read` | `ce667228...188de324` |
| E3 input `10d9fcd` cons `Qppid` read | `068dca67...0e901896` | `DIRECT-CANDIDATE`, helper `consread_qppid_read` | `abb25340...f2119ee3` |
| HEAD RTC `Qrtc` / cons `Qpid` | current | `ALREADY-EXTRACTED`, no patch | n/a |

Each patch inserts a non-static, kernel-internal helper at file top level and
replaces only the selected Qid case with `return <helper>(buf, n, off);`.
RTC's shared `ulong offset` remains untouched; the helper reconstructs its own
local.  The console helper preserves `if(n <= 0) return n;`, while the legacy
pre-dispatch guard remains in `consread`.  Qnvram, Qppid, Qkmesg, Qdir and
other cases are unchanged.  A synthetic renamed driver proves the same rule
without a driver-specific C emitter.

Fail-closed/refused constructs include changed or unpinned SHA, CR/CRLF input,
comments inside the replace span, preprocessor-conditional handlers, unsupported
casts/macros/callbacks, unresolved `up`, parameter/local collisions, fall-through
or missing returns, multiple readnum results, pre-dispatch side effects or
unsupported guards, overlapping spans, already-extracted branches, and
missing/ambiguous selectors.  The helper name is checked against declared and
called symbols.

Evidence: `git apply --check` passed against disposable copies of the exact
bases; applying there changed only the intended lines.  An isolated trial with
the repository's Plan 9 `6c` compiled both patched pre-E2 files
(`E3_COMPILE_RTC_`/`E3_COMPILE_CONS_` empty status; log
`build/vm/serial-20261024-065348.log`, not committed).  This is a compile
check, not a kernel link/boot or a runtime claim.

## E3a pre-dispatch safety repair

E3a closes a false-positive in E3's proposal prefix validation.  Before the
fix, a synthetic handler containing `offset += 1;` before the Qid switch was
accepted as `DIRECT-CANDIDATE` (patch SHA
`65e9c84f85738f60f9c3b96a6126a4236fdf490f0e107dcb6adb8060dcbd8b40`) even
though the generated helper reconstructed only the earlier
`ulong offset = off;` and lost the mutation.

The repair uses one token-aware classifier,
`_e3_classify_prefix()`, plus a shared policy check,
`_e3_validate_prefix_policy()`; `_e3_parse_branch()` no longer resolves locals
and validates the prefix through separate interpretations.  A proposal is
accepted only for:

- side-effect-free declarations without initializers;
- one unambiguous scalar offset initializer `= off` (or a reviewed cast);
- the exact `n <= 0`/`n == 0`-style guard and the existing directory guard;
- no later write or mutation of branch state.

Refused pre-switch constructs include every compound assignment
(`+= -= *= /= %= <<= >>= &= |= ^=`), plain writes to `offset`, `n`, `off`,
`buf`, `up`, `c` or their members/arrays/dereferences, `++`/`--`, pre-switch
`return` outside an approved guard, calls, initializer calls, chained or
conditional initializers, unrelated local initializers, duplicate or
function-pointer declarations, source-local macro aliases, inner
`#define`/`#undef`, statement expressions, unknown statements, and
preprocessor-conditional code inside the handler.

Evidence: `python3 tools/test_kernel_opmap.py` 27/27 PASS; the `offset += 1`
case now reports `REFUSED` with `pre-dispatch compound assignment/mutation is
not supported` and no patch.  The three positive E3 patch hashes are unchanged
and still pass disposable `git apply --check`.  No tracked kernel source was
modified.  This is still lexical/structural analysis, not full dataflow or
semantic equivalence.

## E4 independent integration (24 October 2026)

Implementation commit `f60211d0cd61886c839401262dff4a17abadd8a6` on `main`.
The actual generated Qppid patch retained SHA-256
`abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3`.
It was read, applied and compiled in isolation before applying the same patch
to devcons. E3 now reports Qppid ALREADY-EXTRACTED. Historical pins remain.
The binding requires exact `up->parentpid`, NUMSIZE=12, a live current process,
and a valid kernel caller buffer. Legacy 0444 permissions do **not** authorize
native callers: this helper is strictly kernel-internal, without a syscall.

Independent audit fixed three issues: a mutation hidden inside a directory
condition could be discarded; invalid UTF-8 could rewrite unrelated bytes;
and --check ignored leftover patches after a refusal. Directory recognition
is now exact, byte round-tripping is required, and unmanifested patches fail
check. Artifact publication is not transactional; an error or failed check
must stop consumption. DIRECT-CANDIDATE remains a review proposal.

All 29 generator tests, inventory/proposal/native checks, both kernel builds,
one fresh native QEMU boot, and D2b continuity passed. Native C/header and all
232 kernel files in the build input matched reviewed source. The existing
probe now checks actual parentpid (observed 0), exact text/length, offset-8
partial data, size/zero/negative/bounds/wrap cases alongside Qrtc/Qpid.
BEGIN–END path counters remained zero. D2b preserved 1→2→3 and both negatives.
Kernel builds now export their freshly compiled MicroPython for that gate.
Commands are maintained in [STATUS](STATUS.md); exact logs, hashes, reviewed
lines, limitations and verdict are in [the E4 review](to_astra_review.md).
This establishes three reads, not general driver conversion or whole-kernel
Chan removal. Existing Qzero remains MANUAL: memset/return is outside the
readnum rule. No generalized conversion or new ABI was added.
