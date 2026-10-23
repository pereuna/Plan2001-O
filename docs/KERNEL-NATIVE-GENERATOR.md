# Kernel native-operation generator (E1)

`tools/kernel_opmap.py` is still the one kernel analyser.  E1 adds an
**opt-in** consumer of `Analyzer.analyze()`; it does not add a second scanner,
a second call graph or an obsolete inventory script.  The default
`--write`, `--check`, `--stats` and the checked-in OMAP JSON/Markdown are
unchanged.

This is a reversible experiment towards pathless device operations.  It does
not convert the 27 active drivers, remove `Chan`, add a syscall or change the
kernel build.

## CLI

```sh
# Write reproducible generated artifacts under build/ (ignored by Git).
python3 tools/kernel_opmap.py --generate-native \
    --config pc64 --out-dir build/generated/kernel-native

# Compare the existing generated artifacts; fail if stale or missing.
python3 tools/kernel_opmap.py --generate-native --check \
    --config pc64 --out-dir build/generated/kernel-native

# Existing behaviour, preserved when --generate-native is absent.
python3 tools/kernel_opmap.py --write
python3 tools/kernel_opmap.py --check
python3 tools/kernel_opmap.py --stats
```

Outputs:

| File | Contents |
| --- | --- |
| `kernel_native.h` | numeric selector constants and the RTC native prototypes |
| `rtc_native.c` | reviewed RTC read/write entry; no walk/namec/devdirread |
| `native-decisions.json` | per-active-driver operation specification and refusals |

The generated C is **not** included in the kernel build.  It lives only under
`build/`.

## Source identity

- Generator base revision: `c894eb52ac2eda63227b04651c3aab5ff7976b20`.
- RTC source: `sys/src/9/pc/devrtc.c`, SHA-256
  `45722e4fc13195b14924e7781c5eae09412704919233315f2502c0bfed3f1bcb`.
- Pipe source: `sys/src/9/port/devpipe.c` (analysis only; no generated code).
- The reviewed binding is hash-pinned.  A change to `devrtc.c` makes
  `--generate-native` refuse with a stale-binding error instead of silently
  regenerating a wrapper nobody reviewed.

## RTC pilot

The parsed `rtcdir[]`/enum mapping is `Qdir=0`, `Qrtc=1`, `Qnvram=2`.
`rtcwalk`, `rtcstat` and the directory branch of `rtcread` remain namespace
implementation (`LEGACY`).  The generated entry removes the `c->qid.path`
switch and the `Chan`, not the numeric selectors.

| Selector | Operation | Conversion | Generated binding |
| --- | --- | --- | --- |
| `Qrtc` | read | `DIRECT` | `rtctime()` + `readnum(..., 12)` |
| `Qnvram` | read | `DIRECT` | `nvramread()` with `Nvoff`/`Nvsize` bounds |
| `Qnvram` | write | `DIRECT` | `nvramwrite()` with offset-0 rule and bounds |
| `Qrtc` | write | `MANUAL` | static `sec2rtc()`/`PUTBCD` is not exported; entry raises an error |

Permission semantics from `rtcopen` are preserved at the operation boundary:

- `Qrtc` read: any user; `Qrtc` write: `eve` only.
- `Qnvram` read and write: `eve` only.

`rtc_native_read` calls `rtc_native_permitted(selector, OREAD)` and
`rtc_native_write` calls it with `OWRITE`; both go through `openmode()`, as
`rtcopen` did.  There is no `return 0` success stub and the Qrtc write path is
an explicit error, not a fake hardware operation.

Offset handling is also reviewed rather than invented:

- `Qrtc` read: `readnum` bounds to 0..11.
- `Qnvram` read: `off >= Nvsize` returns 0; `n` is clamped; address is
  `off + Nvoff`.
- `Qnvram` write: `off != 0` is `Ebadarg`, matching `rtcwrite`; then the same
  clamp and `Nvoff` translation.

