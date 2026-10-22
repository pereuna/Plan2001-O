#!/usr/bin/env bash
# Plan2001: the human-facing O-only REPL.  Uses the normal amd64 kernel and
# an ESP + O disk prepared by tools/mkrepl: UEFI -> kernel -> embedded oinit
# -> the MicroPython executable stored in O -> interactive REPL.  Set
# FORCE=1 tools/mkrepl first only when a fresh persistent image is wanted.
set -e
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
. tools/target.sh

img=$tbuild/repl.img
[ -s "$img" ] || tools/mkrepl "$img"
cp "$fwvars" "$tbuild/poc-vars.fd"

exec "$qemu" -name plan2001-repl -nodefaults "${qemuargs[@]}" \
  -m 2048 -smp 8 \
  -drive if=pflash,format=raw,readonly=on,file="$fwcode" \
  -drive if=pflash,format=raw,file="$tbuild/poc-vars.fd" \
  -drive file="$img",format=raw,if=none,id=d0 \
  -device virtio-blk-pci-non-transitional,drive=d0,bootindex=0 \
  -nic none -display none -serial mon:stdio
