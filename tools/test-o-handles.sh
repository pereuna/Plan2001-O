#!/bin/bash
# Plan2001: process-local native O Space handles.  Boots one disposable
# ESP + native O disk with no filesystem root and runs the embedded
# /boot/ohandle bootstrap program as init.  The program uses the native
# O syscalls from real processes: RFMEM and ordinary children, wait,
# successful and failed exec, explicit close, process exit and an
# unfinished transaction.  /boot/ohandle is test bootstrap, not a
# native executable-object loader.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/ohandvm
disk=$b/ohand.img
oimg=$b/ohand-o.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-handles: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/ohandle" ] || { echo "test-o-handles: no build/selfroot ohandle (tools/selfroot)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

echo "### native O volume"
"$here/mkovol" "$oimg" 192
echo "### ESP + O, no FS root"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" \
	INIT='/boot/ohandle -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"

stop
: > "$vm/serial.log"
cp "$fwvars" "$vm/vars.fd"
"$qemu" -name plan2001-ohand -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$disk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
q=$!
end=$((SECONDS + ${SECONDS_TO_RUN:-240}))
until clean | grep -q '^PASS: process-local O handles\|^FAIL: process-local O handles\|^panic' ||
      [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
	sleep 1
done
sleep 1
clean > "$vm/serial.clean.log"
clean | grep -a '^ohandle:\|^PASS:\|^FAIL:\|^panic' || true

for m in \
	'isolation and separate sessions PASS' \
	'explicit close capacity PASS' \
	'process exit capacity PASS' \
	'invalid and double close PASS' \
	'explicit close aborts unfinished transaction PASS' \
	'exit aborts unfinished transaction PASS' \
	'failed exec preserves handles PASS' \
	'successful exec released handles PASS' \
	'PASS: process-local O handles'
do
	clean | grep -q "ohandle: $m\|^$m" || fail "missing: $m"
done
if clean | grep -q '^FAIL:'; then fail "program reported FAIL"; fi
if clean | grep -q '^panic'; then fail "kernel panic"; fi
stop

[ "$fails" = 0 ] && echo "PASS: process-local O handles, isolation/lifetime/cleanup" || { echo "FAIL: $fails"; exit 1; }
