#!/bin/bash
# Plan2001-O Level A: the executed native GE/O storage path opens its
# partition and performs OID register/read/commit/sync without namec,
# kernel Chan allocation, path walk, mount or path exec.  The normal
# 9pc64 -> /boot/oinit -> OID_MP_EXEC -> MicroPython boot is unchanged;
# this gate meters the window from sysovolopen's block discovery through
# the GE workers and checks that it adds zero legacy-namespace events.
#
# The baseline positive control is the same boot before that window:
# initcode's legacy /boot/oinit exec must show nonzero namec/exec counts.
# The test also checks direct PARTUUID GPT discovery, wrong/missing GUID
# and malformed GPT failures, block bounds/oversize behavior, an actual
# virtio flush reaching the driver, three boots of one disk, and OID
# persistence/monotonic registration.  Bootstrap and console remain the
# legacy /boot and /dev path, so this is Level A, not B or C.
#   TARGET      amd64 (default)
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/pathlessvm
disk=$b/pathless.img
oimg=$b/pathless-o.img
badguid=$b/pathless-badguid.img
badgpt=$b/pathless-badgpt.img
badgptdisk=$b/pathless-badgpt-data.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-pathless: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/micropython" ] || { echo "test-o-pathless: no build/selfroot micropython (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/oinit" ] || { echo "test-o-pathless: no build/selfroot oinit (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-o-pathless: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
mpsha=$(sha256sum "$root/build/selfroot/amd64/bin/micropython" | awk '{print $1}')

# boot DISK TAG [EXTRA_QEMU_ARGS...]
boot() {
	local d=$1 tag=$2; shift 2
	stop
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name plan2001-pathless -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$d",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		"$@" -nic none -display none -serial file:"$vm/serial.log" 2>"$vm/$tag-qemu.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-180}))
	until clean | grep -q '^init: done$\|^init: failed, no commit$\|^panic' || [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
		sleep 1
	done
	sleep 1
	clean > "$vm/$tag.log"
	clean | grep -a '^opath:\|^o: O volume\|^oblocktest:\|^sdvirtio:\|^Oreg:\|^init:\|^boot:\|^panic\|no disk has that partition' || true
}

# The counters on an opath line: namec newchan walk devwalk mount exec.
counts() {
	sed -n "s/^opath: $2 namec=\([0-9]*\) newchan=\([0-9]*\) walk=\([0-9]*\) devwalk=\([0-9]*\) mount=\([0-9]*\) exec=\([0-9]*\)$/\1 \2 \3 \4 \5 \6/p" "$1" | tail -1
}
# window TAG LOG: enter == opened == started, and the pre-window control
# has at least one namec/walk/mount/exec from the legacy /boot bootstrap.
window() {
	local tag=$1 log=$VM_LOG e o s
	VM_LOG=$vm/$tag.log
	e=$(counts "$VM_LOG" volopen-enter)
	o=$(counts "$VM_LOG" volopen-opened)
	s=$(counts "$VM_LOG" volopen-started)
	[ -n "$e" ] || { fail "$tag: no opath volopen-enter"; return; }
	[ "$e" = "$o" ] || fail "$tag: Chan/namec events during O open: $e -> $o"
	[ "$e" = "$s" ] || fail "$tag: Chan/namec events during GE start: $o -> $s"
	set -- $e
	[ "$1" -gt 0 ] || fail "$tag: positive control: namec count is zero before the window"
	[ "$3" -gt 0 ] || fail "$tag: positive control: walk count is zero before the window"
	[ "$5" -gt 0 ] || fail "$tag: positive control: mount count is zero before the window"
	[ "$6" -gt 0 ] || fail "$tag: positive control: exec count is zero before the window"
}
checkmark() {
	local tag=$1 m=$2
	grep -q "^$m\$" "$vm/$tag.log" || fail "$tag: missing marker $m"
}
checkcommon() {
	local tag=$1
	grep -q 'o: O volume .* opened without FS (native SD block)' "$vm/$tag.log" ||
		fail "$tag: O volume did not use the native SD block backend"
	grep -q "^oinit: micropython object [0-9]\\+ bytes sha256 $mpsha$" "$vm/$tag.log" ||
		fail "$tag: O object hash differs from MicroPython"
	grep -q 'boot: MicroPython, no root' "$vm/$tag.log" || fail "$tag: MicroPython did not run with no root"
	grep -q '^init: done$' "$vm/$tag.log" || fail "$tag: not done"
	grep -q '^panic' "$vm/$tag.log" && fail "$tag: QEMU panic"
	grep -q '^init: / on gefs' "$vm/$tag.log" && fail "$tag: an FS was mounted"
	grep -q 'srv/.*9p\|9P.*serve\|9p.*serve' "$vm/$tag.log" && fail "$tag: a 9P service"
	checkmark "$tag" 'oblocktest: PASS in-range-read'
	checkmark "$tag" 'oblocktest: PASS read-at-end'
	checkmark "$tag" 'oblocktest: PASS oversized-read-clamped'
	checkmark "$tag" 'oblocktest: PASS write-past-end'
	checkmark "$tag" 'sdvirtio: flush PASS'
}

