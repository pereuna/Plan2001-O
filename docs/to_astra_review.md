ASTRA E4 VERDICT: APPROVE

BASE HEAD / FINAL COMMIT / BRANCH:
Base `10d9fcd2640496e085a6e7b13d02d0643fbad1d0`, clean `main` after
`git pull --ff-only`. Final implementation commit: `f60211d0cd61886c839401262dff4a17abadd8a6`.
This documentation-only report follows that approved code commit on `main`.
Independent execution on 24 October 2026; no OpenCode or delegated agent.

GENERATED PATCH:
- Original/current-source proposal: `build/generated/e4-astra/devcons.c.patch`.
- Source SHA: `068dca67758d90a60baed6d9250241c46ee23974b8f09ce45b06e7140e901896`.
- Patch SHA: `abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3`.
- Applied devcons SHA: `5491d5a76253e25073434fa3913ec87216ffe76dc37465051a9f6c28d2dabf61`.
- Unchanged RTC SHA: `6c2f2fd951f861b99323aa372ad902ffedf0f36124ef354be2f1f336c44cbe5d`.
- Reviewed original devcons lines 314–388 (enum, Dirtab, readnum), 423–443
  (legacy open), 470–541 (helper, prefix, selected branch). Original ASCII
  source span `[9578,9640)`, insertion at 8408: token/string offsets equal
  byte offsets here. Preserved source/output hashes are in
  `build/verification/e4/reviewed-source-sha256.txt` and `native-build-input.log`. New helper lines 478–488, legacy call 549–550.
- Full patch read; applied/check-tested first in `build/e4-isolated`, a
  detached exact-base worktree, then compiled with real 6c and repo headers.
  The tightened generator produced an identical patch in `e4-reviewed`;
  that exact patch was applied to the main worktree and compared byte-for-byte
  with the isolated result. No handwritten replacement body.

INDEPENDENT AUDIT:
1. **Fixed unsafe directory-guard recognition**, `kernel_opmap.py:5202`.
   Minimal counterexample before the switch:
   `if((offset += 1, c->qid.type & QTDIR)) return devdirread(c, buf, n, syndir, 2, devgen);`
   E3a emitted DIRECT-CANDIDATE and lost the increment. Require exact, effect-free
   directory condition and complete return shape now. Regression also uses
   `nelem(syndir)` and an ordinary `offset += 1;` negative; both refused,
   no patch. Positive standard guard retained. Before/after evidence:
   `build/verification/e4/prefix-{before,after}.log`.
2. **Fixed lossy source decoding**, `kernel_opmap.py:5850`: a pinned synthetic
   source with `b"/* \\xff */\\n"` previously decoded with replacement and could
   rewrite unrelated bytes (reproduced with the original E3a tool;
   `build/verification/e4/artifacts-before.log`). Extraction now refuses a UTF-8/hash round-trip
   mismatch. Offsets for valid non-ASCII input remain Python text offsets;
   they must not be advertised universally as byte offsets.
3. **Fixed stale-patch checking**, `kernel_opmap.py:6172`: write a candidate,
   then a REFUSED manifest into the same output directory; the old patch
   remained and --check ignored it. --check now rejects unmanifested patches.
   The original checker returned no problems in the recorded reproducer.
   Output writes are still not a multi-file transaction; generation never
   applies sources, errors must stop consumption, and --check plus manifest
   digest review is required. The actual reviewed output was freshly generated.
4. Reviewed shared prefix classifier/policy at 5289/5411, branch parsing at
   5604, helper rendering at 5714, candidate/hash/collision checks at 5813.
   Existing assignment/member/pointer mutation, conditional/preprocessor,
   unknown statement, collision, overlap, stale-SHA and tamper tests pass.
   ALREADY-EXTRACTED means delegation detected, not semantic approval. Only
   the reviewed devcons binding was repinned; historical E3 pins retained.
5. The helper preserves `n <= 0` (including negative return), `vlong offset`
   then `(ulong)offset`, unsigned parentpid and NUMSIZE=12. Plan 9 long/ulong
   are 32 bits here; off=-1 becomes out-of-range, off=2^32 wraps to zero as
   before. Positive n is at most signed-long max, so off<12 plus n cannot
   overflow ulong. readnum formats width 11 plus trailing blank and copies
   at most the remaining 12 bytes. Its mixed declaration after a guard is
   accepted by the actual Plan 9 compiler (also cc.y:365–386).
