#!/bin/bash
# Plan2001 Boot Experiment B: opt-in oboot=user boots a flat, build-time
# embedded userspace image, enters amd64 ring 3 without the legacy
# userinit/proc0/init0/startboot chain, and requires real user-originated
# syscalls.  Uses a disposable ESP and an empty data partition: no root,
# no init=, no filesystem lookup and no path exec.
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obootuservm
disk=$b/obootuser.img
data=$b/obootuser-data.img
[ -s "$b/$kernel" ] || { echo "test-oboot-user: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$loader" ] || { echo "test-oboot-user: no $b/$loader (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" 2>/dev/null | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill "$q" 2>/dev/null || true; wait "$q" 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

truncate -s 16M "$data"
rm -f "$disk" "$disk.ini" "$disk.partuuid"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$data" KERNEL="$kernel" INI='oboot=user' \
	"$here/gefsdisk" "$disk" > "$vm/gefsdisk.log" 2>&1 || {
		cat "$vm/gefsdisk.log" >&2
		echo "test-oboot-user: gefsdisk failed" >&2
		exit 1
	}
grep -q '^oboot=user$' "$disk.ini" || fail "plan9.ini: missing oboot=user"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^init=' "$disk.ini" && fail "plan9.ini: has init="

cp "$fwvars" "$vm/vars.fd"
: > "$vm/serial.log"
"$qemu" -name plan2001-obootuser -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$disk",format=raw,if=none,id=d0 \
	-device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
q=$!
end=$((SECONDS + ${SECONDS_TO_RUN:-60}))
until clean | grep -q '^OBOOT-B: AFTER-SYSCALLS' || [ $SECONDS -ge $end ] || ! kill -0 "$q" 2>/dev/null; do
	sleep 1
done
sleep 1
stop
clean > "$vm/boot.log"

grep -q '^OBOOT-B: MAIN entry oboot=user$' "$vm/boot.log" || fail "no MAIN entry marker"
grep -q '^OBOOT-B: HANDOFF user o_user_bootstrap$' "$vm/boot.log" || fail "no user handoff marker"
grep -q '^OBOOT-B: KERNEL-READY pid=[0-9][0-9]* entry=0x200028 .* slash=nil dot=nil$' "$vm/boot.log" ||
	fail "no KERNEL-READY marker with valid entry and nil slash/dot"
grep -q '^OBOOT-B: KERNEL-TO-USER pid=[0-9][0-9]* pc=0x200028 ' "$vm/boot.log" ||
	fail "no kernel-to-user marker"
grep -q '^OBOOT-B: legacy-calls userinit=0 proc0=0 init0=0$' "$vm/boot.log" ||
	fail "legacy entry counters are not zero"
grep -q '^OBOOT-B: path-calls namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$vm/boot.log" ||
	fail "path counters are not zero before user entry"
grep -q '^OBOOT-B: AFTER-SYSCALLS legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$vm/boot.log" ||
	fail "counters not zero after user syscalls"

grep -q '^OBOOT-B: SYSCALL-ENTRY pid=[0-9][0-9]* nr=6 .* cs=0x2b ss=0x23 user=1$' "$vm/boot.log" ||
	fail "no user alarm syscall (nr=6)"
grep -q '^OBOOT-B: SYSCALL-ENTRY pid=[0-9][0-9]* nr=17 .* cs=0x2b ss=0x23 user=1$' "$vm/boot.log" ||
	fail "no user sleep syscall (nr=17)"
grep -q '^OBOOT-B: SYSCALL-RETURN pid=[0-9][0-9]* nr=6 ret=0x0 .* cs=0x2b ss=0x23 user=1$' "$vm/boot.log" ||
	fail "no alarm syscall return"
grep -q '^OBOOT-B: SYSCALL-RETURN pid=[0-9][0-9]* nr=17 ret=0x0 .* cs=0x2b ss=0x23 user=1$' "$vm/boot.log" ||
	fail "no sleep syscall return"

awk '
/^OBOOT-B: SYSCALL-ENTRY/ { if(insys) bad=1; insys=1; e++ }
/^OBOOT-B: SYSCALL-RETURN/ { if(!insys) bad=1; insys=0; r++ }
END { exit !(bad==0 && e>=2 && r>=2) }
' "$vm/boot.log" || fail "user syscall entry/return sequence is inconsistent"

npc=$(sed -n 's/^OBOOT-B: SYSCALL-ENTRY .* pc=\(0x[0-9a-f]*\).*/\1/p' "$vm/boot.log" | sort -u | wc -l)
[ "$npc" -ge 2 ] || fail "user syscalls did not continue at distinct user PCs"

grep -q '^OBOOT-A:' "$vm/boot.log" && fail "Boot A marker appeared in the user boot"
grep -q 'panic\|suicide\|kernel fault\|user fault\|SYSCALL-ENTRY.*user=0' "$vm/boot.log" &&
	fail "panic, fault or non-user syscall observed"

[ "$fails" = 0 ] && echo "PASS: Boot Experiment B ring-3 user probe, two syscall round trips" || {
	echo "FAIL: $fails"
	echo "serial log: $vm/boot.log"
	exit 1
}
