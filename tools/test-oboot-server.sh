#!/bin/bash
# Plan2001 Boot Experiment D2b: native noninteractive MicroPython server,
# three consecutive boots of one unchanged combined ESP+O disk.  No
# boot.py, /dev, kbdfs, Chan/path/FD, console input or legacy exec.
#   MEM, SECONDS_TO_RUN
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(dirname "$here")
. "$here/target.sh"
b=$tbuild
vm=$b/obootd2bvm
oimg=$b/obootd2b-o.img
disk=$b/obootd2b.img
missingo=$b/obootd2b-missing-o.img
missing=$b/obootd2b-missing.img
mp=$b/root/$objtype/bin/micropython
[ -x "$root/build/selfroot/amd64/bin/gefs" ] || { echo "test-oboot-server: no build/selfroot gefs (tools/selfroot)" >&2; exit 1; }
[ -x "$mp" ] || { echo "test-oboot-server: no $mp (WHAT=all build)" >&2; exit 1; }
[ -s "$b/$kernel" ] || { echo "test-oboot-server: no $b/$kernel (tools/build.sh)" >&2; exit 1; }
[ -s "$b/$loader" ] || { echo "test-oboot-server: no $b/$loader (tools/build.sh)" >&2; exit 1; }
mkdir -p "$vm"
q=
clean() { tr -d '\r' < "$vm/serial$1.log" 2>/dev/null | sed 's/\x1b\[[0-9;=?]*[a-zA-Z]//g'; }
stop() { [ -n "$q" ] && { kill "$q" 2>/dev/null || true; wait "$q" 2>/dev/null || true; }; q=; }
trap stop EXIT
fails=0
fail() { echo "FAIL: $*"; fails=$((fails+1)); }
mpsize=$(stat -c %s "$mp")
mpsha=$(sha256sum "$mp" | awk '{print $1}')

bootcase() {
	local n=$1 img=$2 waitpat=$3
	: > "$vm/serial$n.log"
	cp "$fwvars" "$vm/vars$n.fd"
	"$qemu" -name "plan2001-obootd2b-$n" -nodefaults "${qemuargs[@]}" -m "${MEM:-2048}" -smp 2 \
		-drive if=pflash,format=raw,readonly=on,file="$fwcode" \
		-drive if=pflash,format=raw,file="$vm/vars$n.fd" \
		-drive file="$img",format=raw,if=none,id=d0 \
		-device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
		-nic none -display none -serial file:"$vm/serial$n.log" 2>"$vm/qemu$n.log" &
	q=$!
	local end=$((SECONDS + ${SECONDS_TO_RUN:-90}))
	until clean "$n" | grep -q "$waitpat" || [ $SECONDS -ge $end ] || ! kill -0 "$q" 2>/dev/null; do
		sleep 1
	done
	sleep 1
	stop
	clean "$n" > "$vm/boot$n.log"
}

echo "### prepare one disposable O image and one ESP+O disk"
rm -f "$oimg" "$disk" "$disk.ini" "$disk.partuuid"
MPEXEC="$mp" "$here/mkovol" "$oimg" 192 "$here/odemo.py" > "$vm/mkovol.log" 2>&1 ||
	{ cat "$vm/mkovol.log" >&2; fail "mkovol failed"; }
grep -q "^seed: mpexec $mpsize 4f45584543000003 $mpsha unchanged$" "$vm/mkovol.log" ||
	fail "OID_MP_EXEC bytes differ from the current build"
grep -q "^seed: object mp oid=0x4f45584543000003 len=$mpsize$" "$vm/mkovol.log" ||
	fail "OID_MP_EXEC absent from the O seed"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$oimg" KERNEL="$kernel" \
	INI='oboot=server;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$disk" > "$vm/gefsdisk.log" 2>&1 ||
	{ cat "$vm/gefsdisk.log" >&2; fail "gefsdisk failed"; }
puuid=$(cat "$disk.partuuid")
grep -q "^obootvol=PARTUUID=$puuid$" "$disk.ini" || fail "plan9.ini: obootvol not substituted"
grep -q '^root=' "$disk.ini" && fail "plan9.ini: has root="
grep -q '^init=' "$disk.ini" && fail "plan9.ini: has init="

