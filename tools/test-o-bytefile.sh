#!/bin/bash
# Plan2001-O: first native GE/O byte-object vertical slice.
# tools/mkovol seeds the normal O demo module with tools/obytefile.py; the
# ordinary 9pc64 boot executes OID_MP_EXEC with -O PARTUUID=... -S init -B.
# run() then uses space.oput/space.oget to commit and read independent native
# O objects by numeric OID.  Three boots of one ESP + O disk check the six
# bytes of OID 42 across reboot, empty/binary/over-chunk values, two distinct
# OIDs with identical bytes, overwrite-across-reboot, and predictable errors.
# A separate REPL image (-O without -S) checks the unsupported-mode error.
# No root filesystem, pathname, directory, 9P service or Python graph value
# is used to carry these bytes.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obytevm
disk=$b/obytefile.img
oimg=$b/obytefile-o.img
repldisk=$b/obytefile-repl.img
reploimg=$b/obytefile-repl-o.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-bytefile: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/micropython" ] || { echo "test-o-bytefile: no build/selfroot micropython (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/oinit" ] || { echo "test-o-bytefile: no build/selfroot oinit (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-o-bytefile: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
mpsha=$(sha256sum "$root/build/selfroot/amd64/bin/micropython" | awk '{print $1}')

boot() {
	local tag=$1
	stop
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name plan2001-obyte -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$disk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-180}))
	until clean | grep -q '^init: done$\|^init: failed, no commit$\|^panic' || [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
		sleep 1
	done
	sleep 1
	clean > "$vm/$tag.log"
	{ echo "### $tag"; cat "$vm/$tag.log"; } >> "$vm/three-boots.log"
	clean | grep -a '^space:\|^init:\|^boot:\|^Obyte:\|^panic' || true
}

checkcommon() {
	local tag=$1 version=$2
	local log=$vm/$tag.log
	grep -q 'o: O volume .* opened without FS' "$log" || fail "$tag: no native O volume"
	grep -q "^oinit: micropython object [0-9]\\+ bytes sha256 $mpsha$" "$log" || fail "$tag: O object hash differs from MicroPython"
	grep -q 'boot: MicroPython, no root' "$log" || fail "$tag: MicroPython did not run with no root"
	grep -q 'space: O: odemo code OID ffffffff00000000, digest [0-9a-f]\{64\}' "$log" || fail "$tag: code not loaded from O"
	grep -q '^init: run() -> 0$' "$log" || fail "$tag: run() did not return 0"
	grep -q "space: O: committed init version $version" "$log" || fail "$tag: no commit $version"
	grep -q '^init: done$' "$log" || fail "$tag: not done"
	grep -q '^panic' "$log" && fail "$tag: QEMU panic"
	grep -q 'commit failed' "$log" && fail "$tag: commit failure"
	grep -q '^init: / on gefs' "$log" && fail "$tag: an FS was mounted"
	grep -q '\.py\|\.mpy\|/usr/glenda/lib' "$log" && fail "$tag: a runtime source/bytecode file"
	grep -q 'srv/.*9p\|9P.*serve\|9p.*serve' "$log" && fail "$tag: a 9P service"
	return 0
}

checkmarks() {
	local tag=$1 log=$vm/$1.log
	shift
	for m in "$@"; do
		grep -q "^Obyte: PASS $m\$" "$log" || fail "$tag: missing marker $m"
	done
	return 0
}

rm -f "$vm/three-boots.log"
echo "### mkovol with the byte-object test module and default MicroPython seed"
if ! "$here/mkovol" "$oimg" 192 "$here/obytefile.py" > "$vm/mkovol.log" 2>&1; then
	cat "$vm/mkovol.log" >&2
	fail "mkovol failed"
fi
cat "$vm/mkovol.log"
grep -q "^seed: mpexec [0-9]\\+ 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "mkovol did not seed the unchanged MicroPython by default"

echo "### ESP + O, no FS root, three boots of the same disk"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"
puuid=$(cat "$disk.partuuid")
grep -q "^init=/boot/oinit -vol PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: wrong init line"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="

