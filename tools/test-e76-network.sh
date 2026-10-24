#!/bin/bash
# E7.6: verify the isolated E7-native kernel has no #l/#I/#W adapter and
# still carries the real NORMAL IPv6/NDP/UDP6/Next-Header-253 path.
# Build first: E76_NATIVE=1 WHAT=kernel tools/build.sh
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e7native
loader=$b/$loader
devc=$b/pc64e7native.devc.c
out=$root/build/verification/e76

[ -s "$kernel" ] || { echo "test-e76-network: no $kernel (E76_NATIVE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e76-network: no $loader (tools/build.sh)" >&2; exit 1; }
[ -s "$devc" ] || { echo "test-e76-network: no $devc" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e76-network: no /dev/kvm" >&2; exit 1; }
mkdir -p "$out"

fail=0
note() { echo "$*" | tee -a "$out/static.log"; }
check_absent() {
	if strings "$kernel" | grep -qx "$1"; then
		note "FAIL present legacy symbol: $1"; fail=1
	else
		note "absent legacy symbol: $1"
	fi
}
check_present() {
	if strings "$kernel" | grep -qx "$1"; then
		note "present native symbol: $1"
	else
		note "FAIL missing native symbol: $1"; fail=1
	fi
}

: > "$out/static.log"
note "kernel: $kernel"
note "md5: $(md5sum "$kernel" | awk '{print $1}')"
note "size: $(stat -c %s "$kernel")"
if grep -qE '&(etherdevtab|ipdevtab|wgdevtab)' "$devc"; then
	note "FAIL generated devtab still registers a legacy network Dev"
	fail=1
else
	note "generated devtab: no etherdevtab/ipdevtab/wgdevtab"
fi
sed -n '/Dev\* devtab\[\]/,/};/p' "$devc" >> "$out/static.log"

for s in etherdevtab ipdevtab wgdevtab etherattach ipattach wglisten \
         chandial netifinit etherlegacyrx ethermux etheroq; do
	check_absent "$s"
done
for s in ethermediumframe6 ipfsinit Fsproto Fsprotoclone ethercore_rxregister \
         ipv6native_start nativeip6_register udp6_open; do
	check_present "$s"
done
[ "$fail" = 0 ] || { echo "FAIL: E7.6 static checks" >&2; exit 1; }

python3 "$here/test_e74_ipproto.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out" 2>&1 | tee "$out/fixture.log"

echo "PASS: E7.6 native profile has no legacy #l/#I/#W adapter and keeps NORMAL IPv6"