for n in 1 2 3; do
	bootcase "$n" "$disk" 'OBOOT-D2B: AFTER-SYSCALLS n=64 '
	log=$vm/boot$n.log
	grep -q "^OBOOT-D2B: ARGV argc=6 <micropython> <-O> <PARTUUID=$puuid> <-S> <init> <-N>$" "$log" ||
		fail "boot$n: wrong six-argument -N contract"
	grep -q "^OBOOT-D2B: OEXECUTE oid=0x4f45584543000003 len=$mpsize sha256=$mpsha " "$log" ||
		fail "boot$n: OID bytes do not match the current build"
	grep -q '^OBOOT-D2B: SYSCALL-RETURN .*nr=60 .*text=micropython ' "$log" ||
		fail "boot$n: MicroPython image transition missing"
	grep -q '^OBOOT-D2B: P9-SPACE-O$' "$log" || fail "boot$n: no P9-SPACE-O"
	grep -q '^OBOOT-D2B: SPACE-OPEN$' "$log" || fail "boot$n: no SPACE-OPEN"
	grep -q '^OBOOT-D2B: RUN$' "$log" || fail "boot$n: no RUN"
	grep -q '^OBOOT-D2B: COMMIT$' "$log" || fail "boot$n: no COMMIT"
	grep -q "^init: run() -> $n$" "$log" || fail "boot$n: run() -> $n missing"
	grep -q "^init: shared Counter n $n, alias same, OID 7 (alias 7)$" "$log" ||
		fail "boot$n: Counter identity/alias mismatch"
	grep -q '^init: done$' "$log" || fail "boot$n: init: done missing"
	grep -q '^OBOOT-D2B: IOWRITE-ENTRY .* h=2 .* text=micropython ' "$log" &&
		grep -q '^OBOOT-D2B: IOWRITE-RETURN .* h=2 .* ret=[1-9]' "$log" ||
		fail "boot$n: native diagnostic write missing"
	grep -q '^OBOOT-D2B: AFTER-SYSCALLS n=4 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" &&
		grep -q '^OBOOT-D2B: AFTER-SYSCALLS n=16 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" &&
		grep -q '^OBOOT-D2B: AFTER-SYSCALLS n=32 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" &&
		grep -q '^OBOOT-D2B: AFTER-SYSCALLS n=64 legacy userinit=0 proc0=0 init0=0 path namec=0 newchan=0 walk=0 devwalk=0 mount=0 exec=0$' "$log" ||
		fail "boot$n: cumulative legacy/path counters not zero"
	grep -q 'OBOOT-D2B: LEGACY-ATTEMPT' "$log" && fail "boot$n: legacy syscall attempt"
	for nr in 2 14 23 51; do
		sed -n '/text=micropython/,$p' "$log" | grep -q "SYSCALL-ENTRY .*nr=$nr " &&
			fail "boot$n: forbidden post-MP syscall nr=$nr"
	done
	grep -q 'panic\|fault\|suicide' "$log" && fail "boot$n: panic/fault"
	grep -q '^OBOOT-A:\|^OBOOT-B:\|^OBOOT-C:\|^OBOOT-D1:' "$log" && fail "boot$n: foreign marker"
done

# Boot 1 fresh, boot 2/3 restored from the same image/disk.
grep -q '^space: O: init has no graph' "$vm/boot1.log" || fail "boot1: not fresh"
grep -q '^space: O: init initialized from O code (odemo)$' "$vm/boot1.log" || fail "boot1: no one-time init"
grep -q '^space: O: committed init version 1 (O version 2)$' "$vm/boot1.log" || fail "boot1: no version 1 commit"
grep -q '^space: O: restored init version 1,' "$vm/boot2.log" || fail "boot2: no restore version 1"
grep -q '^space: O: init restored (odemo), no module initialization$' "$vm/boot2.log" || fail "boot2: reinitialized"
grep -q '^space: O: committed init version 2 (O version 3)$' "$vm/boot2.log" || fail "boot2: no version 2 commit"
grep -q '^space: O: restored init version 2,' "$vm/boot3.log" || fail "boot3: no restore version 2"
grep -q '^space: O: init restored (odemo), no module initialization$' "$vm/boot3.log" || fail "boot3: reinitialized"
grep -q '^space: O: committed init version 3 (O version 4)$' "$vm/boot3.log" || fail "boot3: no version 3 commit"