6. **Authorization/context:** consopen/devopen and Dirtab 0444 authorize
   legacy requests only. The new helper has no independent user permission
   check. Approved exclusively for trusted kernel callers, valid buffer/length,
   `up != nil`; no syscall or userspace entry. kproc/linkproc establishes the
   actual probe process context (proc.c:1583–1648). This is a process observation,
   not hardware identity. No process, clock, O storage or permission mutation.
7. Native chain: numeric dispatcher → native wrapper → shared helper →
   readnum → snprint/vsnprint/dofmt built-in integer formatting and memmove.
   Reviewed libc/fmt and port/print locking: memory formatting, no path I/O;
   format-table caching is internal bookkeeping. No Chan, namec, walk, Dirtab
   or Qid-path lookup in this operation's chain. Numeric 13 is checked against
   the live enum and Dirtab at generation time.
8. Build inspection found WHAT=kernel removed root/ despite compiling
   MicroPython; export that newly compiled binary in build.rc:138–140 so D2b
   uses fresh current-source bytes without WHAT=all or restoring stale output.

NATIVE C:
`consread_qppid_read` is externally linked and used by both legacy consread
and generated `native_cons_qppid_read`; `native_cons_read` dispatches Qpid
and Qppid. Reviewed data allow exactly `up->parentpid` and NUMSIZE=12,
require process context, and document the kernel-only boundary. Same generic
readnum renderer as Qrtc/Qpid, no duplicated readnum algorithm. Qdir/Qpid/
Qkmesg, legacy guards and shared offset local unchanged by the extraction.

VERIFICATION:
All logs below are local ignored artifacts in `build/verification/e4/`.
| Exact command | Observed result / log |
| --- | --- |
| `python3 tools/kernel_opmap.py --propose-extraction --config pc64 --selectors cons:read:Qppid --out-dir build/generated/e4-astra` | PASS, original DIRECT-CANDIDATE; `proposal-original.log` |
| Same command with `--check` | PASS; same log |
| Same generation/check pair with `--out-dir build/generated/e4-reviewed` after repair | PASS, identical patch; `proposal-reviewed.log` |
| `git worktree add --detach build/e4-isolated HEAD` then `git -C build/e4-isolated apply --check /home/lapere/Src/Plan2001-O/build/generated/e4-astra/devcons.c.patch` and same `apply` without `--check` | PASS, exact base, only 13 insertions/1 deletion |
| `tools/9run -t 120 --script build/verification/e4/isolated-compile.rc` | PASS: `6c -I. -I/tmp/sys/include -c ../port/devcons.c`, empty `E4_COMPILE_CONS_` status; `isolated-{compile,serial}.log` |
| `git apply --check build/generated/e4-reviewed/devcons.c.patch` then `git apply build/generated/e4-reviewed/devcons.c.patch` | PASS; `cmp` against isolated devcons passed |
| `python3 tools/test_kernel_opmap.py` | PASS 29/29; `source-tests.log` |
| `python3 tools/kernel_opmap.py --check` | Initial FAIL: new source fingerprint; `omap-before.log` |
| `python3 tools/kernel_opmap.py --write`, then `python3 tools/kernel_opmap.py --check` | PASS after constrained diff review; `omap-{write,check,diff-review}.log`, `omap.diff` |
| `python3 tools/kernel_opmap.py --propose-extraction --config pc64 --selectors cons:read:Qppid --out-dir build/generated/e4-applied`, then same with `--check` | PASS: ALREADY-EXTRACTED, zero patches; `proposal-applied.log` |
| `python3 tools/kernel_opmap.py --generate-native --config pc64 --out-dir build/generated/kernel-native`, then same with `--check` | PASS: 3 DIRECT operations; `native-generation.log` |
| `NATIVE_PROBE=1 WHAT=kernel tools/build.sh` | PASS compile/link; `native-build.log`, `native-build/`, `native-build-serial.log` |
| `python3 build/verification/e4/check-build-input.py` | PASS: all 232 kernel sources, generated C/header, and build.rc in actual VM input matched; `native-build-input.log` |
| `tools/test-o-native-generator.sh` | PASS, **one** fresh native QEMU run, all six helper/entry symbols present; `native-qemu.log`, `o-native-generator-{serial,boot}.log` |
| `WHAT=kernel tools/build.sh` | PASS normal pc64 and script's pc64mp control; `normal-build.log`, `normal-build/`, `normal-build-serial.log` |
| `python3 build/verification/e4/check-build-input.py --normal` | PASS source identity; `normal-build-input.log` |
| `tools/test-oboot-server.sh` | PASS three same-disk boots and both negatives; `d2b.log`, `d2b/serial{1,2,3,fail,missing}.log`, corresponding boot logs |

