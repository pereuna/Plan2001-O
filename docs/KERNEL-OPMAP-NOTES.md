# Kernel operation map — manual cross-check notes

**These notes are manual annotations, not generated output.**  The generated
inventory is [KERNEL-OPMAP.md](KERNEL-OPMAP.md) and
[KERNEL-OPMAP.json](KERNEL-OPMAP.json); regenerate it with
`python3 tools/kernel_opmap.py --write`.

The checks below were made against the source paths named in each item.  They
confirm the representative chains used by the generator and identify the
file-layer responsibilities a future extraction must preserve.  They do not
claim runtime behaviour, semantic equivalence or safe removability.

## 1. GE/O native open still depends on Chan/Dev for volume discovery

- `sys/src/9/port/devgefs.c:437` `sysovolopen` is a native syscall handler.
  It reads the user's volume specification, then calls `gevolume`
  (`devgefs.c:462`) and `oopen` (`devgefs.c:467`).
- `gevolume` (`devgefs.c:286`) resolves `PARTUUID=...` through `scandisks`
  (`devgefs.c:170`).  That function opens `#S` with `namec` (`devgefs.c:181`),
  reads the device directory through `devtab[top->type]->read`
  (`devgefs.c:189`), opens each disk path with `namec` (`devgefs.c:200`) and
  reads GPT entries through `devtab[c->type]->read` (`devgefs.c:132`,
  `devgefs.c:149`).
- `oopen` (`sys/src/9/gefs/o.c:81`) calls the GE engine's `geopen`
  (`sys/src/9/gefs/kern.c:913`).  The generated representative chain records
  `sysovolopen -> gevolume -> namec -> oopen -> geopen`; the `Chan` and
  `devtab[]->read` edges are evidence that `OVOLOPEN` is not yet a purely
  native block-interface operation.
- Responsibilities to preserve in a plain-C operation: volume-spec parsing,
  GPT partition lookup, O-profile/version validation, GE instance start, and
  the process-local O handle lifetime (`sysospaceopen` etc. in
  `devgefs.c:554` onward).

## 2. Partition dispatch reaches SDifc, then a concrete storage backend

- `devsd` read/write Qpart cases call `sdbio` (`sys/src/9/port/devsd.c:796`)
  from `sdread` (`devsd.c:1221`) and `sdwrite` (`devsd.c:1355`).
- `sdbio` checks partition bounds and media-change state, translates the byte
  offset into `bno`/`nb`, and then calls
  `(*unit->dev->ifc->bio)(...)` at `devsd.c:875`, `devsd.c:887` and
  `devsd.c:896`.  The generated chain leaves this as an indirect interface
  edge with candidates `nvmebio`, `ahcibio`, `viobio`, `loopbio`, `rambio`.
- The candidate implementations exist at `sys/src/9/port/sdnvme.c:244`,
  `sys/src/9/pc/sdiahci.c:1797`, `sys/src/9/port/sdvirtio10.c:540`,
  `sys/src/9/port/sdloop.c:279` and `sys/src/9/port/sdram.c:228`.  The scanner
  deliberately does not choose one from `devsd` alone.
- Responsibilities to preserve: partition offset/length and sector-size
  translation, removable-media locking, the raw/SCSI request paths, and the
  controller's own DMA/interrupt lifetime.

## 3. Keyboard input

- `kbdread` (`sys/src/9/pc/devkbd.c:405`) handles Qscancode by calling
  `kbdpoll` (`devkbd.c:327`) and reading the keyboard queue.
- `kbdpoll` calls `i8042intr` (`devkbd.c:262`); the interrupt/poll handler
  reads the controller status and data through `inb(Status)` at
  `devkbd.c:269` (and the low-level helpers use `inb`/`outb` at
  `devkbd.c:70`, `devkbd.c:86`, `devkbd.c:117` and `devkbd.c:131`).
- Responsibilities to preserve: the 8042 lock, interrupt versus polling
  mode, scancode queue ownership, LED writes, and the `iseve` check in
  `kbdopen` (`devkbd.c:369`).