rm -f "$vm/boots.log"
echo "### mkovol with the registration/preload module and default MicroPython seed"
if ! "$here/mkovol" "$oimg" 192 "$here/oregister.py" > "$vm/mkovol.log" 2>&1; then
	cat "$vm/mkovol.log" >&2; fail "mkovol failed"
fi
cat "$vm/mkovol.log"
grep -q "^seed: mpexec [0-9]\\+ 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "mkovol did not seed the unchanged MicroPython by default"

echo "### ESP + O, no FS root; opath/oblocktest/sdflushlog instrumentation"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=@PARTUUID@' \
	INI='opath=1;oblocktest=1;sdflushlog=1' \
	"$here/gefsdisk" "$disk"
puuid=$(cat "$disk.partuuid")
grep -q "^init=/boot/oinit -vol PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: wrong init line"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^opath=1$' "$disk.ini" || fail "plan9.ini: no opath"
grep -q '^oblocktest=1$' "$disk.ini" || fail "plan9.ini: no oblocktest"
grep -q '^sdflushlog=1$' "$disk.ini" || fail "plan9.ini: no sdflushlog"

echo "### boot 1: fresh Space, registration and the Level A window"
boot "$disk" boot1
grep -q 'space: O: init has no graph' "$vm/boot1.log" || fail "boot 1: the O Space was not fresh"
grep -q 'space: O: init initialized from O code (odemo)' "$vm/boot1.log" || fail "boot 1: no one-time initialization"
checkcommon boot1
checkmark boot1 'Oreg: PASS first-boot'
checkmark boot1 'Oreg: PASS fresh-empty-payload'
checkmark boot1 'Oreg: PASS fresh-binary-nul-ff'
checkmark boot1 'Oreg: PASS fresh-multichunk'
checkmark boot1 'Oreg: PASS equal-bytes-distinct-oid'
checkmark boot1 'Oreg: PASS skip-manual-future-candidate'
window boot1
grep -q 'space: O: committed init version 1' "$vm/boot1.log" || fail "boot 1: no graph commit 1"

echo "### boot 2: same disk, persistence and a new local OID"
boot "$disk" boot2
grep -q 'space: O: restored init version 1' "$vm/boot2.log" || fail "boot 2: graph not restored"
grep -q 'init initialized from O code' "$vm/boot2.log" && fail "boot 2: module initialized again"
checkcommon boot2
checkmark boot2 'Oreg: PASS saved-empty'
checkmark boot2 'Oreg: PASS saved-binary'
checkmark boot2 'Oreg: PASS saved-big'
checkmark boot2 'Oreg: PASS new-oid-strictly-above'
checkmark boot2 'Oreg: PASS reboot-new-payload'
checkmark boot2 'Oreg: PASS second-boot'
window boot2
grep -q 'space: O: committed init version 2' "$vm/boot2.log" || fail "boot 2: no graph commit 2"

