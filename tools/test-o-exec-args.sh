#!/bin/bash
# Plan2001: bounded native-exec argv copying and rollback.  One disposable
# ESP + O disk, no root filesystem.  /boot/oexec -args is the embedded
# harness; the target is the same O-resident ohello used by test-o-exec.
# The gate covers valid/empty/maximum argv, the aggregate byte boundary,
# invalid user pointers and counts, a cross-page string, repeated rollback
# and a shared-memory peer changing pointers and terminators during exec.
#   TARGET          amd64 (default); see tools/targets
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/oexecargsvm
disk=$b/oexecargs.img
oimg=$b/oexecargs-o.img
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-o-exec-args: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$root/build/selfroot/amd64/bin/ohello" ] || { echo "test-o-exec-args: no build/selfroot ohello (tools/selfroot)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-o-exec-args: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial.log" | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill $q 2>/dev/null || true; wait $q 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }

echo "### native O volume with executable and malformed object"
NATIVEEXEC="$root/build/selfroot/amd64/bin/ohello" \
	"$here/mkovol" "$oimg" 192 "$here/odemo.py"
echo "### ESP + O, no FS root, argv harness"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" \
	INIT='/boot/oexec -args -vol PARTUUID=@PARTUUID@' \
	"$here/gefsdisk" "$disk"

stop
: > "$vm/serial.log"
cp "$fwvars" "$vm/vars.fd"
"$qemu" -name plan2001-oexecargs -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
	-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
	-drive if=pflash,format=raw,file="$vm/vars.fd" \
	-drive file="$disk",format=raw,if=none,id=d0 -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
	-nic none -display none -serial file:"$vm/serial.log" 2>"$vm/qemu.log" &
q=$!
end=$((SECONDS + ${SECONDS_TO_RUN:-300}))
until clean | grep -q '^PASS: native O argv bounds\|^FAIL: native O argv tests\|^panic' ||
      [ $SECONDS -ge $end ] || ! kill -0 $q 2>/dev/null; do
	sleep 1
done
sleep 1
clean > "$vm/serial.clean.log"
clean | grep -a '^oexec:\|^ohello:\|^PASS:\|^FAIL:\|^panic' || true

for m in \
	'oexec: synthetic argc 0 child PASS' \
	'ohello: native executable from O marker' \
	'ohello: argv, Tos and BSS boundary PASS' \
	'oexec: valid argv child PASS' \
	'ohello: argc 5' \
	'ohello: arg\[1\]=<alpha>' \
	'ohello: arg\[2\]=<>' \
	'ohello: arg\[3\]=<gamma>' \
	'ohello: arg\[4\]=<delta>' \
	'oexec: maximum argv child PASS' \
	'ohello: argc 32' \
	'ohello: arg\[31\]=<m31>' \
	'oexec: bulk boundary accepted child PASS' \
	'ohello: bulk len 16376' \
	'aggregate over limit returned an error and preserved the handle PASS' \
	'missing NUL returned an error and preserved the handle PASS' \
	'negative argc returned an error and preserved the handle PASS' \
	'excessive argc returned an error and preserved the handle PASS' \
	'nil argv returned an error and preserved the handle PASS' \
	'misaligned argv returned an error and preserved the handle PASS' \
	'invalid string pointer returned an error and preserved the handle PASS' \
	'cross-page string returned an error and preserved the handle PASS' \
	'oexec: RFMEM argument mutation bounded PASS' \
	'PASS: native O argv bounds, rollback and race'
do
	clean | grep -q "$m" || fail "missing: $m"
done
[ "$(clean | grep -c 'ohello: native executable from O marker')" = 1 ] ||
	fail "synthetic target marker count is not one"
[ "$(clean | grep -c 'ohello: argv, Tos and BSS boundary PASS')" = 1 ] ||
	fail "synthetic argv/Tos/BSS marker count is not one"
if clean | grep -q '^FAIL:'; then fail "program reported FAIL"; fi
if clean | grep -q '^panic'; then fail "kernel panic"; fi
stop

[ "$fails" = 0 ] && echo "PASS: native O argv bounds, rollback and race" || { echo "FAIL: $fails"; exit 1; }