All required gates ran. Source tests were repeated after the two additional
artifact-safety fixes and once after refining the PPID partial read to offset 8;
no native QEMU rerun was needed. No WHAT=all or unrelated battery ran.
The native boot precedes the normal build intentionally: the latter replaces
staging/loader output. Native compiled artifacts/serial were preserved first.
The builds use the existing VM bootstrap tools/libraries as required by the
kernel-only gate; this was not a full libc rebuild.

Reviewed inventory fingerprint:
`3fe196b84e63da346e5783fad13478a6c10ef3ba8f62f5cbbb32b6939a58f2d6`.
Only devcons/probe source records changed; config/coverage/Dirtab unchanged,
no unrelated operation changes. Generated source SHA:
`5182c79f2072e1645512cdea5db3df8fef278e15b9296ef87b9cd50debaff3a3`.
Native kernel SHA:
`6091b68a9ffb10640c670a5cdbf80361b0141001acf597b775c79bebfe7c08f8`;
normal kernel SHA:
`a6e274a356b43c5add0867c17ca340c885ea023cbeb266ead0fa6bd0bc86955b`.
Generated provenance records base HEAD plus dirty=true and the exact source
fingerprint; committing these unchanged bytes does not retroactively change
the tested artifact. Archived generation is retained in `native-build/`.

Observed native markers: RTC value=1792817643, ret=12, plausible=1;
PID value=1 pid=1 match=1; PPID value=0 ppid=0 match=1, text
`[          0 ]` format_match=1, OFFSET fullret=12 partret=4 match=1;
zero/negative/bounds/wrap matches=1; unsupported selectors 101/112 caught=1;
DONE, no panic/fault/hang. Values were compared at runtime, not fixed in tests.
D2b observed run()=1/2/3, Counter OID=alias=7, commits 1/2/3 (O 2/3/4),
no commit/done on failing run, missing OID_MP_EXEC refusal with no fallback.
Fresh O-resident MicroPython: 2,195,994 bytes, SHA-256
`bc4156a0e44c5e8c96647eb9923e052f5eec6ec7e8e816a761a8ba8c9319c2ba`;
seed and OEXECUTE hashes matched. All disks/firmware variables were disposable.

PATHLESS WINDOW:
Native BEGIN and END: pid=1, namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0.
This includes all Qrtc/Qpid/Qppid probe calls and diagnostic printing, after
rtcinit, before the final sleep. Counters instrument chan.c, dev.c and sysproc.c;
not a proof of absent Chan dependencies elsewhere or all possible execution.
D2b also recorded zero legacy/path counters at syscall counts 4/16/32/64 in
each of the three fresh boots, with no LEGACY-ATTEMPT markers.

UNRESOLVED RISKS:
Only three reviewed reads, no general conversion or independent authorization.
The analyser remains lexical/structural, with bounded call analysis and service
cutoffs, not a compiler or equivalence proof. Source pins, manual review and
fresh compile/boot evidence are part of acceptance; --expect-sha is not review.
Inherited namespaces/Chan, device lifetimes and other driver operations remain.
Stretch: existing OMAP marks cons Qzero read `partial`, service-only; its
`memset(buf,0,n); return n;` is not a readnum result. E2 leaves it MANUAL
without a reviewed binding; E3's readnum-only rule refuses its first statement.
No conversion rule was broadened to make it pass. POC source-branch history
and OpenCode's historical review remain untouched.
