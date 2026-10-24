#!/usr/bin/env python3
"""Focused E6 source and linked-artifact check for the SD migration.

This is a small manifest checker, not a second C parser.  It proves the
things the E6 task can prove without running QEMU:

  * sdcore.c owns the native controller registry and block operations;
  * devsd.c remains the legacy #S Dev adapter over the same records;
  * default/E5 configs still register sd, the new profile registers neither
    cons nor sd, and sdloop is absent from the new profile;
  * when a generated devc.c and/or kernel binary is supplied, the actual
    registration/table and Plan 9 symbol table agree with the source claim.

It deliberately prints SOURCE and LINKED sections separately and does not
claim runtime behavior.  A missing or unreadable artifact fails closed.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "sys/src/9/port"
PCDIR = ROOT / "sys/src/9/pc64"
CORE = PORT / "sdcore.c"
DEVC = PORT / "devsd.c"
SDH = PORT / "sd.h"
MKDEVC = PORT / "mkdevc"
MKFILE = PCDIR / "mkfile"

CORE_DEFS = [
    "sdinitcontrollers",
    "sdreset",
    "sdadddevs",
    "sdgetdev",
    "sdgetunit",
    "sdunititer",
    "sdunitput",
    "sdunitready",
    "sdblockrw",
    "sdblockflush",
    "sdrio",
    "sdsetsense",
    "sdfakescsi",
    "sdfakescsirw",
    "sdaddfile",
]
SDH_DECLS = CORE_DEFS + [
    "sdindex",
    "sdinitpart",
    "sdaddpart",
    "sddelpart",
    "sdfreedev",
]
CONFIG_DEFS = {
    "pc64": ("cons", "sd"),
    "pc64mp": ("cons", "sd"),
    "pc64native": ("cons", "sd"),
    "pc64oconsole": (None, "sd"),
    "pc64onativedisk": (None, None),
}
LEGACY_PROFILES = {
    "default", "oconsole", "pc64", "pc64mp", "pc64native", "pc64oconsole",
}
NATIVE_PROFILES = {"onative", "pc64onativedisk"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def text(path: Path) -> str:
    if not path.exists():
        fail(f"missing source {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def config_sections(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    cur = None
    for line in text(path).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            cur = line.split()[0]
            sections[cur] = []
            continue
        if cur:
            sections[cur].append(line.strip())
    return sections


def config_tokens(path: Path) -> dict[str, set[str]]:
    return {name: {line.split()[0] for line in lines}
            for name, lines in config_sections(path).items()}


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def check_source() -> None:
    core = text(CORE)
    corecode = strip_comments(core)
    devsd = text(DEVC)
    sd = text(SDH)
    mk = text(MKFILE)
    mkdevc = text(MKDEVC)

    for sym in CORE_DEFS:
        if not re.search(rf"^{re.escape(sym)}\s*\(", core, re.M):
            fail(f"sdcore.c does not define {sym}")
    for sym in SDH_DECLS:
        if not re.search(rf"^extern\b[^\n]*\b{re.escape(sym)}\s*\(", sd, re.M):
            fail(f"sd.h has no prototype for {sym}")

    for bad in ("Chan", "Qid", "Dirtab", "namec", "Dev sddevtab"):
        if bad in corecode:
            fail(f"sdcore.c still mentions {bad!r}; it is not Chan-free")
    if not re.search(r"^Dev\s+sddevtab\s*=", devsd, re.M):
        fail("devsd.c no longer defines the legacy sddevtab")
    for sym in ("sdattach", "sdwalk", "sdstat", "sdopen", "sdclose",
                "sdread", "sdwrite", "sdwstat", "sdconfig"):
        if not re.search(rf"^{sym}\s*\(", devsd, re.M):
            fail(f"legacy #S adapter lost {sym}")

    if "CONFLIST" not in mk or "pc64onativedisk" not in mk:
        fail("pc64onativedisk is not in pc64 CONFLIST")
    if "sdcore.$O" not in mk:
        fail("sdcore.$O is not linked unconditionally by the pc64 mkfile")

    for name, (cons, sdline) in CONFIG_DEFS.items():
        sec = config_tokens(PCDIR / name)
        dev = sec.get("dev", set())
        misc = sec.get("misc", set())
        if (cons is None) != ("cons" not in dev):
            fail(f"{name}: cons dev registration disagrees with the manifest")
        if (sdline is None) != ("sd" not in dev):
            fail(f"{name}: sd dev registration disagrees with the manifest")
        if "sdloop" in misc and name == "pc64onativedisk":
            fail("pc64onativedisk still links sdloop")
        if name == "pc64onativedisk":
            for ctl in ("sdiahci", "sdvirtio10", "sdnvme", "sdram"):
                if ctl not in misc:
                    fail(f"pc64onativedisk lost controller {ctl}")
        else:
            for ctl in ("sdiahci", "sdvirtio10", "sdnvme", "sdram", "sdloop"):
                if ctl not in misc:
                    fail(f"legacy profile {name} lost {ctl}")

    if not re.search(r"if\(devsd \|\| nsdifc\)", mkdevc):
        fail("mkdevc does not emit sdifc[] for profiles without the sd Dev")

    print("SOURCE: PASS (sdcore/devsd ownership, configs, mkdevc)")


def check_devtab(path: Path, profile: str) -> None:
    body = text(path)
    table = re.search(r"Dev\*\s*devtab\[\]\s*=\s*\{(.*?)\};", body, re.S)
    if not table:
        fail(f"{path}: no generated devtab[]")
    entries = set(re.findall(r"&([A-Za-z_][A-Za-z0-9_]*)", table.group(1)))
    if profile in LEGACY_PROFILES:
        if "sddevtab" not in entries:
            fail(f"{path}: legacy profile lacks &sddevtab")
    else:
        if "sddevtab" in entries:
            fail(f"{path}: native profile still registers &sddevtab")
        if "consdevtab" in entries:
            fail(f"{path}: native profile still registers &consdevtab")
    if profile in ("oconsole", "pc64oconsole") and "consdevtab" in entries:
        fail(f"{path}: pc64oconsole still registers &consdevtab")
    print(f"DEVTAB: PASS ({path.name}, profile {profile})")


def plan9_symbols(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    if len(data) < 40:
        fail(f"{path}: too short for a Plan 9 a.out")
    try:
        magic, tsz, dsz, bss, symsz, entry, spsz, lcsz = struct.unpack_from(
            ">IIIIIIII", data, 0)
    except struct.error:
        fail(f"{path}: truncated Plan 9 header")
    if magic & 0x7fff != (4 * 26 * 26 + 7):
        fail(f"{path}: not a Plan 9 a.out (magic {magic:#x})")
    off = 32 + tsz + dsz
    end = off + symsz
    if end > len(data):
        fail(f"{path}: symbol table outside the file")
    syms: dict[str, str] = {}
    while off < end:
        if off + 9 > end:
            if not any(data[off:end]):
                break
            fail(f"{path}: truncated symbol entry")
        hi, lo = struct.unpack_from(">II", data, off)
        off += 8
        typ = data[off]
        off += 1
        nul = data.find(b"\0", off)
        if nul < 0 or nul >= end:
            fail(f"{path}: unterminated symbol name")
        name = data[off:nul].decode("latin-1")
        off = nul + 1
        syms[name] = chr(typ & 0x7f)
    return syms


def check_kernel(path: Path, profile: str) -> None:
    syms = plan9_symbols(path)
    required = ["sdinitcontrollers", "sdunititer", "sdunitready",
                "sdblockrw", "sdblockflush", "sdrio", "sdvirtio10ifc"]
    for sym in required:
        if sym not in syms:
            fail(f"{path}: missing linked native SD symbol {sym}")
    if profile in LEGACY_PROFILES:
        if "sddevtab" not in syms:
            fail(f"{path}: legacy profile does not link sddevtab")
    else:
        for sym in ("sddevtab", "consdevtab", "sdloopifc"):
            if sym in syms:
                fail(f"{path}: native profile still links {sym}")
        if "sdcore" not in syms and "sdblockrw" not in syms:
            fail(f"{path}: native SD core is not linked")
    print(f"KERNEL: PASS ({path.name}, profile {profile}, {len(syms)} symbols)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", choices=sorted(CONFIG_DEFS), default=None,
                    help="profile for artifact and config checks")
    ap.add_argument("--devtab", type=Path, help="generated <conf>.c devtab source")
    ap.add_argument("--kernel", type=Path, help="linked Plan 9 kernel binary")
    args = ap.parse_args()

    check_source()
    if args.devtab:
        if not args.profile:
            fail("--devtab requires --profile")
        if not args.devtab.is_file():
            fail(f"{args.devtab}: not a readable generated devtab source")
        check_devtab(args.devtab, args.profile)
    if args.kernel:
        if not args.profile:
            fail("--kernel requires --profile")
        if not args.kernel.is_file():
            fail(f"{args.kernel}: not a readable linked kernel")
        check_kernel(args.kernel, args.profile)
    if bool(args.devtab) != bool(args.kernel):
        print("NOTE: only one linked artifact supplied; source checks stand",
              file=sys.stderr)


if __name__ == "__main__":
    main()