boot boot1
grep -q 'space: O: init has no graph' "$vm/boot1.log" || fail "boot 1: the O Space was not fresh"
grep -q 'space: O: init initialized from O code (odemo)' "$vm/boot1.log" || fail "boot 1: no one-time initialization"
checkcommon boot1 1
checkmarks boot1 first-put-hello first-boot empty-bytes binary-nul-and-ff \
	larger-than-Objchunk two-oids-same-bytes first-oid-changed second-oid-unchanged \
	overwrite-first missing-oid reject-string-oid reject-float-oid reject-negative-oid \
	reject-overflow-oid reject-str-data reject-int-data reject-negative-put \
	reserved-roots reserved-first reserved-graph reserved-env reserved-code \
	reserved-upgrade-meta reserved-exec-test reserved-badexec-test reserved-mp-exec \
	over-limit-put hello-intact-after-errors

boot boot2
grep -q 'space: O: restored init version 1' "$vm/boot2.log" || fail "boot 2: the O graph was not restored"
grep -q 'init initialized from O code' "$vm/boot2.log" && fail "boot 2: module initialized again"
checkcommon boot2 2
checkmarks boot2 reboot-hello reboot-empty reboot-binary reboot-larger-than-Objchunk \
	reboot-first-oid-changed reboot-second-oid-unchanged missing-oid over-limit-put \
	overwrite-second reboot

boot boot3
grep -q 'space: O: restored init version 2' "$vm/boot3.log" || fail "boot 3: the O graph was not restored"
checkcommon boot3 3
checkmarks boot3 reboot-hello overwrite-persisted reboot
stop

echo "### unsupported mode: -O without -S has no open native O Space"
rm -f "$repldisk" "$reploimg"
if ! OIMG="$reploimg" "$here/mkrepl" "$repldisk" > "$vm/mkrepl.log" 2>&1; then
	cat "$vm/mkrepl.log" >&2
	fail "mkrepl failed"
fi
grep -q '^init=/boot/oinit -repl -vol PARTUUID=' "$repldisk.ini" ||
	fail "mkrepl: no oinit -repl init line"
stop
rm -f "$vm/repl.sock"
cp "$fwvars" "$vm/vars.fd"
"$qemu" -name plan2001-obyte-repl -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$repldisk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial unix:"$vm/repl.sock",server=on,wait=on 2>"$vm/repl-qemu.log" &
q=$!
if ! python3 - "$vm/repl.sock" "$vm/repl.log" <<'PY'
import select, socket, sys, time
path, logname = sys.argv[1:3]
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
    end = time.time() + secs
    while time.time() < end:
        read(0.5)
        if pat in buf[start:]:
            return True
    return False
def sendline(line, secs=60):
    start = len(buf)
    for c in (line + "\r").encode():
        s.sendall(bytes([c]))
        time.sleep(0.01)
    return wait_for(b">>> ", secs, start), start
if not wait_for(b">>> "):
    print("REPL: no prompt: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
ok, _ = sendline("import space")
if not ok:
    print("REPL: import failed: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
ok, start = sendline("space.oget(42)")
if not ok or b"space: no native O Space is open" not in buf[start:]:
    print("REPL: oget did not fail explicitly: %r" % buf[-600:], file=sys.stderr)
    sys.exit(1)
ok, start = sendline('space.oput(42, b"x")')
if not ok or b"space: no native O Space is open" not in buf[start:]:
    print("REPL: oput did not fail explicitly: %r" % buf[-600:], file=sys.stderr)
    sys.exit(1)
ok, start = sendline('print("Obyte: PASS unsupported-mode")')
if not ok or b"Obyte: PASS unsupported-mode" not in buf[start:]:
    print("REPL: unsupported-mode marker missing: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
print("REPL: oget/oput failed without an open native O Space")
sys.exit(0)
PY
then
	fail "unsupported mode REPL check"
fi
stop

echo "three-boot serial output: $vm/three-boots.log"
[ "$fails" = 0 ] && echo "PASS: native O byte objects by OID, no FS or Python graph" || { echo "FAIL: $fails"; exit 1; }
