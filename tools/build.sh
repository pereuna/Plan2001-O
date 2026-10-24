#!/bin/bash
# Build the repo's tree, kernel and UEFI loader in the 9front VM, its
# compilers only the bootstrap: the repo's sources, headers and mk
# definitions replace the VM's (tools/build.rc).
#   TARGET  amd64 (default); see tools/targets
#   WHAT    all (default): the tree, the kernel and the loader
#           kernel: the kernel, loader, kbdfs and ktest only (quick)
#           loader: the UEFI loader alone
#   PASSES  2: the tree a second time with its own tools (WHAT=all)
# Results: build/$TARGET/<kernel>, <loader>, kbdfs, ktest, hjfs, *.log
# (amd64: normal 9pc64, test-only 9pc64mp, bootx64.efi) and, WHAT=all,
# root/$objtype/{bin,lib}: the binaries of a root (tools/selfroot).
#
# Boots a throwaway overlay of the base VM (tools/vm, set up once by
# tools/vm-setup), hands it the repo's tree (tools/overlay) and build.rc as a tar on a raw disk image,
# runs build.rc over the serial console (tools/9run) and unpacks the tar the
# VM wrote onto the output disk.  (Raw tar, not FAT: FAT cannot hold a
# directory named aux.)  No network, no display.  The whole serial
# session is in build/vm/serial.log, the build's output in build/$TARGET/session.log.
#   BUILD_TIMEOUT  seconds, default 1800
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
native_probe=${NATIVE_PROBE:-0}
oconsole=${OCONSOLE:-0}
ether_probe=${ETHER_PROBE:-0}
ipv6_probe=${IPV6_PROBE:-0}
udp6_probe=${UDP6_PROBE:-0}
e74_probe=${E74_PROBE:-0}
e76_native=${E76_NATIVE:-0}
e77_native=${E77_NATIVE:-0}
if [ "$((native_probe + oconsole + ether_probe + ipv6_probe + udp6_probe + e74_probe + e76_native + e77_native))" -gt 1 ]; then
	echo "build.sh: NATIVE_PROBE, OCONSOLE, ETHER_PROBE, IPV6_PROBE, UDP6_PROBE, E74_PROBE, E76_NATIVE and E77_NATIVE are separate opt-in builds" >&2
	exit 2
fi
if [ "$native_probe" = 1 ]; then
	# E2 opt-in: regenerate before staging, then build only the probe config.
	python3 "$here/kernel_opmap.py" --generate-native --config pc64 \
		--out-dir "$root/build/generated/kernel-native" >/dev/null
	kconf=pc64native
	kernel=9pc64native
	testkconf=
	testkernel=
elif [ "$oconsole" = 1 ]; then
	# E5 opt-in: no "cons" line in the config's dev section, so the
	# generated devtab has no consdevtab registration.
	kconf=pc64oconsole
	kernel=9pc64oconsole
	testkconf=
	testkernel=
elif [ "$ether_probe" = 1 ]; then
	# E7.1 opt-in: same legacy devices plus the native Ethernet probe.
	kconf=pc64e71
	kernel=9pc64e71
	testkconf=
	testkernel=
elif [ "$ipv6_probe" = 1 ]; then
	# E7.2 opt-in: native Ethernet->IPv6 consumer and VirtIO fixture.
	kconf=pc64e72
	kernel=9pc64e72
	testkconf=
	testkernel=
elif [ "$udp6_probe" = 1 ]; then
	# E7.3 opt-in: native UDP6 endpoint and VirtIO datagram fixture.
	kconf=pc64e73
	kernel=9pc64e73
	testkconf=
	testkernel=
elif [ "$e74_probe" = 1 ]; then
	# E7.4 opt-in: experimental IPv6 Next Header 253 consumer + VirtIO fixture.
	kconf=pc64e74
	kernel=9pc64e74
	testkconf=
	testkernel=