echo "### negative: run() raises, no commit/done"
failimg=$b/obootd2b-fail-o.img
faildisk=$b/obootd2b-fail.img
failsrc=$vm/odemo-fail.py
cat > "$failsrc" <<'PYEOF'
class Counter:
    def __init__(self, n=0):
        self.n = n

shared = Counter(41)
alias = shared

def init():
    shared.n = 0

def run():
    raise Exception("D2B negative run failure")
PYEOF
rm -f "$failimg" "$faildisk" "$faildisk.ini" "$faildisk.partuuid"
MPEXEC="$mp" "$here/mkovol" "$failimg" 192 "$failsrc" > "$vm/mkovol-fail.log" 2>&1 ||
	{ cat "$vm/mkovol-fail.log" >&2; fail "mkovol fail failed"; }
NOROOTFS=1 CONSOLE=0 ROOTIMG="$failimg" KERNEL="$kernel" \
	INI='oboot=server;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$faildisk" > "$vm/gefsdisk-fail.log" 2>&1 ||
	{ cat "$vm/gefsdisk-fail.log" >&2; fail "gefsdisk fail failed"; }
bootcase fail "$faildisk" 'init: failed, no commit'
flog=$vm/bootfail.log
grep -q 'init: run failed' "$flog" || fail "fail: no run failure"
grep -q 'init: failed, no commit' "$flog" || fail "fail: no no-commit marker"
grep -q 'init: done\|OBOOT-D2B: COMMIT\|space: O: committed' "$flog" && fail "fail: claimed commit/done"
grep -q 'panic\|fault\|suicide' "$flog" && fail "fail: panic/fault"

echo "### negative: OID_MP_EXEC absent"
rm -f "$missingo" "$missing" "$missing.ini" "$missing.partuuid"
NOMPEXEC=1 "$here/mkovol" "$missingo" 192 "$here/odemo.py" > "$vm/mkovol-missing.log" 2>&1 ||
	{ cat "$vm/mkovol-missing.log" >&2; fail "mkovol missing failed"; }
grep -q '^seed: mpexec \|^seed: object mp ' "$vm/mkovol-missing.log" && fail "missing image has OID_MP_EXEC"
NOROOTFS=1 CONSOLE=0 ROOTIMG="$missingo" KERNEL="$kernel" \
	INI='oboot=server;obootvol=PARTUUID=@PARTUUID@' "$here/gefsdisk" "$missing" > "$vm/gefsdisk-missing.log" 2>&1 ||
	{ cat "$vm/gefsdisk-missing.log" >&2; fail "gefsdisk missing failed"; }
bootcase missing "$missing" 'OBOOT-D2B: SYSCALL-ENTRY .*nr=6 arg0=0xbaf '
mlog=$vm/bootmissing.log
grep -q '^OBOOT-D2B: SYSCALL-RETURN .*nr=60 .*ret=0xffffffffffffffff text=\*ouser\* ' "$mlog" ||
	fail "missing: OEXECUTE did not return an error"
grep -q '^OBOOT-D2B: SYSCALL-RETURN .*nr=56 .*ret=0xd1 text=\*ouser\* ' "$mlog" ||
	fail "missing: O handle did not survive"
grep -q '^OBOOT-D2B: SYSCALL-ENTRY .*nr=6 arg0=0xbaf text=\*ouser\* .*user=1$' "$mlog" ||
	fail "missing: no userspace failure marker"
grep -q 'init: done\|COMMIT' "$mlog" && fail "missing: claimed commit/done"
grep -q 'text=micropython' "$mlog" && fail "missing: MicroPython ran"
grep -q 'panic\|fault\|suicide' "$mlog" && fail "missing: panic/fault"

[ "$fails" = 0 ] && echo "PASS: D2b native O server, three same-disk boots and negative" || {
	echo "FAIL: $fails"
	exit 1
}
