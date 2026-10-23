#!/bin/bash
# Plan2001-O: local native OID registration.
#
# The normal 9pc64 boot executes OID_MP_EXEC from O; MicroPython loads the
# O-resident test module at OID_CODE and calls run() with -O ... -S init.
# Four boots of one disposable ESP + O disk check empty/text/binary/
# multi-chunk values, identity without content equality, explicit-ID
# coexistence, reboot persistence, and read-only behavior.  A separate
# /boot/ohandle -reg boot runs two processes with independent native
# Space handles registering concurrently.  A REGALLOC fixture image has a
# malformed allocator header and must reject registration without resetting
# it.  A REPL image (-O without -S) checks the unsupported-mode error.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/oregistervm
disk=$b/oregister.img
oimg=$b/oregister-o.img
cdisk=$b/oregister-corrupt.img
coimg=$b/oregister-corrupt-o.img
repldisk=$b/oregister-repl.img
reploimg=$b/oregister-repl-o.img
for f in gefs micropython oinit ohandle; do
	[ -x "$root/build/selfroot/amd64/bin/$f" ] ||
		{ echo "test-o-register: no build/selfroot $f (tools/selfroot)" >&2; exit 1; }
done
[ -s "$b/$kernel" ] || { echo "test-o-register: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
mpsha=$(sha256sum "$root/build/selfroot/amd64/bin/micropython" | awk '{print $1}')

boot() {
	local tag=$1 d=${BOOTDISK:-$disk}
	stop
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name plan2001-oregister -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$d",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-180}))
	until clean | grep -q '^init: done$\|^init: failed, no commit$\|^PASS: native OID registration under two processes$\|^FAIL:.*registration\|^panic' ||
	      [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
		sleep 1
	done
	sleep 1
	clean > "$vm/$tag.log"
	{ echo "### $tag"; cat "$vm/$tag.log"; } >> "$vm/boots.log"
	clean | grep -a '^space:\|^init:\|^boot:\|^Oreg:\|^oreg:\|^PASS:\|^FAIL:\|^panic' || true
}

checkcommon() {
	local tag=$1 log=$vm/$1.log
	grep -q 'o: O volume .* opened without FS' "$log" || fail "$tag: no native O volume"
	grep -q "^oinit: micropython object [0-9]\\+ bytes sha256 $mpsha$" "$log" ||
		fail "$tag: O object hash differs from MicroPython"
	grep -q 'boot: MicroPython, no root' "$log" || fail "$tag: MicroPython did not run with no root"
	grep -q 'space: O: odemo code OID ffffffff00000000, digest [0-9a-f]\{64\}' "$log" ||
		fail "$tag: code not loaded from O"
	grep -q '^init: run() -> 0$' "$log" || fail "$tag: run() did not return 0"
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
		grep -q "^Oreg: PASS $m\$" "$log" || fail "$tag: missing marker $m"
	done
	return 0
}

saved='saved-empty saved-hello saved-binary saved-big saved-revised
	saved-original saved-revision-registration saved-manual-64 saved-manual-70'

rm -f "$vm/boots.log"
echo "### mkovol with the registration test module and default MicroPython seed"
if ! "$here/mkovol" "$oimg" 192 "$here/oregister.py" > "$vm/mkovol.log" 2>&1; then
	cat "$vm/mkovol.log" >&2
	fail "mkovol failed"
fi
cat "$vm/mkovol.log"
grep -q "^seed: mpexec [0-9]\\+ 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "mkovol did not seed the unchanged MicroPython by default"

echo "### ESP + O, no FS root"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"
puuid=$(cat "$disk.partuuid")
grep -q "^init=/boot/oinit -vol PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: wrong init line"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="

echo "### boot 1: fresh Space"
boot boot1
grep -q 'space: O: init has no graph' "$vm/boot1.log" || fail "boot 1: the O Space was not fresh"
grep -q 'space: O: init initialized from O code (odemo)' "$vm/boot1.log" ||
	fail "boot 1: no one-time initialization"
checkcommon boot1
checkmarks boot1 reject-str-data reject-int-data over-limit-data missing-before-write \
	fresh-oid-is-int fresh-oid-in-range skip-explicit-candidate fresh-empty-payload \
	manual-64-intact fresh-second-oid fresh-hello missing-distinct-from-empty \
	fresh-binary-oid fresh-binary-nul-ff fresh-big-oid fresh-multichunk \
	fresh-same-first equal-bytes-distinct-oid skip-manual-future-candidate \
	equal-bytes-both-readable revision-changed revision-other-intact \
	revision-did-not-allocate revision-registration-payload first-boot
grep -q 'space: O: committed init version 1' "$vm/boot1.log" || fail "boot 1: no graph commit 1"

echo "### boot 2: persistence and a new local OID"
boot boot2
grep -q 'space: O: restored init version 1' "$vm/boot2.log" || fail "boot 2: graph not restored"
grep -q 'init initialized from O code' "$vm/boot2.log" && fail "boot 2: module initialized again"
checkcommon boot2
checkmarks boot2 $saved new-oid-strictly-above new-oid-unused \
	reboot-new-payload second-boot
grep -q 'space: O: committed init version 2' "$vm/boot2.log" || fail "boot 2: no graph commit 2"

echo "### boot 3: reads do not allocate; registration continues"
boot boot3
grep -q 'space: O: restored init version 2' "$vm/boot3.log" || fail "boot 3: graph not restored"
checkcommon boot3
checkmarks boot3 $saved saved-boot2 readonly-missing new-oid-strictly-above \
	new-oid-unused third-new-payload third-boot
grep -q 'space: O: committed init version 3' "$vm/boot3.log" || fail "boot 3: no graph commit 3"

echo "### two processes with independent native Space handles"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/ohandle -reg -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"
puuid=$(cat "$disk.partuuid")
grep -q "^init=/boot/ohandle -reg -vol PARTUUID=$puuid$" "$disk.ini" ||
	fail "plan9.ini: wrong concurrency init line"
boot concurrency
grep -q '^PASS: native OID registration under two processes$' "$vm/concurrency.log" ||
	fail "concurrency: no PASS"
grep -q '^oreg: parent ' "$vm/concurrency.log" || fail "concurrency: no OID transcript"
if grep -q '^FAIL:\|^panic' "$vm/concurrency.log"; then fail "concurrency: failure or panic"; fi
ids=$(grep '^oreg: parent ' "$vm/concurrency.log" | awk '{print $3; print $5}' | sort -u | wc -l)
[ "$ids" = 16 ] || fail "concurrency: $ids distinct OIDs, want 16"

echo "### boot 4: Python graph and payloads survive independent native writes"
boot boot4
grep -q 'space: O: restored init version 3' "$vm/boot4.log" || fail "boot 4: graph not restored"
checkcommon boot4
checkmarks boot4 $saved saved-boot2 saved-boot3 new-oid-above-external \
	new-oid-unused fourth-new-payload fourth-boot
grep -q 'space: O: committed init version 4' "$vm/boot4.log" || fail "boot 4: no graph commit 4"

echo "### corrupted allocator state is rejected, not reset"
python3 - "$vm/regalloc-bad" <<'PY'
import struct, sys
open(sys.argv[1], "wb").write(b"OALLOC01" + struct.pack(">Q", 0))
PY
if ! REGALLOC="$vm/regalloc-bad" "$here/mkovol" "$coimg" 192 "$here/oregcorrupt.py" > "$vm/mkovol-corrupt.log" 2>&1; then
	cat "$vm/mkovol-corrupt.log" >&2
	fail "mkovol corrupt fixture failed"
fi
cat "$vm/mkovol-corrupt.log"
grep -q '^seed: regalloc 16 ' "$vm/mkovol-corrupt.log" || fail "corrupt fixture not seeded"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$coimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$cdisk"
puuid=$(cat "$cdisk.partuuid")
grep -q "^init=/boot/oinit -vol PARTUUID=$puuid$" "$cdisk.ini" ||
	fail "corrupt plan9.ini: wrong init line"
BOOTDISK="$cdisk" boot corrupt
checkmarks corrupt corrupt-allocator-rejected corrupt-allocator-still-rejected \
	corrupt-allocator-not-reset
grep -q '^init: done$' "$vm/corrupt.log" || fail "corrupt: module did not finish"
grep -q '^panic' "$vm/corrupt.log" && fail "corrupt: QEMU panic"

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
"$qemu" -name plan2001-oregister-repl -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
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
ok, start = sendline("space.oregister()")
if not ok or b"space: no native O Space is open" not in buf[start:]:
    print("REPL: oregister did not fail explicitly: %r" % buf[-600:], file=sys.stderr)
    sys.exit(1)
ok, start = sendline('print("Oreg: PASS unsupported-mode")')
if not ok or b"Oreg: PASS unsupported-mode" not in buf[start:]:
    print("REPL: unsupported-mode marker missing: %r" % buf[-400:], file=sys.stderr)
    sys.exit(1)
print("REPL: oregister failed without an open native O Space")
sys.exit(0)
PY
then
	fail "unsupported mode REPL check"
fi
stop

echo "automatic boot transcripts: $vm/boots.log"
[ "$fails" = 0 ] && echo "PASS: local native OID registration, persistence and concurrency" ||
	{ echo "FAIL: $fails"; exit 1; }