elif [ "$e76_native" = 1 ]; then
	# E7.6 opt-in: NORMAL IPv6 without #l/#I/#W.
	kconf=pc64e7native
	kernel=9pc64e7native
	testkconf=
	testkernel=
elif [ "$e77_native" = 1 ]; then
	# E7.7 opt-in: native-only IPv6, no executable IPv4/ARP.
	kconf=pc64e7v6only
	kernel=9pc64e7v6only
	testkconf=
	testkernel=
fi
out=$tbuild; b=$root/build
mkdir -p "$out"; rm -rf "$out/$kernel" ${testkernel:+"$out/$testkernel"} "$out/$loader" "$out/hjfs" "$out/kbdfs" "$out/ktest" "$out/root" "$out"/*.log "$out"/*.rootc.c "$out"/*.devc.c "$b"/in.img "$b"/out.img

cp "$here/targets/$TARGET" "$b/target"
printf 'what=%s\npasses=%s\n' "${WHAT:-all}" "${PASSES:-1}" >> "$b/target"
if [ "$native_probe" = 1 ]; then
	printf "kconf=pc64native\nkernel=9pc64native\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$oconsole" = 1 ]; then
	printf "kconf=pc64oconsole\nkernel=9pc64oconsole\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$ether_probe" = 1 ]; then
	printf "kconf=pc64e71\nkernel=9pc64e71\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$ipv6_probe" = 1 ]; then
	printf "kconf=pc64e72\nkernel=9pc64e72\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$udp6_probe" = 1 ]; then
	printf "kconf=pc64e73\nkernel=9pc64e73\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$e74_probe" = 1 ]; then
	printf "kconf=pc64e74\nkernel=9pc64e74\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$e76_native" = 1 ]; then
	printf "kconf=pc64e7native\nkernel=9pc64e7native\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
elif [ "$e77_native" = 1 ]; then
	printf "kconf=pc64e7v6only\nkernel=9pc64e7v6only\ntestkconf=''\ntestkernel=''\n" >> "$b/target"
	printf "ip6cflags=-DE7_IPV6_ONLY\n" >> "$b/target"
fi
# the repo's Plan 9 tree
"$here/overlay" "$b/overlay"
if [ "$native_probe" = 1 ]; then
	mkdir -p "$b/overlay/sys/src/9/pc64"
	cp "$root/build/generated/kernel-native/kernel_native.c" \
		"$root/build/generated/kernel-native/kernel_native.h" \
		"$b/overlay/sys/src/9/pc64/"
fi
tar cf "$b/in.img" --format=ustar -C "$b/overlay" . -C "$here" build.rc -C "$b" target
truncate -s $(( $(stat -c %s "$b/in.img") / 1048576 + 16 ))M "$b/in.img"
truncate -s 512M "$b/out.img"

trap '"$here/vm" stop' EXIT
"$here/vm" start
printf 'term%% \t!done\n' | "$here/9run" -t 180 --dialog - >/dev/null
set +e
"$here/9run" -t "${BUILD_TIMEOUT:-1800}" '@{cd /tmp && tar xf /dev/sdE1/data build.rc target} && rc /tmp/build.rc' 2>&1 | cut -c1-200 | tee "$out/session.log"
st=${PIPESTATUS[0]}
set -e
"$here/vm" stop; trap - EXIT

tar xmf "$b/out.img" -C "$out" 2>/dev/null || true
[ "${WHAT:-all}" = loader ] || results="$kernel hjfs kbdfs ktest${testkernel:+ $testkernel}"
results="$results $loader"
[ "$st" = 0 ] && grep -q BUILD-DONE "$out/session.log" || { echo "build failed"; exit 1; }
for f in $results; do [ -s "$out/$f" ] || { echo "build failed: no $f"; exit 1; }; done
echo "results in $out: $(cd "$out" && ls -l $results | awk '{print $5, $9}' | tr '\n' ' ')"
