#!/bin/bash
# E7.1: boot the opt-in 9pc64e71 kernel with a real VirtIO Ethernet device
# in disposable QEMU.  Build it first:
#   ETHER_PROBE=1 WHAT=kernel tools/build.sh
#
# The host/dgram fixture is tools/test_e71_ether.py; logs go to
# build/verification/e71/ (ignored by Git).  This needs mtools and KVM.
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
kernel=$b/9pc64e71
loader=$b/$loader
[ -s "$kernel" ] || { echo "test-e71-ether: no $kernel (ETHER_PROBE=1 WHAT=kernel tools/build.sh)" >&2; exit 1; }
[ -s "$loader" ] || { echo "test-e71-ether: no $loader (tools/build.sh)" >&2; exit 1; }
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "test-e71-ether: no /dev/kvm" >&2; exit 1; }
out=$root/build/verification/e71
mkdir -p "$out"
python3 "$here/test_e71_ether.py" \
	--qemu "$qemu" --fwcode "$fwcode" --fwvars "$fwvars" \
	--loader "$loader" --kernel "$kernel" --espname "$espname" \
	--workdir "$out"
