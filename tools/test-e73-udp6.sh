#!/bin/bash
# E7.3: real VirtIO native UDP6 datagram fixture.
# Build first: UDP6_PROBE=1 WHAT=kernel tools/build.sh
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e73
loader=$b/$loader
[ -s "$kernel" ] || { echo "test-e73-udp6: no $kernel (UDP6_PROBE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e73-udp6: no $loader (tools/build.sh)" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e73-udp6: no /dev/kvm" >&2; exit 1; }
out=$root/build/verification/e73
mkdir -p "$out"
python3 "$here/test_e73_udp6.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out"
