#!/bin/bash
# E7.7: verify the native-only kernel has no executable IPv4/ARP path.
# Build first: E77_NATIVE=1 WHAT=kernel tools/build.sh
set -e
set -o pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e7v6only
loader=$b/$loader
devc=$b/pc64e7v6only.devc.c
out=$root/build/verification/e77

[ -s "$kernel" ] || { echo "test-e77-ipv6-only: no $kernel (E77_NATIVE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e77-ipv6-only: no $loader (tools/build.sh)" >&2; exit 1; }
[ -s "$devc" ] || { echo "test-e77-ipv6-only: no $devc" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e77-ipv6-only: no /dev/kvm" >&2; exit 1; }
mkdir -p "$out"

fail=0
note() { echo "$*" | tee -a "$out/static.log"; }
strings "$kernel" > "$out/strings.txt"
check_absent() {
	if grep -qx "$1" "$out/strings.txt"; then
		note "FAIL present IPv4/legacy symbol: $1"; fail=1
	else
		note "absent IPv4/legacy symbol: $1"
	fi
}
check_present() {
	if grep -qx "$1" "$out/strings.txt"; then
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

for s in ipoput4 ipiput4 ipfraginit ipfragreass ipfragtag ipfragfree \
         ipfraglookup tcpinit tcpiput tcpconnect tcpclose icmpinit \
         icmpiput icmpnohost v4lookup v4source v4lookupskip arpwrite \
         arpread convmac readipifc ipselftabread \
         etherdevtab ipdevtab wgdevtab etherattach ipattach wglisten \
         chandial netifinit etherlegacyrx ethermux etheroq; do
	check_absent "$s"
done
for s in ipoput6 ipiput6 v6lookup v6source icmp6init icmpiput6 \
         udp6_open ndpsendsol ethermediumframe6 tcpmssclamp arpenter \
         nativeip6_register ipv6native_start ipfsinit Fsproto Fsprotoclone \
         ethercore_rxregister ipfmtinstall; do
	check_present "$s"
done
[ "$fail" = 0 ] || { echo "FAIL: E7.7 static checks" >&2; exit 1; }

python3 "$here/test_e74_ipproto.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out" --profile e77 2>&1 | tee "$out/fixture.log"

echo "PASS: E7.7 native-only kernel has no executable IPv4/ARP and keeps IPv6/NDP/UDP6/253"
