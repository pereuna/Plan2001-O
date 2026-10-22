#!/bin/bash
# Plan2001: boot the real MicroPython executable from a native O object.
# A dedicated test kernel (9pc64omp) embeds only /boot/oinit and /boot/kbdfs;
# oinit opens the O volume and "init" Space and executes the MicroPython
# object at OID 0x4f45584543000003 with the arguments main.c needs.  The
# three-boot run must preserve the existing Counter 1 -> 2 -> 3 and its
# OID/alias; a separate boot reaches the REPL and evaluates an expression;
# a third checks missing and malformed interpreter objects.  No root
# filesystem, pathname exec, synthetic filesystem or 9P is used.
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
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-boot-omp: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/micropython" ] || { echo "test-o-boot-omp: no build/selfroot micropython (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/oinit" ] || { echo "test-o-boot-omp: no build/selfroot oinit (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$testkernel" ] || { echo "test-o-boot-omp: no $b/$testkernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$testkconf.rootc.c" ] || { echo "test-o-boot-omp: no generated $testkconf.rootc.c" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

mpsha=$(sha256sum "$root/build/selfroot/amd64/bin/micropython" | awk '{print $1}')
echo "### generated boot contents"
# The tested kernel's generated bootdir, not a successful boot, establishes
# that MicroPython is absent from its image.  The ordinary config still has it.
grep -q 'addbootfile("mp"' "$b/$testkconf.rootc.c" && fail "$testkconf.rootc.c embeds mp"
grep -q 'addbootfile("oinit"' "$b/$testkconf.rootc.c" || fail "$testkconf.rootc.c has no oinit"
grep -q 'addbootfile("kbdfs"' "$b/$testkconf.rootc.c" || fail "$testkconf.rootc.c has no kbdfs"
grep -q 'addbootfile("mp"' "$b/pc64.rootc.c" || fail "ordinary pc64.rootc.c has no mp"
grep -q 'bin/micropython' "$root/sys/src/9/pc64/$testkconf" && fail "$testkconf source names micropython"

echo "### O image: demo Environment, code, MicroPython byte for byte"
if ! MPEXEC="$root/build/selfroot/amd64/bin/micropython" \
	"$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1; then
	cat "$vm/mkovol.log" >&2
	fail "mkovol failed"
fi
cat "$vm/mkovol.log"
grep -q "^seed: mpexec [0-9]\\+ 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "mkovol did not verify the unchanged MicroPython seed"

echo "### ESP + O, no FS root, three boots"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$testkernel" \
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

echo "### interactive REPL through the O-loaded interpreter"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$testkernel" \
	INIT='/boot/oinit -repl -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$repldisk" >/dev/null
stop
rm -f "$vm/repl.sock"
cp "$fwvars" "$vm/vars.fd"
"$qemu" -name plan2001-omprepl -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$repldisk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial unix:"$vm/repl.sock",server=on,wait=on 2>"$vm/repl-qemu.log" &
q=$!
if python3 - "$vm/repl.sock" "$vm/repl.log" <<'PY'
import select, socket, sys, time
path = sys.argv[1]
log = open(sys.argv[2], "wb")
end = time.time() + 120
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
while time.time() < end:
    read(0.5)
    if b">>> " in buf:
        break
if b">>> " not in buf:
    print("REPL: no prompt: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
for c in b"print('OINIT-REPL', 6*7)\r":
    s.sendall(bytes([c]))
    time.sleep(0.01)
while time.time() < end:
    read(0.5)
    if b"OINIT-REPL 42" in buf:
        print("REPL: OINIT-REPL 42 PASS")
        sys.exit(0)
print("REPL: expression result missing: %r" % buf[-400:], file=sys.stderr)
sys.exit(1)
PY
then
	echo "repl: expression evaluated"
else
	fail "REPL smoke test"
fi
stop

echo "### missing and malformed interpreter objects"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$testkernel" \
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

echo "boot serial output: $vm/omp-boots.log"
[ "$fails" = 0 ] && echo "PASS: MicroPython loaded from a native O object (no embedded mp)" || { echo "FAIL: $fails"; exit 1; }
