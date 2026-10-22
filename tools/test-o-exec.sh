#!/bin/bash
# Plan2001: native executable object loading.  One disposable ESP + O
# disk, no root filesystem.  /boot/oexec is the embedded test harness;
# the target program exists only as an O object seeded by tools/mkovol
# (NATIVEEXEC).  A child loads it with the native O syscall, executes,
# prints its marker and exits.  Failed loads must leave the caller and
# its process-local O handle intact.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/oexecvm
disk=$b/oexec.img
oimg=$b/oexec-o.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-exec: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/ohello" ] || { echo "test-o-exec: no build/selfroot ohello (tools/selfroot)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

echo "### native O volume with executable object"
NATIVEEXEC="$root/build/selfroot/amd64/bin/ohello" \
	"$here/mkovol" "$oimg" 192 "$here/odemo.py"
echo "### ESP + O, no FS root"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" \
	INIT='/boot/oexec -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"

stop
: > "$vm/serial.log"
cp "$fwvars" "$vm/vars.fd"
"$qemu" -name plan2001-oexec -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$disk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
q=$!
end=$((SECONDS + ${SECONDS_TO_RUN:-240}))
until clean | grep -q '^PASS: native O executable loading\|^FAIL: native O executable loading\|^panic' ||
      [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
	sleep 1
done
sleep 1
clean > "$vm/serial.clean.log"
clean | grep -a '^oexec:\|^ohello:\|^PASS:\|^FAIL:\|^panic' || true

for m in \
	'ohello: native executable from O marker' \
	'ohello: argv, Tos and BSS boundary PASS' \
	'oexec: parent observed native child completion PASS' \
	'missing OID returned an error and preserved the handle PASS' \
	'malformed executable returned an error and preserved the handle PASS' \
	'PASS: native O executable loading'
do
	clean | grep -q "$m" || fail "missing: $m"
done
[ "$(clean | grep -c 'ohello: native executable from O marker')" = 1 ] ||
	fail "target marker count is not one"
[ "$(clean | grep -c 'ohello: argv, Tos and BSS boundary PASS')" = 1 ] ||
	fail "argv/Tos/BSS marker count is not one"
if clean | grep -q '^FAIL:'; then fail "program reported FAIL"; fi
if clean | grep -q '^panic'; then fail "kernel panic"; fi
stop

[ "$fails" = 0 ] && echo "PASS: native executable object from O, exec and rollback" || { echo "FAIL: $fails"; exit 1; }
