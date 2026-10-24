#!/usr/bin/env python3
"""Focused source/coverage check for the E5 #c migration.

This is deliberately a small manifest checker, not a second C analyser.
It validates that every live Qid enumerator has a row in
docs/CONS-MIGRATION.md, that statuses are explicit, that the native names
cited by the manifest exist in the kernel source, and that pc64oconsole does
not register the legacy cons Dev.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVCONS = ROOT / "sys/src/9/port/devcons.c"
MANIFEST = ROOT / "docs/CONS-MIGRATION.md"
PCDIR = ROOT / "sys/src/9/pc64"
CORE = [
    ROOT / "sys/src/9/port/cons.c",
    ROOT / "sys/src/9/port/procobs.c",
    ROOT / "sys/src/9/port/sysinfo.c",
]
SOURCE_FILES = [
    ROOT / "sys/src/9/port/portfns.h",
    ROOT / "sys/src/9/port/portdat.h",
    ROOT / "sys/src/9/port/devcons.c",
    ROOT / "sys/src/9/port/tod.c",
    ROOT / "sys/src/9/port/random.c",
    ROOT / "sys/src/9/port/auth.c",
    ROOT / "sys/src/9/port/rebootcmd.c",
    ROOT / "sys/src/9/port/rdb.c",
] + CORE

COLUMNS = [
    "Qid_or_symbol",
    "current_read",
    "current_write",
    "legacy_perm",
    "owner",
    "native_operation",
    "callers",
    "security",
    "state/lifetime",
    "migration_status",
    "evidence",
]
STATUSES = {"native", "legacy-only", "intentionally-unsupported"}

REQUIRED_SYMBOLS = {
    "consinit",
    "devreset",
    "devshutdown",
    "print",
    "iprint",
    "panic",
    "putstrn",
    "pprint",
    "readnum",
    "readstr",
}

NEW_PROTOTYPES = [
    "consinit",
    "consputstr",
    "kmesgreadat",
    "kmesgwrite",
    "kprintacquire",
    "kprintread",
    "kprintrelease",
    "proccputimes",
    "procpid",
    "procppid",
    "procusername",
    "sysnameget",
    "sysnameset",
    "hostownerget",
    "hostdomainget",
    "configget",
    "osversionget",
    "timecontrolallowed",
    "sysstatget",
    "sysstatreset",
    "nulldiscard",
    "zerofill",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def qids() -> list[str]:
    text = DEVCONS.read_text(encoding="utf-8")
    m = re.search(r"enum\s*\{\s*Qdir,(.*?)\};", text, re.S)
    if not m:
        fail("cannot find the Qid enum in devcons.c")
    names = ["Qdir"] + [x.strip() for x in m.group(1).split(",")]
    return [x for x in names if x]


def split_row(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    cell = []
    cur = []
    esc = False
    for ch in line[1:-1] if line.endswith("|") else line[1:]:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
            cur.append(ch)
        elif ch == "|":
            cell.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cell.append("".join(cur).strip())
    return cell


def manifest_rows() -> tuple[dict[str, dict[str, str]], list[str]]:
    rows: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    header_seen = False
    in_table = False
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_table = False
        cells = split_row(line)
        if not cells:
            continue
        if cells[0] == "Qid_or_symbol":
            header_seen = True
            in_table = True
            if cells != COLUMNS:
                errors.append(f"manifest header is {cells!r}, want {COLUMNS!r}")
            continue
        if not in_table:
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        if len(cells) != len(COLUMNS):
            errors.append(f"{cells[0]}: {len(cells)} columns, want {len(COLUMNS)}")
            continue
        row = dict(zip(COLUMNS, cells))
        if row["Qid_or_symbol"] in rows:
            errors.append(f"duplicate manifest row {row['Qid_or_symbol']}")
        rows[row["Qid_or_symbol"]] = row
    if not header_seen:
        errors.append("manifest table header not found")
    return rows, errors


def config_section(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            cur = line.split()[0]
            sections[cur] = []
            continue
        if cur:
            sections[cur].append(line.strip())
    return sections


def config_has_cons(path: Path) -> bool:
    dev = config_section(path).get("dev", [])
    return any(line.split()[:1] == ["cons"] for line in dev)


def check_configs() -> None:
    mk = (PCDIR / "mkfile").read_text(encoding="utf-8")
    m = re.search(r"^CONFLIST=(.*)$", mk, re.M)
    confs = m.group(1).split() if m else []
    if "pc64oconsole" not in confs:
        fail("pc64oconsole is not in CONFLIST")
    for name in ("pc64", "pc64mp", "pc64native"):
        if not config_has_cons(PCDIR / name):
            fail(f"{name} lost its legacy cons registration")
    if config_has_cons(PCDIR / "pc64oconsole"):
        fail("pc64oconsole still registers the cons Dev")
    if (PCDIR / "pc64oconsole").read_text(encoding="utf-8").count("\n") < 20:
        fail("pc64oconsole looks truncated")


def check_source() -> None:
    for path in CORE + [DEVCONS]:
        if not path.exists():
            fail(f"missing source {path.relative_to(ROOT)}")
    devdefs = []
    for path in (ROOT / "sys/src/9").rglob("*.c"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*Dev\s+consdevtab\b", text, re.M):
            devdefs.append(path.relative_to(ROOT))
    if devdefs != [Path("sys/src/9/port/devcons.c")]:
        fail(f"consdevtab defined in unexpected files: {devdefs}")

    pf = (ROOT / "sys/src/9/port/portfns.h").read_text(encoding="utf-8")
    for sym in NEW_PROTOTYPES:
        m = re.search(rf"^[^\n]*\b{sym}\s*\([^\n]*\);", pf, re.M)
        if not m:
            fail(f"no prototype for {sym} in portfns.h")
        line = m.group(0)
        for bad in ("Chan*", "Qid", "Dirtab", "char *path"):
            if bad in line:
                fail(f"{sym} prototype leaks {bad}: {line}")


def check_manifest() -> tuple[int, int, int]:
    names = qids()
    if len(names) != 23:
        fail(f"Qid enum has {len(names)} entries, expected 23: {names}")
    rows, errors = manifest_rows()
    if errors:
        fail("; ".join(errors))
    for name in names + sorted(REQUIRED_SYMBOLS):
        if name not in rows:
            errors.append(f"missing manifest row {name}")
    if errors:
        fail("; ".join(errors))

    source = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in SOURCE_FILES if p.exists())
    counts = {"native": 0, "legacy-only": 0, "intentionally-unsupported": 0}
    qidcounts = {"native": 0, "legacy-only": 0, "intentionally-unsupported": 0}
    for name, row in rows.items():
        status = row["migration_status"]
        if status not in STATUSES:
            fail(f"{name}: bad status {status!r}")
        counts[status] += 1
        if name in names:
            qidcounts[status] += 1
        if status == "native":
            op = row["native_operation"]
            if op.strip().lower() in ("", "none", "n/a"):
                fail(f"{name}: native row has no operation")
            for tok in re.findall(r"`([^`]+)`", op):
                for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", tok):
                    if ident in {
                        "void", "long", "int", "char", "uvlong", "str", "n",
                        "usewrite", "buf", "off", "t", "v", "id", "get",
                        "set", "none", "and", "or", "with", "the", "as",
                    }:
                        continue
                    if not re.search(rf"\b{re.escape(ident)}\b", source):
                        fail(f"{name}: manifest cites missing symbol {ident}")
    return (qidcounts["native"], qidcounts["legacy-only"],
            qidcounts["intentionally-unsupported"],
            counts["native"], counts["legacy-only"], counts["intentionally-unsupported"])


def check_kernel(path: Path) -> None:
    data = path.read_bytes()
    def has(sym: str) -> bool:
        return sym.encode() in data
    for sym in ("consdevtab",):
        if has(sym):
            fail(f"{path.name}: linked symbol {sym} is present")
    for sym in ("panic", "iprint", "putstrn", "consinit", "consputstr",
                "kmesgreadat", "procpid", "sysstatget", "todinit",
                "randominit", "readnum", "readstr"):
        if not has(sym):
            fail(f"{path.name}: linked core symbol {sym} is absent")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", type=Path, help="built O-only kernel to inspect")
    ap.add_argument("--devc", type=Path, help="generated pc64oconsole devtab C")
    args = ap.parse_args()
    check_configs()
    check_source()
    qn, ql, qu, an, al, au = check_manifest()
    if args.devc:
        text = args.devc.read_text(encoding="utf-8", errors="replace")
        if "&consdevtab" in text or "Dev consdevtab" in text:
            fail(f"{args.devc}: generated devtab still registers consdevtab")
    if args.kernel:
        check_kernel(args.kernel)
    print(f"PASS: 23 Qids; native {qn}, legacy-only {ql}, "
          f"intentionally-unsupported {qu}; all rows native {an}, legacy-only {al}, "
          f"intentionally-unsupported {au}; pc64oconsole has no cons Dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
