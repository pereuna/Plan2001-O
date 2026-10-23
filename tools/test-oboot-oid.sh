#!/bin/bash
# Plan2001 Boot Experiment C: ring-3 OID executable over the native
# PARTUUID= GE/O path, with no pathname/Chan/console.  Positive,
# wrong-PARTUUID and missing-OID cases on separate disposable boots.
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obootoidvm
oimg=$b/obootoid-o.img
disk=$b/obootoid.img
wrong=$b/obootoid-wrong.img
missingo=$b/obootoid-missing-o.img
missing=$b/obootoid-missing.img
target=$root/build/selfroot/amd64/bin/obootctarget
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-oboot-oid: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$target" ] || { echo "test-oboot-oid: no $target (tools/selfroot after WHAT=all)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-oboot-oid: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$loader" ] || { echo "test-oboot-oid: no $b/$loader (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" 2>/dev/null | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill "$q" 2>/dev/null || true; wait "$q" 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
tsize=$(stat -c %s "$target")
tsum=$(python3 -c 'import sys; print(format(sum(open(sys.argv[1],"rb").read()) & 0xff, "x"))' "$target")

bootcase() {
	local tag=$1 img=$2 ini=$3 waitpat=$4
	: > "$vm/serial.log"
	cp "$fwvars" "$vm/vars.fd"
	"$qemu" -name "plan2001-obootoid-$tag" -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars.fd" \
		-drive file="$img",format=raw,if=none,id=d0 \
		-device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu-$tag.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-60}))
	until clean | grep -q "$waitpat" || [ $SECONDS -ge $end ] || ! kill -0 "$q" 2>/dev/null; do
		sleep 1
	done
	sleep 1
	stop
	clean > "$vm/boot-$tag.log"
}

echo "### positive: native O volume with raw Experiment C target"
rm -f "$oimg"
RAWEXEC="$target" NOMPEXEC=1 "$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1 ||
	{ cat "$vm/mkovol.log" >&2; fail "mkovol positive failed"; }
grep -q "^seed: rawexec $tsize 4f45584543000004 .* unchanged$" "$vm/mkovol.log" ||
	fail "positive image did not preserve the raw target bytes"
grep -q '^seed: object rawexec oid=0x4f45584543000004 ' "$vm/mkovol.log" ||
	fail "positive image did not seed the raw target OID"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INI='oboot=oid;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$disk" > "$vm/gefsdisk.log" 2>&1 ||
	{ cat "$vm/gefsdisk.log" >&2; fail "gefsdisk positive failed"; }
puuid=$(cat "$disk.partuuid")
grep -q "^obootvol=PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: obootvol was not substituted"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^init=' "$disk.ini" && fail "plan9.ini: has init="

bootcase pos "$disk" x 'OBOOT-C: SYSCALL-ENTRY .*nr=17 arg0=0x5678 text=obootctarget'
log=$vm/boot-pos.log
grep -q '^OBOOT-C: MAIN entry oboot=oid$' "$log" || fail "positive: no MAIN entry"
grep -q '^OBOOT-C: KERNEL-READY .*slash=nil dot=nil$' "$log" || fail "positive: no KERNEL-READY"
grep -q "^OBOOT-C: VOLSPEC len=45 PARTUUID=$puuid$" "$log" || fail "positive: wrong handed volume spec"
grep -q "^OBOOT-C: OVOLOPEN spec=PARTUUID=$puuid .*ret=1$" "$log" || fail "positive: OVOLOPEN did not succeed"
grep -q '^OBOOT-C: OSPACEOPEN-HANDLE h=1$' "$log" || fail "positive: no positive Space handle"
grep -q "^OBOOT-C: OEXECUTE oid=0x4f45584543000004 len=$tsize sum=$tsum " "$log" ||
	fail "positive: OEXECUTE bytes do not match the target length/checksum"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=60 .*text=\*ouser\* ' "$log" || fail "positive: no OEXECUTE entry"
grep -q '^OBOOT-C: SYSCALL-RETURN .*nr=60 .*text=obootctarget ' "$log" ||
	fail "positive: no post-exec register transition to the target"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=56 .*text=obootctarget ' "$log" ||
	fail "positive: target did not check the released O handle"
grep -q '^OBOOT-C: SYSCALL-RETURN .*nr=56 .*ret=0xffffffffffffffff text=obootctarget ' "$log" ||
	fail "positive: pre-exec O handle survived the image replacement"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=6 arg0=0x42 text=obootctarget .*cs=0x2b ss=0x23 user=1$' "$log" ||
	fail "positive: target alarm(0x42) not seen in ring 3"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=17 arg0=0x1234 text=obootctarget .*user=1$' "$log" ||
	fail "positive: target sleep(0x1234) not seen"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=17 arg0=0x5678 text=obootctarget .*user=1$' "$log" ||
	fail "positive: target sleep(0x5678) not seen"
grep -q '^OBOOT-C: AFTER-SYSCALLS legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
	fail "positive: counters not zero after the exec transition"
grep -q 'panic\|fault\|suicide\|^OBOOT-A:\|^OBOOT-B:' "$log" && fail "positive: panic/fault/foreign marker"

echo "### negative: wrong PARTUUID"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INI='oboot=oid;obootvol=PARTUUID=00000000-0000-0000-0000-000000000000' \
	"$here/gefsdisk" "$wrong" > "$vm/gefsdisk-wrong.log" 2>&1 ||
	{ cat "$vm/gefsdisk-wrong.log" >&2; fail "gefsdisk wrong failed"; }
bootcase wrong "$wrong" x 'OBOOT-C: AFTER-SYSCALLS '
wlog=$vm/boot-wrong.log
grep -q '^OBOOT-C: OVOLOPEN-ERROR spec=PARTUUID=00000000-0000-0000-0000-000000000000 err=no disk has that partition$' "$wlog" ||
	fail "wrong: OVOLOPEN did not fail clearly"
grep -q '^OBOOT-C: SYSCALL-RETURN .*nr=54 .*ret=0xffffffffffffffff ' "$wlog" ||
	fail "wrong: OVOLOPEN did not return -1"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=6 arg0=0xbad .*user=1$' "$wlog" ||
	fail "wrong: no userspace failure marker"
grep -q 'OBOOT-C: OSPACEOPEN\|OBOOT-C: OEXECUTE' "$wlog" && fail "wrong: continued after failed volume open"
grep -q 'panic\|fault\|suicide' "$wlog" && fail "wrong: panic/fault"
grep -q '^OBOOT-C: AFTER-SYSCALLS .*path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$wlog" ||
	fail "wrong: path counters not zero"

echo "### negative: missing target OID, handle survives"
rm -f "$missingo"
NOMPEXEC=1 "$here/mkovol" "$missingo" 192 "$here/odemo.py" > "$vm/mkovol-missing.log" 2>&1 ||
	{ cat "$vm/mkovol-missing.log" >&2; fail "mkovol missing failed"; }
grep -q '^seed: object rawexec ' "$vm/mkovol-missing.log" && fail "missing image unexpectedly has a raw target"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$missingo" KERNEL="$kernel" \
	INI='oboot=oid;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$missing" > "$vm/gefsdisk-missing.log" 2>&1 ||
	{ cat "$vm/gefsdisk-missing.log" >&2; fail "gefsdisk missing failed"; }
bootcase missing "$missing" x 'OBOOT-C: SYSCALL-ENTRY .*nr=6 arg0=0xbaf '
mlog=$vm/boot-missing.log
grep -q '^OBOOT-C: OSPACEOPEN-HANDLE h=1$' "$mlog" || fail "missing: no Space handle"
grep -q '^OBOOT-C: SYSCALL-RETURN .*nr=60 .*ret=0xffffffffffffffff text=\*ouser\* ' "$mlog" ||
	fail "missing: OEXECUTE did not return an error"
grep -q '^OBOOT-C: SYSCALL-RETURN .*nr=56 .*ret=0xd1 text=\*ouser\* ' "$mlog" ||
	fail "missing: O handle did not survive the failed load"
grep -q '^OBOOT-C: SYSCALL-ENTRY .*nr=6 arg0=0xbaf text=\*ouser\* .*user=1$' "$mlog" ||
	fail "missing: no userspace failure marker"
grep -q 'text=obootctarget' "$mlog" && fail "missing: target ran without an object"
grep -q 'panic\|fault\|suicide' "$mlog" && fail "missing: panic/fault"

[ "$fails" = 0 ] && echo "PASS: Boot Experiment C OID executable over native O, post-exec syscalls and negatives" || {
	echo "FAIL: $fails"
	exit 1
}
