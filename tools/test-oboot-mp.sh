#!/bin/bash
# HISTORICAL D1 HARNESS: expects the pre-D2a nil-Fgrp PWRITE panic.
# Superseded by tools/test-oboot-output.sh; do not use against a D2a kernel.
# Plan2001 Boot Experiment D1: start the unchanged O-resident MicroPython
# by the pathless first-user process, then record the highest reached
# startup milestone and the first inherited FD/namespace dependency.
# This is a diagnostic gate: a missing FD table may panic the kernel, and
# that panic is reported, not hidden as a working MicroPython boot.
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obootmpvm
oimg=$b/obootmp-o.img
disk=$b/obootmp.img
missingo=$b/obootmp-missing-o.img
missing=$b/obootmp-missing.img
mp=$root/build/selfroot/amd64/bin/micropython
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-oboot-mp: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$mp" ] || { echo "test-oboot-mp: no $mp (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-oboot-mp: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$loader" ] || { echo "test-oboot-mp: no $b/$loader (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" 2>/dev/null | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill "$q" 2>/dev/null || true; wait "$q" 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
mpsize=$(stat -c %s "$mp")
mpsha=$(sha256sum "$mp" | awk '{print $1}')

bootcase() {
	local tag=$1 img=$2 waitpat=$3
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name "plan2001-obootmp-$tag" -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$img",format=raw,if=none,id=d0 \
		-device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu-$tag.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-90}))
	until clean | grep -q "$waitpat" || [ $SECONDS -ge $end ] || ! kill -0 "$q" 2>/dev/null; do
		sleep 1
	done
	sleep 1
	stop
	clean > "$vm/boot-$tag.log"
}

echo "### positive: default O image, OID_MP_EXEC, oboot=mp"
rm -f "$oimg"
"$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1 ||
	{ cat "$vm/mkovol.log" >&2; fail "mkovol positive failed"; }
grep -q "^seed: mpexec $mpsize 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "positive: MicroPython seed bytes changed"
grep -q "^seed: object mp oid=0x4f45584543000003 len=$mpsize$" "$vm/mkovol.log" ||
	fail "positive: OID_MP_EXEC not present in the O seed"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INI='oboot=mp;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$disk" > "$vm/gefsdisk.log" 2>&1 ||
	{ cat "$vm/gefsdisk.log" >&2; fail "gefsdisk positive failed"; }
puuid=$(cat "$disk.partuuid")
grep -q "^obootvol=PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: obootvol not substituted"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^init=' "$disk.ini" && fail "plan9.ini: has init="

bootcase pos "$disk" 'OBOOT-D1: SYSCALL-ENTRY .*nr=51 '
log=$vm/boot-pos.log
grep -q '^OBOOT-D1: MAIN entry oboot=mp$' "$log" || fail "positive: no MAIN entry"
grep -q '^OBOOT-D1: HANDOFF mp o_user_bootstrap$' "$log" || fail "positive: no MP handoff"
grep -q '^OBOOT-D1: KERNEL-READY .*slash=nil dot=nil$' "$log" || fail "positive: no KERNEL-READY"
grep -q "^OBOOT-D1: VOLSPEC len=45 PARTUUID=$puuid$" "$log" || fail "positive: wrong volume spec"
grep -q "^OBOOT-D1: ARGV argc=6 <micropython> <-O> <PARTUUID=$puuid> <-S> <init> <-B>$" "$log" ||
	fail "positive: wrong six-argument contract"
grep -q '^OBOOT-D1: OID=0x4f45584543000003$' "$log" || fail "positive: wrong target OID"
grep -q "^OBOOT-D1: OVOLOPEN spec=PARTUUID=$puuid .*ret=1$" "$log" || fail "positive: OVOLOPEN failed"
grep -q '^OBOOT-D1: OSPACEOPEN-HANDLE h=1$' "$log" || fail "positive: no Space handle"
grep -q "^OBOOT-D1: OEXECUTE oid=0x4f45584543000003 len=$mpsize sha256=$mpsha " "$log" ||
	fail "positive: OID bytes do not match the unchanged MicroPython SHA"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=60 .*text=micropython ' "$log" ||
	fail "positive: OEXECUTE did not commit the MicroPython image"
grep -q '^OBOOT-D1: SYSCALL-ENTRY .*nr=54 .*text=micropython ' "$log" ||
	fail "positive: MicroPython did not enter p9_space_o/ovolopen"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=54 .*ret=0x1 .*text=micropython ' "$log" ||
	fail "positive: MicroPython's p9_space_o ovolopen did not succeed"
grep -q '^OBOOT-D1: AFTER-SYSCALLS n=4 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
	fail "positive: counters not zero through the first four syscalls"
grep -q '^OBOOT-D1: SYSCALL-ENTRY .*nr=51 arg0=0x2 text=micropython ' "$log" ||
	fail "positive: no first inherited fd-2 PWRITE observed"
grep -q '^fault: nlocks 1, proc 1 micropython, addr 0x8' "$log" ||
	fail "positive: expected nil-Fgrp fault after fd-2 write not observed"
grep -q '^panic: kernel fault: write addr=0x8$' "$log" ||
	fail "positive: expected first-dependency kernel fault not observed"
grep -q '^OBOOT-A:\|^OBOOT-B:\|^OBOOT-C:' "$log" && fail "positive: foreign boot marker"
grep -q '^init: done$\|^boot: MicroPython' "$log" && fail "positive: falsely claimed a MicroPython boot"

echo "### negative: OID_MP_EXEC absent"
rm -f "$missingo"
NOMPEXEC=1 "$here/mkovol" "$missingo" 192 "$here/odemo.py" > "$vm/mkovol-missing.log" 2>&1 ||
	{ cat "$vm/mkovol-missing.log" >&2; fail "mkovol missing failed"; }
grep -q '^seed: mpexec \|^seed: object mp ' "$vm/mkovol-missing.log" && fail "missing image unexpectedly has OID_MP_EXEC"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$missingo" KERNEL="$kernel" \
	INI='oboot=mp;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$missing" > "$vm/gefsdisk-missing.log" 2>&1 ||
	{ cat "$vm/gefsdisk-missing.log" >&2; fail "gefsdisk missing failed"; }
bootcase missing "$missing" 'OBOOT-D1: SYSCALL-ENTRY .*nr=6 arg0=0xbaf '
mlog=$vm/boot-missing.log
grep -q '^OBOOT-D1: OSPACEOPEN-HANDLE h=1$' "$mlog" || fail "missing: no Space handle"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=60 .*ret=0xffffffffffffffff text=\*ouser\* ' "$mlog" ||
	fail "missing: OEXECUTE did not return an error"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=56 .*ret=0xd1 text=\*ouser\* ' "$mlog" ||
	fail "missing: O handle did not survive the failed load"
grep -q '^OBOOT-D1: SYSCALL-ENTRY .*nr=6 arg0=0xbaf text=\*ouser\* .*user=1$' "$mlog" ||
	fail "missing: no userspace failure marker"
grep -q 'text=micropython' "$mlog" && fail "missing: MicroPython ran without OID_MP_EXEC"
grep -q 'panic\|fault\|suicide' "$mlog" && fail "missing: panic/fault"

[ "$fails" = 0 ] && echo "PASS: D1 EXEC, OID_MP_EXEC image transition and first-dependency diagnosis" || {
	echo "FAIL: $fails"
	exit 1
}