What this does **not** prove: that the generated wrapper is linked and called
on a real boot, or that the hardware, locking and IRQ behaviour is equivalent.
`rtctime`/`nvramread`/`nvramwrite` still take the existing `nvrtlock` and do
port I/O.  E1 is therefore **PARTIAL**: the interface is generated and
compile-checked, but not executed in a booted kernel.

The minimal next reviewed step is a controlled in-kernel call of
`rtc_native_read(NQrtc, ...)` on a disposable boot, plus a reviewed exported
`rtc_settime(ulong)` (or a reviewed extraction of the static `sec2rtc`/`PUTBCD`
path) before any Qrtc write can leave `MANUAL`.

## Pipe

`devpipe.c` is analysed with the same frontend and deliberately **not**
generated.  Safe automation is blocked by dynamic endpoint ownership:

- `Pipe` state is stored in `c->aux`; a native caller has no equivalent handle.
- `ref`/`qref` counting in `pipeopen`/`pipeclose` decides `qhangup`, `qclose`,
  `qreopen` and the final free.
- read on `Qdata0` and write on `Qdata1` target opposite queues `q[0]`/`q[1]`.
- `wstat` changes queue limits with `qsetlimit`.

The manifest marks these operations `MANUAL` and records the blockers.  A
future bridge would need a reviewed `Pipe`/queue object, not a text template.

## Classification vocabulary

- **DIRECT**: a pathless entry is generated from a reviewed binding and the
  selected branch calls no `Chan`-dependent helper.
- **BRIDGE**: a pathless entry would still use `Chan` internally.  E1 has no
  generated bridge instances; it records the category for comparison.
- **MANUAL**: unsafe or unproven for automatic extraction (indirect callback,
  dynamic lifetime, missing semantic evidence).
- **LEGACY**: namespace/metadata implementation (`walk`, `stat`, directory
  read, generic `Dev` helpers) not required by a numeric-selector native O
  operation.

## Unsupported constructs, categorised

- **Namespace:** `devwalk`, `devdirread`, `namec`, path/mount state.
- **Chan state:** `c->qid`, `c->aux`, `c->flag`, `c->mode`, `c->offset`,
  `c->dev`.
- **Indirect dispatch:** callbacks whose concrete target is not unique.
- **Preprocessor:** alternative branches and source-local `Chan`/`Mount`/
  `Path` macro aliases (for example the GEFS-local names, which are not the
  kernel types).
- **Lifetime:** pipe queues, mount/9P transports, open/close handle identity.
- **Hardware/OS state:** init/reset/shutdown, interrupt and DMA ownership,
  locking.

## Reproduce and compile-check

```sh
python3 tools/test_kernel_opmap.py
python3 tools/kernel_opmap.py --generate-native \
    --out-dir build/generated/kernel-native
python3 tools/kernel_opmap.py --generate-native --check \
    --out-dir build/generated/kernel-native
```

The generated C was also compiled with the repository's Plan 9 `6c` in the
build VM, against the repository's kernel headers (`tools/overlay -k`, then
`6c -I/tmp/sys/include -c rtc_native.c` from a disposable copy of
`sys/src/9/pc64`).  The session reported `REPO_COMPILE_STATUS_` (empty status =
success); the first base-header attempt had already compiled after the
include-order fix.  Observed logs are `build/vm/serial-20261023-233225.log`
(repository headers) and `build/vm/serial-20261023-232948.log` (base headers),
not committed.  This is compile validation only, not a runtime RTC test.

## Remaining Chan dependencies

The generator removes nothing from the kernel.  `Chan`, `Qid`, `Dirtab`,
`Walk`, `Dev`, namespace and 9P code remain, including non-pilot drivers'
`walk`/`stat`/`open`/`close` paths, pipe endpoints, GE/O volume discovery and
the RTC directory interface.  Only the three generated RTC selector operations
have a compile-checked, Chan-free entry; this is not a Chan-free driver claim.