## 4. Kernel console and serial/UART

- `conswrite` (`sys/src/9/port/devcons.c:636`) has a Qcons branch that copies
  the user buffer and calls `putstrn0` (`devcons.c:112`).
- `putstrn0` writes the kernel message ring, then either calls the
  `screenputs` hook or `uartputs` (`sys/src/9/port/devuart.c:846`).
  `uartputs` ends in the `PhysUart.putc` callback at `devuart.c:856` and
  `devuart.c:857`; the pc implementation is `i8250putc`
  (`sys/src/9/pc/uarti8250.c`), registered as `i8250physuart`.
- Responsibilities to preserve: console ownership, the `serialoq` and
  `kprintoq` queues, `kmesg` ring accounting, the escape-sequence exception,
  and the polling fallback used by `iprint`/panic.

## 5. Network data path

- `etherwrite` (`sys/src/9/port/devether.c:311`) treats a non-`Ndataqid`
  write as control, including the manually dispatched `nonblocking` command
  and the `ether->ctl` callback (`devether.c:339`).
- The data branch frames the packet through `etheroq`
  (`devether.c:290`) -> `ethermux` (`devether.c:184`) and finally
  `qbwrite(ether->oq, bp)` (`devether.c:307`).  The output queue's `Qkick`
  callback is installed as `ether->transmit` at `devether.c:478`
  (`qopen(q, Qmsg|Qkick, (void (*)(void*))ether->transmit, ether)`), so the
  generated chain keeps the transmit callback as an interface edge rather
  than pretending it is called directly from `etherwrite`.
- Candidates include `rtl8169transmit` (`sys/src/9/pc/ether8169.c:919`) and
  the other `addethercard` registrations.  Responsibilities to preserve:
  MTU checks, bridge/bypass/promiscuous modes, queue ownership and kick
  semantics, and DMA/proxy handling.

## 6. Dynamic Qid directory and textual control dispatch

- `devsd` has no static `Dirtab` array for its unit/partition tree.  `sdgen`
  (`sys/src/9/port/devsd.c:534`) switches on `TYPE(c->qid)` and constructs
  entries for `Qtopdir`, `Qunitdir`, `Qraw`, `Qctl`, `Qpart`, `Qextra` and
  `Qtopctl`.  `sdread`/`sdwrite` switch on the same type encoding.
- `devsd` also accepts first-field commands implemented without a `Cmdtab`
  table (`part`, `delpart` around `devsd.c:1443`), alongside Cmdtab-driven
  controls such as `devcons` (`rebootmsg` at `sys/src/9/port/devcons.c:35`,
  `drivermsg` at `devcons.c:47`) and `devvga` (`vgactlmsg` at
  `sys/src/9/pc/devvga.c:44`).
- Responsibilities to preserve: the packed `QID(dev, unit, part, type)`
  encoding, version checks (`c->qid.vers`), the dynamic directory generator,
  and the difference between a local Dev write and a mounted 9P transport.
  The report does not describe local dispatch as 9P.

## 7. User-space kbdfs boundary

- The normal `pc64` configuration's `bootdir` embeds
  `/$objtype/bin/aux/kbdfs`, but `kbdfs` is a user-space 9P server that edits
  and forwards console input.  It is not a kernel-mode driver.
- Kernel endpoints relevant to the boundary are `#c` (`devcons`), `#b`
  (`devkbd`, pc64 only), `#t` (`devuart`), the `screenputs` hook and the
  `PhysUart.putc`/`getc` callbacks.  The operation map records the embedded
  binary only as a configuration entry; it does not audit the kbdfs
  user-space server.

## 8. Source and artifact identity for this check

- Generated artifacts were regenerated with
  `python3 tools/kernel_opmap.py --write` from the tree whose fingerprint is
  in `KERNEL-OPMAP.md`; the current commit and verification result are in
  `docs/STATUS.md`.  The generated report contains the full current counts;
  the manual notes above are not used to compute them.
