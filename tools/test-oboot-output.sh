#!/bin/bash
# Plan2001 Boot Experiment D2a: process-local native output stream over the
# existing UART backend, then the next observed legacy dependency.
# Positive: oboot=mp with a fresh O image seeded from the current build's
# MicroPython.  Negative: OID_MP_EXEC absent.
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obootd2avm
oimg=$b/obootd2a-o.img
disk=$b/obootd2a.img
missingo=$b/obootd2a-missing-o.img
missing=$b/obootd2a-missing.img
mp=$b/root/$objtype/bin/micropython
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-oboot-output: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$mp" ] || { echo "test-oboot-output: no $mp (WHAT=all build)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-oboot-output: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$loader" ] || { echo "test-oboot-output: no $b/$loader (tools/build.sh)" >&2; exit 1; }
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
	"$qemu" -name "plan2001-obootd2a-$tag" -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
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

echo "### positive: oboot=mp, native output over UART"
rm -f "$oimg"
MPEXEC="$mp" "$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1 ||
	{ cat "$vm/mkovol.log" >&2; fail "mkovol positive failed"; }
grep -q "^seed: mpexec $mpsize 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "positive: OID_MP_EXEC bytes differ from the current build"
grep -q "^seed: object mp oid=0x4f45584543000003 len=$mpsize$" "$vm/mkovol.log" ||
	fail "positive: OID_MP_EXEC absent from the O seed"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INI='oboot=mp;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$disk" > "$vm/gefsdisk.log" 2>&1 ||
	{ cat "$vm/gefsdisk.log" >&2; fail "gefsdisk positive failed"; }
puuid=$(cat "$disk.partuuid")
grep -q "^obootvol=PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: obootvol not substituted"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^init=' "$disk.ini" && fail "plan9.ini: has init="

bootcase pos "$disk" 'OBOOT-D1: BIND-ENTRY '
log=$vm/boot-pos.log
grep -q "^OBOOT-D1: ARGV argc=6 <micropython> <-O> <PARTUUID=$puuid> <-S> <init> <-B>$" "$log" ||
	fail "positive: wrong six-argument contract"
grep -q '^OBOOT-D1: OID=0x4f45584543000003$' "$log" || fail "positive: wrong OID"
grep -q "^OBOOT-D1: OEXECUTE oid=0x4f45584543000003 len=$mpsize sha256=$mpsha " "$log" ||
	fail "positive: OID bytes do not match the current build"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=60 .*text=micropython ' "$log" ||
	fail "positive: MicroPython image transition not observed"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=54 .*ret=0x1 .*text=micropython ' "$log" ||
	fail "positive: post-MP p9_space_o OVOLOPEN missing"
# The first native-output calls: unbound handle, negative length, oversize.
grep -q '^OBOOT-D1: IOWRITE-ENTRY .* h=99 buf=0x0 n=0 text=\*ouser\*.*$' "$log" &&
	grep -q '^OBOOT-D1: IOWRITE-RETURN .* h=99 buf=0x0 n=0 ret=-1$' "$log" ||
	fail "positive: unbound handle did not return -1"
grep -q '^OBOOT-D1: IOWRITE-ENTRY .* h=1 buf=0x0 n=-1 text=\*ouser\*.*$' "$log" &&
	grep -q '^OBOOT-D1: IOWRITE-RETURN .* h=1 buf=0x0 n=-1 ret=-1$' "$log" ||
	fail "positive: negative length did not return -1"
grep -q '^OBOOT-D1: IOWRITE-ENTRY .* h=2 buf=0x0 n=65537 text=\*ouser\*.*$' "$log" &&
	grep -q '^OBOOT-D1: IOWRITE-RETURN .* h=2 buf=0x0 n=65537 ret=-1$' "$log" ||
	fail "positive: oversize length did not return -1"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=51 .*ret=0xffffffffffffffff text=\*ouser\* ' "$log" ||
	fail "positive: nil-Fgrp legacy PWRITE did not return -1"
