#!/bin/bash
# Plan2001: the normal O-only boot path loads the real MicroPython executable
# from a native O object.  The default 9pc64 kernel embeds only oinit and the
# kbdfs console helper (plus the separate ohandle/oexec regression harnesses);
# oinit opens the O volume and "init" Space and executes OID_MP_EXEC.  The
# three-boot run must preserve the existing Counter 1 -> 2 -> 3 and its
# OID/alias; a REPL disk must evaluate an expression and keep a value across
# a restart of the same disk; a third check covers missing and malformed
# interpreter objects.  No root filesystem, pathname exec, synthetic
# filesystem or 9P is used.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/ompbootvm
disk=$b/ompboot.img
oimg=$b/ompboot-o.img
checkdisk=$b/ompcheck.img
repldisk=$b/omprepl.img
reploimg=$b/omprepl-o.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-boot-omp: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/micropython" ] || { echo "test-o-boot-omp: no build/selfroot micropython (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/oinit" ] || { echo "test-o-boot-omp: no build/selfroot oinit (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-o-boot-omp: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$kconf.rootc.c" ] || { echo "test-o-boot-omp: no generated $b/$kconf.rootc.c" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

mpsha=$(sha256sum "$root/build/selfroot/amd64/bin/micropython" | awk '{print $1}')
echo "### generated normal boot contents"
# The generated default bootdir, not a successful boot, establishes that
# MicroPython is absent from the normal kernel image.
grep -q 'addbootfile("mp"' "$b/$kconf.rootc.c" && fail "$kconf.rootc.c embeds mp"
grep -q 'addbootfile("oinit"' "$b/$kconf.rootc.c" || fail "$kconf.rootc.c has no oinit"
grep -q 'addbootfile("kbdfs"' "$b/$kconf.rootc.c" || fail "$kconf.rootc.c has no kbdfs"
grep -q 'bin/micropython' "$root/sys/src/9/pc64/$kconf" && fail "$kconf source names micropython"
# The historical embedded-MicroPython configuration is test-only and is not
# used by this normal-path gate.
if [ -n "$testkconf" ] && [ -s "$b/$testkconf.rootc.c" ]; then
	grep -q 'addbootfile("mp"' "$b/$testkconf.rootc.c" || fail "$testkconf.rootc.c (test-only) has no mp"
fi

echo "### fresh O image: default seeding of the built MicroPython, byte for byte"
if ! "$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1; then
	cat "$vm/mkovol.log" >&2
	fail "mkovol failed"
fi
cat "$vm/mkovol.log"
grep -q "^seed: mpexec [0-9]\\+ 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "mkovol did not seed the unchanged MicroPython by default"

echo "### ESP + O, no FS root, three boots"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"
puuid=$(cat "$disk.partuuid")
grep -q "^init=/boot/oinit -vol PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: wrong init line"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="

bootfile() {
	local tag=$1 file=$2
	stop
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name plan2001-ompboot -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$file",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-240}))
	until clean | grep -q '^init: done$\|^init: failed, no commit$\|^PASS: oinit object error handling\|^panic' ||
	      [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
		sleep 1
	done
	sleep 1
	clean > "$vm/$tag.log"
	{ echo "### $tag"; cat "$vm/$tag.log"; } >> "$vm/omp-boots.log"
	clean | grep -a '^oinit:\|^space:\|^init:\|^boot:\|^panic' || true
}

oidof() { sed -n 's/^init: shared Counter n [0-9]*, alias same, OID \([0-9a-f]*\).*/\1/p' "$1" | tail -1; }
checkboot() {
	local tag=$1 n=$2 version=$3 oidprev=$4
	local log=$vm/$tag.log oid
	grep -q 'o: O volume .* opened without FS' "$log" || fail "$tag: no native O volume"
	grep -q "^oinit: micropython object [0-9]\\+ bytes sha256 $mpsha$" "$log" || fail "$tag: O object hash differs from MicroPython"
	grep -q 'boot: MicroPython, no root' "$log" || fail "$tag: MicroPython did not run with no root"
	grep -q 'space: O: odemo code OID ffffffff00000000, digest [0-9a-f]\{64\}' "$log" || fail "$tag: code not loaded from O"
	grep -q "^init: run() -> $n\$" "$log" || fail "$tag: run() -> $n missing"
	grep -q "^init: shared Counter n $n, alias same, OID [0-9a-f]\+ (alias [0-9a-f]\+)\$" "$log" || fail "$tag: no same Counter/alias"
	grep -q "space: O: committed init version $version" "$log" || fail "$tag: no commit $version"
	grep -q '^init: done$' "$log" || fail "$tag: not done"
	grep -q '^panic' "$log" && fail "$tag: QEMU panic"
	grep -q 'commit failed' "$log" && fail "$tag: commit failure"
	grep -q '^init: / on gefs' "$log" && fail "$tag: an FS was mounted"
	grep -q '\.py\|\.mpy\|/usr/glenda/lib' "$log" && fail "$tag: a runtime source/bytecode file"
	oid=$(oidof "$log")
	[ -n "$oid" ] || fail "$tag: no Counter OID"
	[ -n "$oidprev" ] && [ "$oid" != "$oidprev" ] && fail "$tag: Counter OID changed ($oidprev -> $oid)"
	lastoid=$oid
}

rm -f "$vm/omp-boots.log"
bootfile boot1 "$disk"
grep -q 'space: O: init has no graph' "$vm/boot1.log" || fail "boot 1: the O Space was not fresh"
grep -q 'space: O: init initialized from O code (odemo)' "$vm/boot1.log" || fail "boot 1: no one-time initialization"
checkboot boot1 1 1 ""; oid=$lastoid
bootfile boot2 "$disk"
grep -q 'space: O: restored init version 1' "$vm/boot2.log" || fail "boot 2: the O graph was not restored"
grep -q 'init initialized from O code' "$vm/boot2.log" && fail "boot 2: module initialized again"
checkboot boot2 2 2 "$oid"; oid2=$lastoid
bootfile boot3 "$disk"
grep -q 'space: O: restored init version 2' "$vm/boot3.log" || fail "boot 3: the O graph was not restored"
grep -q 'init initialized from O code' "$vm/boot3.log" && fail "boot 3: module initialized again"
checkboot boot3 3 3 "$oid2"
stop

echo "### interactive REPL and a value persisted across a restart of one disk"
# tools/mkrepl is the supported human-facing image preparation tool: the same
# default kernel, a fresh O image with the built MicroPython, and oinit -repl.
# Remove only this gate's disposable image, never a user's repl.img.
rm -f "$repldisk" "$reploimg"
if ! OIMG="$reploimg" "$here/mkrepl" "$repldisk" > "$vm/mkrepl.log" 2>&1; then
	cat "$vm/mkrepl.log" >&2
	fail "mkrepl failed"
fi
cat "$vm/mkrepl.log"
grep -q '^init=/boot/oinit -repl -vol PARTUUID=' "$repldisk.ini" ||
	fail "mkrepl: no oinit -repl init line"
grep -q '^root=' "$repldisk.ini" && fail "mkrepl: has root="

repl_run() {
	local tag=$1 mode=$2
	stop
	rm -f "$vm/repl.sock"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name plan2001-omprepl -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$repldisk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial unix:"$vm/repl.sock",server=on,wait=on 2>"$vm/repl-qemu.log" &
	q=$!
	python3 - "$vm/repl.sock" "$vm/$tag.log" "$mode" <<'PY'
import select, socket, sys, time
path, logname, mode = sys.argv[1:4]
log = open(logname, "wb")
end = time.time() + 150
s = None
while time.time() < end:
    try:
        s = socket.socket(socket.AF_UNIX)
        s.connect(path)
        break
    except OSError:
        s = None
        time.sleep(0.2)
if s is None:
    print("REPL: no serial socket", file=sys.stderr)
    sys.exit(1)
s.setblocking(False)
buf = b""
def read(t):
    global buf
    e = time.time() + t
    while time.time() < e:
        r, _, _ = select.select([s], [], [], 0.2)
        if r:
            x = s.recv(65536)
            if not x:
                return
            buf += x
            log.write(x)
            log.flush()
def wait_for(pat, secs=60, start=0):
    global buf
    end = time.time() + secs
    while time.time() < end:
        read(0.5)
        if pat in buf[start:]:
            return True
    return False
def send(line):
    for c in (line + "\r").encode():
        s.sendall(bytes([c]))
        time.sleep(0.01)
def sendline(line, secs=60):
    start = len(buf)
    send(line)
    return wait_for(b">>> ", secs, start)
if not wait_for(b">>> "):
    print("REPL: no prompt: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
send("print('OINIT-REPL', 6*7)")
if not wait_for(b"OINIT-REPL 42"):
    print("REPL: expression result missing: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
if mode == "set":
    if not sendline("import space") or not sendline("space.open('init')"):
        print("REPL: set setup failed: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    start = len(buf)
    if not sendline("kept = 4242"):
        print("REPL: set assignment failed: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    if not wait_for(b"space: O: committed init version", 30, start):
        print("REPL: no commit: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    if not sendline("print('REPL-SET', kept)") or not wait_for(b"REPL-SET 4242"):
        print("REPL: set value missing: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    print("REPL: value set and committed")
else:
    if not sendline("import space"):
        print("REPL: restart setup failed: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    start = len(buf)
    if not sendline("space.open('init')"):
        print("REPL: restart open failed: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    if not wait_for(b"space: O: restored init version", 10, start):
        print("REPL: graph was not restored: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    if not sendline("print('REPL-KEPT', kept)") or not wait_for(b"REPL-KEPT 4242"):
        print("REPL: value did not survive: %r" % buf[-500:], file=sys.stderr)
        sys.exit(1)
    print("REPL: OINIT-REPL 42 PASS; value survived restart")
sys.exit(0)
PY
	st=$?
	if [ "$st" != 0 ]; then
		fail "REPL $mode (status $st)"
	else
		echo "repl $mode: PASS"
	fi
	stop
}

repl_run repl1 set
repl_run repl2 kept

echo "### missing and malformed interpreter objects"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -test -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$checkdisk" >/dev/null
bootfile check "$checkdisk"
grep -q 'oinit: missing interpreter returned an error PASS' "$vm/check.log" || fail "missing object: no error PASS"
grep -q 'oinit: handle usable after missing interpreter PASS' "$vm/check.log" || fail "missing object: handle lost"
grep -q 'oinit: malformed interpreter returned an error PASS' "$vm/check.log" || fail "malformed object: no error PASS"
grep -q 'oinit: handle usable after malformed interpreter PASS' "$vm/check.log" || fail "malformed object: handle lost"
grep -q 'PASS: oinit object error handling' "$vm/check.log" || fail "object error handling: no PASS"
grep -q '^panic' "$vm/check.log" && fail "object error handling: QEMU panic"
stop

echo "### normal startup with an older image that lacks the interpreter"
legacydisk=$b/omplegacy.img
if ! NOMPEXEC=1 "$here/mkovol" "$b/omplegacy-o.img" 192 "$here/odemo.py" > "$vm/legacy.log" 2>&1; then
	cat "$vm/legacy.log" >&2
	fail "mkovol legacy image"
fi
if grep -q '^seed: mpexec ' "$vm/legacy.log"; then fail "legacy image unexpectedly has an interpreter"; fi
NOROOTFS=1 CONSOLE=0 ROOTIMG="$b/omplegacy-o.img" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$legacydisk" >/dev/null
bootfile legacy "$legacydisk"
grep -q 'MicroPython object 0x4f45584543000003 is missing from O' "$vm/legacy.log" ||
	fail "legacy image: no clear missing-interpreter diagnostic"
grep -q 'oinit: MicroPython object .* could not be executed' "$vm/legacy.log" && fail "legacy image: tried to execute the missing object"
stop

echo "boot serial output: $vm/omp-boots.log"
[ "$fails" = 0 ] && echo "PASS: MicroPython loaded from a native O object (no embedded mp)" || { echo "FAIL: $fails"; exit 1; }
