#!/bin/bash
# E2 opt-in native read probe: boot the pc64native kernel in disposable QEMU
# and verify the generated RTC Qrtc and console Qpid/Qppid entries are linked and
# executed in a real kernel process.  No O disk, user namespace or Chan is
# involved in the measured window.
#   SECONDS_TO_RUN  hard timeout, default 120
#   MEM             guest RAM in MiB, default 2048
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
nkernel=9pc64native
verification=$root/build/verification
serial=$verification/o-native-generator-serial.log
vm=$root/build/nativeprobe-vm
[ -s "$b/$nkernel" ] || {
	echo "test-o-native-generator: no $b/$nkernel; run NATIVE_PROBE=1 WHAT=kernel tools/build.sh" >&2
	exit 1
}
[ -s "$b/$loader" ] || {
	echo "test-o-native-generator: no $b/$loader; run NATIVE_PROBE=1 WHAT=kernel tools/build.sh" >&2
	exit 1
}
[ -s "$root/build/generated/kernel-native/kernel_native.c" ] || {
	echo "test-o-native-generator: no generated kernel_native.c" >&2
	exit 1
}
mkdir -p "$verification" "$vm"
rm -rf "$vm"
mkdir -p "$vm"
esp=$vm/esp.img
mformat -C -i "$esp" -T 65536 -h 64 -s 32 ::
mmd -i "$esp" ::/EFI ::/EFI/BOOT
mcopy -i "$esp" "$b/$loader" "::/EFI/BOOT/$espname"
mcopy -i "$esp" "$b/$nkernel" ::/
printf 'bootfile=/%s\nconsole=0\nonativeprobe=1\n' "$nkernel" > "$vm/plan9.ini"
mcopy -i "$esp" "$vm/plan9.ini" ::/
cp "$fwvars" "$vm/vars.fd"
: > "$serial"

q=
clean() { tr -d '\r' < "$serial" 2>/dev/null | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill "$q" 2>/dev/null || true; wait "$q" 2>/dev/null || true; }; q=; }
trap stop EXIT

"$qemu" -name plan2001-nativeprobe -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$esp",format=raw,if=none,id=esp "${espdev[@]}" \
	-nic none -display none -serial file:"$serial" 2>"$vm/qemu.log" &
q=$!
end=$((SECONDS + ${SECONDS_TO_RUN:-120}))
until clean | grep -q '^ONATIVEPROBE: DONE$' || [ $SECONDS -ge $end ] || ! kill -0 "$q" 2>/dev/null; do
	sleep 1
done
sleep 1
stop
clean > "$verification/o-native-generator-boot.log"
log=$verification/o-native-generator-boot.log

fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

grep -q '^ONATIVEPROBE: INIT rtcinit=done chandevinit=not-run$' "$log" ||
	fail "RTC init marker missing"
grep -q '^ONATIVEPROBE: BEGIN pid=[0-9][0-9]* namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
	fail "probe BEGIN counters are not zero"
grep -q '^ONATIVEPROBE: END pid=[0-9][0-9]* namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
	fail "probe END counters are not zero"

grep -q '^ONATIVEPROBE: RTC symbol=native_rtc_qrtc_read source=rtcqread selector=1 n=32 off=0 ret=12 value=[0-9][0-9]*$' "$log" ||
	fail "RTC native read marker missing or wrong"
grep -q '^ONATIVEPROBE: RTC text=\[[ 0-9]*\] plausible=1$' "$log" ||
	fail "RTC value not plausible/formatted"
grep -q '^ONATIVEPROBE: RTC OFFSET fullret=12 partret=4 match=1$' "$log" ||
	fail "RTC offset read mismatch"
grep -q '^ONATIVEPROBE: rtc selector=1 n=64 off=0 ret=12 want=12 match=1$' "$log" ||
	fail "RTC size clamp mismatch"
grep -q '^ONATIVEPROBE: rtc selector=1 n=0 off=0 ret=0 want=0 match=1$' "$log" ||
	fail "RTC zero-length read mismatch"
grep -q '^ONATIVEPROBE: rtc selector=1 n=8 off=4096 ret=0 want=0 match=1$' "$log" ||
	fail "RTC bounds read mismatch"