echo "### boot 3: reads do not allocate; registration continues"
boot "$disk" boot3
grep -q 'space: O: restored init version 2' "$vm/boot3.log" || fail "boot 3: graph not restored"
checkcommon boot3
checkmark boot3 'Oreg: PASS readonly-missing'
checkmark boot3 'Oreg: PASS third-new-payload'
checkmark boot3 'Oreg: PASS third-boot'
window boot3
grep -q 'space: O: committed init version 3' "$vm/boot3.log" || fail "boot 3: no graph commit 3"

echo "### missing PARTUUID: block discovery fails without a namec fallback"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=00000000-0000-0000-0000-000000000000' \
	INI='opath=1' \
	"$here/gefsdisk" "$badguid"
puuid=$(cat "$badguid.partuuid")
boot "$badguid" badguid
grep -q 'no disk has that partition' "$vm/badguid.log" || fail "badguid: no clean missing-partition error"
grep -q 'o: O volume .*native SD block' "$vm/badguid.log" && fail "badguid: opened a volume"
e=$(counts "$vm/badguid.log" volopen-enter)
x=$(counts "$vm/badguid.log" volopen-error)
[ -n "$e" ] || fail "badguid: no volopen-enter"
[ "$e" = "$x" ] || fail "badguid: namespace events on failed discovery: $e -> $x"

echo "### malformed GPT on another unit: rejected, no namec fallback"
truncate -s 64M "$badgptdisk"
python3 - "$badgptdisk" <<'PY'
import struct, sys
p = sys.argv[1]
with open(p, "r+b") as f:
    f.seek(512)
    f.write(b"EFI PART")
    f.write(struct.pack("<Q", 1))          # revision
    f.write(struct.pack("<I", 92))         # header size
    f.write(struct.pack("<I", 0))          # crc (not checked here)
    f.write(struct.pack("<I", 0))          # reserved
    f.write(struct.pack("<Q", 0x123456))   # my lba
    f.write(struct.pack("<Q", 0xffffffffffffffff))  # alternate lba
    f.write(struct.pack("<Q", 2))          # first usable
    f.write(struct.pack("<Q", 1 << 40))    # last usable (too large)
    f.write(b"\0" * 16)
    f.write(struct.pack("<Q", 1 << 50))    # entries lba (out of range)
    f.write(struct.pack("<I", 1 << 20))    # entries (over limit)
    f.write(struct.pack("<I", 4096))       # entry size (over limit)
PY
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INIT='/boot/oinit -vol PARTUUID=00000000-0000-0000-0000-000000000001' \
	INI='opath=1' \
	"$here/gefsdisk" "$badgpt"
boot "$badgpt" badgpt \
	-drive file="$badgptdisk",format=raw,if=none,id=d1 \
	-device virtio-blk-pci-non-transitional,drive=d1
grep -q 'no disk has that partition' "$vm/badgpt.log" || fail "badgpt: no clean missing-partition error"
grep -q 'o: O volume .*native SD block' "$vm/badgpt.log" && fail "badgpt: opened a volume"
e=$(counts "$vm/badgpt.log" volopen-enter)
x=$(counts "$vm/badgpt.log" volopen-error)
[ -n "$e" ] || fail "badgpt: no volopen-enter"
[ "$e" = "$x" ] || fail "badgpt: namespace events on malformed discovery: $e -> $x"
stop

echo "three-boot serial output: $vm/boot1.log $vm/boot2.log $vm/boot3.log"
[ "$fails" = 0 ] && echo "PASS: Level A pathless native GE/O storage window, persistence and bounds" || { echo "FAIL: $fails"; exit 1; }