# Native probe and the real diagnostic write.
grep -q '^OBOOT-D1: IOWRITE-ENTRY .* h=1 buf=0x0 n=0 text=micropython ' "$log" &&
	grep -q '^OBOOT-D1: IOWRITE-RETURN .* h=1 buf=0x0 n=0 ret=0$' "$log" ||
	fail "positive: zero-length native capability probe missing"
grep -q '^OBOOT-D1: IOWRITE-ENTRY .* h=2 buf=0x[0-9a-f]* n=72 text=micropython ' "$log" &&
	grep -q '^OBOOT-D1: IOWRITE-RETURN .* h=2 buf=0x[0-9a-f]* n=72 ret=72$' "$log" ||
	fail "positive: diagnostic native output syscall missing"
grep -q "^space: O volume selected: PARTUUID=$puuid$" "$log" ||
	fail "positive: native diagnostic text missing from UART"
grep -q '^OBOOT-D2A: OUTPUT h=2 n=72 counters namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
	fail "positive: output checkpoint counters are not zero"
# The diagnostic must not use PWRITE after MicroPython started.
if sed -n '/text=micropython/,$p' "$log" | grep -q '^OBOOT-D1: SYSCALL-ENTRY .*nr=51 '; then
	fail "positive: MicroPython diagnostic still attempted PWRITE"
fi
# Downstream: boot.py reached and tried its first bind; record, do not hide.
grep -q '^OBOOT-D1: BIND-ENTRY .*slash=0x0 counters namec=0 ' "$log" ||
	fail "positive: boot.py bind entry not observed"
grep -q '^OBOOT-D1: NAMEC-ENTER aname=.* counters namec=1 ' "$log" ||
	fail "positive: first namec after output not recorded"
grep -q '^OBOOT-D1: NAMEC-ENTER aname=.* counters namec=2 newchan=2 walk=1 devwalk=1 ' "$log" ||
	fail "positive: second namec after output not recorded"
grep -q '^panic: kernel fault: read addr=0x0$' "$log" ||
	fail "positive: expected downstream BIND note/panic not observed"
grep -q '^OBOOT-A:\|^OBOOT-B:\|^OBOOT-C:' "$log" && fail "positive: foreign boot marker"
grep -q '^boot: MicroPython\|^init: done$' "$log" && fail "positive: falsely claimed a complete MicroPython boot"

echo "### negative: OID_MP_EXEC absent, no native diagnostic text"
rm -f "$missingo"
NOMPEXEC=1 "$here/mkovol" "$missingo" 192 "$here/odemo.py" > "$vm/mkovol-missing.log" 2>&1 ||
	{ cat "$vm/mkovol-missing.log" >&2; fail "mkovol missing failed"; }
grep -q '^seed: mpexec \|^seed: object mp ' "$vm/mkovol-missing.log" && fail "missing image unexpectedly has OID_MP_EXEC"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$missingo" KERNEL="$kernel" \
	INI='oboot=mp;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$missing" > "$vm/gefsdisk-missing.log" 2>&1 ||
	{ cat "$vm/gefsdisk-missing.log" >&2; fail "gefsdisk missing failed"; }
bootcase missing "$missing" 'OBOOT-D1: SYSCALL-ENTRY .*nr=6 arg0=0xbaf '
mlog=$vm/boot-missing.log
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=60 .*ret=0xffffffffffffffff text=\*ouser\* ' "$mlog" ||
	fail "missing: OEXECUTE did not return an error"
grep -q '^OBOOT-D1: SYSCALL-RETURN .*nr=56 .*ret=0xd1 text=\*ouser\* ' "$mlog" ||
	fail "missing: O handle did not survive"
grep -q '^OBOOT-D1: SYSCALL-ENTRY .*nr=6 arg0=0xbaf text=\*ouser\* .*user=1$' "$mlog" ||
	fail "missing: no userspace failure marker"
grep -q 'text=micropython\|space: O volume selected' "$mlog" && fail "missing: MicroPython ran or printed"
grep -q 'panic\|fault\|suicide' "$mlog" && fail "missing: panic/fault"

[ "$fails" = 0 ] && echo "PASS: D2a native output over UART and downstream blocker diagnosis" || {
	echo "FAIL: $fails"
	exit 1
}
