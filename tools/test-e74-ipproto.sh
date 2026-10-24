#!/bin/bash
# E7.4: real VirtIO experimental IPv6 Next Header 253 fixture.
# Build first: E74_PROBE=1 WHAT=kernel tools/build.sh
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e74
loader=$b/$loader
[ -s "$kernel" ] || { echo "test-e74-ipproto: no $kernel (E74_PROBE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e74-ipproto: no $loader (tools/build.sh)" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e74-ipproto: no /dev/kvm" >&2; exit 1; }
out=$root/build/verification/e74
mkdir -p "$out"
python3 "$here/test_e74_ipproto.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out"
