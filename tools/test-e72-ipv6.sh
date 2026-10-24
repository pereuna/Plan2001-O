#!/bin/bash
# E7.2: real VirtIO native IPv6/NDP/ICMPv6 fixture.
# Build first: IPV6_PROBE=1 WHAT=kernel tools/build.sh
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e72
loader=$b/$loader
[ -s "$kernel" ] || { echo "test-e72-ipv6: no $kernel (IPV6_PROBE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e72-ipv6: no $loader (tools/build.sh)" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e72-ipv6: no /dev/kvm" >&2; exit 1; }
out=$root/build/verification/e72
mkdir -p "$out"
python3 "$here/test_e72_ipv6.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out"