grep -q '^ONATIVEPROBE: PID symbol=native_cons_qpid_read source=consqpidread selector=12 n=32 off=0 ret=12 value=[0-9][0-9]* pid=[0-9][0-9]* match=1$' "$log" ||
	fail "Qpid native read marker missing or PID mismatch"
grep -q '^ONATIVEPROBE: PID text=\[[ 0-9]*\] pid_match=1$' "$log" ||
	fail "Qpid formatting/PID text mismatch"
grep -q '^ONATIVEPROBE: PID OFFSET fullret=12 partret=4 match=1$' "$log" ||
	fail "Qpid offset read mismatch"
grep -q '^ONATIVEPROBE: cons selector=12 n=64 off=0 ret=12 want=12 match=1$' "$log" ||
	fail "Qpid size clamp mismatch"
grep -q '^ONATIVEPROBE: cons selector=12 n=0 off=0 ret=0 want=0 match=1$' "$log" ||
	fail "Qpid zero-length read mismatch"
grep -q '^ONATIVEPROBE: cons selector=12 n=-5 off=0 ret=-5 want=-5 match=1$' "$log" ||
	fail "Qpid negative-length read mismatch"
grep -q '^ONATIVEPROBE: cons selector=12 n=8 off=4096 ret=0 want=0 match=1$' "$log" ||
	fail "Qpid bounds read mismatch"

grep -q '^ONATIVEPROBE: PPID symbol=native_cons_qppid_read source=consread_qppid_read selector=13 n=32 off=0 ret=12 value=[0-9][0-9]* ppid=[0-9][0-9]* match=1$' "$log" ||
	fail "Qppid native read marker missing or parent PID mismatch"
grep -q '^ONATIVEPROBE: PPID text=\[[ 0-9]*\] format_match=1$' "$log" ||
	fail "Qppid exact formatting mismatch"
grep -q '^ONATIVEPROBE: PPID OFFSET fullret=12 partret=4 match=1$' "$log" ||
	fail "Qppid offset read mismatch"
for expected in \
	'n=64 off=0 ret=12 want=12' \
	'n=0 off=0 ret=0 want=0' \
	'n=-5 off=0 ret=-5 want=-5' \
	'n=8 off=4096 ret=0 want=0' \
	'n=8 off=-1 ret=0 want=0' \
	'n=8 off=4294967296 ret=8 want=8'; do
	grep -q "^ONATIVEPROBE: cons selector=13 $expected match=1$" "$log" ||
		fail "Qppid boundary mismatch: $expected"
done

grep -q '^ONATIVEPROBE: AUTH rtc=kernel-internal-only cons=kernel-internal-only up=set$' "$log" ||
	fail "authorization/context marker missing"
grep -q '^ONATIVEPROBE: rtc selector=101 caught=1 err=native rtc: unsupported selector$' "$log" ||
	fail "RTC unsupported-selector refusal missing"
grep -q '^ONATIVEPROBE: cons selector=112 caught=1 err=native cons: unsupported selector$' "$log" ||
	fail "console unsupported-selector refusal missing"

grep -q '^ONATIVEPROBE: DONE$' "$log" || fail "probe DONE marker missing"
grep -q 'panic\|fault\|suicide' "$log" && fail "panic/fault observed"
grep -q '^OBOOT-' "$log" && fail "foreign legacy boot marker observed"
grep -q '^ONATIVEPROBE: HANDOFF opt-in native read probe$' "$log" ||
	fail "native probe handoff marker missing"

# Link evidence: the generated symbols and shared helpers are in the kernel.
for sym in native_rtc_qrtc_read native_cons_qpid_read native_cons_qppid_read rtcqread consqpidread consread_qppid_read; do
	grep -a -q "$sym" "$b/$nkernel" || fail "kernel lacks linked symbol $sym"
done

if [ "$fails" = 0 ]; then
	echo "PASS: E4 native RTC Qrtc and console Qpid/Qppid probe (linked and executed)"
	echo "serial: $serial"
else
	echo "FAIL: $fails"
	echo "serial: $serial"
	exit 1
fi
