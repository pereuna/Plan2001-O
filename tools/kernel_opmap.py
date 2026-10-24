#!/usr/bin/env python3
"""Machine-generated operation map of the Plan2001-O kernel driver surface.

This is a deliberately small lexical/structural analyser for the Plan 9 C
dialect used under sys/src/9.  It is not a C compiler and it does not claim
to prove the behaviour of a call chain.  It does:

  * tokenise C with comments and string/character contents removed from the
    declaration and call search;
  * read build configurations (mkdevlist/mkfile semantics) to separate source
    presence from build inclusion;
  * find Dev, Dirtab, Cmdtab, SDifc, PhysUart, VGA, PCArch and ether cards;
  * split Qid switches and Cmdtab commands into separate operations;
  * follow direct C calls with a bounded, cycle-safe graph, while retaining
    indirect callback edges and their known candidates instead of inventing a
    concrete target;
  * emit deterministic JSON and Markdown from the same analysis data.

Regenerate the checked-in inventory from the repository root with:

    python3 tools/kernel_opmap.py --write

Verify that the checked-in outputs are current with:

    python3 tools/kernel_opmap.py --check

The analyser intentionally has no third-party dependencies.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "plan2001.kernel-opmap/v1"
GENERATOR = "tools/kernel_opmap.py"
GENERATOR_VERSION = "1"
KERNEL_REL = "sys/src/9"
DEFAULT_JSON = "docs/KERNEL-OPMAP.json"
DEFAULT_MD = "docs/KERNEL-OPMAP.md"
NATIVE_SCHEMA = "plan2001.kernel-native/v2"
NATIVE_DEFAULT_CONFIG = "pc64"
NATIVE_DEFAULT_OUT = "build/generated/kernel-native"
NATIVE_GENERATOR_VERSION = "2"

# Reviewed E2 bindings.  The source hashes are deliberate: a change to either
# driver invalidates its binding and generation fails closed.  The generator
# derives the readnum expression, offset, size and return shape from the named
# helper's tokens; these records only provide provenance, selector mapping and
# the narrow allow-lists needed to validate that source.
NATIVE_REVIEWED_BINDINGS: dict[str, dict[str, Any]] = {
    "sys/src/9/pc/devrtc.c": {
        "sha256": "6c2f2fd951f861b99323aa372ad902ffedf0f36124ef354be2f1f336c44cbe5d",
        "driver": "rtc",
        "device": "r",
        "dirtab": "rtcdir",
        "selector_values": {"Qdir": 0, "Qrtc": 1, "Qnvram": 2},
        "constants": {"Nvoff": 128, "Nvsize": 256},
        "operations": {
            "read:Qrtc": {
                "kind": "readnum",
                "conversion": "DIRECT",
                "helper": "rtcqread",
                "allowed_calls": ["rtctime"],
                "allowed_idents": [],
                "allowed_constants": {},
                "require_up": False,
                "authorization": (
                    "kernel-internal-only; rtcdir Qrtc is 0664 (other-read "
                    "set) and rtcopen permits any user read; this is not a "
                    "new user entry"
                ),
                "context": ["shared helper is called by rtcread's Qrtc branch"],
                "reason": (
                    "E2 generic readnum extraction: Qrtc branch delegates to "
                    "the shared Chan-free rtcqread helper; value/size are derived "
                    "from its tokenised source"
                ),
            },
            "read:Qnvram": {
                "conversion": "MANUAL",
                "reason": (
                    "E1's separately reviewed NVRAM read binding is not emitted "
                    "by the E2 generic readnum rule; downgraded explicitly to "
                    "MANUAL rather than silently dropped"
                ),
            },
            "write:Qnvram": {
                "conversion": "MANUAL",
                "reason": (
                    "E1's separately reviewed NVRAM write binding is not emitted "
                    "by the E2 generic readnum rule; downgraded explicitly to "
                    "MANUAL rather than silently dropped"
                ),
            },
            "write:Qrtc": {
                "conversion": "MANUAL",
                "reason": (
                    "Qrtc write needs the static sec2rtc()/PUTBCD path and "
                    "textual decimal parsing; no shared Chan-free helper exists"
                ),
            },
        },
    },
    "sys/src/9/port/devcons.c": {
        "sha256": "068dca67758d90a60baed6d9250241c46ee23974b8f09ce45b06e7140e901896",
        "driver": "cons",
        "device": "c",
        "dirtab": "consdir",
        "selector_values": {"Qpid": 12},
        "constants": {},
        "operations": {
            "read:Qpid": {
                "kind": "readnum",
                "conversion": "DIRECT",
                "helper": "consqpidread",
                "allowed_calls": [],
                "allowed_idents": ["up", "pid"],
                "allowed_constants": {"NUMSIZE": 12},
                "require_up": True,
                "authorization": (
                    "kernel-internal-only; consdir pid is 0444 and "
                    "consopen/devopen permit any user read; this is not a new "
                    "user API"
                ),
                "context": ["up != nil", "current process pid"],
                "reason": (
                    "E2 generic readnum extraction: Qpid branch delegates to "
                    "the shared Chan-free consqpidread helper; the helper's n "
                    "guard, value and NUMSIZE are derived from its tokens"
                ),
            },
        },
    },
}

# Driver-level analysis notes.  These are not generation allow-lists; every
# active Dev registration still receives a manifest record.
NATIVE_DRIVER_NOTES: dict[str, dict[str, Any]] = {
    "pipe": {
        "blockers": [
            "endpoint state lives in Pipe via c->aux; a native caller has no equivalent handle lifetime",
            "ref/qref counting decides qhangup/qclose/qreopen and free in pipeclose",
            "both directions share q[0]/q[1]; read on Qdata0 and write on Qdata1 target opposite queues",
            "open/close and wstat change queue ownership and limits (qsetlimit) dynamically",
            "no reviewed Chan-free FIFO binding exists; E1 will not synthesize the queue runtime",
        ],
        "reason": (
            "dynamic endpoint ownership and open/close hangup semantics block "
            "safe automatic extraction; classification only"
        ),
    },
}

# Limits are per call-chain scope, not per driver.  They are deliberately
# generous enough to cross a driver into the shared port code and a backend,
# but bounded so a cycle or a very branchy function cannot run away.
MAX_CHAIN_DEPTH = 8
MAX_CHAIN_NODES = 350
MAX_CHAIN_TERMINALS = 80

KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "int", "long", "register", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "typedef", "union", "unsigned", "void",
    "volatile", "while", "_Noreturn", "inline", "restrict",
}

# Identifiers that look like calls in the token stream but are not C calls.
NON_CALL_IDENTIFIERS = KEYWORDS | {
    "if", "for", "while", "switch", "return", "sizeof", "case", "do",
    "__attribute__", "va_start", "va_end",
    # Plan 9 macros that are frequently written in call form.
    "nelem", "howmany", "QID", "TYPE", "NETTYPE", "NETID", "PART", "UNIT",
    "DEV", "BLEN", "BPLONG", "BGLONG", "PACK64", "UNPACK64", "MACHP",
    "ROUND", "RND", "PGROUND", "MIN", "MAX", "USED", "Tname",
}

QUALIFIERS = {"static", "extern", "const", "volatile", "register", "inline"}

REG_TYPES = {
    "Dev", "SDifc", "PhysUart", "VGAdev", "VGAcur", "PCArch", "ADifc",
    "Dirtab", "Cmdtab", "Ether", "Netif", "Wifi", "ISAConf",
}

# Fallback interface schemas.  The analyser reads the real struct definitions
# from the scanned headers first; these are only used when a fixture (or an
# unusual tree) has no struct declaration in the scanned headers.
FALLBACK_STRUCTS: dict[str, list[str]] = {
    "Dev": [
        "dc", "name", "reset", "init", "shutdown", "attach", "walk", "stat",
        "open", "create", "close", "read", "bread", "write", "bwrite",
        "remove", "wstat", "power", "config",
    ],
    "SDifc": [
        "name", "pnp", "enable", "disable", "verify", "online", "rio",
        "rctl", "wctl", "bio", "probe", "clear", "rtopctl", "wtopctl",
        "ataio",
    ],
    "PhysUart": [
        "name", "pnp", "enable", "disable", "kick", "dobreak", "baud",
        "bits", "stop", "parity", "modemctl", "rts", "dtr", "status",
        "fifo", "power", "getc", "putc",
    ],
    "VGAdev": [
        "name", "enable", "disable", "page", "linear", "drawinit", "fill",
        "ovlctl", "ovlwrite", "flush",
    ],
    "VGAcur": ["name", "enable", "disable", "load", "move"],
    "PCArch": [
        "id", "ident", "reset", "intrinit", "intrassign", "intrirqno",
        "intrspurious", "intrvecno", "introff", "intron", "clockinit",
        "clockenable", "fastclock", "timerset",
    ],
    "Dirtab": ["name", "qid", "length", "perm"],
    "Cmdtab": ["index", "cmd", "narg"],
    "Ether": [
        "ISAConf", "tbdf", "ctlrno", "minmtu", "maxmtu", "attach",
        "transmit", "ctl", "power", "shutdown", "ctlr", "oq", "Netif",
        "ea", "mactab", "dmat",
    ],
    "Netif": [
        "in", "out", "f", "nqueue", "alen", "addr", "bcast", "name",
        "type", "prom", "scan", "bridge", "bypass", "headersonly", "link",
        "mbps", "inpackets", "outpackets", "soverflows",
    ],
}

# Exact calls that are directly at a hardware/controller boundary.  This is
# deliberately not a "safe to remove" judgement.
HARDWARE_CALLS = {
    "inb", "inw", "inl", "ins", "outs", "outb", "outw", "outl",
    "rdmsr", "wrmsr", "rdtsc", "cpuid", "halt",
}

# Prefixes used to recognise controller/service entry points whose exact
# implementation is outside the scanned C tree.  They are reported as
# controller primitives, not as proven hardware accesses.
CONTROLLER_PREFIXES = (
    "pci", "pcimap", "pcicfg", "intr", "dma", "mmio", "csr", "sysreg",
    "nvme", "ahci", "virtio", "uart", "i825", "i8042", "rtc", "vga",
)

# Kernel services and generic Dev helpers.  Calls to these are recorded as
# intermediate steps, but they do not satisfy "device or service primitive".
KERNEL_SERVICES = {
    "alarm", "allocb", "atoi", "atol", "blen", "block", "cclose",
    "cclone", "cmount", "copen", "create", "cmderror", "delay",
    "decref", "devattach", "devbread", "devbwrite", "devcreate",
    "devdirread", "devgen", "devinit", "devopen", "devremove", "devreset",
    "devshutdown", "devstat", "devwalk", "devwstat", "devpower", "error",
    "evenaddr", "exit", "free", "freeb", "iallocb", "iallocbp", "ilock",
    "incref", "iunlock", "iprint", "iseve", "kstrdup", "kstrcpy",
    "lock", "lookupcmd", "malloc", "memchr", "memcmp", "memcpy",
    "memmove", "memset", "microdelay", "mount", "namec", "nexterror",
    "panic", "parsecmd", "pexit", "poperror", "print", "qbread",
    "qbwrite", "qclose", "qconsume", "qdiscard", "qfull", "qget",
    "qio", "qisclosed", "qiwrite", "qlen", "qnoblock", "qopen",
    "qpass", "qproduce", "qput", "qread", "qsetbypass", "qsetlimit",
    "qunlock", "qwrite", "qlock", "readnum", "readstr", "realloc",
    "rendezvous", "rlock", "rwlock", "sleep", "smalloc", "smprint",
    "snprint", "sprint", "strcmp", "strcpy", "strlen", "strncmp",
    "strncpy", "strtol", "strtoul", "strtoull", "tokenize", "tsleep",
    "unlock", "validaddr", "validnamedup", "wakeup", "waserror", "wlock",
    "yield", "seprint", "vseprint", "vsnprint", "fmtstrinit",
    "quotestrdup", "runlock", "rwlock", "wunlock", "mmuflush",
    "flushmmu", "pmap", "kmap", "kunmap", "vmap", "vunmap", "ioalloc",
    "iofree", "splhi", "spllo", "splx", "islo", "getcallerpc",
    "setlabel", "gotolabel", "cistrcmp", "cistrncmp", "isaconfig",
    "getconf", "ksetenv", "kset", "todset", "todget", "randomread",
    "coherence", "assert", "_assert", "convD2M", "convM2D", "convM2S",
    "convS2M", "convD2M", "getirqs", "setuplink", "panic", "iprint",
    "print", "seprint", "snprint", "sprint", "vseprint", "vsnprint",
    "fmtinstall", "fmtstrinit", "resrcwait", "sched", "resched",
    "putstrn", "putstrn0", "isodump", "dump", "dprint", "deprint",
    "ddeprint", "ddprint", "diprint", "ddiprint", "dbgprint", "fprint", "gfprint",
    "cachedwbse", "cachedwbin", "cachedwbtlb", "cachedwbinvse",
    "cachedwbinv", "cycles", "lcycles", "synccycles", "vcycles", "µs",
    "tas", "cmpswap", "xadd", "xchg", "offsetof", "chartorune", "runetochar",
    "delay", "microdelay", "addclock0link", "delclock", "dmaflush",
    "cachedinv", "cachedinvse",
    "poolalloc", "poolfree", "poolallocalign", "poolisoverlap", "sdmalloc",
    "sdfree", "setupAESstate", "hmac_sha1", "dec16", "sha1",
}

SUBSYSTEM_NAMES = {
    "network", "storage", "display-and-input", "console-and-input",
    "ge-o", "process-and-memory", "security-and-tracing", "usb",
    "platform", "other",
}


class ParseError(Exception):
    pass


@dataclass
class Token:
    kind: str
    value: str
    raw: str
    line: int
    col: int
    offset: int


@dataclass
class Call:
    kind: str  # direct, member, pointer, local-pointer
    name: str
    field: str | None
    expr: str
    line: int
    offset: int
    args_text: list[str] = field(default_factory=list)


@dataclass
class CaseLabel:
    label: str
    line: int
    start: int
    end: int


@dataclass
class Switch:
    condition: str
    line: int
    start: int
    end: int
    cases: list[CaseLabel]


@dataclass
class Function:
    id: str
    name: str
    path: str
    line: int
    end_line: int
    static: bool
    params: str
    body: list[Token]
    source_start: int
    source_end: int
    calls: list[Call] = field(default_factory=list)
    switches: list[Switch] = field(default_factory=list)
    local_function_pointers: set[str] = field(default_factory=set)
    conditions: tuple[str, ...] = ()
    text: str = ""

    @property
    def key(self) -> str:
        return self.id


@dataclass
class SourceFile:
    path: str
    abs_path: Path
    text: str
    masked: str
    kind: str
    tokens: list[Token] = field(default_factory=list)
    conditions: list[tuple[str, ...]] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    parse_status: str = "ok"
    parse_error: str | None = None
    parse_error_line: int | None = None
    functions: list[Function] = field(default_factory=list)
    initializers: list[dict[str, Any]] = field(default_factory=list)
    structs: dict[str, list[str]] = field(default_factory=dict)
    sha256: str = ""


# ---------------------------------------------------------------------------
# Lexical handling


def mask_comments(text: str) -> str:
    """Replace comments with spaces, preserving offsets and newlines."""
    out = list(text)
    i = 0
    n = len(text)
    state = "code"
    while i < n:
        c = text[i]
        if state == "code":
            if c == "/" and i + 1 < n and text[i + 1] == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block"
                continue
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line"
                continue
            if c == '"':
                state = "string"
            elif c == "'":
                state = "char"
            i += 1
            continue
        if state == "block":
            if c == "*" and i + 1 < n and text[i + 1] == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
            continue
        if state == "line":
            if c == "\n":
                state = "code"
                i += 1
            else:
                out[i] = " "
                i += 1
            continue
        if state in ("string", "char"):
            quote = '"' if state == "string" else "'"
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                state = "code"
            i += 1
    return "".join(out)


def compute_line_conditions(masked: str) -> list[tuple[str, ...]]:
    lines = masked.splitlines()
    result: list[tuple[str, ...]] = [()] * (len(lines) + 2)
    stack: list[str] = []
    pending = ""
    for lineno, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if pending:
            stripped = pending + " " + stripped
            pending = ""
        if not stripped.startswith("#"):
            result[lineno] = tuple(stack)
            continue
        body = stripped[1:].strip()
        if body.endswith("\\"):
            pending = body[:-1]
            result[lineno] = tuple(stack)
            continue
        m = re.match(r"([A-Za-z_]+)\b(.*)", body)
        if not m:
            result[lineno] = tuple(stack)
            continue
        directive, rest = m.group(1), m.group(2).strip()
        if directive in ("if", "ifdef", "ifndef"):
            if directive == "ifdef":
                expr = f"defined({rest})"
            elif directive == "ifndef":
                expr = f"!defined({rest})"
            else:
                expr = rest
            stack.append(expr)
        elif directive == "elif" and stack:
            stack[-1] = rest
        elif directive == "else" and stack:
            stack[-1] = f"!({stack[-1]})"
        elif directive == "endif" and stack:
            stack.pop()
        result[lineno] = tuple(stack)
    return result


def decode_escape(s: str) -> str:
    if not s.startswith("\\"):
        return s
    m = {
        "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
        "v": "\v", "a": "\a", "\\": "\\", "'": "'", '"': '"', "0": "\0",
    }
    return m.get(s[1:], s[1:])


def decode_literal(raw: str) -> str:
    if raw.startswith("L'"):
        raw = raw[1:]
    elif raw.startswith('L"'):
        raw = raw[1:]
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(decode_escape(body[i:i + 2]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)
    line = 1
    col = 1

    def advance(raw: str) -> None:
        nonlocal line, col
        nl = raw.count("\n")
        if nl:
            line += nl
            col = len(raw.rsplit("\n", 1)[-1]) + 1
        else:
            col += len(raw)

    num_re = re.compile(
        r"0[xX][0-9a-fA-F]+[uUlL]*|"
        r"[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[uUlLfF]*"
    )
    multi_ops = [
        ">>=", "<<=", "->", "++", "--", "==", "!=", "<=", ">=", "&&",
        "||", "<<", ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
        "...", "##",
    ]

    while i < n:
        c = text[i]
        if c == "\n":
            advance(c)
            i += 1
            continue
        if c in " \t\r\f\v":
            advance(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            advance(text[start:i])
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            start = i
            while i < n and text[i] != "\n":
                i += 1
            advance(text[start:i])
            continue
        if c == "#":
            # Preprocessor directives are tracked by line conditions.  They
            # are not C declarations or calls.
            start = i
            while i < n:
                if text[i] == "\\" and i + 1 < n and text[i + 1] == "\n":
                    i += 2
                    continue
                if text[i] == "\n":
                    break
                i += 1
            advance(text[start:i])
            continue
        if c == "L" and i + 1 < n and text[i + 1] in "'\"":
            q = text[i + 1]
            start = i
            i += 2
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == q:
                    i += 1
                    break
                i += 1
            raw = text[start:i]
            tokens.append(Token("str" if q == '"' else "chr",
                                decode_literal(raw), raw, line, col, start))
            advance(raw)
            continue
        if c in "'\"":
            q = c
            start = i
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == q:
                    i += 1
                    break
                i += 1
            raw = text[start:i]
            tokens.append(Token("str" if q == '"' else "chr",
                                decode_literal(raw), raw, line, col, start))
            advance(raw)
            continue
        if c.isalpha() or c == "_":
            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            raw = text[start:i]
            tokens.append(Token("id", raw, raw, line, col, start))
            advance(raw)
            continue
        if c.isdigit():
            m = num_re.match(text, i)
            if m:
                raw = m.group(0)
                tokens.append(Token("num", raw, raw, line, col, i))
                advance(raw)
                i = m.end()
                continue
        matched = None
        for op in multi_ops:
            if text.startswith(op, i):
                matched = op
                break
        if matched is None:
            matched = c
        tokens.append(Token("punct", matched, matched, line, col, i))
        advance(matched)
        i += len(matched)
    return tokens


def join_tokens(tokens: Sequence[Token]) -> str:
    """Compact source-like text for evidence, not for re-parsing."""
    out = ""
    prev = ""
    for t in tokens:
        v = t.raw
        if not out:
            out = v
        elif v in (")", "]", ",", ";", ":", "->", ".") or prev in ("(", "[", "->", "."):
            out += v
        elif v == "(" and prev and (prev[-1].isalnum() or prev[-1] in "_*]"):
            out += v
        else:
            out += " " + v
        prev = v
    return out


def find_matching(tokens: Sequence[Token], start: int, open_v: str, close_v: str) -> int | None:
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i].value == open_v:
            depth += 1
        elif tokens[i].value == close_v:
            depth -= 1
            if depth == 0:
                return i
    return None


def find_matching_back(tokens: Sequence[Token], end: int, open_v: str, close_v: str) -> int | None:
    depth = 0
    for i in range(end, -1, -1):
        if tokens[i].value == close_v:
            depth += 1
        elif tokens[i].value == open_v:
            depth -= 1
            if depth == 0:
                return i
    return None


def split_top_level(tokens: Sequence[Token], sep: str = ",") -> list[list[Token]]:
    out: list[list[Token]] = []
    cur: list[Token] = []
    depth = 0
    for t in tokens:
        if t.value in ("(", "[", "{"):
            depth += 1
        elif t.value in (")", "]", "}"):
            depth = max(0, depth - 1)
        if t.value == sep and depth == 0:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# Structural parsing


def looks_like_function(tokens: Sequence[Token], start: int, brace: int) -> bool:
    p = brace - 1
    if p < start or tokens[p].value != ")":
        return False
    q = find_matching_back(tokens, p, "(", ")")
    if q is None or q <= start:
        return False
    name_idx = q - 1
    if tokens[name_idx].kind != "id":
        return False
    if tokens[name_idx].value in KEYWORDS:
        return False
    # A declaration with an initializer is handled before this point.  If a
    # top-level array/struct declaration reaches here, its token before '('
    # would not be a plain function name in practice.
    return True


def scan_to_semicolon(tokens: Sequence[Token], start: int) -> int | None:
    depth = 0
    for i in range(start, len(tokens)):
        v = tokens[i].value
        if v in ("(", "[", "{"):
            depth += 1
        elif v in (")", "]", "}"):
            depth = max(0, depth - 1)
        elif v == ";" and depth == 0:
            return i
    return None


def parse_decl_lhs(tokens: Sequence[Token]) -> tuple[str, str, str | None]:
    if not tokens:
        return "", "", None
    seg = list(tokens)
    while seg and seg[0].value in QUALIFIERS:
        seg.pop(0)
    name_idx = None
    array = None
    for i, t in enumerate(seg):
        if t.value == "[":
            if i > 0 and seg[i - 1].kind == "id":
                name_idx = i - 1
                close = find_matching(seg, i, "[", "]")
                if close is not None:
                    array = join_tokens(seg[i + 1:close])
            break
    if name_idx is None:
        for i in range(len(seg) - 1, -1, -1):
            if seg[i].kind == "id":
                name_idx = i
                break
    if name_idx is None:
        return "", "", array
    name = seg[name_idx].value
    type_tokens = [t for t in seg[:name_idx] if t.value not in QUALIFIERS]
    if len(type_tokens) >= 2 and type_tokens[0].value == "struct":
        typ = "struct " + type_tokens[1].value
    elif type_tokens:
        typ = type_tokens[-1].value
        # Keep "*" out of the type name; the registration table only needs
        # the base interface type.
    else:
        typ = ""
    return typ, name, array


def extract_structs(tokens: Sequence[Token], path: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    i = 0
    while i < len(tokens):
        if tokens[i].value != "struct":
            i += 1
            continue
        if i + 2 >= len(tokens) or tokens[i + 1].kind != "id" or tokens[i + 2].value != "{":
            i += 1
            continue
        name = tokens[i + 1].value
        close = find_matching(tokens, i + 2, "{", "}")
        if close is None:
            break
        body = tokens[i + 3:close]
        fields: list[str] = []
        for member in split_top_level(body, ";"):
            if not member:
                continue
            member_ids = [t for t in member if t.kind == "id"]
            if not member_ids:
                continue
            fp = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", join_tokens(member))
            if fp:
                field = fp.group(1)
            else:
                # Array member: the name is before '['.
                cut = len(member)
                for j, t in enumerate(member):
                    if t.value == "[":
                        cut = j
                        break
                ids = [t.value for t in member[:cut] if t.kind == "id"]
                if not ids:
                    ids = [t.value for t in member_ids]
                field = ids[-1] if ids else ""
            if field and field not in fields:
                fields.append(field)
        if fields:
            result.setdefault(name, fields)
        i = close + 1
    return result


def parse_top_level(
    tokens: Sequence[Token],
    path: str,
    conditions: Sequence[tuple[str, ...]],
) -> tuple[list[Function], list[dict[str, Any]], list[str]]:
    functions: list[Function] = []
    initializers: list[dict[str, Any]] = []
    unsupported: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].value in (";", "}"):
            i += 1
            continue
        start = i
        j = i
        paren = brack = 0
        while j < n:
            v = tokens[j].value
            if v == "(":
                paren += 1
            elif v == ")":
                paren = max(0, paren - 1)
            elif v == "[":
                brack += 1
            elif v == "]":
                brack = max(0, brack - 1)
            elif paren == 0 and brack == 0 and v in (";", "=", "{", "}"):
                break
            j += 1
        if j >= n:
            break
        v = tokens[j].value
        if v == "}":
            i = j + 1
            continue
        if v == ";":
            i = j + 1
            continue
        if v == "=":
            end = scan_to_semicolon(tokens, j + 1)
            if end is None:
                raise ParseError(f"unterminated initializer at line {tokens[start].line}")
            # Find the initializer brace, if any, after the '='.
            brace = None
            for k in range(j + 1, end):
                if tokens[k].value == "{":
                    brace = k
                    break
                if tokens[k].value == ";":
                    break
            typ, name, array = parse_decl_lhs(tokens[start:j])
            init: dict[str, Any] = {
                "type": typ,
                "name": name,
                "array": array,
                "line": tokens[start].line,
                "start": start,
                "eq": j,
                "end": end,
                "brace": brace,
                "body": tokens[brace + 1:find_matching(tokens, brace, "{", "}")]
                if brace is not None and find_matching(tokens, brace, "{", "}") is not None
                else [],
                "conditions": tuple(conditions[tokens[start].line]) if tokens[start].line < len(conditions) else (),
            }
            initializers.append(init)
            i = end + 1
            continue
        if v == "{":
            close = find_matching(tokens, j, "{", "}")
            if close is None:
                raise ParseError(f"unterminated brace at line {tokens[j].line}")
            if looks_like_function(tokens, start, j):
                q = find_matching_back(tokens, j - 1, "(", ")")
                assert q is not None
                name_idx = q - 1
                name = tokens[name_idx].value
                static = any(t.value == "static" for t in tokens[start:name_idx])
                params = join_tokens(tokens[q + 1:j - 1])
                source_end = close + 1
                func = Function(
                    id=f"func:{path}#{name}",
                    name=name,
                    path=path,
                    line=tokens[start].line,
                    end_line=tokens[close].line,
                    static=static,
                    params=params,
                    body=list(tokens[j + 1:close]),
                    source_start=start,
                    source_end=source_end,
                    conditions=tuple(conditions[tokens[start].line])
                    if tokens[start].line < len(conditions) else (),
                    text=join_tokens(tokens[start:source_end]),
                )
                functions.append(func)
            else:
                # enum/struct/union blocks and any other non-function block.
                pass
            i = close + 1
            continue
        unsupported.append(
            f"{path}:{tokens[start].line}: unsupported top-level token {tokens[start].raw!r}"
        )
        i = j + 1
    return functions, initializers, unsupported


# ---------------------------------------------------------------------------
# Calls, switches and command text


def call_args(tokens: Sequence[Token], open_idx: int) -> list[list[Token]]:
    close = find_matching(tokens, open_idx, "(", ")")
    if close is None:
        return []
    return split_top_level(tokens[open_idx + 1:close], ",")


def backward_expr(tokens: Sequence[Token], idx: int, limit: int = 10) -> str:
    pieces: list[Token] = []
    j = idx
    while j >= 0 and len(pieces) < limit:
        v = tokens[j].value
        if v in (";", "{", "}", ",", "=", "?", ":"):
            break
        pieces.append(tokens[j])
        if v in ("(",):
            break
        j -= 1
    pieces.reverse()
    return join_tokens(pieces)


def extract_calls(
    tokens: Sequence[Token],
    start: int,
    end: int,
    function: Function,
) -> list[Call]:
    calls: list[Call] = []
    i = start
    while i < end:
        t = tokens[i]
        # Form (*expr)(...)
        if t.value == "(" and i + 1 < end and tokens[i + 1].value == "*":
            close = find_matching(tokens, i, "(", ")")
            if close is not None and close + 1 < end and tokens[close + 1].value == "(":
                expr = join_tokens(tokens[i + 2:close])
                field = None
                for k in range(close - 1, i, -1):
                    if tokens[k].kind == "id" and tokens[k - 1].value in ("->", "."):
                        field = tokens[k].value
                        break
                calls.append(Call("pointer", expr, field, "(*" + expr + ")",
                                  t.line, t.offset))
                i = close + 2
                continue
        if t.kind == "id" and i + 1 < end and tokens[i + 1].value == "(":
            name = t.value
            if name in NON_CALL_IDENTIFIERS:
                i += 1
                continue
            # Plan 9 macros are conventionally all-uppercase and are often
            # written in call form (DPRINT, BUSBDF, PACK64, ...).  There are no
            # all-uppercase function definitions in the scanned kernel tree.
            if len(name) > 1 and name.isupper():
                i += 1
                continue
            prev = tokens[i - 1].value if i > start else ""
            if prev in ("->", "."):
                expr = backward_expr(tokens, i)
                calls.append(Call("member", name, name, expr, t.line, t.offset))
                i += 1
                continue
            if name in function.local_function_pointers:
                calls.append(Call("local-pointer", name, None, name, t.line, t.offset))
                i += 1
                continue
            args = call_args(tokens, i + 1)
            args_text = [join_tokens(a) for a in args]
            calls.append(Call("direct", name, None, name, t.line, t.offset, args_text))
            i += 1
            continue
        i += 1
    return calls


def extract_switches(tokens: Sequence[Token], start: int, end: int) -> list[Switch]:
    switches: list[Switch] = []
    i = start
    while i < end:
        if tokens[i].value != "switch":
            i += 1
            continue
        if i + 1 >= end or tokens[i + 1].value != "(":
            i += 1
            continue
        pclose = find_matching(tokens, i + 1, "(", ")")
        if pclose is None or pclose + 1 >= end or tokens[pclose + 1].value != "{":
            i += 1
            continue
        bclose = find_matching(tokens, pclose + 1, "{", "}")
        if bclose is None:
            i += 1
            continue
        condition = join_tokens(tokens[i + 2:pclose])
        body_start = pclose + 2
        body_end = bclose
        labels: list[tuple[str, int, int]] = []
        j = body_start
        while j < body_end:
            v = tokens[j].value
            # Skip nested switch bodies here; they are parsed as their own
            # Switch objects.  Case labels may legally sit inside ordinary
            # blocks within this switch (for example `if(0){ case X: ... }`).
            if v == "switch" and j + 1 < body_end and tokens[j + 1].value == "(":
                pclose = find_matching(tokens, j + 1, "(", ")")
                if pclose is not None and pclose + 1 < body_end and tokens[pclose + 1].value == "{":
                    nclose = find_matching(tokens, pclose + 1, "{", "}")
                    if nclose is not None:
                        j = nclose + 1
                        continue
            if v in ("case", "default"):
                label_line = tokens[j].line
                k = j + 1
                if v == "default":
                    label = "default"
                else:
                    label_tokens: list[Token] = []
                    while k < body_end:
                        if tokens[k].value == ":":
                            break
                        if tokens[k].value in ("{", "}"):
                            break
                        label_tokens.append(tokens[k])
                        k += 1
                    label = join_tokens(label_tokens)
                while k < body_end and tokens[k].value != ":":
                    k += 1
                if k < body_end and tokens[k].value == ":":
                    labels.append((label, label_line, k + 1))
                j = k
            j += 1
        cases: list[CaseLabel] = []
        for idx, (label, line, case_start) in enumerate(labels):
            case_end = labels[idx + 1][2] - 1 if idx + 1 < len(labels) else body_end
            # The next label's start includes its `case` keyword; trim back to
            # the keyword itself so the previous case does not claim it.
            if idx + 1 < len(labels):
                # find the next `case`/`default` token at or before case_end
                k = case_start
                while k < case_end and tokens[k].value not in ("case", "default"):
                    k += 1
                case_end = k
            cases.append(CaseLabel(label, line, case_start, case_end))
        switches.append(Switch(condition, tokens[i].line, body_start, body_end, cases))
        # Continue scanning inside the switch body so nested switches (for
        # example a Qid case containing a Cmdtab index switch) are captured.
        i += 1
    return switches


def extract_if_qid_branches(tokens: Sequence[Token], start: int, end: int) -> list[CaseLabel]:
    """Recognise simple `if(c->qid... == Qfoo)` branches as file operations."""
    out: list[CaseLabel] = []
    i = start
    while i < end:
        if tokens[i].value != "if" or i + 1 >= end or tokens[i + 1].value != "(":
            i += 1
            continue
        close = find_matching(tokens, i + 1, "(", ")")
        if close is None or close + 1 >= end:
            i += 1
            continue
        cond = join_tokens(tokens[i + 2:close])
        low = cond.lower()
        if "qid" not in low or "==" not in cond or "!=" in cond:
            i += 1
            continue
        label = None
        for t in tokens[i + 2:close]:
            if t.kind == "id" and t.value.startswith("Q"):
                label = t.value
            elif t.kind == "num":
                label = t.value
        if not label:
            i += 1
            continue
        body_start = close + 1
        if tokens[body_start].value == "{":
            body_end = find_matching(tokens, body_start, "{", "}")
            if body_end is None:
                i += 1
                continue
            op_start, op_end = body_start + 1, body_end
        else:
            op_start = body_start
            k = body_start
            depth = 0
            while k < end:
                if tokens[k].value in ("(", "[", "{"):
                    depth += 1
                elif tokens[k].value in (")", "]", "}"):
                    depth = max(0, depth - 1)
                if tokens[k].value == ";" and depth == 0:
                    break
                k += 1
            if k >= end:
                i += 1
                continue
            op_end = k + 1
        out.append(CaseLabel(label, tokens[i].line, op_start, op_end))
        i = close + 1
    return out


def extract_local_function_pointers(tokens: Sequence[Token], start: int, end: int) -> set[str]:
    names: set[str] = set()
    for i in range(start, end):
        if tokens[i].value != "(":
            continue
        close = find_matching(tokens, i, "(", ")")
        if close is None or close >= end:
            continue
        inner = tokens[i + 1:close]
        if len(inner) >= 2 and inner[0].value == "*" and inner[1].kind == "id":
            names.add(inner[1].value)
    # A local variable assigned from a function-pointer field is also an
    # indirect call when it is later called.  Only retain names that actually
    # appear in call position, so ordinary scalar assignments stay scalar.
    assigned: set[str] = set()
    for i in range(start, end - 2):
        if tokens[i].kind != "id" or tokens[i + 1].value != "=":
            continue
        j = i + 2
        has_member = False
        while j < end and tokens[j].value not in (";", ","):
            if tokens[j].value in ("->", "."):
                has_member = True
            j += 1
        if has_member:
            assigned.add(tokens[i].value)
    for name in assigned:
        for i in range(start, end - 1):
            if tokens[i].value == name and tokens[i + 1].value == "(":
                names.add(name)
                break
    return names


def extract_manual_commands(tokens: Sequence[Token], start: int, end: int) -> list[tuple[str, int]]:
    commands: list[tuple[str, int]] = []
    for i in range(start, end):
        if tokens[i].kind != "id" or tokens[i].value not in ("strcmp", "strncmp", "cistrcmp"):
            continue
        if i + 1 >= end or tokens[i + 1].value != "(":
            continue
        args = call_args(tokens, i + 1)
        if len(args) < 2:
            continue
        left = re.sub(r"\s+", "", join_tokens(args[0]))
        if "f[0]" not in left and not re.search(r"(^|->)f\[0\]$", left):
            continue
        right = args[1]
        if len(right) == 1 and right[0].kind == "str":
            commands.append((right[0].value, tokens[i].line))
    return commands


# ---------------------------------------------------------------------------
# Build configuration


def parse_target_file(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("(") and val.endswith(")"):
            data[key] = [x for x in val[1:-1].split() if x]
        else:
            data[key] = val
    return data


def parse_mk_assignment(text: str, name: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        if not capture:
            if re.match(rf"^{re.escape(name)}\s*=\s*\\?\s*$", line):
                capture = True
                continue
            if re.match(rf"^{re.escape(name)}\s*=", line):
                # Single-line assignment.
                rest = line.split("=", 1)[1]
                out.extend(re.findall(r"(?<![\w.$])([A-Za-z0-9_.]+)\.\$O", rest))
                continue
        else:
            if not line.strip():
                break
            out.extend(re.findall(r"(?<![\w.$])([A-Za-z0-9_.]+)\.\$O", line))
            if not line.rstrip().endswith("\\"):
                break
    return out


def parse_config_sections(text: str) -> tuple[list[str], list[str], list[str]]:
    """Return (object stems, bootdir entries, notes) using mkdevlist rules."""
    stems: list[str] = []
    bootdir: list[str] = []
    notes: list[str] = []
    section = None
    isdev = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            fields = raw.split()
            section = fields[0]
            isdev = section.startswith("dev")
            if section == "bootdir":
                for field in fields[1:]:
                    bootdir.append(field)
            continue
        if section not in ("dev", "link", "misc", "ip"):
            if section == "bootdir":
                fields = raw.split()
                if len(fields) >= 2:
                    bootdir.append(fields[1])
                elif fields:
                    bootdir.append(fields[0])
            continue
        fields = raw.split()
        if not fields:
            continue
        if isdev:
            stems.append("dev" + fields[0])
            fields = fields[1:]
        for field in fields:
            if re.match(r"^[+=-].*", field):
                continue
            stems.append(field)
    # Deduplicate, keep first occurrence then sort for deterministic output.
    stems = sorted(set(stems))
    bootdir = [x for x in bootdir if x]
    return stems, bootdir, notes


def parse_config_sections_exact(text: str) -> list[dict[str, Any]]:
    """Return config section rows for documentation/debugging."""
    rows: list[dict[str, Any]] = []
    section = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            section = raw.split()[0]
            rows.append({"section": section, "entries": []})
            continue
        if section is None or not rows:
            continue
        rows[-1]["entries"].append(raw.strip())
    return rows


# ---------------------------------------------------------------------------
# Analyser


def slug(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^A-Za-z0-9_.+-]+", "-", text)
    return text.strip("-") or "x"


def file_kind(path: Path) -> str:
    name = path.name
    if name.endswith(".c"):
        return "c"
    if name.endswith(".h"):
        return "header"
    if name.endswith(".s"):
        return "assembly"
    if name in ("mkfile",) or name.startswith("mk") or name.endswith(".rc"):
        return "build-tool"
    if path.suffix == "":
        return "config"
    return "other"


def expr_info(tokens: Sequence[Token]) -> dict[str, Any]:
    text = join_tokens(tokens)
    info: dict[str, Any] = {"text": text, "symbol": None, "nil": False, "literal": None}
    if not tokens or text in ("nil", "0", "NULL"):
        info["nil"] = True
        return info
    if len(tokens) == 1 and tokens[0].kind in ("str", "chr"):
        info["literal"] = tokens[0].value
        return info
    ids = [t.value for t in tokens if t.kind == "id" and t.value not in KEYWORDS]
    if ids:
        # A cast may contain type identifiers; the function/value identifier is
        # conventionally the last non-keyword identifier in these initialisers.
        info["symbol"] = ids[-1]
    return info


def char_value(tokens: Sequence[Token]) -> str | None:
    for t in tokens:
        if t.kind == "chr":
            return t.value
    return None


def is_service_call(name: str) -> bool:
    """Kernel helpers and logging macros that must not be followed as devices."""
    return name in KERNEL_SERVICES or name.endswith("print")


class Analyzer:
    def __init__(self, root: Path):
        self.root = root
        self.kernel = root / KERNEL_REL
        self.files: list[SourceFile] = []
        self.file_by_path: dict[str, SourceFile] = {}
        self.struct_fields: dict[str, list[str]] = dict(FALLBACK_STRUCTS)
        self.struct_sources: dict[str, dict[str, Any]] = {}
        self.functions: list[Function] = []
        self.function_by_id: dict[str, Function] = {}
        self.global_by_name: dict[str, list[Function]] = defaultdict(list)
        self.configs: list[dict[str, Any]] = []
        self.registration_records: list[dict[str, Any]] = []
        self.interface_candidates: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.initializer_records: list[dict[str, Any]] = []
        self.dirtab_records: list[dict[str, Any]] = []
        self.cmdtab_records: list[dict[str, Any]] = []
        self.operations: list[dict[str, Any]] = []
        self.chains: dict[str, dict[str, Any]] = {}
        self._chain_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.native_records: list[dict[str, Any]] = []
        self.representative: list[dict[str, Any]] = []
        self.parse_issues: list[dict[str, Any]] = []
        self.unsupported_declarations: list[dict[str, Any]] = []
        self.source_revision: dict[str, Any] = {}
        self.fingerprint = ""

    # -- source and parsing -------------------------------------------------

    def discover_files(self) -> None:
        if not self.kernel.is_dir():
            raise SystemExit(f"kernel tree not found: {self.kernel}")
        for p in sorted(self.kernel.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            kind = file_kind(p)
            raw = p.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            masked = mask_comments(text)
            conditions = compute_line_conditions(masked)
            includes = re.findall(r'^\s*#\s*include\s+[<"]([^>"]+)[>"]', masked, re.M)
            sf = SourceFile(
                path=rel,
                abs_path=p,
                text=text,
                masked=masked,
                kind=kind,
                conditions=conditions,
                includes=includes,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
            self.files.append(sf)
            self.file_by_path[rel] = sf
        # Fingerprint the complete scanned source tree.
        h = hashlib.sha256()
        for sf in self.files:
            h.update(sf.path.encode("utf-8"))
            h.update(b"\0")
            h.update(sf.sha256.encode("ascii"))
            h.update(b"\n")
        self.fingerprint = h.hexdigest()
        self.source_revision = self._git_revision()

    def _git_revision(self) -> dict[str, Any]:
        try:
            commit = subprocess.check_output(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            status = subprocess.check_output(
                ["git", "-C", str(self.root), "status", "--porcelain", "--", KERNEL_REL],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            return {"commit": commit, "kernel_tree_dirty": bool(status)}
        except (OSError, subprocess.CalledProcessError):
            return {"commit": None, "kernel_tree_dirty": None}

    def parse_all(self) -> None:
        for sf in self.files:
            if sf.kind not in ("c", "header"):
                continue
            try:
                sf.tokens = tokenize(sf.text)
                sf.structs = extract_structs(sf.tokens, sf.path)
                for name, fields in sf.structs.items():
                    old = self.struct_fields.get(name)
                    if old is None or len(fields) > len(old):
                        self.struct_fields[name] = fields
                        self.struct_sources[name] = {"path": sf.path, "line": None}
                if sf.kind == "c":
                    funcs, inits, unsupported = parse_top_level(
                        sf.tokens, sf.path, sf.conditions
                    )
                    sf.functions = funcs
                    sf.initializers = inits
                    for item in unsupported:
                        self.unsupported_declarations.append({
                            "path": sf.path,
                            "detail": item,
                            "reason": "unsupported top-level declaration",
                        })
                    for f in funcs:
                        f.local_function_pointers = extract_local_function_pointers(
                            f.body, 0, len(f.body)
                        )
                        f.local_function_pointers.update(
                            re.findall(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", f.params)
                        )
                        f.calls = extract_calls(f.body, 0, len(f.body), f)
                        f.switches = extract_switches(f.body, 0, len(f.body))
                        f.text = join_tokens(sf.tokens[f.source_start:f.source_end])
                    for init in inits:
                        init["path"] = sf.path
                        self.initializer_records.append(init)
                    self.functions.extend(funcs)
            except ParseError as exc:
                sf.parse_status = "error"
                sf.parse_error = str(exc)
                m = re.search(r"line (\d+)", str(exc))
                sf.parse_error_line = int(m.group(1)) if m else None
                self.parse_issues.append({
                    "path": sf.path,
                    "status": "error",
                    "reason": str(exc),
                    "line": sf.parse_error_line,
                })
            except Exception as exc:  # keep the rest of the tree analysable
                sf.parse_status = "error"
                sf.parse_error = f"{type(exc).__name__}: {exc}"
                self.parse_issues.append({
                    "path": sf.path,
                    "status": "error",
                    "reason": sf.parse_error,
                    "line": None,
                })
        # Stable function identifiers even if two definitions share a name in
        # one file (not expected, but do not silently merge them).
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for f in self.functions:
            counts[(f.path, f.name)] += 1
        for f in self.functions:
            if counts[(f.path, f.name)] > 1:
                f.id = f"{f.id}@{f.line}"
            self.function_by_id[f.id] = f
            self.global_by_name[f.name].append(f)
        for name in self.global_by_name:
            self.global_by_name[name].sort(key=lambda f: (f.path, f.line))

    # -- build configuration ------------------------------------------------

    def discover_configs(self) -> None:
        targets: dict[str, dict[str, Any]] = {}
        tdir = self.root / "tools" / "targets"
        if tdir.is_dir():
            for p in sorted(tdir.iterdir()):
                if p.is_file() and p.name != "README":
                    targets[p.name] = parse_target_file(p)

        config_specs: list[dict[str, Any]] = []
        if targets:
            for tname, target in sorted(targets.items()):
                kdir = target.get("kdir")
                if not kdir:
                    continue
                mkfile = self.kernel / kdir / "mkfile"
                if not mkfile.is_file():
                    config_specs.append({
                        "name": target.get("kconf") or kdir,
                        "arch": kdir,
                        "target": tname,
                        "status": target.get("status", "unknown"),
                        "mkfile": None,
                        "config_path": None,
                        "roots": [],
                        "skip_reason": "target source tree is absent",
                    })
                    continue
                text = mkfile.read_text(encoding="utf-8", errors="replace")
                conflist = re.search(r"^CONFLIST\s*=\s*(.+)$", text, re.M)
                confs = conflist.group(1).split() if conflist else []
                if target.get("kconf") and target["kconf"] not in confs:
                    confs.insert(0, target["kconf"])
                if target.get("testkconf") and target["testkconf"] not in confs:
                    confs.append(target["testkconf"])
                for conf in confs:
                    kind = "normal-amd64" if (
                        tname == "amd64" and conf == target.get("kconf")
                    ) else "test-only" if conf == target.get("testkconf") else "other"
                    config_specs.append({
                        "name": conf,
                        "arch": kdir,
                        "target": tname,
                        "status": target.get("status", "unknown"),
                        "mkfile": mkfile,
                        "config_path": self.kernel / kdir / conf,
                        "roots": [self.kernel / r for r in target.get("ksrc", [])],
                        "kind": kind,
                        "conflist": confs,
                    })
        else:
            for mkfile in sorted(self.kernel.glob("*/mkfile")):
                text = mkfile.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^CONFLIST\s*=\s*(.+)$", text, re.M)
                if not m:
                    continue
                for conf in m.group(1).split():
                    config_specs.append({
                        "name": conf,
                        "arch": mkfile.parent.name,
                        "target": None,
                        "status": "unknown",
                        "mkfile": mkfile,
                        "config_path": mkfile.parent / conf,
                        "roots": [mkfile.parent, self.kernel / "port", self.kernel / "ip"],
                        "kind": "other",
                    })

        # Deduplicate config names, keeping the first specification.
        seen: set[str] = set()
        for spec in config_specs:
            if spec["name"] in seen:
                continue
            seen.add(spec["name"])
            self.configs.append(self._resolve_config(spec))
        self.configs.sort(key=lambda c: ({
            "normal-amd64": 0, "test-only": 1, "other": 2
        }.get(c.get("kind", "other"), 3), c["name"]))

    def _resolve_config(self, spec: dict[str, Any]) -> dict[str, Any]:
        cfg: dict[str, Any] = {
            "name": spec["name"],
            "arch": spec["arch"],
            "target": spec.get("target"),
            "status": spec.get("status", "unknown"),
            "kind": spec.get("kind", "other"),
            "config_path": spec["config_path"].relative_to(self.root).as_posix()
            if spec.get("config_path") else None,
            "mkfile": spec["mkfile"].relative_to(self.root).as_posix()
            if spec.get("mkfile") else None,
            "roots": [p.relative_to(self.root).as_posix() for p in spec.get("roots", [])
                      if p.is_dir()],
            "object_stems": [],
            "active_files": [],
            "unresolved_objects": [],
            "shadowed_objects": [],
            "bootdir": [],
            "whole_archives": [],
            "notes": [],
        }
        if spec.get("skip_reason"):
            cfg["notes"].append(spec["skip_reason"])
            cfg["unresolved_objects"].append({"stem": "*", "reason": spec["skip_reason"]})
            return cfg
        config_path: Path = spec["config_path"]
        mkfile: Path = spec["mkfile"]
        roots: list[Path] = []
        for p in spec.get("roots", []):
            if p.is_dir() and p not in roots:
                roots.append(p)
        # The architecture directory is always searchable first.
        arch_root = mkfile.parent
        if arch_root not in roots:
            roots.insert(0, arch_root)
        cfg["roots"] = [p.relative_to(self.root).as_posix() for p in roots]

        text = ""
        if config_path.is_file():
            text = config_path.read_text(encoding="utf-8", errors="replace")
        else:
            cfg["notes"].append("configuration file is absent")
            cfg["unresolved_objects"].append({
                "stem": "*", "reason": "configuration file is absent",
            })
        stems, bootdir, _ = parse_config_sections(text)
        cfg["bootdir"] = sorted(set(bootdir))

        mktext = mkfile.read_text(encoding="utf-8", errors="replace")
        extra: list[str] = []
        extra.extend(parse_mk_assignment(mktext, "PORT"))
        extra.extend(parse_mk_assignment(mktext, "OBJ"))
        for m in re.finditer(r"(?<![\w.$])([A-Za-z0-9_.]+)\.\$O", mktext):
            extra.append(m.group(1))
        for m in re.finditer(r"(?<![\w.$])([A-Za-z0-9_.]+)\.(?:c|s)\b", mktext):
            extra.append(m.group(1))
        # GEFS is an archive of every .c in a sibling directory in the pc64
        # mkfile.  Mark the whole archive, not a hand-picked file list.
        if "gefs.a$O" in mktext:
            archive = (mkfile.parent / ".." / "gefs").resolve()
            if archive.is_dir():
                cfg["whole_archives"].append(archive.relative_to(self.root).as_posix())
                for p in sorted(archive.glob("*.c")):
                    rel = p.relative_to(self.root).as_posix()
                    if rel not in cfg["active_files"]:
                        cfg["active_files"].append(rel)
        stems = sorted(set(stems + extra))
        cfg["object_stems"] = stems

        for stem in stems:
            found: list[Path] = []
            for root in roots:
                for suffix in (".c", ".s"):
                    candidate = root / (stem + suffix)
                    if candidate.is_file():
                        found.append(candidate)
                        break
            if found:
                chosen = found[0]
                rel = chosen.relative_to(self.root).as_posix()
                if rel not in cfg["active_files"]:
                    cfg["active_files"].append(rel)
                if len(found) > 1:
                    cfg["shadowed_objects"].append({
                        "stem": stem,
                        "chosen": rel,
                        "shadowed": [p.relative_to(self.root).as_posix() for p in found[1:]],
                    })
            else:
                # Ignore obvious generated/expanded variables that the regex
                # may still have caught.  Everything else is an unresolved
                # build inclusion and is reported.
                if stem in ("root", "rootc", "CONF.root", "CONF.rootc",
                            "CONF", "O", "c", "s", "a") or stem.isdigit() or "$" in stem:
                    continue
                cfg["unresolved_objects"].append({
                    "stem": stem,
                    "reason": "no source file found in the configuration's search roots",
                })
        cfg["active_files"] = sorted(set(cfg["active_files"]))
        cfg["unresolved_objects"].sort(key=lambda x: (x["stem"], x["reason"]))
        cfg["shadowed_objects"].sort(key=lambda x: x["stem"])
        return cfg

    def normal_config_name(self) -> str:
        for cfg in self.configs:
            if cfg.get("kind") == "normal-amd64":
                return cfg["name"]
        for cfg in self.configs:
            if cfg.get("kind") == "other":
                return cfg["name"]
        return self.configs[0]["name"] if self.configs else "pc64"

    def file_build_map(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {sf.path: {} for sf in self.files}
        for cfg in self.configs:
            active = set(cfg.get("active_files", []))
            roots = cfg.get("roots", [])
            for sf in self.files:
                if sf.kind not in ("c", "header", "assembly"):
                    out[sf.path][cfg["name"]] = "not-applicable"
                elif sf.path in active:
                    out[sf.path][cfg["name"]] = "active"
                elif sf.kind == "header" and any(sf.path.startswith(r + "/") for r in roots):
                    out[sf.path][cfg["name"]] = "support"
                elif any(sf.path.startswith(r + "/") for r in roots):
                    out[sf.path][cfg["name"]] = "not-selected"
                else:
                    out[sf.path][cfg["name"]] = "outside-config-roots"
        return out

    def active_configs_for(self, path: str) -> list[str]:
        return [c["name"] for c in self.configs if path in c.get("active_files", [])]

    # -- registrations ------------------------------------------------------

    def parse_struct_initializer(self, init: dict[str, Any]) -> dict[str, dict[str, Any]]:
        fields = self.struct_fields.get(init["type"], [])
        elements = split_top_level(init.get("body", []), ",")
        mapping: dict[str, dict[str, Any]] = {}
        pos = 0
        for el in elements:
            if not el:
                continue
            if len(el) >= 3 and el[0].value == "." and el[1].kind == "id" and el[2].value == "=":
                field = el[1].value
                mapping[field] = expr_info(el[3:])
                if field in fields:
                    pos = max(pos, fields.index(field) + 1)
            else:
                while pos < len(fields) and fields[pos] in mapping:
                    pos += 1
                field = fields[pos] if pos < len(fields) else f"arg{pos}"
                mapping[field] = expr_info(el)
                pos += 1
        return mapping

    def flat_records(self, init: dict[str, Any], width: int) -> tuple[list[list[Token]], str | None]:
        elements = split_top_level(init.get("body", []), ",")
        # Some tables use { ... } around each record; accept both forms.
        if elements and all(e and e[0].value == "{" and e[-1].value == "}" for e in elements):
            inner: list[list[Token]] = []
            for e in elements:
                inner.extend(split_top_level(e[1:-1], ","))
            elements = inner
        if len(elements) % width != 0:
            return elements, f"record count {len(elements)} is not a multiple of {width}"
        return elements, None

    def parse_dirtab(self, init: dict[str, Any]) -> dict[str, Any]:
        elements, error = self.flat_records(init, 4)
        entries: list[dict[str, Any]] = []
        if error is None:
            for i in range(0, len(elements), 4):
                group = elements[i:i + 4]
                name = group[0][0].value if group[0] and group[0][0].kind == "str" else join_tokens(group[0])
                qid_tokens = group[1]
                qid_expr = join_tokens(qid_tokens)
                qid_symbol = None
                for t in qid_tokens:
                    if t.kind == "id" and t.value != "Qid":
                        qid_symbol = t.value
                        break
                line = group[0][0].line if group[0] else init["line"]
                sf = self.file_by_path.get(init["path"])
                cond = tuple(sf.conditions[line]) if (sf and line < len(sf.conditions)) else tuple(init["conditions"])
                entries.append({
                    "name": name,
                    "qid": qid_expr,
                    "qid_symbol": qid_symbol,
                    "length": join_tokens(group[2]),
                    "perm": join_tokens(group[3]),
                    "line": line,
                    "conditions": list(cond),
                })
        rec = {
            "id": f"dirtab:{init['path']}#{init['name']}",
            "path": init["path"],
            "name": init["name"],
            "line": init["line"],
            "array": init.get("array"),
            "conditions": list(init["conditions"]),
            "entries": entries,
            "status": "resolved" if error is None else "unresolved",
            "reason": error,
        }
        self.dirtab_records.append(rec)
        return rec

    def parse_cmdtab(self, init: dict[str, Any]) -> dict[str, Any]:
        elements, error = self.flat_records(init, 3)
        entries: list[dict[str, Any]] = []
        if error is None:
            for i in range(0, len(elements), 3):
                group = elements[i:i + 3]
                index = join_tokens(group[0])
                cmd = group[1][0].value if group[1] and group[1][0].kind == "str" else join_tokens(group[1])
                narg = join_tokens(group[2])
                line = group[0][0].line if group[0] else init["line"]
                sf = self.file_by_path.get(init["path"])
                cond = tuple(sf.conditions[line]) if (sf and line < len(sf.conditions)) else tuple(init["conditions"])
                entries.append({
                    "index": index,
                    "cmd": cmd,
                    "narg": narg,
                    "line": line,
                    "conditions": list(cond),
                })
        rec = {
            "id": f"cmdtab:{init['path']}#{init['name']}",
            "path": init["path"],
            "name": init["name"],
            "line": init["line"],
            "conditions": list(init["conditions"]),
            "entries": entries,
            "status": "resolved" if error is None else "unresolved",
            "reason": error,
        }
        self.cmdtab_records.append(rec)
        return rec

    def build_registrations(self) -> None:
        # Dirtab/Cmdtab first: they are data, not lower-level interfaces.
        for init in self.initializer_records:
            if init["type"] == "Dirtab":
                self.parse_dirtab(init)
            elif init["type"] == "Cmdtab":
                self.parse_cmdtab(init)

        for init in self.initializer_records:
            typ = init["type"]
            if typ not in ("Dev", "SDifc", "PhysUart", "VGAdev", "VGAcur", "PCArch", "ADifc"):
                continue
            mapping = self.parse_struct_initializer(init)
            record_id = f"reg:{typ}:{init['path']}#{init['name']}"
            if typ == "Dev":
                dc = None
                if "dc" in mapping:
                    dc = mapping["dc"].get("literal")
                    if dc is None:
                        first = split_top_level(init["body"], ",")
                        if first:
                            dc = char_value(first[0])
                name = mapping.get("name", {}).get("literal") or init["name"]
                callbacks = {
                    k: v for k, v in mapping.items() if k not in ("dc", "name")
                }
                rec = {
                    "id": record_id,
                    "type": "Dev",
                    "name": name,
                    "identifier": init["name"],
                    "dc": dc,
                    "path": init["path"],
                    "line": init["line"],
                    "conditions": list(init["conditions"]),
                    "fields": mapping,
                    "callbacks": callbacks,
                    "active_configs": self.active_configs_for(init["path"]),
                }
            else:
                name = mapping.get("name", {}).get("literal") or init["name"]
                callbacks = {
                    k: v for k, v in mapping.items() if k not in ("name",)
                }
                rec = {
                    "id": record_id,
                    "type": typ,
                    "name": name,
                    "identifier": init["name"],
                    "path": init["path"],
                    "line": init["line"],
                    "conditions": list(init["conditions"]),
                    "fields": mapping,
                    "callbacks": callbacks,
                    "active_configs": self.active_configs_for(init["path"]),
                }
            self.registration_records.append(rec)
            for field, value in rec["callbacks"].items():
                sym = value.get("symbol")
                if sym and not value.get("nil"):
                    self.interface_candidates[typ][field].append(sym)
        for typ in self.interface_candidates:
            for field in self.interface_candidates[typ]:
                self.interface_candidates[typ][field] = sorted(
                    set(self.interface_candidates[typ][field])
                )

        self._add_ether_cards()
        self._add_hci_linkages()
        self.registration_records.sort(key=lambda r: (r["path"], r["line"], r["id"]))

    def _add_ether_cards(self) -> None:
        for f in self.functions:
            for call in f.calls:
                if call.kind != "direct" or call.name != "addethercard":
                    continue
                args = call.args_text
                if len(args) < 2:
                    continue
                m = re.match(r'"(.*)"$', args[0].strip())
                if not m:
                    continue
                card = m.group(1)
                pnp = args[1].strip()
                pnp_func = next(
                    (x for x in self.global_by_name.get(pnp, []) if x.path == f.path),
                    None,
                )
                fields: dict[str, dict[str, Any]] = {}
                if pnp_func is not None:
                    fields = self._collect_assignments(pnp_func, depth=1)
                callbacks = {
                    k: v for k, v in fields.items()
                    if k in ("attach", "transmit", "ctl", "power", "shutdown")
                }
                rec = {
                    "id": f"reg:Ether:{f.path}#{card}",
                    "type": "Ether",
                    "name": card,
                    "identifier": card,
                    "path": f.path,
                    "line": call.line,
                    "conditions": list(f.conditions),
                    "fields": fields,
                    "callbacks": callbacks,
                    "active_configs": self.active_configs_for(f.path),
                    "registration_call": "addethercard",
                    "pnp": pnp,
                }
                self.registration_records.append(rec)
                for field, value in callbacks.items():
                    sym = value.get("symbol")
                    if sym:
                        self.interface_candidates["Ether"][field].append(sym)
        for field in self.interface_candidates["Ether"]:
            self.interface_candidates["Ether"][field] = sorted(
                set(self.interface_candidates["Ether"][field])
            )

    def _collect_assignments(self, func: Function, depth: int = 1) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        body = func.body
        for i in range(len(body) - 3):
            if body[i].value in ("->", ".") and body[i + 1].kind == "id":
                field = body[i + 1].value
                if body[i + 2].value == "=" and body[i + 3].kind == "id":
                    out[field] = expr_info(body[i + 3:i + 4])
        if depth > 0:
            for call in func.calls:
                if call.kind != "direct":
                    continue
                callee = self.resolve(call, func)[0]
                if callee is not None and callee.path == func.path and callee.id != func.id:
                    for k, v in self._collect_assignments(callee, depth - 1).items():
                        out.setdefault(k, v)
        return out


    def _add_hci_linkages(self) -> None:
        """USB HCI implementations are installed by *linkage() functions."""
        fields_wanted = {
            "init", "interrupt", "epopen", "epstop", "epclose", "epread",
            "epwrite", "seprintep", "devclose", "portenable", "portreset",
            "bhportreset", "portpower", "portstatus", "shutdown", "debug",
        }
        for f in self.functions:
            if not f.name.endswith("linkage"):
                continue
            fields = self._collect_assignments(f, depth=0)
            callbacks = {
                k: v for k, v in fields.items()
                if k in fields_wanted and v.get("symbol")
            }
            if len(callbacks) < 3:
                continue
            name = (fields.get("type") or {}).get("literal") or f.name
            rec = {
                "id": f"reg:Hciimpl:{f.path}#{f.name}",
                "type": "Hciimpl",
                "name": name,
                "identifier": f.name,
                "path": f.path,
                "line": f.line,
                "conditions": list(f.conditions),
                "fields": fields,
                "callbacks": callbacks,
                "active_configs": self.active_configs_for(f.path),
                "registration_call": "linkage assignment",
            }
            self.registration_records.append(rec)
            for field, value in callbacks.items():
                sym = value.get("symbol")
                if sym:
                    self.interface_candidates["Hciimpl"][field].append(sym)
        for field in self.interface_candidates["Hciimpl"]:
            self.interface_candidates["Hciimpl"][field] = sorted(
                set(self.interface_candidates["Hciimpl"][field])
            )

    # -- call graph and chains ---------------------------------------------

    def resolve(self, call: Call, from_func: Function) -> tuple[Function | None, str | None]:
        if call.kind != "direct":
            return None, "indirect"
        candidates = self.global_by_name.get(call.name, [])
        local = [f for f in candidates if f.path == from_func.path]
        if len(local) == 1:
            return local[0], None
        if len(local) > 1:
            return None, "ambiguous-local-symbol"
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, "ambiguous-global-symbol"
        return None, "external"

    def calls_in_scope(self, func: Function, start: int, end: int) -> list[Call]:
        return extract_calls(func.body, start, end, func)

    def indirect_candidates(self, call: Call) -> list[str]:
        expr = (call.expr or "").lower()
        field = call.field or call.name
        typ = None
        if "ifc" in expr:
            typ = "SDifc"
        elif "phys" in expr:
            typ = "PhysUart"
        elif "ether" in expr or "edev" in expr:
            typ = "Ether"
        elif "hp" in expr or "hci" in expr:
            typ = "Hciimpl"
        elif re.search(r"(^|[^a-z])cur($|[^a-z])", expr):
            typ = "VGAcur"
        elif "scr" in expr and "dev" in expr:
            typ = "VGAdev"
        elif "devtab" in expr or "->dev" in expr or re.search(r"(^|[^a-z])dev($|[^a-z])", expr):
            typ = "Dev"
        if typ is not None:
            cands = self.interface_candidates.get(typ, {}).get(field, [])
            if cands:
                return cands
        all_cands: set[str] = set()
        for t in self.interface_candidates.values():
            all_cands.update(t.get(field, []))
        return sorted(all_cands)

    def classify_external(self, name: str) -> str:
        if name in HARDWARE_CALLS or re.match(r"^(in|out)[bwl]$", name):
            return "hardware"
        if name.startswith(CONTROLLER_PREFIXES):
            return "controller"
        if (
            is_service_call(name)
            or name.startswith(("q", "str", "mem", "fmt", "sprint", "seprint", "snprint"))
        ):
            return "service"
        return "external-unknown"

    def build_chain(
        self,
        start_func: Function | None,
        calls: list[Call],
        scope_key: Any,
    ) -> dict[str, Any]:
        cache_key = (start_func.id if start_func else None, json.dumps(scope_key, sort_keys=True))
        if cache_key in self._chain_cache:
            return self._chain_cache[cache_key]
        if start_func is None:
            chain = {
                "id": "chain:missing",
                "nodes": [],
                "edges": [],
                "terminal": {"kind": "handler-missing", "symbol": None, "line": None},
                "status": "unresolved",
                "reason": "handler definition was not found",
                "responsibilities": [],
                "services": [],
            }
            self._chain_cache[cache_key] = chain
            return chain

        terminals: list[dict[str, Any]] = []
        services: list[dict[str, Any]] = []
        visited_depth: dict[str, int] = {start_func.id: 0}
        queue: deque[tuple[Function, list[Call], list[str], list[dict[str, Any]], int]] = deque()
        queue.append((start_func, calls, [start_func.id], [], 0))
        explored = 0
        while queue and explored < MAX_CHAIN_NODES and len(terminals) < MAX_CHAIN_TERMINALS:
            func, f_calls, path, edges, depth = queue.popleft()
            explored += 1
            for call in sorted(f_calls, key=lambda c: (c.line, c.offset, c.name)):
                if call.kind in ("member", "pointer", "local-pointer"):
                    cands = self.indirect_candidates(call) if call.kind != "local-pointer" else []
                    kind = "interface" if cands else "indirect-unresolved"
                    terminals.append({
                        "kind": kind,
                        "symbol": call.field or call.name,
                        "expr": call.expr,
                        "line": call.line,
                        "path": func.path,
                        "depth": depth,
                        "candidates": cands,
                        "path_nodes": list(path),
                        "path_edges": edges + [{
                            "from": func.id,
                            "to": "indirect:" + (call.field or call.name),
                            "kind": "indirect",
                            "symbol": call.field or call.name,
                            "expr": call.expr,
                            "line": call.line,
                            "path": func.path,
                            "candidates": cands,
                        }],
                    })
                    continue
                if is_service_call(call.name):
                    services.append({
                        "symbol": call.name,
                        "line": call.line,
                        "path": func.path,
                        "from": func.id,
                    })
                    continue
                callee, reason = self.resolve(call, func)
                if callee is not None:
                    if callee.id in path:
                        continue
                    if depth + 1 > MAX_CHAIN_DEPTH:
                        terminals.append({
                            "kind": "depth-limit",
                            "symbol": call.name,
                            "line": call.line,
                            "path": func.path,
                            "depth": depth + 1,
                            "candidates": [],
                            "path_nodes": list(path),
                            "path_edges": edges + [{
                                "from": func.id, "to": "depth-limit:" + call.name,
                                "kind": "depth-limit", "symbol": call.name,
                                "line": call.line, "path": func.path,
                                "candidates": [],
                            }],
                        })
                        continue
                    nd = depth + 1
                    if visited_depth.get(callee.id, 10**9) <= nd:
                        continue
                    visited_depth[callee.id] = nd
                    newpath = path + [callee.id]
                    newedges = edges + [{
                        "from": func.id,
                        "to": callee.id,
                        "kind": "direct",
                        "symbol": call.name,
                        "line": call.line,
                        "path": func.path,
                    }]
                    queue.append((callee, callee.calls, newpath, newedges, nd))
                else:
                    if reason == "external":
                        ext_kind = self.classify_external(call.name)
                    else:
                        ext_kind = "ambiguous-symbol"
                    if ext_kind == "service":
                        services.append({
                            "symbol": call.name,
                            "line": call.line,
                            "path": func.path,
                            "from": func.id,
                        })
                        continue
                    terminals.append({
                        "kind": ext_kind,
                        "symbol": call.name,
                        "line": call.line,
                        "path": func.path,
                        "depth": depth,
                        "candidates": [],
                        "reason": reason,
                        "path_nodes": list(path),
                        "path_edges": edges + [{
                            "from": func.id, "to": "external:" + call.name,
                            "kind": "terminal", "symbol": call.name,
                            "line": call.line, "path": func.path,
                        }],
                    })
        priority = {
            "hardware": 0,
            "controller": 1,
            "interface": 2,
            "external-unknown": 3,
            "ambiguous-symbol": 5,
            "indirect-unresolved": 6,
            "depth-limit": 7,
        }
        if terminals:
            terminals.sort(key=lambda t: (
                priority.get(t["kind"], 9), t.get("depth", 99), t.get("line") or 0,
                t.get("symbol") or "",
            ))
            chosen = terminals[0]
        else:
            chosen = {
                "kind": "service-only" if services else "no-primitive",
                "symbol": None,
                "line": None,
                "path": start_func.path,
                "depth": None,
                "candidates": [],
            }
        if chosen["kind"] in ("hardware",):
            status = "resolved"
            reason = None
        elif chosen["kind"] in ("controller",):
            status = "partial"
            reason = "external controller/register primitive; semantics not established by this scanner"
        elif chosen["kind"] == "interface":
            status = "partial"
            reason = "indirect callback edge retained; concrete target not statically resolved"
        elif chosen["kind"] == "service-only":
            status = "partial"
            reason = "chain reached only kernel services/generic Dev helpers"
        elif chosen["kind"] == "no-primitive":
            status = "partial"
            reason = "no device or service primitive identified within the bounded chain"
        elif chosen["kind"] == "external-unknown":
            status = "partial"
            reason = "external call without a recognised device/service classification"
        elif chosen["kind"] == "ambiguous-symbol":
            status = "unresolved"
            reason = chosen.get("reason") or "symbol has multiple definitions"
        elif chosen["kind"] == "indirect-unresolved":
            status = "unresolved"
            reason = "indirect call with no known candidates"
        else:
            status = "unresolved"
            reason = "chain depth limit reached before a primitive"

        # The chosen terminal carries the exact bounded path that produced it.
        # Do not re-search the graph here: a second search could find the same
        # field name through an unrelated branch and fabricate a plausible but
        # wrong chain.
        nodes: list[str] = list(chosen.get("path_nodes") or [start_func.id])
        edges: list[dict[str, Any]] = list(chosen.get("path_edges") or [])
        if not nodes:
            nodes = [start_func.id]
        responsibilities = self._responsibilities(nodes, start_func, calls)
        behavior = self._behavior(nodes, start_func, calls)
        chain = {
            "id": "",
            "start": start_func.id,
            "nodes": nodes,
            "edges": edges,
            "terminal": chosen,
            "service_symbols": sorted({x["symbol"] for x in services})[:40],
            "service_edge_count": len(services),
            "status": status,
            "reason": reason,
            "responsibilities": responsibilities,
            "return_behavior": behavior["return_behavior"],
            "async": behavior["async"],
        }
        digest = hashlib.sha256(
            json.dumps({
                "start": chain["start"], "nodes": nodes, "edges": edges,
                "terminal": chosen, "status": status,
            }, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        chain["id"] = "chain:" + digest
        self.chains[chain["id"]] = chain
        self._chain_cache[cache_key] = chain
        return chain

    def _find_terminal_path(
        self,
        start_func: Function,
        calls: list[Call],
        chosen: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        target = chosen.get("symbol")
        queue: deque[tuple[Function, list[Call], list[str], list[dict[str, Any]], int]] = deque()
        queue.append((start_func, calls, [start_func.id], [], 0))
        seen: set[str] = {start_func.id}
        while queue:
            func, f_calls, path, edges, depth = queue.popleft()
            if depth > MAX_CHAIN_DEPTH:
                continue
            for call in sorted(f_calls, key=lambda c: (c.line, c.offset, c.name)):
                if call.kind == "direct" and call.name == target:
                    return path, edges + [{
                        "from": func.id,
                        "to": "external:" + target,
                        "kind": "terminal",
                        "symbol": target,
                        "line": call.line,
                        "path": func.path,
                    }]
                if call.kind == "direct":
                    callee, _ = self.resolve(call, func)
                    if callee is not None and callee.id not in seen:
                        seen.add(callee.id)
                        queue.append((callee, callee.calls, path + [callee.id],
                                      edges + [{
                                          "from": func.id, "to": callee.id,
                                          "kind": "direct", "symbol": call.name,
                                          "line": call.line, "path": func.path,
                                      }], depth + 1))
        return [start_func.id], []

    def _find_indirect_path(
        self,
        start_func: Function,
        calls: list[Call],
        chosen: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        target = chosen.get("symbol")
        queue: deque[tuple[Function, list[Call], list[str], list[dict[str, Any]], int]] = deque()
        queue.append((start_func, calls, [start_func.id], [], 0))
        seen: set[str] = {start_func.id}
        while queue:
            func, f_calls, path, edges, depth = queue.popleft()
            if depth > MAX_CHAIN_DEPTH:
                continue
            for call in sorted(f_calls, key=lambda c: (c.line, c.offset, c.name)):
                if call.kind in ("member", "pointer", "local-pointer") and (call.field or call.name) == target:
                    return path, edges + [{
                        "from": func.id,
                        "to": "indirect:" + (call.field or call.name),
                        "kind": "indirect",
                        "symbol": call.field or call.name,
                        "expr": call.expr,
                        "line": call.line,
                        "path": func.path,
                        "candidates": self.indirect_candidates(call),
                    }]
                if call.kind == "direct":
                    callee, _ = self.resolve(call, func)
                    if callee is not None and callee.id not in seen:
                        seen.add(callee.id)
                        queue.append((callee, callee.calls, path + [callee.id],
                                      edges + [{
                                          "from": func.id, "to": callee.id,
                                          "kind": "direct", "symbol": call.name,
                                          "line": call.line, "path": func.path,
                                      }], depth + 1))
        return [start_func.id], []

    def _behavior(self, node_ids: list[str], start_func: Function, calls: list[Call]) -> dict[str, Any]:
        names: list[str] = [c.name for c in calls]
        texts: list[str] = [start_func.text]
        for nid in node_ids:
            f = self.function_by_id.get(nid)
            if f is None:
                continue
            names.extend(c.name for c in f.calls)
            texts.append(f.text)
        joined = " ".join(texts)
        error_calls = [n for n in names if n in ("error", "nexterror", "waserror", "poperror")]
        async_calls = [
            n for n in names
            if n in ("sleep", "tsleep", "wakeup", "rendezvous", "qread", "qwrite",
                     "qwait", "qio", "qpass", "qproduce", "qconsume")
        ]
        if error_calls:
            error_behavior = (
                "may raise a Plan 9 error; waserror/poperror rollback is present"
                if any(n in ("waserror", "poperror") for n in error_calls)
                else "may raise a Plan 9 error; rollback was not observed in the selected path"
            )
        else:
            error_behavior = "returns through C return paths; error escalation not observed in the selected path"
        async_behavior = (
            "queue/wait/sleep/wakeup primitives observed"
            if async_calls else "no asynchronous completion primitive identified"
        )
        return {
            "return_behavior": error_behavior,
            "async": async_behavior,
        }

    def _responsibilities(self, node_ids: list[str], start_func: Function, calls: list[Call]) -> list[str]:
        flags: set[str] = set()
        texts: list[str] = []
        all_calls: list[str] = [c.name for c in calls]
        for nid in node_ids:
            f = self.function_by_id.get(nid)
            if f is None:
                continue
            texts.append(f.text)
            all_calls.extend(c.name for c in f.calls)
        joined = " ".join(texts)
        names = " ".join(all_calls)

        if re.search(r"\b(namec|copen|cclose|cmount|devattach|devopen)\b", names):
            flags.add("path/Chan handling")
        if re.search(r"\bdevwalk\b|\bwalk\b", names):
            flags.add("walk")
        if re.search(r"\b(parsecmd|lookupcmd|strcmp|strncmp|strtol|tokenize|atoi)\b", names):
            flags.add("textual parsing")
        if re.search(r"\b(snprint|seprint|sprint|print|readstr|readnum)\b", names):
            flags.add("formatting")
        if re.search(r"\b(iseve|eve|validaddr|validnamedup|Eperm|Ebadarg)\b", joined):
            flags.add("access/bounds validation")
        if re.search(r"\b(qlock|qunlock|ilock|iunlock|lock|unlock|rlock|wlock)\b", names):
            flags.add("locking")
        if re.search(r"\b(incref|decref|kstrdup|free|malloc|smalloc|cclose)\b", names):
            flags.add("lifetime/reference management")
        if re.search(r"\b(sleep|tsleep|wakeup|rendezvous|qread|qwrite|qwait|sleep)\b", names):
            flags.add("waiting/blocking")
        if re.search(r"\b(dma|DMAT|dmat|pcimap|intrenable|intrdisable|Vctl)\b", joined):
            flags.add("DMA/interrupt/controller interaction")
        if re.search(r"\b(inb|inw|inl|outb|outw|outl|ins|outs|rdmsr|wrmsr)\b", names):
            flags.add("hardware register/port interaction")
        if re.search(r"\b(qio|qpass|qproduce|qconsume|Block|allocb|freeb)\b", joined):
            flags.add("queue/framing/transport")
        if re.search(r"\boff\b|\boffset\b|\bdevoffset\b", joined):
            flags.add("offset translation")
        if start_func.switches:
            flags.add("Qid/command dispatch")
        return sorted(flags)

    # -- operations ---------------------------------------------------------

    def _find_function(self, symbol: str | None, path: str | None = None) -> Function | None:
        if not symbol:
            return None
        candidates = self.global_by_name.get(symbol, [])
        if path:
            local = [f for f in candidates if f.path == path]
            if local:
                return local[0]
        if len(candidates) == 1:
            return candidates[0]
        return candidates[0] if candidates else None

    def _qid_path_map(self, path: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for tab in self.dirtab_records:
            if tab["path"] != path:
                continue
            for entry in tab["entries"]:
                sym = entry.get("qid_symbol")
                if sym:
                    out[sym].append(entry["name"])
        return out

    def _operation(
        self,
        *,
        op_id: str,
        kind: str,
        subsystem: str,
        driver: str,
        registration_id: str,
        source_path: str,
        source_line: int,
        entry: dict[str, Any],
        handler: Function | None,
        calls: list[Call],
        input_output: dict[str, Any],
        conditions: Sequence[str] = (),
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chain = self.build_chain(handler, calls, scope_key=(
            handler.id if handler else None,
            [c.offset for c in calls],
            [c.name for c in calls],
        ))
        active = self.active_configs_for(source_path)
        rec: dict[str, Any] = {
            "id": op_id,
            "kind": kind,
            "subsystem": subsystem,
            "driver": driver,
            "registration_id": registration_id,
            "source": {"path": source_path, "line": source_line},
            "entry": entry,
            "input_output": input_output,
            "handler": {
                "symbol": handler.name if handler else None,
                "path": handler.path if handler else None,
                "line": handler.line if handler else None,
            },
            "chain_id": chain["id"],
            "status": chain["status"],
            "reason": chain["reason"],
            "return_behavior": chain.get("return_behavior"),
            "async": chain.get("async"),
            "active_configs": active,
            "conditions": list(conditions),
        }
        if extra:
            rec.update(extra)
        self.operations.append(rec)
        return rec

    def _shape(self, callback: str, branch: str | None = None) -> dict[str, Any]:
        if callback in ("read",):
            return {"shape": "byte stream or textual value", "units": "offset, length"}
        if callback in ("write",):
            return {"shape": "byte stream or textual control", "units": "offset, length"}
        if callback in ("bread", "bwrite"):
            return {"shape": "block-oriented data", "units": "block, length"}
        if callback in ("stat", "wstat"):
            return {"shape": "Plan 9 Dir metadata", "units": "serialised Dir bytes"}
        if callback in ("walk",):
            return {"shape": "path components/Qids", "units": "name list"}
        if callback in ("open", "create", "close", "remove", "attach"):
            return {"shape": "Chan lifecycle/state transition", "units": "mode/flags"}
        if callback in ("power",):
            return {"shape": "device power state", "units": "on/off"}
        if callback in ("config",):
            return {"shape": "device configuration record", "units": "DevConf"}
        return {"shape": "control/lifecycle", "units": "unspecified"}

    def build_operations(self) -> None:
        for reg in self.registration_records:
            if reg["type"] != "Dev":
                continue
            path = reg["path"]
            driver = reg["name"]
            qidpaths = self._qid_path_map(path)
            subsystem = subsystem_for(path, driver)
            devchar = reg.get("dc")
            for callback, value in reg["callbacks"].items():
                sym = value.get("symbol")
                if value.get("nil") or not sym:
                    continue
                handler = self._find_function(sym, path)
                qid_switches = [
                    sw for sw in (handler.switches if handler else [])
                    if "qid" in sw.condition.lower()
                ]
                qid_ifs = extract_if_qid_branches(
                    handler.body, 0, len(handler.body)
                ) if handler and not qid_switches else []
                if qid_switches or qid_ifs:
                    seen_labels: set[str] = set()
                    branch_specs: list[tuple[CaseLabel, str]] = []
                    for sw in qid_switches:
                        for case in sw.cases:
                            if case.label == "default":
                                continue
                            branch_specs.append((case, sw.condition))
                    for case in qid_ifs:
                        branch_specs.append((case, "if qid comparison"))
                    for case, dispatch in branch_specs:
                        label = case.label
                        if label in seen_labels:
                            continue
                        seen_labels.add(label)
                        branch_calls = self.calls_in_scope(handler, case.start, case.end) if handler else []
                        op_id = f"op:{reg['id']}:{callback}:{slug(label)}"
                        qpaths = qidpaths.get(case.label, [])
                        self._operation(
                            op_id=op_id,
                            kind="file-operation",
                            subsystem=subsystem,
                            driver=driver,
                            registration_id=reg["id"],
                            source_path=path,
                            source_line=case.line,
                            entry={
                                "device": devchar,
                                "device_syntax": f"#{devchar}" if devchar else None,
                                "callback": callback,
                                "qid": case.label,
                                "path": qpaths[0] if qpaths else None,
                                "paths": qpaths,
                                "dispatch": dispatch,
                                "command": None,
                            },
                            handler=handler,
                            calls=branch_calls,
                            input_output=self._shape(callback, case.label),
                            conditions=handler.conditions if handler else (),
                            extra={"branch": case.label},
                        )
                else:
                    op_id = f"op:{reg['id']}:{callback}"
                    self._operation(
                        op_id=op_id,
                        kind="file-operation",
                        subsystem=subsystem,
                        driver=driver,
                        registration_id=reg["id"],
                        source_path=path,
                        source_line=value.get("line") or reg["line"],
                        entry={
                            "device": devchar,
                            "device_syntax": f"#{devchar}" if devchar else None,
                            "callback": callback,
                            "qid": None,
                            "path": None,
                            "paths": [],
                            "dispatch": "direct Dev callback",
                            "command": None,
                        },
                        handler=handler,
                        calls=handler.calls if handler else [],
                        input_output=self._shape(callback),
                        conditions=handler.conditions if handler else (),
                    )

            # Commands implemented with Cmdtab and lookupcmd.
            for tab in self.cmdtab_records:
                if tab["path"] != path:
                    continue
                dispatcher = self._find_dispatcher(tab)
                index_switch = self._find_index_switch(dispatcher, tab) if dispatcher else None
                for entry in tab["entries"]:
                    idx = entry["index"]
                    idx_sym = self._last_symbol(idx) or idx
                    case = None
                    if index_switch is not None:
                        for c in index_switch.cases:
                            if self._same_index(c.label, idx, idx_sym):
                                case = c
                                break
                    calls = self.calls_in_scope(dispatcher, case.start, case.end) if (dispatcher and case) else (
                        dispatcher.calls if dispatcher else []
                    )
                    op_id = f"cmd:{tab['id']}:{slug(idx_sym)}:{slug(entry['cmd'])}"
                    chain = self.build_chain(dispatcher, calls, scope_key=(
                        dispatcher.id if dispatcher else None,
                        case.start if case else "whole-function",
                        case.end if case else None,
                    ))
                    status = chain["status"]
                    reason = chain["reason"]
                    if dispatcher is None:
                        status, reason = "unresolved", "Cmdtab dispatcher not found"
                    elif case is None:
                        status = "partial" if chain["status"] != "unresolved" else "unresolved"
                        reason = ("command dispatched by the function outside a directly matched "
                                  "switch case; branch-specific scope is not established")
                    self.operations.append({
                        "id": op_id,
                        "kind": "control-command",
                        "subsystem": subsystem,
                        "driver": driver,
                        "registration_id": reg["id"],
                        "source": {"path": path, "line": entry["line"]},
                        "entry": {
                            "device": devchar,
                            "device_syntax": f"#{devchar}" if devchar else None,
                            "callback": "write/ctl",
                            "qid": None,
                            "path": None,
                            "paths": [],
                            "dispatch": index_switch.condition if index_switch else "Cmdtab lookup",
                            "command": entry["cmd"],
                            "command_index": idx,
                            "narg": entry["narg"],
                            "table": tab["name"],
                            "dispatch_scope": "case" if case else "whole-dispatcher",
                        },
                        "input_output": {"shape": "textual control command", "units": "command name and arguments"},
                        "handler": {
                            "symbol": dispatcher.name if dispatcher else None,
                            "path": dispatcher.path if dispatcher else None,
                            "line": dispatcher.line if dispatcher else None,
                        },
                        "chain_id": chain["id"],
                        "status": status,
                        "reason": reason,
                        "return_behavior": chain.get("return_behavior"),
                        "async": chain.get("async"),
                        "active_configs": self.active_configs_for(path),
                        "conditions": [],
                    })

            # Commands implemented without Cmdtab: first-field strcmp tests in
            # a Dev write handler.
            write_value = reg["callbacks"].get("write", {})
            write_handler = self._find_function(write_value.get("symbol"), path)
            if write_handler is not None:
                for command, line in extract_manual_commands(
                    write_handler.body, 0, len(write_handler.body)
                ):
                    op_id = f"cmd:{reg['id']}:manual:{slug(write_handler.name)}:{slug(command)}"
                    chain = self.build_chain(
                        write_handler, write_handler.calls,
                        scope_key=(write_handler.id, "manual", command),
                    )
                    self.operations.append({
                        "id": op_id,
                        "kind": "manual-control-command",
                        "subsystem": subsystem,
                        "driver": driver,
                        "registration_id": reg["id"],
                        "source": {"path": path, "line": line},
                        "entry": {
                            "device": devchar,
                            "device_syntax": f"#{devchar}" if devchar else None,
                            "callback": "write/ctl",
                            "qid": None,
                            "path": None,
                            "paths": [],
                            "dispatch": f"strcmp in {write_handler.name}",
                            "command": command,
                            "table": None,
                        },
                        "input_output": {"shape": "textual control command", "units": "command name and arguments"},
                        "handler": {
                            "symbol": write_handler.name,
                            "path": write_handler.path,
                            "line": write_handler.line,
                        },
                        "chain_id": chain["id"],
                        "status": "partial" if chain["status"] == "resolved" else chain["status"],
                        "reason": "manual command branch isolated only to the containing function"
                        if chain["status"] == "resolved" else chain["reason"],
                        "return_behavior": chain.get("return_behavior"),
                        "async": chain.get("async"),
                        "active_configs": self.active_configs_for(path),
                        "conditions": [],
                    })

        # Lower-level interface callbacks (SDifc, PhysUart, VGA, PCArch, Ether).
        for reg in self.registration_records:
            if reg["type"] in ("Dev", "Dirtab", "Cmdtab"):
                continue
            path = reg["path"]
            for callback, value in reg["callbacks"].items():
                sym = value.get("symbol")
                if value.get("nil") or not sym:
                    continue
                handler = self._find_function(sym, path)
                op_id = f"iface:{reg['id']}:{callback}"
                chain = self.build_chain(handler, handler.calls if handler else [], scope_key=(
                    handler.id if handler else None, "full",
                ))
                self.operations.append({
                    "id": op_id,
                    "kind": "interface-operation",
                    "subsystem": subsystem_for(path, reg["name"]),
                    "driver": reg["name"],
                    "registration_id": reg["id"],
                    "source": {"path": path, "line": value.get("line") or reg["line"]},
                    "entry": {
                        "device": None,
                        "device_syntax": None,
                        "callback": callback,
                        "qid": None,
                        "path": None,
                        "paths": [],
                        "dispatch": f"{reg['type']} callback",
                        "command": None,
                        "interface": reg["type"],
                        "registration": reg["name"],
                    },
                    "input_output": {"shape": "interface callback", "units": "interface-specific"},
                    "handler": {
                        "symbol": handler.name if handler else sym,
                        "path": handler.path if handler else None,
                        "line": handler.line if handler else None,
                    },
                    "chain_id": chain["id"],
                    "status": chain["status"],
                    "reason": chain["reason"],
                    "return_behavior": chain.get("return_behavior"),
                    "async": chain.get("async"),
                    "active_configs": self.active_configs_for(path),
                    "conditions": list(reg.get("conditions", [])),
                })

        self.operations.sort(key=lambda o: (o["subsystem"], o["driver"], o["id"]))

    def _last_symbol(self, text: str) -> str | None:
        ids = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
        return ids[-1] if ids else None

    def _same_index(self, case_label: str, entry_index: str, symbol: str) -> bool:
        norm = lambda s: re.sub(r"\s+", "", s)
        a, b, c = norm(case_label), norm(entry_index), norm(symbol)
        return a == b or a == c or (c and re.search(rf"(^|[^A-Za-z0-9_]){re.escape(c)}($|[^A-Za-z0-9_])", a) is not None)

    def _index_vars(self, func: Function) -> set[str]:
        names: set[str] = {"index"}
        body = func.body
        for i, t in enumerate(body):
            if t.kind != "id" or i + 1 >= len(body) or body[i + 1].value != "=":
                continue
            for j in range(i + 2, min(len(body), i + 16)):
                if body[j].value == ";":
                    break
                if body[j].value == "index" and j > 0 and body[j - 1].value in ("->", "."):
                    names.add(t.value)
                    break
        return names

    def _is_index_switch(self, sw: Switch, func: Function) -> bool:
        cond = re.sub(r"\s+", "", sw.condition)
        if "index" in cond:
            return True
        for name in self._index_vars(func):
            if name == "index":
                continue
            if re.search(rf"(^|[^A-Za-z0-9_]){re.escape(name)}($|[^A-Za-z0-9_])", cond):
                return True
        return False

    def _find_index_switch(self, dispatcher: Function | None, tab: dict[str, Any]) -> Switch | None:
        if dispatcher is None:
            return None
        candidates = [sw for sw in dispatcher.switches if self._is_index_switch(sw, dispatcher)]
        if not candidates:
            return None
        best = None
        best_score = -1
        entries = tab.get("entries", [])
        for sw in candidates:
            score = 0
            for entry in entries:
                idx = entry.get("index", "")
                sym = self._last_symbol(idx) or idx
                if any(self._same_index(c.label, idx, sym) for c in sw.cases):
                    score += 1
            if score > best_score:
                best, best_score = sw, score
        return best or candidates[0]

    def _find_dispatcher(self, tab: dict[str, Any]) -> Function | None:
        direct: list[Function] = []
        for f in self.functions:
            if f.path != tab["path"]:
                continue
            for call in f.calls:
                if call.kind == "direct" and call.name == "lookupcmd":
                    if tab["name"] in " ".join(call.args_text):
                        direct.append(f)
                        break
        candidates: list[Function] = list(direct)
        # Helpers (for example devfs parseconfig) return the Cmdtab to a
        # caller that performs the substantive switch.  Include direct callers
        # of the lookupcmd helper when they have an index-like switch.
        for helper in list(direct):
            for f in self.functions:
                if f.path != helper.path:
                    continue
                if any(call.kind == "direct" and call.name == helper.name for call in f.calls):
                    if any(self._is_index_switch(sw, f) for sw in f.switches):
                        candidates.append(f)
        # Also accept a function that names the table and has an index switch.
        for f in self.functions:
            if f.path != tab["path"]:
                continue
            if tab["name"] in f.text and any(self._is_index_switch(sw, f) for sw in f.switches):
                candidates.append(f)
        # Deduplicate and score by how many table entries the best switch covers.
        uniq: dict[str, Function] = {f.id: f for f in candidates}
        best = None
        best_score = -1
        candidate_ids = set(uniq)
        for f in uniq.values():
            sw = self._find_index_switch(f, tab)
            score = 0
            if sw is not None:
                for entry in tab.get("entries", []):
                    idx = entry.get("index", "")
                    sym = self._last_symbol(idx) or idx
                    if any(self._same_index(c.label, idx, sym) for c in sw.cases):
                        score += 1
            # Prefer the caller that performs the substantive switch when a
            # parse/helper function returns the Cmdtab to it.
            for call in f.calls:
                if call.kind == "direct":
                    callee, _ = self.resolve(call, f)
                    if callee is not None and callee.id in candidate_ids and callee.id != f.id:
                        score += 50
            if score > best_score or (score == best_score and best is not None and f.line < best.line):
                best, best_score = f, score
        return best

    # -- native syscall entries --------------------------------------------

    def build_native_entries(self) -> None:
        systab_path = "sys/src/9/port/systab.h"
        sf = self.file_by_path.get(systab_path)
        if sf is None:
            self.native_records.append({
                "id": "native:unresolved",
                "name": None,
                "handler": None,
                "status": "unresolved",
                "reason": "sys/src/9/port/systab.h was not found",
            })
            return
        text = sf.masked
        numbers: dict[str, str] = {}
        sysh = self.file_by_path.get("sys/src/libc/9syscall/sys.h")
        if sysh is None:
            try:
                sysh_path = self.root / "sys/src/libc/9syscall/sys.h"
                if sysh_path.is_file():
                    sysh_text = sysh_path.read_text(encoding="utf-8", errors="replace")
                else:
                    sysh_text = ""
            except OSError:
                sysh_text = ""
        else:
            sysh_text = sysh.text
        for m in re.finditer(r"#define\s+([A-Za-z0-9_]+)\s+([0-9]+)", sysh_text):
            numbers[m.group(1)] = m.group(2)

        def array_entries(array_name: str, pattern: str) -> list[re.Match[str]]:
            m = re.search(rf"{array_name}\s*\[\s*\]\s*=\s*\{{(.*?)\}}\s*;", text, re.S)
            if not m:
                return []
            return list(re.finditer(pattern, m.group(1)))

        names: dict[str, str] = {}
        for m in array_entries("sysctab", r'\[([A-Z0-9_]+)\]\s*"([^"]+)"'):
            names[m.group(1)] = m.group(2)
        entries = array_entries("systab", r"\[([A-Z0-9_]+)\]\s*(sys[A-Za-z0-9_]+)")
        registered_handlers: set[str] = set()
        for m in entries:
            macro, handler_name = m.group(1), m.group(2)
            registered_handlers.add(handler_name)
            handler = self._find_function(handler_name)
            chain = self.build_chain(handler, handler.calls if handler else [], scope_key=(
                handler.id if handler else None, "syscall",
            ))
            self.native_records.append({
                "id": f"native:{macro}",
                "syscall": macro,
                "number": numbers.get(macro),
                "display_name": names.get(macro),
                "handler": handler_name,
                "handler_path": handler.path if handler else None,
                "handler_line": handler.line if handler else None,
                "source": {
                    "path": handler.path if handler else systab_path,
                    "line": handler.line if handler else None,
                },
                "systab_source": {"path": systab_path},
                "chain_id": chain["id"],
                "status": chain["status"],
                "reason": chain["reason"],
                "return_behavior": chain.get("return_behavior"),
                "async": chain.get("async"),
                "native_o": macro in {
                    "OVOLOPEN", "OSPACEOPEN", "OSPACEGET", "OSPACEPUT",
                    "OSPACECOMMIT", "OSPACECLOSE", "OEXECUTE",
                },
            })
        # Functions that look like native O entry points but are not wired to
        # systab[] are reported rather than omitted.
        for f in self.functions:
            if not re.match(r"^syso[a-z0-9_]*$", f.name):
                continue
            if f.name in registered_handlers:
                continue
            chain = self.build_chain(f, f.calls, scope_key=(f.id, "unregistered-syscall"))
            self.native_records.append({
                "id": f"native:unregistered:{f.name}",
                "syscall": None,
                "number": None,
                "display_name": None,
                "handler": f.name,
                "handler_path": f.path,
                "handler_line": f.line,
                "source": {"path": f.path, "line": f.line},
                "chain_id": chain["id"],
                "status": "unresolved",
                "reason": "native syscall-like function is defined but has no systab[] entry",
                "return_behavior": chain.get("return_behavior"),
                "async": chain.get("async"),
                "native_o": True,
            })
        self.native_records.sort(key=lambda r: (r["id"],))

    # -- representatives ----------------------------------------------------

    def build_representatives(self) -> None:
        specs = [
            {
                "id": "rep:ge-o-volopen",
                "title": "GE/O native volume open through the storage backend",
                "start": "sysovolopen",
                "focus": ["gevolume", "namec", "oopen", "geopen"],
                "note": "OVOLOPEN remains a native syscall but still discovers/opens a Chan through #S/devsd before oopen/geopen.",
            },
            {
                "id": "rep:sd-partition",
                "title": "Block partition read through SDifc to a storage backend",
                "start": "sdbio",
                "focus": [],
                "prefer_interface": "bio",
                "note": "sdbio is reached from devsd read/write Qpart; the concrete controller is selected by unit->dev->ifc->bio.",
            },
            {
                "id": "rep:kbd",
                "title": "Keyboard scancode read path",
                "start": "kbdread",
                "focus": ["kbdpoll", "i8042intr"],
                "note": "The Qscancode branch polls the i8042 controller; inb/outb are the hardware endpoint.",
            },
            {
                "id": "rep:console-serial",
                "title": "Kernel console write and serial backend",
                "start": "conswrite",
                "focus": ["putstrn0", "uartputs"],
                "prefer_interface": "putc",
                "note": "Qcons writes go through the console ring and either screenputs or the PhysUart putc callback.",
            },
            {
                "id": "rep:ether-data",
                "title": "Ethernet data write path",
                "start": "etherwrite",
                "focus": ["etheroq", "ethermux"],
                "prefer_interface": "transmit",
                "note": "The data branch is framed through etheroq/ethermux; the queue kick ultimately invokes Ether.transmit.",
            },
            {
                "id": "rep:dynamic-qid",
                "title": "Dynamically generated directory and Qid dispatch",
                "start": "sdgen",
                "focus": [],
                "switch_start": True,
                "note": "devsd has no static Dirtab array for units/partitions; sdgen builds Qids from QID(dev, unit, part, type) and sdread/sdwrite switch on TYPE().",
            },
        ]
        for spec in specs:
            start = self._best_function(spec["start"])
            nodes: list[str] = []
            edges: list[dict[str, Any]] = []
            notes: list[str] = [spec["note"]]
            if start is None:
                self.representative.append({
                    "id": spec["id"], "title": spec["title"], "status": "unresolved",
                    "reason": f"start function {spec['start']} not found",
                    "nodes": [], "edges": [], "notes": notes,
                })
                continue
            current = start
            nodes.append(current.id)
            pool: list[Function] = [start]
            for target in spec.get("focus", []):
                found = None
                # Prefer the current function, then earlier functions in the
                # selected path.  This handles sequential calls such as
                # sysovolopen -> gevolume, then oopen, then geopen.
                for candidate in [current] + list(reversed(pool)):
                    for call in candidate.calls:
                        if call.kind == "direct" and call.name == target:
                            callee, _ = self.resolve(call, candidate)
                            found = (candidate, call, callee)
                            break
                    if found:
                        break
                if found is None:
                    notes.append(f"focused call {target} not found in the selected path")
                    continue
                frm, call, callee = found
                if callee is not None:
                    if callee.id not in nodes:
                        nodes.append(callee.id)
                    edges.append({
                        "from": frm.id, "to": callee.id, "kind": "direct",
                        "symbol": call.name, "line": call.line, "path": frm.path,
                    })
                    current = callee
                    if callee not in pool:
                        pool.append(callee)
                else:
                    edges.append({
                        "from": frm.id, "to": "external:" + target, "kind": "direct",
                        "symbol": call.name, "line": call.line, "path": frm.path,
                    })
            terminal = None
            if spec.get("prefer_interface"):
                field = spec["prefer_interface"]
                for f in [current] + list(reversed(pool)):
                    for call in f.calls:
                        if call.kind in ("member", "pointer") and (call.field == field or call.name == field):
                            terminal = {
                                "kind": "interface", "symbol": field, "expr": call.expr,
                                "line": call.line, "path": f.path,
                                "candidates": self.indirect_candidates(call),
                            }
                            edges.append({
                                "from": f.id, "to": "indirect:" + field,
                                "kind": "indirect", "symbol": field,
                                "expr": call.expr, "line": call.line, "path": f.path,
                                "candidates": terminal["candidates"],
                            })
                            break
                    if terminal:
                        break
                if terminal is None:
                    # A field such as Ether.transmit is installed as a queue
                    # kick in a probe/attach function rather than called
                    # directly from the data path.  Keep that assignment edge
                    # visible with its candidates.
                    for f in self.functions:
                        if f.path != start.path:
                            continue
                        for i, tok in enumerate(f.body[:-1]):
                            if tok.value == "->" and f.body[i + 1].value == field:
                                expr = join_tokens(f.body[max(0, i - 3):i + 2])
                                terminal = {
                                    "kind": "interface", "symbol": field,
                                    "expr": expr, "line": tok.line, "path": f.path,
                                    "candidates": self.interface_candidates.get("Ether", {}).get(field, []),
                                    "assignment": True,
                                }
                                edges.append({
                                    "from": f.id, "to": "indirect:" + field,
                                    "kind": "indirect-assignment", "symbol": field,
                                    "expr": expr, "line": tok.line, "path": f.path,
                                    "candidates": terminal["candidates"],
                                })
                                notes.append(
                                    f"{field} is installed as a callback/queue kick in "
                                    f"{f.name}; the data path itself reaches it indirectly."
                                )
                                break
                        if terminal:
                            break
            if spec.get("switch_start"):
                qid_cases = []
                for sw in start.switches:
                    if "qid" in sw.condition.lower():
                        for c in sw.cases:
                            qid_cases.append({"case": c.label, "line": c.line})
                if qid_cases:
                    terminal = {
                        "kind": "qid-dispatch", "symbol": None, "line": start.line,
                        "path": start.path, "cases": qid_cases,
                    }
            elif spec["id"] == "rep:ge-o-volopen":
                terminal = {
                    "kind": "engine-entry", "symbol": current.name,
                    "line": current.line, "path": current.path,
                    "candidates": [],
                }
                notes.append(
                    "The selected path reaches the GE engine entry; controller "
                    "hardware is reached later through the storage backend, not "
                    "by this bounded focus path."
                )
            elif terminal is None:
                chain = self.build_chain(current, current.calls, scope_key=(current.id, "representative"))
                terminal = chain["terminal"]
                if len(chain["nodes"]) > len(nodes):
                    nodes = chain["nodes"]
                    edges = chain["edges"]
                else:
                    for e in chain["edges"]:
                        if e not in edges:
                            edges.append(e)
            status = "resolved" if terminal.get("kind") in ("hardware", "qid-dispatch") else "partial"
            if terminal.get("kind") in ("indirect-unresolved", "ambiguous-symbol", "depth-limit"):
                status = "unresolved"
            self.representative.append({
                "id": spec["id"],
                "title": spec["title"],
                "status": status,
                "start": start.id,
                "nodes": nodes,
                "edges": edges,
                "terminal": terminal,
                "notes": notes,
            })

    def _best_function(self, name: str) -> Function | None:
        candidates = self.global_by_name.get(name, [])
        if not candidates:
            return None
        candidates = sorted(candidates, key=lambda f: (f.path, f.line))
        return candidates[0]

    # -- coverage and data assembly ----------------------------------------

    def build_file_records(self, build_map: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
        regs_by_file: dict[str, list[str]] = defaultdict(list)
        for r in self.registration_records:
            regs_by_file[r["path"]].append(r["id"])
        records: list[dict[str, Any]] = []
        normal = self.normal_config_name()
        for sf in self.files:
            if sf.kind == "c":
                if regs_by_file.get(sf.path):
                    classification = "kernel driver/interface source"
                elif sf.functions:
                    classification = "kernel support source"
                else:
                    classification = "scanned C source (no functions found)"
            elif sf.kind == "header":
                classification = "kernel header"
            elif sf.kind == "assembly":
                classification = "assembly support"
            elif sf.kind == "config":
                classification = "kernel build configuration"
            elif sf.kind == "build-tool":
                classification = "build helper"
            else:
                classification = "other scanned file"
            rec = {
                "path": sf.path,
                "kind": sf.kind,
                "classification": classification,
                "sha256": sf.sha256,
                "bytes": len(sf.text.encode("utf-8")),
                "functions": len(sf.functions),
                "initializers": len(sf.initializers),
                "registrations": sorted(regs_by_file.get(sf.path, [])),
                "build": build_map.get(sf.path, {}),
                "normal_amd64": build_map.get(sf.path, {}).get(normal, "not-applicable"),
                "parse": {
                    "status": sf.parse_status,
                    "reason": sf.parse_error,
                    "line": sf.parse_error_line,
                },
                "conditions": sorted(self._file_conditions(sf)),
            }
            records.append(rec)
        return records

    def _file_conditions(self, sf: SourceFile) -> set[str]:
        out: set[str] = set()
        for c in sf.conditions:
            out.update(c)
        return out

    def coverage(self, file_records: list[dict[str, Any]], build_map: dict[str, dict[str, str]]) -> dict[str, Any]:
        by_kind: dict[str, int] = defaultdict(int)
        for sf in self.files:
            by_kind[sf.kind] += 1
        by_dir: dict[str, int] = defaultdict(int)
        for sf in self.files:
            parts = sf.path.split("/")
            by_dir["/".join(parts[:4]) if len(parts) >= 4 else sf.path] += 1
        regs_by_type: dict[str, int] = defaultdict(int)
        for r in self.registration_records:
            regs_by_type[r["type"]] += 1
        ops_by_kind: dict[str, int] = defaultdict(int)
        ops_by_status: dict[str, int] = defaultdict(int)
        for op in self.operations:
            ops_by_kind[op["kind"]] += 1
            ops_by_status[op["status"]] += 1
        native_by_status: dict[str, int] = defaultdict(int)
        for n in self.native_records:
            native_by_status[n["status"]] += 1
        chain_status: dict[str, int] = defaultdict(int)
        for ch in self.chains.values():
            chain_status[ch["status"]] += 1
        per_config: list[dict[str, Any]] = []
        for cfg in self.configs:
            active_c = [p for p in cfg.get("active_files", []) if p in self.file_by_path and self.file_by_path[p].kind == "c"]
            per_config.append({
                "name": cfg["name"],
                "kind": cfg.get("kind"),
                "arch": cfg.get("arch"),
                "target": cfg.get("target"),
                "status": cfg.get("status"),
                "config_path": cfg.get("config_path"),
                "active_c_files": len(active_c),
                "active_files_total": len(cfg.get("active_files", [])),
                "unresolved_objects": len(cfg.get("unresolved_objects", [])),
                "shadowed_objects": len(cfg.get("shadowed_objects", [])),
            })
        files_with_regs = sum(1 for r in file_records if r["registrations"])
        c_files = sum(1 for sf in self.files if sf.kind == "c")
        return {
            "scanned_files": len(self.files),
            "by_kind": dict(sorted(by_kind.items())),
            "by_directory": dict(sorted(by_dir.items())),
            "c_files": c_files,
            "parsed_c_files": sum(1 for sf in self.files if sf.kind == "c" and sf.parse_status == "ok"),
            "parse_failures": sum(1 for sf in self.files if sf.parse_status != "ok"),
            "files_with_registrations": files_with_regs,
            "registrations": len(self.registration_records),
            "registrations_by_type": dict(sorted(regs_by_type.items())),
            "dirtab_tables": len(self.dirtab_records),
            "cmdtab_tables": len(self.cmdtab_records),
            "exposed_operations": len(self.operations),
            "operations_by_kind": dict(sorted(ops_by_kind.items())),
            "operations_by_status": dict(sorted(ops_by_status.items())),
            "mapped_hardware_primitives": sum(1 for op in self.operations if self.chains.get(op["chain_id"], {}).get("terminal", {}).get("kind") == "hardware"),
            "mapped_controller_primitives": sum(1 for op in self.operations if self.chains.get(op["chain_id"], {}).get("terminal", {}).get("kind") == "controller"),
            "partial_mappings": sum(1 for op in self.operations if op["status"] == "partial"),
            "unresolved_operations": sum(1 for op in self.operations if op["status"] == "unresolved"),
            "unique_chains": len(self.chains),
            "chains_by_status": dict(sorted(chain_status.items())),
            "native_entry_points": len(self.native_records),
            "native_by_status": dict(sorted(native_by_status.items())),
            "per_config": per_config,
            "unresolved_build_objects": sum(len(c.get("unresolved_objects", [])) for c in self.configs),
            "unsupported_declarations": len(self.unsupported_declarations),
        }

    def unresolved_work(self) -> dict[str, Any]:
        ops = []
        for op in self.operations:
            if op["status"] == "resolved":
                continue
            ch = self.chains.get(op["chain_id"], {})
            term = ch.get("terminal", {})
            ops.append({
                "operation": op["id"],
                "kind": op["kind"],
                "driver": op["driver"],
                "status": op["status"],
                "reason": op["reason"],
                "terminal_kind": term.get("kind"),
                "terminal_symbol": term.get("symbol"),
                "candidates": term.get("candidates", []),
                "source": op["source"],
            })
        parse = list(self.parse_issues)
        build = []
        for cfg in self.configs:
            for item in cfg.get("unresolved_objects", []):
                build.append({
                    "config": cfg["name"],
                    "stem": item.get("stem"),
                    "reason": item.get("reason"),
                })
        conditional = []
        for reg in self.registration_records:
            if reg.get("conditions"):
                conditional.append({
                    "registration": reg["id"],
                    "conditions": reg["conditions"],
                    "source": {"path": reg["path"], "line": reg["line"]},
                })
        conditional_entries = []
        for tab in self.dirtab_records:
            for entry in tab.get("entries", []):
                if entry.get("conditions"):
                    conditional_entries.append({
                        "table": tab["name"],
                        "kind": "Dirtab",
                        "entry": entry["name"],
                        "qid": entry.get("qid_symbol") or entry.get("qid"),
                        "conditions": entry["conditions"],
                        "source": {"path": tab["path"], "line": entry["line"]},
                    })
        for tab in self.cmdtab_records:
            for entry in tab.get("entries", []):
                if entry.get("conditions") or tab.get("conditions"):
                    conditional_entries.append({
                        "table": tab["name"],
                        "kind": "Cmdtab",
                        "entry": entry["cmd"],
                        "qid": entry["index"],
                        "conditions": entry.get("conditions") or tab["conditions"],
                        "source": {"path": tab["path"], "line": entry["line"]},
                    })
        return {
            "operations": ops,
            "parse_failures": parse,
            "unresolved_build_objects": build,
            "conditional_registrations": conditional,
            "conditional_entries": conditional_entries,
            "unsupported_declarations": list(self.unsupported_declarations),
        }

    def analyze(self) -> dict[str, Any]:
        self.discover_files()
        self.parse_all()
        self.discover_configs()
        build_map = self.file_build_map()
        self.build_registrations()
        self.build_operations()
        self.build_native_entries()
        self.build_representatives()
        file_records = self.build_file_records(build_map)
        coverage = self.coverage(file_records, build_map)
        unresolved = self.unresolved_work()
        function_index: list[dict[str, Any]] = []
        indirect_edges: list[dict[str, Any]] = []
        dynamic_directories: list[dict[str, Any]] = []
        direct_edge_count = 0
        external_edge_count = 0
        for f in sorted(self.functions, key=lambda x: (x.path, x.line, x.name)):
            function_index.append({
                "id": f.id,
                "name": f.name,
                "path": f.path,
                "line": f.line,
                "end_line": f.end_line,
                "static": f.static,
                "params": f.params,
                "conditions": list(f.conditions),
                "call_count": len(f.calls),
                "switch_count": len(f.switches),
            })
            qid_cases = []
            for sw in f.switches:
                if "qid" in sw.condition.lower():
                    qid_cases.extend(
                        {"case": c.label, "line": c.line} for c in sw.cases
                    )
            if qid_cases and (f.name.endswith("gen") or f.name in (
                "sdgen", "rootgen", "ipgen", "drawgen", "pnpgen",
            )):
                dynamic_directories.append({
                    "function": f.id,
                    "name": f.name,
                    "path": f.path,
                    "line": f.line,
                    "cases": qid_cases,
                })
            for c in f.calls:
                if c.kind == "direct":
                    callee, reason = self.resolve(c, f)
                    if callee is not None:
                        direct_edge_count += 1
                    else:
                        external_edge_count += 1
                else:
                    indirect_edges.append({
                        "from": f.id, "kind": c.kind,
                        "symbol": c.field or c.name, "expr": c.expr,
                        "line": c.line, "path": f.path,
                        "candidates": self.indirect_candidates(c),
                    })
        indirect_edges.sort(key=lambda e: (e["from"], e["line"], e["symbol"]))
        dynamic_directories.sort(key=lambda x: (x["path"], x["line"]))
        data = {
            "schema": SCHEMA,
            "generator": {
                "name": GENERATOR,
                "version": GENERATOR_VERSION,
                "command": "python3 tools/kernel_opmap.py --write",
                "limitations": [
                    "lexical/structural scanner for Plan 9 C; not a compiler",
                    "Qid and command branches are split only where a switch case is visible",
                    "indirect callbacks are retained as edges with candidates, not resolved as facts",
                    "preprocessor expressions are reported as conditions; no macro expansion is performed",
                    "call chains are bounded and do not prove behavioural equivalence or safe removability",
                    "duplicate non-static symbols across architecture trees remain ambiguous unless a local definition resolves them",
                ],
            },
            "source": {
                "root": KERNEL_REL,
                "fingerprint_sha256": self.fingerprint,
                "fingerprint_algorithm": "sha256 over sorted 'path\\0file-sha256\\n' records",
                "files": file_records,
            },
            "configs": [
                {
                    "name": c["name"],
                    "kind": c.get("kind"),
                    "arch": c.get("arch"),
                    "target": c.get("target"),
                    "status": c.get("status"),
                    "config_path": c.get("config_path"),
                    "mkfile": c.get("mkfile"),
                    "roots": c.get("roots", []),
                    "object_stems": c.get("object_stems", []),
                    "active_files": c.get("active_files", []),
                    "unresolved_objects": c.get("unresolved_objects", []),
                    "shadowed_objects": c.get("shadowed_objects", []),
                    "whole_archives": c.get("whole_archives", []),
                    "bootdir": c.get("bootdir", []),
                    "notes": c.get("notes", []),
                }
                for c in self.configs
            ],
            "structs": {
                name: {
                    "fields": self.struct_fields[name],
                    "source": self.struct_sources.get(name),
                }
                for name in sorted(self.struct_fields)
            },
            "functions": function_index,
            "dynamic_directories": dynamic_directories,
            "graph": {
                "function_nodes": len(function_index),
                "resolved_direct_edges": direct_edge_count,
                "external_or_unresolved_direct_edges": external_edge_count,
                "indirect_edges": indirect_edges,
                "note": "Selected operation chains are stored once in chains[] and referenced by operations[].chain_id; full direct-edge lists are not duplicated here.",
            },
            "dirtab": sorted(self.dirtab_records, key=lambda r: (r["path"], r["line"], r["name"])),
            "cmdtab": sorted(self.cmdtab_records, key=lambda r: (r["path"], r["line"], r["name"])),
            "registrations": self.registration_records,
            "interface_candidates": {
                typ: {field: sorted(vals) for field, vals in sorted(fields.items())}
                for typ, fields in sorted(self.interface_candidates.items())
            },
            "operations": self.operations,
            "chains": {k: self.chains[k] for k in sorted(self.chains)},
            "native_entry_points": self.native_records,
            "representative_chains": self.representative,
            "coverage": coverage,
            "unresolved_work": unresolved,
        }
        return data


# ---------------------------------------------------------------------------
# Native-operation specification and generated C
#
# The generator is deliberately a consumer of Analyzer.analyze().  It does not
# tokenise a second time and it never rewrites source text.  Automatic code is
# emitted only from the small reviewed bindings above; every other active Dev
# operation is still described in the manifest, with an explicit refusal.


class NativeGenerationError(Exception):
    pass


def _file_record(data: dict[str, Any], path: str) -> dict[str, Any] | None:
    for rec in data.get("source", {}).get("files", []):
        if rec.get("path") == path:
            return rec
    return None


def _enum_expr_value(expr: str, known: dict[str, int]) -> int | None:
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None

    def ev(n: ast.AST) -> int:
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return int(n.value)
        if isinstance(n, ast.Name):
            if n.id not in known:
                raise ValueError(n.id)
            return known[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Invert)):
            v = ev(n.operand)
            if isinstance(n.op, ast.USub):
                return -v
            if isinstance(n.op, ast.Invert):
                return ~v
            return v
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return a // b
            if isinstance(n.op, ast.FloorDiv):
                return a // b
            if isinstance(n.op, ast.Mod):
                return a % b
            if isinstance(n.op, ast.LShift):
                return a << b
            if isinstance(n.op, ast.RShift):
                return a >> b
            if isinstance(n.op, ast.BitOr):
                return a | b
            if isinstance(n.op, ast.BitAnd):
                return a & b
            if isinstance(n.op, ast.BitXor):
                return a ^ b
        raise ValueError(type(n).__name__)

    try:
        return int(ev(node))
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def parse_enum_constants(tokens: Sequence[Token]) -> dict[str, int]:
    """Read simple integer enum constants from the existing token stream."""
    out: dict[str, int] = {}
    i = 0
    while i < len(tokens):
        if tokens[i].value != "enum":
            i += 1
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].value not in ("{", "}", ";"):
            j += 1
        if j >= len(tokens) or tokens[j].value != "{":
            i = j + 1
            continue
        close = find_matching(tokens, j, "{", "}")
        if close is None:
            break
        value = 0
        for seg in split_top_level(tokens[j + 1:close], ","):
            if not seg:
                continue
            name = seg[0].value
            if not re.match(r"^[A-Za-z_]\w*$", name):
                continue
            if len(seg) >= 3 and seg[1].value == "=":
                expr = " ".join(t.value for t in seg[2:])
                parsed = _enum_expr_value(expr, out)
                if parsed is None:
                    out.pop(name, None)
                    value = 0
                    continue
                value = parsed
            out[name] = value
            value += 1
        i = close + 1
    return out


def _macro_alias_risks(analyzer: Analyzer, path: str) -> list[str]:
    sf = analyzer.file_by_path.get(path)
    if sf is None:
        return []
    names = sorted(set(re.findall(
        r"^\s*#\s*define\s+(Chan|Mount|Path)\b", sf.masked, re.M
    )))
    return [
        f"source-local macro alias {name!r} is not proof of the kernel {name} type"
        for name in names
    ]


def _handler_function(analyzer: Analyzer, op: dict[str, Any]) -> Function | None:
    if op.get("handler", {}).get("path"):
        return analyzer._find_function(
            op["handler"].get("symbol"), op["handler"].get("path")
        )
    return analyzer._find_function(op.get("handler", {}).get("symbol"))


def _chan_dependencies(fn: Function | None) -> list[str]:
    if fn is None:
        return ["handler definition not found"]
    text = fn.text
    deps: set[str] = set()
    if re.search(r"\bChan\s*\*", fn.params):
        deps.add("Chan parameter")
    patterns = [
        (r"\bc\s*->\s*qid\b", "Chan Qid dispatch"),
        (r"\bc\s*->\s*aux\b", "Chan aux device state"),
        (r"\bc\s*->\s*flag\b", "Chan flags"),
        (r"\bc\s*->\s*mode\b", "Chan access mode"),
        (r"\bc\s*->\s*offset\b", "Chan offset"),
        (r"\bc\s*->\s*dev\b", "Chan device pointer"),
        (r"\bdevwalk\s*\(", "devwalk namespace helper"),
        (r"\bdevstat\s*\(", "devstat namespace helper"),
        (r"\bdevdirread\s*\(", "devdirread namespace helper"),
        (r"\bdevopen\s*\(", "devopen lifecycle helper"),
        (r"\bdevattach\s*\(", "devattach lifecycle helper"),
        (r"\bdevcreate\s*\(", "devcreate lifecycle helper"),
        (r"\bnamec\s*\(", "namec path traversal"),
        (r"\bwalk\s*\(", "walk path traversal"),
        (r"\bmount\s*\(", "mount namespace state"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text):
            deps.add(label)
    return sorted(deps)


def _backend_evidence(
    data: dict[str, Any], op: dict[str, Any], full: bool = False
) -> dict[str, Any]:
    chain = data.get("chains", {}).get(op.get("chain_id") or "", {})
    terminal = chain.get("terminal") or {}
    evidence = {
        "chain_id": op.get("chain_id"),
        "status": op.get("status"),
        "reason": op.get("reason"),
        "node_count": len(chain.get("nodes", [])),
        "terminal": {
            "kind": terminal.get("kind"),
            "symbol": terminal.get("symbol"),
            "line": terminal.get("line"),
            "path": terminal.get("path"),
            "candidates": sorted(terminal.get("candidates") or []),
            "reason": terminal.get("reason"),
        },
        "services": list(chain.get("service_symbols", [])),
    }
    if full:
        evidence["nodes"] = list(chain.get("nodes", []))
        evidence["responsibilities"] = list(chain.get("responsibilities", []))
    return evidence


def _semantics(callback: str | None) -> dict[str, Any]:
    cb = callback or "unknown"

    def rec(operation: str, shape: str, units: str) -> dict[str, Any]:
        return {"callback": cb, "operation": operation, "shape": shape, "units": units}

    if cb in ("read", "bread"):
        return rec("read", "byte stream or block", "offset, length")
    if cb in ("write", "bwrite"):
        return rec("write", "byte stream, block or textual control", "offset, length")
    if cb in ("walk",):
        return rec("walk", "directory/name traversal", "name list")
    if cb in ("stat", "wstat"):
        return rec("metadata", "Plan 9 Dir metadata", "serialised Dir bytes")
    if cb in ("open", "create", "close", "remove", "attach"):
        return rec("lifecycle", "device instance lifecycle", "mode/flags")
    if cb in ("init", "reset", "shutdown", "power", "config"):
        return rec("device lifecycle", "device state transition", "device-specific")
    return rec(cb, "control/lifecycle", "unspecified")


def _condition_info(
    data: dict[str, Any], reg: dict[str, Any], op: dict[str, Any], config: str
) -> dict[str, Any]:
    rec = _file_record(data, op.get("source", {}).get("path", "")) or {}
    conds: list[str] = []
    for c in list(reg.get("conditions", [])) + list(op.get("conditions", [])):
        if c and c not in conds:
            conds.append(c)
    parse = (rec.get("parse") or {}).get("status")
    return {
        "active_configs": list(op.get("active_configs", [])),
        "selected_config": config,
        "active_in_selected_config": config in op.get("active_configs", []),
        "preprocessor_conditions": conds,
        "ambiguous_alternatives": bool(conds),
        "source_parse_status": parse,
        "source_parse_reason": (rec.get("parse") or {}).get("reason"),
    }


RTC_PERMISSION_EVIDENCE = {
    "Qrtc": {
        "read": "any user",
        "write": "eve only",
        "open_read": "any user",
        "open_other": "eve only",
        "evidence": (
            "rtcopen Qrtc branch: strcmp(up->user, eve) != 0 && omode != OREAD "
            "raises Eperm; generated read passes OREAD, write passes OWRITE "
            "through openmode()"
        ),
    },
    "Qnvram": {
        "read": "eve only",
        "write": "eve only",
        "open": "eve only",
        "evidence": (
            "rtcopen Qnvram branch: strcmp(up->user, eve) != 0 raises Eperm; "
            "the generated predicate preserves that rule for read and write"
        ),
    },
}

RTC_OFFSET_EVIDENCE = {
    "read:Qrtc": (
        "readnum(off, buf, n, rtctime(), 12): offsets 0..11, out-of-range "
        "returns 0; no Chan offset is read"
    ),
    "read:Qnvram": (
        "off >= Nvsize returns 0; n is clamped to Nvsize-off; hardware "
        "address is off + Nvoff (128); Nvsize is the Dirtab length 256"
    ),
    "write:Qnvram": (
        "rtcwrite rejects off != 0 with Ebadarg before dispatch; n is clamped "
        "to Nvsize; hardware address is off + Nvoff (128)"
    ),
    "write:Qrtc": (
        "rtcwrite rejects off != 0; the remaining textual parsing, sec2rtc "
        "and BCD writes are not bound in E1"
    ),
}


def _permission_evidence(op: dict[str, Any], fn: Function | None) -> dict[str, Any]:
    driver = op.get("driver")
    qid = op.get("entry", {}).get("qid")
    callback = op.get("entry", {}).get("callback")
    if driver == "rtc" and qid in RTC_PERMISSION_EVIDENCE:
        return dict(RTC_PERMISSION_EVIDENCE[qid])
    text = fn.text if fn else ""
    if "Eperm" in text:
        return {
            "observed": "Eperm permission check present in handler",
            "branch_rule": "branch-specific policy not established",
            "evidence": "tokenised handler text contains Eperm",
        }
    return {
        "observed": "no explicit Eperm check observed in handler",
        "branch_rule": "not established",
        "callback": callback,
    }


def _offset_evidence(op: dict[str, Any], fn: Function | None) -> str:
    key = f"{op.get('entry', {}).get('callback')}:{op.get('entry', {}).get('qid')}"
    if op.get("driver") == "rtc" and key in RTC_OFFSET_EVIDENCE:
        return RTC_OFFSET_EVIDENCE[key]
    text = fn.text if fn else ""
    if re.search(r"\boff(?:set)?\b", text):
        return "handler mentions offset/length; semantic equivalence not established"
    return "no offset handling identified; equivalent bounds not established"


def _state_risks(
    analyzer: Analyzer,
    data: dict[str, Any],
    op: dict[str, Any],
    fn: Function | None,
    path: str,
) -> list[str]:
    chain = data.get("chains", {}).get(op.get("chain_id") or "", {})
    services = set(chain.get("service_symbols", []))
    text = fn.text if fn else ""
    callback = op.get("entry", {}).get("callback")
    risks: set[str] = set()
    if {"ilock", "iunlock"} & services or re.search(r"\b(ilock|iunlock|qlock|qunlock)\s*\(", text):
        risks.add("locking/resource serialisation")
    if re.search(r"\b(inb|outb|inl|outl|inw|outw)\s*\(", text):
        risks.add("hardware I/O (port/register or DMA-visible access)")
    if {"malloc", "free"} & services:
        risks.add("heap ownership")
    if any(s.startswith("q") for s in services) or re.search(r"\bq(open|close|hangup|reopen|read|write|setlimit)\s*\(", text):
        risks.add("queue/endpoint lifetime")
    if "waserror" in text or "postnote" in text:
        risks.add("Plan 9 error/note rollback")
    if "up->" in text:
        risks.add("process context (up)")
    if callback in ("open", "close", "create", "remove", "attach"):
        risks.add("device instance lifecycle")
    if op.get("conditions"):
        risks.add("conditional build")
    risks.update(_macro_alias_risks(analyzer, path))
    if op.get("driver") == "pipe":
        risks.add("dynamic endpoint ownership (Pipe ref/qref/c->aux)")
    return sorted(risks)


def _selector_info(
    data: dict[str, Any],
    op: dict[str, Any],
    enum_values: dict[str, int],
) -> dict[str, Any]:
    entry = op.get("entry", {})
    qid = entry.get("qid")
    if qid:
        tab_entry = None
        for tab in data.get("dirtab", []):
            if tab.get("path") != op.get("source", {}).get("path"):
                continue
            for item in tab.get("entries", []):
                if item.get("qid_symbol") == qid:
                    tab_entry = dict(item)
                    tab_entry["table"] = tab.get("name")
                    break
            if tab_entry is not None:
                break
        value = enum_values.get(qid)
        return {
            "kind": "qid",
            "symbol": qid,
            "value": value,
            "name": (tab_entry or {}).get("name"),
            "length": (tab_entry or {}).get("length"),
            "perm": (tab_entry or {}).get("perm"),
            "directory": bool(tab_entry and (
                "QTDIR" in (tab_entry.get("qid") or "")
                or (tab_entry.get("name") == ".")
            )),
            "dirtab": (tab_entry or {}).get("table"),
        }
    if entry.get("command"):
        return {
            "kind": "command",
            "command": entry.get("command"),
            "index": entry.get("command_index"),
            "narg": entry.get("narg"),
            "table": entry.get("table"),
        }
    return {"kind": "callback", "callback": entry.get("callback")}


def _generic_classification(
    data: dict[str, Any], op: dict[str, Any]
) -> tuple[str, str]:
    callback = op.get("entry", {}).get("callback")
    chain = data.get("chains", {}).get(op.get("chain_id") or "", {})
    terminal = chain.get("terminal") or {}
    reason = op.get("reason") or chain.get("reason") or "no conversion evidence"
    if op.get("kind") in ("control-command", "manual-control-command"):
        return ("MANUAL", "textual control command is not converted into a native selector entry")
    if callback in ("walk", "stat", "attach", "create", "remove", "wstat"):
        return (
            "LEGACY",
            "namespace/metadata/lifecycle implementation; not required by a pathless "
            "numeric-selector operation and not converted in E1",
        )
    if callback in ("read", "write", "bread", "bwrite"):
        if op.get("status") == "unresolved":
            return ("MANUAL", f"operation chain is unresolved: {reason}")
        if terminal.get("kind") in ("interface", "indirect-unresolved"):
            cands = ", ".join(terminal.get("candidates") or []) or "none"
            return (
                "MANUAL",
                "indirect callback target is not statically proven "
                f"(symbol {terminal.get('symbol')!r}, candidates: {cands})",
            )
        return (
            "MANUAL",
            "no reviewed Chan-free binding for this driver; automatic body "
            f"generation was not attempted (structural chain: {reason})",
        )
    if callback in ("open", "close"):
        return (
            "MANUAL",
            "open/close carries Chan lifecycle, permission and state; no reviewed "
            "native handle contract exists",
        )
    if callback in ("init", "reset", "shutdown", "power", "config"):
        return (
            "MANUAL",
            "device lifecycle hook is outside the pathless selector operation and "
            "is not converted in E1",
        )
    return ("MANUAL", f"no reviewed native binding; {reason}")


def _binding_key(op: dict[str, Any]) -> str:
    entry = op.get("entry", {})
    callback = entry.get("callback")
    if entry.get("qid"):
        return f"{callback}:{entry['qid']}"
    if entry.get("command"):
        return f"{callback}:cmd:{entry['command']}"
    return f"{callback}:*"


def _build_driver_selectors(
    binding: dict[str, Any],
    data: dict[str, Any],
    enum_values: dict[str, int],
) -> list[dict[str, Any]]:
    expected = binding.get("selector_values", {})
    selectors: list[dict[str, Any]] = []
    for symbol, value in expected.items():
        if enum_values.get(symbol) != value:
            raise NativeGenerationError(
                f"{binding['driver']}: selector {symbol} is {enum_values.get(symbol)!r} "
                f"in the parsed enum, expected {value!r}; reviewed binding is stale"
            )
        found = None
        for tab in data.get("dirtab", []):
            if tab.get("name") != binding.get("dirtab"):
                continue
            if (tab.get("path") or "").rsplit("/", 1)[-1] != (
                binding.get("source_path", "").rsplit("/", 1)[-1]
            ):
                continue
            for item in tab.get("entries", []):
                if item.get("qid_symbol") == symbol:
                    found = item
                    break
            if found is not None:
                break
        if found is None:
            raise NativeGenerationError(
                f"{binding['driver']}: selector {symbol} is not in Dirtab "
                f"{binding.get('dirtab')!r}; reviewed binding is stale"
            )
        selectors.append({
            "symbol": symbol,
            "value": value,
            "name": found.get("name"),
            "length": found.get("length"),
            "perm": found.get("perm"),
            "directory": "QTDIR" in (found.get("qid") or "") or found.get("name") == ".",
        })
    selectors.sort(key=lambda s: (s["value"], s["symbol"]))
    return selectors



NATIVE_CAST_TYPES = {
    "char", "uchar", "short", "ushort", "int", "uint", "long", "ulong",
    "vlong", "uvlong", "u8int", "u16int", "u32int", "u64int", "s8int",
    "s16int", "s32int", "s64int", "usize", "uintptr", "intptr",
}


def _norm_params(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace(" *", "*").replace("* ", "*").strip()


def _global_enum_constants(analyzer: Analyzer) -> dict[str, int]:
    """Enum constants from scanned headers; conflicting names are omitted."""
    values: dict[str, int] = {}
    conflicts: set[str] = set()
    for sf in analyzer.files:
        if sf.kind != "header" or not sf.tokens:
            continue
        try:
            parsed = parse_enum_constants(sf.tokens)
        except Exception:
            continue
        for name, value in parsed.items():
            if name in values and values[name] != value:
                conflicts.add(name)
            else:
                values.setdefault(name, value)
    for name in conflicts:
        values.pop(name, None)
    return values


def _c_int_literal(raw: str) -> int | None:
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        if raw.startswith("0") and len(raw) > 1:
            return int(raw, 8)
        return int(raw, 10)
    except ValueError:
        return None


def _split_statements(body: Sequence[Token]) -> list[list[Token]]:
    """Split a narrow helper body into top-level statements."""
    out: list[list[Token]] = []
    i = 0
    while i < len(body):
        if body[i].value in (";", "}"):
            i += 1
            continue
        start = i
        if body[i].value == "if":
            if i + 1 >= len(body) or body[i + 1].value != "(":
                raise NativeGenerationError("unsupported if without parenthesised condition")
            close = find_matching(body, i + 1, "(", ")")
            if close is None:
                raise NativeGenerationError("unterminated if condition")
            k = close + 1
            if k >= len(body):
                raise NativeGenerationError("if without a statement")
            if body[k].value == "{":
                end = find_matching(body, k, "{", "}")
                if end is None:
                    raise NativeGenerationError("unterminated if block")
                out.append(list(body[start:end + 1]))
                i = end + 1
                continue
            end = scan_to_semicolon(body, k)
            if end is None:
                raise NativeGenerationError("unterminated if statement")
            out.append(list(body[start:end + 1]))
            i = end + 1
            continue
        end = scan_to_semicolon(body, i)
        if end is None:
            raise NativeGenerationError("unterminated statement in native helper")
        out.append(list(body[start:end + 1]))
        i = end + 1
    return out


def _strip_leading_casts(tokens: Sequence[Token]) -> list[Token]:
    toks = list(tokens)
    while (
        len(toks) >= 3
        and toks[0].value == "("
        and toks[1].kind == "id"
        and toks[1].value in NATIVE_CAST_TYPES
        and toks[2].value == ")"
    ):
        toks = toks[3:]
    return toks


def _expr_is_name(tokens: Sequence[Token], name: str) -> bool:
    toks = _strip_leading_casts(tokens)
    return len(toks) == 1 and toks[0].kind == "id" and toks[0].value == name


def _expr_is_off(tokens: Sequence[Token], local: str | None) -> bool:
    toks = _strip_leading_casts(tokens)
    if len(toks) != 1 or toks[0].kind != "id":
        return False
    return toks[0].value == "off" or (local is not None and toks[0].value == local)


def _parse_guard(stmt: Sequence[Token]) -> dict[str, Any] | None:
    if not stmt or stmt[0].value != "if":
        return None
    if len(stmt) < 5 or stmt[1].value != "(":
        return None
    close = find_matching(stmt, 1, "(", ")")
    if close is None:
        return None
    cond = "".join(t.value for t in stmt[2:close])
    body = list(stmt[close + 1:])
    if body and body[0].value == "{":
        end = find_matching(body, 0, "{", "}")
        if end is None:
            return None
        body = body[1:end]
    if len(body) != 3 or body[0].value != "return" or body[1].value != "n" or body[2].value != ";":
        return None
    accepted = {
        "n<=0": "n <= 0",
        "n<1": "n < 1",
        "n==0": "n == 0",
        "0>=n": "0 >= n",
        "1>n": "1 > n",
        "0==n": "0 == n",
    }
    if cond not in accepted:
        return None
    return {"condition": accepted[cond], "returns": "n", "text": f"if({accepted[cond]}) return n;"}


def _match_call(tokens: Sequence[Token], name: str) -> list[list[Token]] | None:
    if not tokens or tokens[0].value != name:
        return None
    if len(tokens) < 2 or tokens[1].value != "(":
        return None
    close = find_matching(tokens, 1, "(", ")")
    if close != len(tokens) - 1:
        return None
    return call_args(tokens, 1)


def _validate_value_expr(
    tokens: Sequence[Token],
    allowed_calls: Sequence[str],
    allowed_idents: Sequence[str],
) -> str:
    if not tokens:
        raise NativeGenerationError("empty readnum value expression")
    work = _strip_leading_casts(tokens)
    if not work:
        raise NativeGenerationError("readnum value expression is only a cast")
    calls = set(allowed_calls)
    idents = set(allowed_idents)
    rest: list[Token] = []
    i = 0
    while i < len(work):
        t = work[i]
        if t.kind == "id" and i + 1 < len(work) and work[i + 1].value == "(":
            if t.value not in calls:
                raise NativeGenerationError(
                    f"readnum value expression calls unreviewed {t.value!r}"
                )
            if i > 0 and work[i - 1].value in ("->", "."):
                raise NativeGenerationError("member/indirect call in readnum value expression")
            close = find_matching(work, i + 1, "(", ")")
            if close is None:
                raise NativeGenerationError("unterminated call in readnum value expression")
            i = close + 1
            continue
        rest.append(t)
        i += 1
    for t in rest:
        if t.kind == "id":
            if t.value not in idents:
                raise NativeGenerationError(
                    f"readnum value identifier {t.value!r} is not reviewed"
                )
        elif t.kind == "num":
            continue
        elif t.value in ("->", "."):
            continue
        else:
            raise NativeGenerationError(
                f"unsupported token {t.raw!r} in readnum value expression"
            )
    if not rest and not calls:
        raise NativeGenerationError("readnum value expression has no value")
    return join_tokens(tokens)


def _validate_size_expr(
    tokens: Sequence[Token],
    allowed_constants: dict[str, int],
    global_enums: dict[str, int],
) -> tuple[str, int]:
    toks = _strip_leading_casts(tokens)
    if len(toks) == 1 and toks[0].kind == "num":
        value = _c_int_literal(toks[0].raw)
        if value is None:
            raise NativeGenerationError(f"unsupported readnum size literal {toks[0].raw!r}")
    elif len(toks) == 1 and toks[0].kind == "id" and toks[0].value in allowed_constants:
        name = toks[0].value
        value = global_enums.get(name)
        if value is None or value != allowed_constants[name]:
            raise NativeGenerationError(
                f"readnum size constant {name} is not the reviewed value "
                f"{allowed_constants[name]!r} (parsed {value!r})"
            )
    else:
        raise NativeGenerationError("readnum size is not a literal or reviewed constant")
    return join_tokens(tokens), value


def _find_case(handler: Function, selector: str) -> tuple[CaseLabel, Switch]:
    matches: list[tuple[CaseLabel, Switch]] = []
    for sw in handler.switches:
        if "qid" not in sw.condition.lower():
            continue
        for case in sw.cases:
            if case.label == selector:
                matches.append((case, sw))
    if not matches:
        raise NativeGenerationError(
            f"selector {selector} has no visible Qid switch case in {handler.name}"
        )
    if len(matches) > 1:
        raise NativeGenerationError(
            f"selector {selector} has {len(matches)} Qid switch cases in {handler.name}"
        )
    return matches[0]


def _validate_branch_call(case_tokens: Sequence[Token], helper: str) -> str:
    stmts = _split_statements(case_tokens)
    if len(stmts) != 1:
        raise NativeGenerationError(
            f"selected branch must contain exactly one statement, found {len(stmts)}"
        )
    stmt = stmts[0]
    if not stmt or stmt[0].value != "return":
        raise NativeGenerationError("selected branch is not a direct return")
    expr = stmt[1:-1]
    args = _match_call(expr, helper)
    if args is None:
        raise NativeGenerationError(
            f"selected branch does not return the reviewed helper {helper!r}"
        )
    if len(args) != 3 or not _expr_is_name(args[0], "buf") \
            or not _expr_is_name(args[1], "n") or not _expr_is_off(args[2], None):
        raise NativeGenerationError(
            f"selected branch does not call {helper}(buf, n, off)"
        )
    return join_tokens(stmt)


def _find_pre_dispatch_guard(handler: Function, switch_start: int) -> dict[str, Any] | None:
    pre = list(handler.body[:switch_start])
    for i in range(len(pre) - 1, -1, -1):
        if pre[i].value == "switch":
            pre = pre[:i]
            break
    try:
        stmts = _split_statements(pre)
    except NativeGenerationError:
        return None
    found = None
    for stmt in stmts:
        if not stmt or stmt[0].value != "if":
            continue
        guard = _parse_guard(stmt)
        if guard is not None:
            if found is not None:
                raise NativeGenerationError(
                    f"{handler.name}: multiple n guards before Qid dispatch"
                )
            found = guard
    return found


def _native_const_name(driver: str, selector: str) -> str:
    text = f"{driver}_{selector}".upper()
    return re.sub(r"[^A-Z0-9]+", "_", text).strip("_")


def _native_symbol(driver: str, selector: str) -> str:
    text = f"{driver}_{selector}".lower()
    return "native_" + re.sub(r"[^a-z0-9]+", "_", text).strip("_") + "_read"


def _native_read_dispatch(driver: str) -> str:
    return "native_" + re.sub(r"[^a-z0-9]+", "_", driver.lower()).strip("_") + "_read"


def _extract_readnum_operation(
    analyzer: Analyzer,
    data: dict[str, Any],
    path: str,
    binding_op: dict[str, Any],
    op: dict[str, Any],
    selector: str,
    global_enums: dict[str, int],
) -> dict[str, Any]:
    helper_name = binding_op.get("helper")
    if not helper_name:
        raise NativeGenerationError(f"{path}: readnum binding has no helper")
    fn = analyzer._find_function(helper_name, path)
    if fn is None:
        raise NativeGenerationError(
            f"{path}: reviewed helper {helper_name!r} was not found"
        )
    if fn.static:
        raise NativeGenerationError(
            f"{path}: helper {helper_name!r} is static and cannot be linked by generated C"
        )
    if not fn.text.startswith("long "):
        raise NativeGenerationError(
            f"{path}: helper {helper_name!r} does not return long"
        )
    params = _norm_params(fn.params)
    if params != "void*buf, long n, vlong off":
        raise NativeGenerationError(
            f"{path}: helper {helper_name!r} signature is {fn.params!r}; "
            "expected void *buf, long n, vlong off"
        )

    guard = None
    local_offset = None
    readnum_args: list[list[Token]] | None = None
    assigned = False
    return_shape = None
    for stmt in _split_statements(fn.body):
        if not stmt:
            continue
        first = stmt[0].value
        if first == "if":
            if readnum_args is not None:
                raise NativeGenerationError(
                    f"{helper_name}: control flow after readnum is not supported"
                )
            parsed = _parse_guard(stmt)
            if parsed is None:
                raise NativeGenerationError(
                    f"{helper_name}: unsupported if statement in native helper"
                )
            if guard is not None:
                raise NativeGenerationError(f"{helper_name}: duplicate n guard")
            guard = parsed
            continue
        if first == "return":
            if len(stmt) < 2:
                raise NativeGenerationError(f"{helper_name}: empty return is not supported")
            expr = stmt[1:-1]
            args = _match_call(expr, "readnum")
            if args is not None:
                if readnum_args is not None or assigned:
                    raise NativeGenerationError(
                        f"{helper_name}: multiple readnum results are not supported"
                    )
                readnum_args = args
                return_shape = "direct-return"
            elif assigned and _expr_is_name(expr, "n"):
                return_shape = "assign-return"
            else:
                raise NativeGenerationError(
                    f"{helper_name}: unsupported return expression in native helper"
                )
            continue
        if first in ("goto", "switch", "for", "while", "do", "break", "continue", "else"):
            raise NativeGenerationError(
                f"{helper_name}: unsupported control flow {first!r} in native helper"
            )
        eq = None
        depth = 0
        for idx, t in enumerate(stmt):
            if t.value in ("(", "[", "{"):
                depth += 1
            elif t.value in (")", "]", "}"):
                depth = max(0, depth - 1)
            elif t.value == "=" and depth == 0:
                eq = idx
                break
        if eq is None or eq < 1:
            raise NativeGenerationError(
                f"{helper_name}: unsupported statement in native helper"
            )
        lhs = stmt[:eq]
        rhs = stmt[eq + 1:-1]
        target = None
        for t in reversed(lhs):
            if t.kind == "id":
                target = t.value
                break
        if target is None:
            raise NativeGenerationError(f"{helper_name}: assignment without a target")
        if readnum_args is not None:
            raise NativeGenerationError(
                f"{helper_name}: assignment after readnum is not supported"
            )
        if target == "n":
            args = _match_call(rhs, "readnum")
            if args is None:
                raise NativeGenerationError(
                    f"{helper_name}: n is assigned from an unreviewed expression"
                )
            if assigned:
                raise NativeGenerationError(f"{helper_name}: duplicate readnum assignment")
            readnum_args = args
            assigned = True
        elif target == "offset":
            if local_offset is not None:
                raise NativeGenerationError(f"{helper_name}: duplicate offset local")
            if not _expr_is_off(rhs, None):
                raise NativeGenerationError(
                    f"{helper_name}: offset local is not initialised from off"
                )
            local_offset = target
        else:
            raise NativeGenerationError(
                f"{helper_name}: unsupported local assignment to {target!r}"
            )

    if readnum_args is None or return_shape is None:
        raise NativeGenerationError(
            f"{helper_name}: no supported readnum return shape found"
        )
    if len(readnum_args) != 5:
        raise NativeGenerationError(
            f"{helper_name}: readnum takes {len(readnum_args)} arguments, expected 5"
        )
    if not _expr_is_off(readnum_args[0], local_offset):
        raise NativeGenerationError(
            f"{helper_name}: readnum offset is not off/the reviewed local"
        )
    if not _expr_is_name(readnum_args[1], "buf"):
        raise NativeGenerationError(f"{helper_name}: readnum buffer is not buf")
    if not _expr_is_name(readnum_args[2], "n"):
        raise NativeGenerationError(f"{helper_name}: readnum length is not n")
    value_expr = _validate_value_expr(
        readnum_args[3],
        binding_op.get("allowed_calls", []),
        binding_op.get("allowed_idents", []),
    )
    size_expr, size_value = _validate_size_expr(
        readnum_args[4],
        binding_op.get("allowed_constants", {}),
        global_enums,
    )

    lowered = fn.text.lower()
    for bad in ("chan", "qid", "dirtab", "devwalk", "devdirread", "namec", "c->"):
        if bad in lowered:
            raise NativeGenerationError(
                f"{helper_name}: helper text contains forbidden {bad!r}"
            )

    handler = _handler_function(analyzer, op)
    if handler is None:
        raise NativeGenerationError(
            f"{path}: Dev handler for {selector} was not found"
        )
    if fn.conditions:
        raise NativeGenerationError(
            f"{helper_name}: helper is inside preprocessor conditions {list(fn.conditions)!r}"
        )
    if handler.conditions:
        raise NativeGenerationError(
            f"{handler.name}: handler is inside preprocessor conditions {list(handler.conditions)!r}"
        )
    if not binding_op.get("authorization"):
        raise NativeGenerationError(
            f"{helper_name}: binding has no explicit authorization contract"
        )
    if binding_op.get("require_up") and not re.search(r"\bup\b", fn.text):
        raise NativeGenerationError(
            f"{helper_name}: binding requires up but helper does not use it"
        )
    case, switch = _find_case(handler, selector)
    branch_call = _validate_branch_call(handler.body[case.start:case.end], helper_name)
    entry_guard = _find_pre_dispatch_guard(handler, switch.start)

    driver = op.get("driver") or ""
    symbol = _native_symbol(driver, selector)
    const = _native_const_name(driver, selector)
    return {
        "rule": "readnum",
        "helper": helper_name,
        "helper_line": fn.line,
        "helper_params": "void *buf, long n, vlong off",
        "helper_return": "long",
        "value_expression": value_expr,
        "size_expression": size_expr,
        "size_value": size_value,
        "offset_expression": join_tokens(readnum_args[0]),
        "return_shape": return_shape,
        "guard": guard,
        "entry_guard": entry_guard,
        "branch_call": branch_call,
        "branch_line": case.line,
        "handler": handler.name,
        "handler_line": handler.line,
        "generated_symbol": symbol,
        "dispatcher_symbol": _native_read_dispatch(driver),
        "selector_constant": "NATIVE_" + const,
        "size_constant": "NATIVE_" + const + "_SIZE",
        "authorization": binding_op.get("authorization", "not stated"),
        "context": list(binding_op.get("context", [])),
        "require_up": bool(binding_op.get("require_up", False)),
        "allowed_calls": list(binding_op.get("allowed_calls", [])),
        "allowed_idents": list(binding_op.get("allowed_idents", [])),
    }


def build_native_spec(
    analyzer: Analyzer,
    data: dict[str, Any],
    config: str = NATIVE_DEFAULT_CONFIG,
    bindings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bindings = NATIVE_REVIEWED_BINDINGS if bindings is None else bindings
    config_names = {c.get("name") for c in data.get("configs", [])}
    if config not in config_names:
        raise NativeGenerationError(f"build config {config!r} was not discovered")

    active_paths = {
        f["path"]
        for f in data.get("source", {}).get("files", [])
        if (f.get("build") or {}).get(config) == "active"
    }
    file_records = {
        f["path"]: f for f in data.get("source", {}).get("files", [])
    }
    global_enums = _global_enum_constants(analyzer)

    # Validate the reviewed bindings against the same parsed tree first.
    binding_state: dict[str, dict[str, Any]] = {}
    for path, binding in sorted(bindings.items()):
        rec = file_records.get(path)
        if rec is None:
            raise NativeGenerationError(
                f"reviewed binding source not found in analysed tree: {path}"
            )
        if rec.get("sha256") != binding.get("sha256"):
            raise NativeGenerationError(
                f"reviewed binding is stale for {path}: source SHA-256 is "
                f"{rec.get('sha256')}, binding expects {binding.get('sha256')}"
            )
        sf = analyzer.file_by_path.get(path)
        if sf is None:
            raise NativeGenerationError(f"parser has no source record for {path}")
        enum_values = parse_enum_constants(sf.tokens)
        for name, value in binding.get("constants", {}).items():
            if enum_values.get(name) != value:
                raise NativeGenerationError(
                    f"{binding.get('driver')}: constant {name} is "
                    f"{enum_values.get(name)!r}, expected {value!r}"
                )
        driver_binding = dict(binding)
        driver_binding["source_path"] = path
        driver_binding["selectors"] = _build_driver_selectors(
            driver_binding, data, enum_values
        )
        driver_binding["enum_values"] = enum_values
        binding_state[path] = driver_binding

    drivers: list[dict[str, Any]] = []
    binding_keys_seen: dict[str, set[str]] = {p: set() for p in bindings}

    for reg in data.get("registrations", []):
        if reg.get("type") != "Dev":
            continue
        path = reg.get("path")
        if path not in active_paths:
            continue
        rec = file_records.get(path) or {}
        sf = analyzer.file_by_path.get(path)
        enum_values = parse_enum_constants(sf.tokens) if sf else {}
        ops = [
            o for o in data.get("operations", [])
            if o.get("registration_id") == reg.get("id")
        ]
        binding = binding_state.get(path)
        op_records: list[dict[str, Any]] = []
        for op in ops:
            key = _binding_key(op)
            fn = _handler_function(analyzer, op)
            binding_op = (binding or {}).get("operations", {}).get(key)
            native = None
            generated_symbol = None
            if binding_op is not None:
                binding_keys_seen[path].add(key)
                conversion = binding_op["conversion"]
                reason = binding_op["reason"]
                if conversion == "DIRECT":
                    if binding_op.get("kind") != "readnum":
                        raise NativeGenerationError(
                            f"{binding.get('driver')}: DIRECT {key} does not use "
                            "the generic readnum rule"
                        )
                    selector_symbol = op.get("entry", {}).get("qid")
                    if not selector_symbol:
                        raise NativeGenerationError(
                            f"{binding.get('driver')}: {key} is not a Qid read"
                        )
                    native = _extract_readnum_operation(
                        analyzer, data, path, binding_op, op,
                        selector_symbol, global_enums,
                    )
                    generated_symbol = native["generated_symbol"]
                elif binding_op.get("kind") == "readnum":
                    raise NativeGenerationError(
                        f"{binding.get('driver')}: {key} has a readnum binding "
                        "but is not marked DIRECT"
                    )
            else:
                conversion, reason = _generic_classification(data, op)
            entry_deps = _chan_dependencies(fn)
            if conversion == "DIRECT":
                branch_deps = {
                    "chan": [],
                    "path": [],
                    "note": (
                        "reviewed selected branch only; the generated entry takes "
                        "a numeric selector, buffer, length and offset, not a Chan"
                    ),
                }
            else:
                branch_deps = {
                    "chan": entry_deps,
                    "path": [],
                    "note": "branch-specific independence not established",
                }
            selector = _selector_info(data, op, enum_values)
            source_mapping = {
                "path": op.get("source", {}).get("path"),
                "line": op.get("source", {}).get("line"),
                "function": op.get("handler", {}).get("symbol"),
                "function_line": op.get("handler", {}).get("line"),
                "sha256": rec.get("sha256"),
            }
            if native is not None:
                source_mapping.update({
                    "helper": native["helper"],
                    "helper_line": native["helper_line"],
                    "branch_line": native["branch_line"],
                    "branch_call": native["branch_call"],
                })
            op_records.append({
                "id": op.get("id"),
                "kind": op.get("kind"),
                "source": source_mapping,
                "device": {
                    "driver": reg.get("name"),
                    "char": reg.get("dc"),
                    "syntax": op.get("entry", {}).get("device_syntax"),
                },
                "selector": selector,
                "semantics": _semantics(op.get("entry", {}).get("callback")),
                "conditional": _condition_info(data, reg, op, config),
                "backend": _backend_evidence(
                    data, op, full=(conversion == "DIRECT")
                ),
                "dependencies": {
                    "entry_chan": entry_deps,
                    "selected_branch": branch_deps,
                },
                "permissions": _permission_evidence(op, fn),
                "authorization": (
                    native["authorization"] if native is not None
                    else "kernel-internal-only; no generated native entry"
                ),
                "offsets": _offset_evidence(op, fn),
                "state_risks": _state_risks(analyzer, data, op, fn, path or ""),
                "lifecycle": (
                    "kernel-internal-only; no persistent native handle in E2; "
                    "caller supplies selector and offset"
                    if conversion == "DIRECT"
                    else "current implementation is tied to Chan/device lifecycle; "
                         "native lifetime contract not established"
                ),
                "conversion": conversion,
                "reasons": [reason],
                "generated_symbol": generated_symbol,
                "native": native,
            })

        # A binding that does not match an actual parsed operation is stale.
        if binding is not None:
            missing = sorted(set(binding.get("operations", {})) - binding_keys_seen[path])
            if missing:
                raise NativeGenerationError(
                    f"{binding.get('driver')}: reviewed operations were not found in "
                    f"the parsed operation list: {', '.join(missing)}"
                )

        detail = (
            any(o.get("native") is not None for o in op_records)
            or reg.get("name") in NATIVE_DRIVER_NOTES
        )
        if not detail:
            # Compact refusal record for analysis-only drivers: status and
            # evidence remain inspectable without duplicating the full
            # backend/lifecycle schema for hundreds of unconverted operations.
            op_records = [{
                "id": o.get("id"),
                "kind": o.get("kind"),
                "source": {
                    "path": o.get("source", {}).get("path"),
                    "line": o.get("source", {}).get("line"),
                    "function": o.get("source", {}).get("function"),
                    "function_line": o.get("source", {}).get("function_line"),
                },
                "selector": o.get("selector"),
                "semantics": o.get("semantics"),
                "conditional": {
                    "active_in_selected_config":
                        (o.get("conditional") or {}).get("active_in_selected_config"),
                    "preprocessor_conditions":
                        (o.get("conditional") or {}).get("preprocessor_conditions"),
                    "ambiguous_alternatives":
                        (o.get("conditional") or {}).get("ambiguous_alternatives"),
                },
                "backend": {
                    "chain_id": (o.get("backend") or {}).get("chain_id"),
                    "status": (o.get("backend") or {}).get("status"),
                    "reason": (o.get("backend") or {}).get("reason"),
                },
                "state_risks": o.get("state_risks"),
                "conversion": o.get("conversion"),
                "reasons": o.get("reasons"),
                "generated_symbol": o.get("generated_symbol"),
            } for o in op_records]
        counts = {"DIRECT": 0, "BRIDGE": 0, "MANUAL": 0, "LEGACY": 0}
        for op in op_records:
            counts[op["conversion"]] = counts.get(op["conversion"], 0) + 1
        note = NATIVE_DRIVER_NOTES.get(reg.get("name"), {})
        driver = {
            "registration_id": reg.get("id"),
            "driver": reg.get("name"),
            "device_char": reg.get("dc"),
            "path": path,
            "sha256": rec.get("sha256"),
            "active_configs": sorted(
                c.get("name") for c in data.get("configs", [])
                if (rec.get("build") or {}).get(c.get("name")) == "active"
            ),
            "pilot": path in bindings,
            "detail": detail,
            "generated_files": [],
            "classification": (
                "DIRECT-PARTIAL" if counts["DIRECT"] and counts["MANUAL"]
                else "DIRECT" if counts["DIRECT"]
                else "MANUAL"
            ) if counts["DIRECT"] else ("MANUAL" if counts["MANUAL"] else "LEGACY"),
            "counts": counts,
            "blockers": list(note.get("blockers", [])),
            "reason": note.get("reason"),
            "operations": op_records,
        }
        drivers.append(driver)

    # Generated files are attached to the pilot driver record.
    selectors = {
        state["driver"]: state["selectors"] for state in binding_state.values()
    }
    constants = {
        state["driver"]: {
            "source_path": state["source_path"],
            "values": state["constants"],
        }
        for state in binding_state.values()
    }
    for driver in drivers:
        if driver["path"] in binding_state:
            state = binding_state[driver["path"]]
            if any(o.get("native") is not None for o in driver["operations"]):
                driver["generated_files"] = ["kernel_native.h", "kernel_native.c"]
            driver["selectors"] = state["selectors"]
            driver["source_constants"] = state["constants"]

    conversion_totals = {"DIRECT": 0, "BRIDGE": 0, "MANUAL": 0, "LEGACY": 0}
    for driver in drivers:
        for key, value in driver["counts"].items():
            conversion_totals[key] = conversion_totals.get(key, 0) + value

    source_refusals = []
    for path in sorted(active_paths):
        rec = file_records.get(path) or {}
        parse = rec.get("parse") or {}
        if parse.get("status") not in (None, "ok"):
            source_refusals.append({
                "path": path,
                "parse_status": parse.get("status"),
                "reason": parse.get("reason"),
                "line": parse.get("line"),
                "sha256": rec.get("sha256"),
            })

    spec = {
        "schema": NATIVE_SCHEMA,
        "generator": {
            "name": GENERATOR,
            "version": NATIVE_GENERATOR_VERSION,
            "command": (
                "python3 tools/kernel_opmap.py --generate-native "
                f"--config {config} --out-dir {NATIVE_DEFAULT_OUT}"
            ),
            "limitations": [
                "lexical/structural frontend reused from Analyzer.analyze(); not a compiler",
                "automatic C is emitted only for reviewed, hash-pinned bindings",
                "all other operations are described and refused in the manifest",
                "no macro expansion, preprocessed typed AST or semantic-equivalence proof",
                "compiled generated C is not by itself proof of equivalent operation, permissions, resource lifetime or IRQ/DMA behaviour",
            ],
        },
        "config": config,
        "source": {
            "root": KERNEL_REL,
            "fingerprint_sha256": data.get("source", {}).get("fingerprint_sha256"),
            "commit": analyzer.source_revision.get("commit"),
            "kernel_tree_dirty": analyzer.source_revision.get("kernel_tree_dirty"),
        },
        "selectors": selectors,
        "constants": constants,
        "source_refusals": source_refusals,
        "drivers": drivers,
        "summary": {
            "active_dev_registrations": len(drivers),
            "operations": sum(len(d["operations"]) for d in drivers),
            "conversion": conversion_totals,
            "generated_drivers": [
                d["driver"] for d in drivers if d["generated_files"]
            ],
            "analysis_only_drivers": [
                d["driver"] for d in drivers if not d["generated_files"]
            ],
        },
        "unsupported_constructs": [
            "directory walk and name traversal (devwalk/devdirread/namec)",
            "Chan state fields (qid, aux, flag, mode, offset, dev)",
            "indirect callbacks without a unique proven target",
            "alternative preprocessor branches and macro aliases",
            "dynamic handle/endpoint lifetime (pipe queues, mount and 9P transports)",
            "device init/reset/shutdown and interrupt/DMA ownership",
        ],
    }
    return spec


def _provenance(spec: dict[str, Any], source_path: str) -> str:
    src = spec.get("source", {})
    rec = None
    for driver in spec.get("drivers", []):
        if driver.get("path") == source_path:
            rec = driver
            break
    return (
        "/*\n"
        f" * Generated by {GENERATOR} --generate-native.  Do not edit.\n"
        f" * Config: {spec.get('config')}\n"
        f" * Source: {source_path}\n"
        f" * Source SHA-256: {(rec or {}).get('sha256')}\n"
        f" * Source commit: {src.get('commit')}\n"
        f" * Kernel fingerprint: {src.get('fingerprint_sha256')}\n"
        " * This file is generated under build/ and is NOT part of the kernel build.\n"
        " */\n"
    )


def _native_operations(spec: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for driver in spec.get("drivers", []):
        for op in driver.get("operations", []):
            if op.get("native") is not None:
                out.append((driver, op))
    out.sort(key=lambda item: (
        item[0].get("driver") or "", item[1]["native"].get("selector_constant") or ""
    ))
    return out


def _native_driver_operations(
    spec: dict[str, Any],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    driver_by_name: dict[str, dict[str, Any]] = {}
    for driver, op in _native_operations(spec):
        name = driver.get("driver") or ""
        grouped.setdefault(name, []).append(op)
        driver_by_name[name] = driver
    return [(driver_by_name[name], grouped[name]) for name in sorted(grouped)]


def _native_provenance(spec: dict[str, Any]) -> str:
    src = spec.get("source", {})
    lines = [
        "/*",
        f" * Generated by {GENERATOR} --generate-native.  Do not edit.",
        f" * Config: {spec.get('config')}",
        f" * Source commit: {src.get('commit')}",
        f" * Kernel fingerprint: {src.get('fingerprint_sha256')}",
    ]
    for driver in spec.get("drivers", []):
        if not any(o.get("native") is not None for o in driver.get("operations", [])):
            continue
        lines.append(
            f" * Source: {driver.get('path')} SHA-256: {driver.get('sha256')}"
        )
    lines.extend([
        " * Generated code is opt-in, lives under build/ and is not part of the normal kernel build.",
        " */",
    ])
    return "\n".join(lines) + "\n"


def render_native_header(spec: dict[str, Any]) -> str:
    ops = _native_operations(spec)
    if not ops:
        raise NativeGenerationError("no generated native read operations")
    lines = [
        _native_provenance(spec).rstrip("\n"),
        "",
        "#ifndef PLAN2001_KERNEL_NATIVE_H",
        "#define PLAN2001_KERNEL_NATIVE_H",
        "",
        "/* Include \"u.h\" before this header; Plan 9 u.h has no include guard. */",
        "",
        "/* Numeric selectors derived from the reviewed enum/Dirtab mapping. */",
        "enum {",
    ]
    seen_const: set[str] = set()
    for _, op in ops:
        native = op["native"]
        const = native["selector_constant"]
        selector = op.get("selector") or {}
        value = selector.get("value")
        if value is None:
            raise NativeGenerationError(
                f"selector {selector.get('symbol')} has no numeric value"
            )
        if const not in seen_const:
            lines.append(f"\t{const} = {value},")
            seen_const.add(const)
    lines.extend(["};", "", "enum {"])
    seen_size: set[str] = set()
    for _, op in ops:
        native = op["native"]
        if native["size_constant"] in seen_size:
            continue
        lines.append(f"\t{native['size_constant']} = {native['size_value']},")
        seen_size.add(native["size_constant"])
    lines.extend(["};", "", "/* Reviewed Chan-free helpers implemented in the driver sources. */"])
    seen_helper: set[str] = set()
    for _, op in ops:
        helper = op["native"]["helper"]
        if helper in seen_helper:
            continue
        lines.append(f"long\t{helper}(void*, long, vlong);")
        seen_helper.add(helper)
    lines.extend(["", "/* Generic generated read entries. */"])
    for _, op in ops:
        native = op["native"]
        lines.append(f"long\t{native['generated_symbol']}(void*, long, vlong);")
    lines.extend(["", "/* Per-driver selector dispatch; kernel-internal only. */"])
    seen_dispatch: set[str] = set()
    for _, op in ops:
        native = op["native"]
        disp = native["dispatcher_symbol"]
        if disp in seen_dispatch:
            continue
        lines.append(f"long\t{disp}(ulong, void*, long, vlong);")
        seen_dispatch.add(disp)
    lines.extend(["", "#endif", ""])
    return "\n".join(lines)


def render_native_source(spec: dict[str, Any]) -> str:
    ops = _native_operations(spec)
    if not ops:
        raise NativeGenerationError("no generated native read operations")
    lines = [
        _native_provenance(spec).rstrip("\n"),
        "",
        '#include "u.h"',
        '#include "../port/lib.h"',
        '#include "mem.h"',
        '#include "dat.h"',
        '#include "fns.h"',
        '#include "../port/error.h"',
        '#include "kernel_native.h"',
        "",
        "/*",
        " * Thin bindings only: the readnum body, guard and offset handling live",
        " * in the reviewed helper shared with the inherited Dev branch.",
        " * No Chan, Qid dispatch, Dirtab, walk, namec or namespace traversal.",
        " */",
        "",
    ]
    for driver, op in ops:
        native = op["native"]
        lines.extend([
            "long",
            f"{native['generated_symbol']}(void *buf, long n, vlong off)",
            "{",
            f"\treturn {native['helper']}(buf, n, off);",
            "}",
            "",
        ])
    for driver, driver_ops in _native_driver_operations(spec):
        name = driver.get("driver") or ""
        disp = driver_ops[0]["native"]["dispatcher_symbol"]
        lines.extend([
            "long",
            f"{disp}(ulong selector, void *buf, long n, vlong off)",
            "{",
            "\tswitch(selector){",
        ])
        for op in driver_ops:
            native = op["native"]
            lines.extend([
                f"\tcase {native['selector_constant']}:",
                f"\t\treturn {native['generated_symbol']}(buf, n, off);",
            ])
        lines.extend([
            "\t}",
            f'\terror("native {name}: unsupported selector");',
            "}",
            "",
        ])
    return "\n".join(lines)


def dumps_native_manifest(spec: dict[str, Any]) -> str:
    return json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _native_outputs(spec: dict[str, Any]) -> dict[str, str]:
    return {
        "kernel_native.h": render_native_header(spec),
        "kernel_native.c": render_native_source(spec),
        "native-decisions.json": dumps_native_manifest(spec),
    }


def write_native_artifacts(
    spec: dict[str, Any], out_dir: Path
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, content in sorted(_native_outputs(spec).items()):
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def check_native_artifacts(
    spec: dict[str, Any], out_dir: Path
) -> list[str]:
    problems: list[str] = []
    for name, content in sorted(_native_outputs(spec).items()):
        path = out_dir / name
        if not path.is_file():
            problems.append(f"missing generated native artifact: {path}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"stale generated native artifact: {path}")
    return problems



# ---------------------------------------------------------------------------
# E3 source-to-source extraction proposals
#
# This stage consumes the same Analyzer IR.  It never writes to the source
# tree: it only proposes a helper insertion and a selected-case replacement,
# then emits a unified diff under build/generated/ for review.

EXTRACTION_SCHEMA = "plan2001.kernel-extraction/v1"
EXTRACTION_GENERATOR_VERSION = "1"
EXTRACTION_DEFAULT_OUT = "build/generated/e3"
E3_SAFE_PROCESS_FIELDS = {"pid", "parentpid"}
E3_PINNED_SHA = {
    "sys/src/9/pc/devrtc.c": {
        "45722e4fc13195b14924e7781c5eae09412704919233315f2502c0bfed3f1bcb",
        "6c2f2fd951f861b99323aa372ad902ffedf0f36124ef354be2f1f336c44cbe5d",
    },
    "sys/src/9/port/devcons.c": {
        "b6811757c92d7dcee2cfd5413b8b887f21f8b12c503bb839b301506d7e01ece4",
        "068dca67758d90a60baed6d9250241c46ee23974b8f09ce45b06e7140e901896",
    },
}
E3_KNOWN_REV_SHA = {
    "7b4dfac4903e909dc2a00f37e9320335808029ac": {
        "sys/src/9/pc/devrtc.c":
            "45722e4fc13195b14924e7781c5eae09412704919233315f2502c0bfed3f1bcb",
        "sys/src/9/port/devcons.c":
            "b6811757c92d7dcee2cfd5413b8b887f21f8b12c503bb839b301506d7e01ece4",
    },
}


class ExtractionRefusal(Exception):
    def __init__(self, reason: str, evidence: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence or {}


def _e3_line_start(text: str, offset: int) -> int:
    p = text.rfind("\n", 0, offset)
    return 0 if p < 0 else p + 1


def _e3_span_text(text: str, tokens: Sequence[Token]) -> str:
    if not tokens:
        return ""
    first, last = tokens[0], tokens[-1]
    return text[first.offset:last.offset + len(last.raw)]


def _e3_token_end(tok: Token) -> int:
    return tok.offset + len(tok.raw)


def _e3_top_level_depth(sf: SourceFile, offset: int) -> int:
    depth = 0
    for t in sf.tokens:
        if t.offset >= offset:
            break
        if t.value == "{":
            depth += 1
        elif t.value == "}":
            depth = max(0, depth - 1)
    return depth


def _e3_token_crosses(sf: SourceFile, offset: int) -> bool:
    for t in sf.tokens:
        if t.offset < offset < _e3_token_end(t):
            return True
        if t.offset >= offset:
            break
    return False


def _e3_comment_adjusted_start(text: str, line_start: int) -> int:
    """Move above a comment block directly attached to the following code."""
    pos = line_start
    while pos > 0:
        prev_end = pos - 1
        prev_start = text.rfind("\n", 0, prev_end) + 1
        line = text[prev_start:prev_end].strip()
        if line == "":
            break
        if line.startswith(("/*", "*", "*/", "//")):
            pos = prev_start
            continue
        break
    return pos


def _e3_prefix_statements(handler: Function, switch_start: int) -> list[list[Token]]:
    pre = list(handler.body[:switch_start])
    for i in range(len(pre) - 1, -1, -1):
        if pre[i].value == "switch":
            pre = pre[:i]
            break
    return _split_statements(pre)


def _e3_top_level_eq(stmt: Sequence[Token]) -> int | None:
    depth = 0
    for i, t in enumerate(stmt):
        if t.value in ("(", "[", "{"):
            depth += 1
        elif t.value in (")", "]", "}"):
            depth = max(0, depth - 1)
        elif t.value == "=" and depth == 0:
            return i
    return None


def _e3_has_call(tokens: Sequence[Token]) -> bool:
    for i, t in enumerate(tokens):
        if t.kind == "id" and i + 1 < len(tokens) and tokens[i + 1].value == "(":
            if t.value not in NATIVE_CAST_TYPES:
                return True
        if t.value in ("->", ".") and i + 1 < len(tokens) and tokens[i + 1].kind == "id":
            if i + 2 < len(tokens) and tokens[i + 2].value == "(":
                return True
    return False


def _e3_directory_guard(stmt: Sequence[Token]) -> dict[str, Any] | None:
    if not stmt or stmt[0].value != "if":
        return None
    if len(stmt) < 5 or stmt[1].value != "(":
        return None
    close = find_matching(stmt, 1, "(", ")")
    if close is None or close + 1 >= len(stmt):
        return None
    cond = join_tokens(stmt[2:close])
    if "qid" not in cond or "QTDIR" not in cond:
        return None
    body = list(stmt[close + 1:])
    if body and body[0].value == "{":
        end = find_matching(body, 0, "{", "}")
        if end is None:
            return None
        body = body[1:end]
    if len(body) < 3 or body[0].value != "return" or body[1].value != "devdirread":
        return None
    return {"condition": cond, "text": join_tokens(stmt)}


E3_TYPE_STARTERS = NATIVE_CAST_TYPES | {
    "auto", "const", "extern", "register", "static", "volatile",
    "struct", "union", "enum", "typedef", "signed", "unsigned", "void",
    "Mach", "Proc", "Chan", "Dirtab", "Cmdtab", "Rune", "Lock", "QLock",
    "Queue", "Block", "Cmdbuf", "Ureg", "Page", "Segment", "Pgrp", "Egrp",
    "Fgrp", "Rgrp", "Image", "Mnt", "Mntrpc", "Path", "Walkqid", "ISAConf",
    "SDunit", "SDifc", "Dev", "Ether", "Netif", "Wifi", "PhysUart", "VGAdev",
    "VGAcur", "PCArch", "ADifc", "Dir", "Qid",
}
E3_COMPOUND_ASSIGN = {
    "+=", "-=", "*=", "/=", "%=", "<<=", ">>=", "&=", "|=", "^=",
}


def _e3_type_starter(tok: Token) -> bool:
    if tok.kind != "id":
        return False
    if tok.value in E3_TYPE_STARTERS:
        return True
    return tok.value[:1].isupper()


def _e3_rhs_has_unsafe(tokens: Sequence[Token]) -> bool:
    vals = [t.value for t in tokens]
    if "?" in vals or "=" in vals or "{" in vals or "}" in vals:
        return True
    if any(v in E3_COMPOUND_ASSIGN for v in vals):
        return True
    return False


def _e3_declarator_names(tokens: Sequence[Token]) -> list[str]:
    names: list[str] = []
    text = [t.value for t in tokens]
    for i in range(len(text) - 1):
        if text[i] == "(" and text[i + 1] == "*":
            raise ExtractionRefusal(
                "function-pointer pre-dispatch declaration is not supported"
            )
    for part in split_top_level(tokens, ","):
        name = None
        for t in reversed(part):
            if t.kind == "id":
                name = t.value
                break
        if name is None:
            raise ExtractionRefusal("pre-dispatch declaration without a name")
        names.append(name)
    return names


def _e3_classify_prefix(handler: Function, switch_start: int) -> dict[str, Any]:
    """One conservative classifier shared by local resolution and validation."""
    stmts = _e3_prefix_statements(handler, switch_start)
    guard = None
    directory = None
    locals_: dict[str, list[dict[str, Any]]] = {}
    initializers: list[dict[str, Any]] = []
    declarations: list[str] = []

    def declare(name: str) -> None:
        if name in declarations:
            raise ExtractionRefusal(
                f"pre-dispatch declaration {name!r} is duplicated"
            )
        declarations.append(name)

    for stmt in stmts:
        if not stmt:
            continue
        first = stmt[0].value
        if first == "if":
            g = _parse_guard(stmt)
            if g is not None:
                if guard is not None:
                    raise ExtractionRefusal("multiple n guards before Qid dispatch")
                guard = g
                continue
            d = _e3_directory_guard(stmt)
            if d is not None:
                if directory is not None:
                    raise ExtractionRefusal("multiple directory guards before Qid dispatch")
                directory = d
                continue
            raise ExtractionRefusal(
                "unsupported pre-dispatch condition; refusing side-effect or unproven guard"
            )
        if first in ("goto", "switch", "for", "while", "do", "break", "continue",
                     "else", "return"):
            raise ExtractionRefusal(f"unsupported pre-dispatch control flow {first!r}")
        values = [t.value for t in stmt]
        if "++" in values or "--" in values:
            raise ExtractionRefusal("pre-dispatch increment/decrement is not supported")
        if any(v in E3_COMPOUND_ASSIGN for v in values):
            raise ExtractionRefusal(
                "pre-dispatch compound assignment/mutation is not supported"
            )
        if "?" in values or "{" in values or "}" in values:
            raise ExtractionRefusal(
                "pre-dispatch conditional, statement expression or block is not supported"
            )
        if any(stmt[i].value == "(" and stmt[i + 1].value == "*"
               for i in range(len(stmt) - 1)):
            raise ExtractionRefusal(
                "function-pointer pre-dispatch declaration is not supported"
            )
        eq = _e3_top_level_eq(stmt)
        if eq is None:
            if _e3_has_call(stmt):
                raise ExtractionRefusal("pre-dispatch call statement is not supported")
            if not _e3_type_starter(stmt[0]):
                raise ExtractionRefusal(
                    "unrecognized pre-dispatch statement; refusing unproven side effect"
                )
            for name in _e3_declarator_names(stmt[:-1]):
                declare(name)
            continue
        lhs = stmt[:eq]
        rhs = stmt[eq + 1:-1]
        if _e3_rhs_has_unsafe(rhs):
            raise ExtractionRefusal(
                "pre-dispatch initializer/assignment has chained, conditional or compound effects"
            )
        if _e3_has_call(rhs):
            raise ExtractionRefusal("pre-dispatch initializer with a call is not supported")
        target = None
        target_idx = None
        for i in range(len(lhs) - 1, -1, -1):
            if lhs[i].kind == "id":
                target = lhs[i].value
                target_idx = i
                break
        if target is None or target_idx is None:
            raise ExtractionRefusal("pre-dispatch assignment without a target")
        if target in ("c", "up", "n", "off", "buf"):
            raise ExtractionRefusal(f"pre-dispatch assignment to {target!r} is not supported")
        # A plain assignment has only the target on the left; the E3 rule only
        # accepts declarations, never a later write to any local.
        if len(lhs) == target_idx + 1 and target_idx == 0:
            raise ExtractionRefusal(
                f"pre-dispatch assignment to {target!r} is not supported"
            )
        if not _e3_type_starter(lhs[0]):
            raise ExtractionRefusal(
                "pre-dispatch write through pointer/member/array is not supported"
            )
        if len(split_top_level(lhs, ",")) != 1:
            raise ExtractionRefusal(
                "multi-declarator pre-dispatch initializer is not supported"
            )
        type_toks = lhs[:target_idx]
        type_text = join_tokens(type_toks)
        if "*" in [t.value for t in type_toks]:
            raise ExtractionRefusal(
                "pointer-typed pre-dispatch initializer is not supported"
            )
        declare(target)
        rec = {
            "name": target,
            "type": type_text,
            "init": join_tokens(rhs),
            "line": stmt[0].line,
        }
        initializers.append(rec)
        locals_.setdefault(target, []).append(rec)
    return {
        "guard": guard,
        "directory_guard": directory,
        "locals": locals_,
        "initializers": initializers,
    }


def _e3_validate_prefix_policy(
    classification: dict[str, Any],
    offset_local: dict[str, Any] | None,
) -> None:
    """Reject initializers unrelated to the selected branch's offset local."""
    allowed = (offset_local or {}).get("name")
    for init in classification["initializers"]:
        if allowed is None or init["name"] != allowed:
            raise ExtractionRefusal(
                f"pre-dispatch initializer for {init['name']!r} is not proven harmless"
            )
    if allowed is not None:
        entries = classification["locals"].get(allowed, [])
        if len(entries) != 1:
            raise ExtractionRefusal(
                f"branch offset local {allowed!r} has multiple or missing initializers"
            )


def _e3_chan_free_function(
    analyzer: Analyzer,
    func: Function,
    depth: int = 0,
    seen: frozenset[str] = frozenset(),
) -> list[str]:
    if depth > 4:
        raise ExtractionRefusal(f"call chain from {func.name!r} exceeds the E3 depth limit")
    if func.id in seen:
        raise ExtractionRefusal(f"call cycle through {func.name!r} is not supported")
    text = func.text
    forbidden = [
        (r"\bChan\b", "Chan type"),
        (r"\bc\s*->", "Chan variable c->"),
        (r"\bqid\b", "Qid field/type"),
        (r"\bDirtab\b", "Dirtab"),
        (r"\bdevwalk\s*\(", "devwalk"),
        (r"\bdevdirread\s*\(", "devdirread"),
        (r"\bnamec\s*\(", "namec"),
        (r"\bmount\s*\(", "mount"),
    ]
    for pattern, label in forbidden:
        if re.search(pattern, text, re.I):
            raise ExtractionRefusal(
                f"value helper chain member {func.name!r} contains {label!r}"
            )
    deps: list[str] = []
    for call in func.calls:
        if call.kind != "direct":
            raise ExtractionRefusal(
                f"value helper chain member {func.name!r} has an indirect/member call"
            )
        kind = analyzer.classify_external(call.name)
        if kind in ("hardware", "service"):
            # Stop at reviewed service/hardware primitives even when a kernel
            # definition exists; their internal queues are outside this helper.
            deps.append(call.name)
            continue
        callee, _ = analyzer.resolve(call, func)
        if callee is not None:
            deps.extend(_e3_chan_free_function(
                analyzer, callee, depth + 1, seen | {func.id}
            ))
        else:
            raise ExtractionRefusal(
                f"value helper chain member {func.name!r} calls unreviewed external {call.name!r}"
            )
    return deps


def _e3_validate_value(
    tokens: Sequence[Token],
    analyzer: Analyzer,
    source_path: str,
    handler_line: int | None = None,
) -> tuple[str, list[str], list[str]]:
    text = join_tokens(tokens)
    toks = _strip_leading_casts(tokens)
    if not toks:
        raise ExtractionRefusal("readnum value is only a cast")
    if len(toks) == 1 and toks[0].kind == "num":
        return text, [], []
    if (
        len(toks) == 3
        and toks[0].value == "up"
        and toks[1].value == "->"
        and toks[2].kind == "id"
    ):
        field = toks[2].value
        if field not in E3_SAFE_PROCESS_FIELDS:
            raise ExtractionRefusal(
                f"process field up->{field} is not in the reviewed scalar-context set"
            )
        return text, [], ["up != nil", f"up->{field}"]
    if (
        len(toks) >= 3
        and toks[0].kind == "id"
        and toks[1].value == "("
        and find_matching(toks, 1, "(", ")") == len(toks) - 1
    ):
        args = call_args(toks, 1)
        if args:
            raise ExtractionRefusal("readnum value call with arguments is not supported")
        func = analyzer._find_function(toks[0].value, source_path)
        if func is None:
            func = analyzer._find_function(toks[0].value)
        if func is None:
            raise ExtractionRefusal(
                f"readnum value call {toks[0].value!r} has no resolvable definition"
            )
        if func.path != source_path:
            raise ExtractionRefusal(
                f"readnum value call {toks[0].value!r} is outside the translation unit"
            )
        if handler_line is not None and func.line > handler_line:
            raise ExtractionRefusal(
                f"readnum value call {toks[0].value!r} is defined after the insertion point"
            )
        deps = _e3_chan_free_function(analyzer, func)
        context = ["up != nil"] if re.search(r"\bup\b", func.text) else []
        return text, [toks[0].value] + deps, context
    raise ExtractionRefusal("readnum value is not a reviewed literal, up scalar or call")


def _e3_validate_size(tokens: Sequence[Token], global_enums: dict[str, int]) -> tuple[str, int]:
    text = join_tokens(tokens)
    toks = _strip_leading_casts(tokens)
    if len(toks) == 1 and toks[0].kind == "num":
        value = _c_int_literal(toks[0].raw)
        if value is None:
            raise ExtractionRefusal(f"unsupported size literal {toks[0].raw!r}")
        return text, value
    if len(toks) == 1 and toks[0].kind == "id" and toks[0].value in global_enums:
        return text, global_enums[toks[0].value]
    raise ExtractionRefusal("readnum size is not a literal or uniquely resolved enum constant")


def _e3_offset_local(
    arg_tokens: Sequence[Token],
    locals_: dict[str, list[dict[str, Any]]],
) -> tuple[str, dict[str, Any] | None]:
    text = join_tokens(arg_tokens)
    toks = _strip_leading_casts(arg_tokens)
    if len(toks) != 1 or toks[0].kind != "id":
        raise ExtractionRefusal("readnum offset is not off or a single reviewed local")
    name = toks[0].value
    if name == "off":
        return text, None
    if name in ("buf", "n", "off"):
        raise ExtractionRefusal(
            f"readnum offset local {name!r} collides with a helper parameter"
        )
    entries = locals_.get(name, [])
    if len(entries) != 1:
        raise ExtractionRefusal(
            f"readnum offset local {name!r} is missing or has multiple declarations"
        )
    info = entries[0]
    if info["type"] not in ("ulong", "vlong", "long", "uvlong"):
        raise ExtractionRefusal(
            f"readnum offset local {name!r} has unsupported type {info['type']!r}"
        )
    if not _expr_is_off(tokenize(info["init"]), None):
        raise ExtractionRefusal(f"readnum offset local {name!r} is not initialised from off")
    return text, info


def _e3_already_extracted(
    analyzer: Analyzer,
    branch_tokens: Sequence[Token],
    source_path: str,
) -> str | None:
    try:
        stmts = _split_statements(branch_tokens)
    except NativeGenerationError:
        return None
    if len(stmts) != 1 or not stmts[0] or stmts[0][0].value != "return":
        return None
    expr = stmts[0][1:-1]
    if len(expr) < 3 or expr[0].kind != "id" or expr[1].value != "(":
        return None
    close = find_matching(expr, 1, "(", ")")
    if close != len(expr) - 1:
        return None
    args = call_args(expr, 1)
    if len(args) != 3 or not _expr_is_name(args[0], "buf") \
            or not _expr_is_name(args[1], "n") or not _expr_is_off(args[2], None):
        return None
    callee = analyzer._find_function(expr[0].value, source_path)
    if callee is not None:
        return expr[0].value
    return None


def _e3_parse_branch(
    analyzer: Analyzer,
    branch_tokens: Sequence[Token],
    source_path: str,
    handler: Function,
    switch: Switch,
    global_enums: dict[str, int],
) -> dict[str, Any]:
    classification = _e3_classify_prefix(handler, switch.start)
    locals_ = classification["locals"]
    stmts = _split_statements(branch_tokens)
    guard = None
    offset_local = None
    readnum_args = None
    assigned = False
    return_shape = None
    statement_texts: list[str] = []
    sf = analyzer.file_by_path[source_path]
    for stmt in stmts:
        if not stmt:
            continue
        first = stmt[0].value
        if first == "if":
            if readnum_args is not None:
                raise ExtractionRefusal("control flow after readnum in selected branch")
            g = _parse_guard(stmt)
            if g is None:
                raise ExtractionRefusal("unsupported if in selected branch")
            if guard is not None:
                raise ExtractionRefusal("duplicate n guard in selected branch")
            guard = g
            continue
        if first == "return":
            if len(stmt) < 2:
                raise ExtractionRefusal("empty return in selected branch")
            expr = stmt[1:-1]
            args = _match_call(expr, "readnum")
            if args is not None:
                if readnum_args is not None or assigned:
                    raise ExtractionRefusal("multiple readnum results in selected branch")
                readnum_args = args
                return_shape = "direct-return"
                statement_texts.append(_e3_span_text(sf.text, stmt))
            elif assigned and _expr_is_name(expr, "n"):
                return_shape = "assign-return"
                statement_texts.append(_e3_span_text(sf.text, stmt))
            else:
                raise ExtractionRefusal("unsupported return expression in selected branch")
            continue
        if first in ("goto", "switch", "for", "while", "do", "break", "continue", "else"):
            raise ExtractionRefusal(f"unsupported control flow {first!r} in selected branch")
        eq = _e3_top_level_eq(stmt)
        if eq is None or eq < 1:
            raise ExtractionRefusal("unsupported statement in selected branch")
        lhs = stmt[:eq]
        rhs = stmt[eq + 1:-1]
        target = None
        for t in reversed(lhs):
            if t.kind == "id":
                target = t.value
                break
        if target != "n":
            raise ExtractionRefusal(
                f"selected branch assignment to {target!r} is not supported"
            )
        args = _match_call(rhs, "readnum")
        if args is None:
            raise ExtractionRefusal("selected branch assignment is not from readnum")
        if assigned or readnum_args is not None:
            raise ExtractionRefusal("multiple readnum assignments in selected branch")
        readnum_args = args
        assigned = True
        statement_texts.append(_e3_span_text(sf.text, stmt))
    if readnum_args is None or return_shape is None:
        raise ExtractionRefusal("selected branch has no supported readnum result")
    if len(readnum_args) != 5:
        raise ExtractionRefusal("readnum call does not have five arguments")
    offset_text, offset_local = _e3_offset_local(readnum_args[0], locals_)
    _e3_validate_prefix_policy(classification, offset_local)
    if not _expr_is_name(readnum_args[1], "buf"):
        raise ExtractionRefusal("readnum buffer is not buf")
    if not _expr_is_name(readnum_args[2], "n"):
        raise ExtractionRefusal("readnum length is not n")
    value_text, value_deps, value_context = _e3_validate_value(
        readnum_args[3], analyzer, source_path, handler.line
    )
    size_text, size_value = _e3_validate_size(readnum_args[4], global_enums)
    guards = []
    if classification["guard"] is not None:
        guards.append(classification["guard"])
    if guard is not None:
        guards.append(guard)
    return {
        "locals": locals_,
        "offset_expression": offset_text,
        "offset_local": offset_local,
        "value_expression": value_text,
        "size_expression": size_text,
        "size_value": size_value,
        "return_shape": return_shape,
        "guard": guard,
        "entry_guard": classification["guard"],
        "directory_guard": classification["directory_guard"],
        "guards": guards,
        "statement_texts": statement_texts,
        "value_deps": value_deps,
        "value_context": value_context,
    }


def _e3_render_helper(
    name: str,
    driver: str,
    callback: str,
    qid: str,
    ir: dict[str, Any],
) -> str:
    lines = [
        "/*",
        f" * E3 proposal: {driver} {callback} {qid} extraction candidate.",
        " * Kernel-internal only; review before applying.  Not an approved ABI.",
        " */",
        "long",
        f"{name}(void *buf, long n, vlong off)",
        "{",
    ]
    for guard in ir["guards"]:
        lines.append(f"\t{guard['text']}")
    local = ir["offset_local"]
    if local is not None:
        lines.append(f"\t{local['type']} {local['name']} = {local['init']};")
    for text in ir["statement_texts"]:
        if "\n" in text or "\r" in text:
            raise ExtractionRefusal("multi-line selected-branch statements are not supported")
        lines.append(f"\t{text}")
    lines.extend(["}", "", ""])
    return "\n".join(lines)


def _e3_symbol_in_use(analyzer: Analyzer, sf: SourceFile, name: str) -> bool:
    if analyzer.global_by_name.get(name):
        return True
    if re.search(r"\b" + re.escape(name) + r"\b", sf.masked):
        return True
    for func in analyzer.functions:
        for call in func.calls:
            if call.name == name:
                return True
    return False


def _e3_insertion_offset(sf: SourceFile, handler: Function) -> int:
    if handler.conditions:
        raise ExtractionRefusal(
            f"handler {handler.name!r} is inside preprocessor conditions"
        )
    tok = sf.tokens[handler.source_start]
    start = _e3_line_start(sf.text, tok.offset)
    start = _e3_comment_adjusted_start(sf.text, start)
    if _e3_top_level_depth(sf, start) != 0:
        raise ExtractionRefusal("proposed helper insertion is not at file top level")
    if _e3_token_crosses(sf, start):
        raise ExtractionRefusal("proposed helper insertion falls inside an existing token")
    line = sf.text[start:sf.text.find("\n", start) if sf.text.find("\n", start) >= 0 else len(sf.text)]
    if line.lstrip().startswith("#"):
        raise ExtractionRefusal("proposed helper insertion is on a preprocessor line")
    return start


def _e3_selector_metadata(data: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    path = op.get("source", {}).get("path")
    qid = op.get("entry", {}).get("qid")
    for tab in data.get("dirtab", []):
        if tab.get("path") != path:
            continue
        for item in tab.get("entries", []):
            if item.get("qid_symbol") == qid:
                return {
                    "name": item.get("name"),
                    "perm": item.get("perm"),
                    "length": item.get("length"),
                    "table": tab.get("name"),
                }
    return {}


def _e3_find_operation(
    data: dict[str, Any], config: str, driver: str, callback: str, qid: str
) -> dict[str, Any]:
    matches = [
        o for o in data.get("operations", [])
        if o.get("driver") == driver
        and o.get("entry", {}).get("callback") == callback
        and o.get("entry", {}).get("qid") == qid
        and config in o.get("active_configs", [])
    ]
    if not matches:
        raise ExtractionRefusal(
            f"selector {driver}:{callback}:{qid} was not found in config {config}"
        )
    if len(matches) > 1:
        paths = sorted({m.get("source", {}).get("path") or "" for m in matches})
        if len(paths) > 1:
            raise ExtractionRefusal(
                f"selector {driver}:{callback}:{qid} is ambiguous across {paths}"
            )
    return matches[0]


def _e3_candidate(
    analyzer: Analyzer,
    data: dict[str, Any],
    config: str,
    spec: str,
    global_enums: dict[str, int],
    expect_sha: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    parts = spec.split(":")
    if len(parts) != 3 or not all(parts):
        raise ExtractionRefusal(f"invalid selector {spec!r}; expected driver:callback:qid")
    driver, callback, qid = parts
    base = {
        "selector": spec,
        "driver": driver,
        "callback": callback,
        "qid": qid,
        "status": "REFUSED",
        "reasons": [],
        "approval_state": "proposal-only; not an approved native binding",
    }
    try:
        op = _e3_find_operation(data, config, driver, callback, qid)
        path = op.get("source", {}).get("path") or ""
        sf = analyzer.file_by_path.get(path)
        base["source"] = {
            "path": path,
            "sha256": sf.sha256 if sf is not None else None,
            "pinned": False,
            "handler": op.get("handler", {}).get("symbol"),
            "handler_line": op.get("handler", {}).get("line"),
            "case_line": op.get("source", {}).get("line"),
        }
        if sf is None:
            raise ExtractionRefusal(f"source file {path!r} is not in the analysed tree")
        if "\r" in sf.text:
            raise ExtractionRefusal("CR/CRLF line endings are not supported")
        for macro in ("off", "n", "buf", "up", "readnum"):
            if re.search(r"^\s*#\s*define\s+" + macro + r"\b", sf.masked, re.M):
                raise ExtractionRefusal(
                    f"source-local macro alias {macro!r} changes extraction semantics"
                )
        expected = expect_sha.get(path)
        if expected is not None:
            if sf.sha256 != expected:
                raise ExtractionRefusal(
                    f"source SHA-256 changed: got {sf.sha256}, expected {expected}"
                )
        elif sf.sha256 not in E3_PINNED_SHA.get(path, set()):
            raise ExtractionRefusal(
                f"source SHA-256 {sf.sha256} is not pinned for {path}"
            )
        base["source"]["pinned"] = (
            expected is not None or sf.sha256 in E3_PINNED_SHA.get(path, set())
        )
        handler = _handler_function(analyzer, op)
        if handler is None:
            raise ExtractionRefusal("handler definition was not found")
        if handler.conditions:
            raise ExtractionRefusal("selected handler is inside preprocessor conditions")
        hstart = sf.tokens[handler.source_start].offset
        hend = _e3_token_end(sf.tokens[handler.source_end - 1])
        if re.search(r"^\s*#\s*(define|undef)\b", sf.text[hstart:hend], re.M):
            raise ExtractionRefusal(
                "selected handler contains an inner macro definition/undefinition"
            )
        for line in range(handler.line, handler.end_line + 1):
            if 0 <= line < len(sf.conditions) and sf.conditions[line]:
                raise ExtractionRefusal(
                    "selected handler contains preprocessor-conditional code"
                )
        case, switch = _find_case(handler, qid)
        branch_tokens = handler.body[case.start:case.end]
        branch_text = _e3_span_text(sf.text, branch_tokens)
        base["source"].update({
            "case_start_offset": branch_tokens[0].offset,
            "case_end_offset": _e3_token_end(branch_tokens[-1]),
            "case_start_line": branch_tokens[0].line,
            "case_end_line": branch_tokens[-1].line,
            "branch_text": branch_text,
        })
        if "#" in branch_text:
            raise ExtractionRefusal("selected branch contains preprocessor text")
        if mask_comments(branch_text) != branch_text:
            raise ExtractionRefusal("selected branch contains comments inside the replace span")
        already = _e3_already_extracted(analyzer, branch_tokens, path)
        if already is not None:
            base["status"] = "ALREADY-EXTRACTED"
            base["reasons"].append(
                f"selected branch already calls same-file helper {already!r}"
            )
            return base, None
        ir = _e3_parse_branch(
            analyzer, branch_tokens, path, handler, switch, global_enums
        )
        span_start = branch_tokens[0].offset
        span_end = _e3_token_end(branch_tokens[-1])
        if any(ctx.startswith("up") or "up->" in ctx for ctx in ir["value_context"]):
            outside = sf.text[:span_start] + sf.text[span_end:]
            if not re.search(r"\bup\b", outside):
                raise ExtractionRefusal(
                    "process context 'up' is not visible outside the selected branch"
                )
        helper = f"{handler.name}_{qid.lower()}_read"
        if _e3_symbol_in_use(analyzer, sf, helper):
            raise ExtractionRefusal(f"generated helper name {helper!r} collides with an existing symbol")
        insert = _e3_insertion_offset(sf, handler)
        helper_text = _e3_render_helper(helper, driver, callback, qid, ir)
        replacement = f"return {helper}(buf, n, off);"
        metadata = _e3_selector_metadata(data, op)
        deps = sorted(set(
            ir["value_deps"]
            + [t for t in ("readnum",) if t not in ir["value_deps"]]
            + (["up"] if ir["value_context"] else [])
            + ([ir["size_expression"]] if ir["size_expression"] and ir["size_expression"][0].isalpha() else [])
        ))
        if ir["directory_guard"] is not None:
            deps = sorted(set(deps))
        base.update({
            "status": "DIRECT-CANDIDATE",
            "reasons": [
                "selected branch matched the narrow readnum shape; proposal only"
            ],
            "value_expression": ir["value_expression"],
            "size_expression": ir["size_expression"],
            "size_value": ir["size_value"],
            "offset_expression": ir["offset_expression"],
            "offset_local": ir["offset_local"],
            "return_shape": ir["return_shape"],
            "guard": ir["guard"],
            "entry_guard": ir["entry_guard"],
            "directory_guard": ir["directory_guard"],
            "generated_helper": {
                "name": helper,
                "signature": "long (void *buf, long n, vlong off)",
                "insertion_offset": insert,
                "insertion_line": sf.text.count("\n", 0, insert) + 1,
            },
            "external_dependencies": deps,
            "permission": {
                **metadata,
                "policy": "legacy open/Dirtab boundary remains; helper is kernel-internal-only",
            },
            "context": sorted(set(ir["value_context"] + (
                ["offset local reconstructed from off"] if ir["offset_local"] else []
            ))),
            "lifecycle": "read-only; legacy open/close and Qid dispatch unchanged",
            "replacement": replacement,
            "normalization": {
                "readnum_text": "original selected-branch statement text reused verbatim",
                "guard": (
                    "n guard canonicalised to one line; semantics preserved"
                    if ir["guards"] else "no n guard copied"
                ),
                "offset_local": (
                    "original local type/initialiser copied into the helper; shared local left in place"
                    if ir["offset_local"] else "no offset local needed"
                ),
            },
            "patch_scope": "one helper insertion and one selected-case replacement",
        })
        return base, {
            "candidate": base,
            "path": path,
            "insert": insert,
            "helper_text": helper_text,
            "replacement": replacement,
            "span_start": span_start,
            "span_end": span_end,
        }
    except ExtractionRefusal as exc:
        base["status"] = "ALREADY-EXTRACTED" if base.get("status") == "ALREADY-EXTRACTED" else "REFUSED"
        base["reasons"].append(exc.reason)
        if exc.evidence:
            base["refusal_evidence"] = exc.evidence
        return base, None


def _e3_apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    ordered = sorted(edits, key=lambda e: (e[0], e[1]))
    merged: list[tuple[int, int, str]] = []
    for start, end, repl in ordered:
        if merged:
            ps, pe, pr = merged[-1]
            if start < pe:
                raise ExtractionRefusal("overlapping proposed patch spans")
            if start == pe and start == end and ps == pe:
                merged[-1] = (ps, pe, pr + repl)
                continue
            if start == ps and end == ps:
                merged[-1] = (ps, pe, pr + repl)
                continue
        merged.append((start, end, repl))
    out = text
    for start, end, repl in sorted(merged, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:start] + repl + out[end:]
    return out


def _e3_unified_diff(path: str, before: str, after: str) -> str:
    diff = list(difflib.unified_diff(
        before.splitlines(True),
        after.splitlines(True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    ))
    if not diff:
        return ""
    patch = "".join(diff)
    if not patch.endswith("\n"):
        patch += "\n"
    return patch


def _e3_input_pin(source_root: Path, expect_sha: dict[str, str]) -> dict[str, Any]:
    return {
        "source_tree": str(source_root),
        "expect_sha": dict(sorted(expect_sha.items())),
    }


def propose_extractions(
    source_root: Path,
    config: str,
    selectors: Sequence[str],
    source_rev: str | None = None,
    expect_sha: dict[str, str] | None = None,
) -> dict[str, Any]:
    expect_sha = expect_sha or {}
    seen: set[str] = set()
    for spec in selectors:
        if spec in seen:
            raise ValueError(f"duplicate selector {spec!r}")
        seen.add(spec)
    analyzer = Analyzer(source_root)
    data = analyzer.analyze()
    global_enums = _global_enum_constants(analyzer)
    candidates: list[dict[str, Any]] = []
    edit_groups: dict[str, list[dict[str, Any]]] = {}
    patch_texts: dict[str, str] = {}
    for spec in selectors:
        record, edit = _e3_candidate(
            analyzer, data, config, spec, global_enums, expect_sha
        )
        candidates.append(record)
        if edit is not None:
            edit_groups.setdefault(edit["path"], []).append(edit)
    patches: list[dict[str, Any]] = []
    for path in sorted(edit_groups):
        sf = analyzer.file_by_path[path]
        group = edit_groups[path]
        edits = [(e["insert"], e["insert"], e["helper_text"]) for e in group]
        edits.extend((e["span_start"], e["span_end"], e["replacement"]) for e in group)
        try:
            patched = _e3_apply_edits(sf.text, edits)
        except ExtractionRefusal as exc:
            for e in group:
                e["candidate"]["status"] = "REFUSED"
                e["candidate"]["reasons"].append(exc.reason)
            continue
        patch = _e3_unified_diff(path, sf.text, patched)
        if not patch:
            for e in group:
                e["candidate"]["status"] = "REFUSED"
                e["candidate"]["reasons"].append("proposed edit produced no diff")
            continue
        name = Path(path).name + ".patch"
        digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        for e in group:
            e["candidate"]["patch"] = name
            e["candidate"]["patch_sha256"] = digest
        patches.append({
            "path": path,
            "file": name,
            "sha256": digest,
            "helper_symbols": sorted({e["candidate"]["generated_helper"]["name"] for e in group}),
        })
        patch_texts[name] = patch
    tree_rev = analyzer.source_revision.get("commit")
    if source_rev is not None:
        known = E3_KNOWN_REV_SHA.get(source_rev)
        if known is not None:
            # Historical snapshot inside the main worktree: git -C resolves the
            # enclosing repository, so validate by the pinned file hashes.
            for c in candidates:
                src = c.get("source") or {}
                path = src.get("path")
                if path in known and src.get("sha256") != known[path]:
                    raise ValueError(
                        f"source revision {source_rev} does not match {path} SHA-256"
                    )
        elif tree_rev is None:
            raise ValueError(
                f"unknown source revision {source_rev}; omit --source-rev or use a pinned revision"
            )
        elif source_rev != tree_rev:
            raise ValueError(
                f"source revision {source_rev} does not match source-tree HEAD {tree_rev}"
            )
    # Refused candidates must not claim a patch.
    for c in candidates:
        if c["status"] != "DIRECT-CANDIDATE":
            c.pop("patch", None)
            c.pop("patch_sha256", None)
    source_hashes = {}
    for c in candidates:
        src = c.get("source") or {}
        if src.get("path"):
            source_hashes[src["path"]] = src.get("sha256")
    spec = {
        "schema": EXTRACTION_SCHEMA,
        "generator": {
            "name": GENERATOR,
            "version": EXTRACTION_GENERATOR_VERSION,
            "command": "python3 tools/kernel_opmap.py --propose-extraction",
            "limitations": [
                "proposal-only source-to-source experiment; never applied automatically",
                "reuses Analyzer.analyze() token spans; no second parser",
                "a patch is a review candidate, not proof of semantic equivalence",
                "kernel-internal helper only; not a userspace capability or ABI",
            ],
        },
        "config": config,
        "source_rev": source_rev or analyzer.source_revision.get("commit"),
        "source_hashes": dict(sorted(source_hashes.items())),
        "candidates": candidates,
        "patches": patches,
        "approval_state": "proposal-only",
        "_patch_texts": patch_texts,
    }
    return spec


def _extraction_outputs(spec: dict[str, Any], source_root: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    # Patch bodies are carried in a private key; the manifest stores only
    # paths and hashes so it remains deterministic and reviewable.
    for name, text in spec.get("_patch_texts", {}).items():
        outputs[name] = text
    outputs["extraction-decisions.json"] = (
        json.dumps({k: v for k, v in spec.items() if not k.startswith("_")},
                   sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    )
    return outputs


def write_extraction_artifacts(spec: dict[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, text in sorted(_extraction_outputs(spec, out_dir).items()):
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return paths


def check_extraction_artifacts(spec: dict[str, Any], out_dir: Path) -> list[str]:
    problems: list[str] = []
    for name, text in sorted(_extraction_outputs(spec, out_dir).items()):
        p = out_dir / name
        if not p.is_file():
            problems.append(f"missing extraction proposal artifact: {p}")
        elif p.read_text(encoding="utf-8") != text:
            problems.append(f"stale extraction proposal artifact: {p}")
    return problems


# ---------------------------------------------------------------------------
# Report rendering


def subsystem_for(path: str, name: str | None) -> str:
    p = path.lower()
    n = (name or "").lower()
    base = p.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0]
    if "/gefs/" in p or n == "gefs" or stem == "devgefs":
        return "ge-o"
    if (
        "/ip/" in p or n in ("ether", "ip", "wg")
        or stem.startswith(("ether", "netif", "wifi"))
    ):
        return "network"
    if (
        n == "sd" or stem.startswith(("sd", "nvme", "ahci"))
        or "virtio10" in stem and "ether" not in stem
    ):
        return "storage"
    if n in ("cons", "uart", "kbd") or stem.startswith(("uart", "devcons", "devkbd")):
        return "console-and-input"
    if (
        n in ("draw", "mouse", "vga")
        or stem.startswith(("vga", "screen", "swcursor", "devdraw", "devmouse"))
    ):
        return "display-and-input"
    if n == "usb" or stem.startswith("usb"):
        return "usb"
    if n in ("cap", "tls", "kprof") or stem in ("devcap", "devtls", "devkprof"):
        return "security-and-tracing"
    if n in (
        "root", "env", "pipe", "proc", "mnt", "srv", "shr", "dup", "swap",
        "fs", "segment",
    ) or stem in (
        "devroot", "devenv", "devpipe", "devproc", "devmnt", "devsrv",
        "devshr", "devdup", "devswap", "devfs", "devsegment",
    ):
        return "process-and-memory"
    if "/pc64/" in p or "/arm64/" in p or "/pc/" in p:
        return "platform"
    return "other"


def md_cell(text: Any) -> str:
    s = "" if text is None else str(text)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s


def short_source(obj: dict[str, Any] | None) -> str:
    if not obj:
        return ""
    return f"{obj.get('path', '')}:{obj.get('line', '')}"


def op_label(op: dict[str, Any]) -> str:
    e = op.get("entry", {})
    if op["kind"] == "file-operation":
        s = f"{op['driver']}:{e.get('callback')}"
        if e.get("qid"):
            s += f" {e['qid']}"
        if e.get("path"):
            s += f" ({e['path']})"
        return s
    if op["kind"] in ("control-command", "manual-control-command"):
        return f"{op['driver']}:cmd {e.get('command')}"
    if op["kind"] == "interface-operation":
        return f"{op['driver']}/{e.get('interface')}:{e.get('callback')}"
    return op["id"]


def terminal_text(chain: dict[str, Any] | None) -> str:
    if not chain:
        return "unknown"
    t = chain.get("terminal", {})
    kind = t.get("kind") or "unknown"
    sym = t.get("symbol")
    cands = t.get("candidates") or []
    s = kind + (f" {sym}" if sym else "")
    if cands:
        s += f" ({len(cands)} candidates)"
    return s


def render_markdown(data: dict[str, Any]) -> str:
    cov = data["coverage"]
    funcs = {f["id"]: f for f in data.get("functions", [])}
    chains = data.get("chains", {})
    normal_name = next((c["name"] for c in data["configs"] if c.get("kind") == "normal-amd64"), None)
    other_names = [c["name"] for c in data["configs"] if c["name"] != normal_name]
    lines: list[str] = []
    add = lines.append

    add("# Kernel driver operation map (generated)")
    add("")
    add("<!-- This file is generated by tools/kernel_opmap.py; do not edit by hand. -->")
    add("")
    add("Regenerate both this report and the machine-readable map from the repository root:")
    add("")
    add("```sh")
    add("python3 tools/kernel_opmap.py --write")
    add("```")
    add("")
    add("Verify that the checked-in artifacts are current:")
    add("")
    add("```sh")
    add("python3 tools/kernel_opmap.py --check")
    add("```")
    add("")
    add(f"- Source tree: `{data['source']['root']}`")
    add(f"- Source fingerprint (SHA-256): `{data['source']['fingerprint_sha256']}`")
    add("- Source revision is recorded in `docs/STATUS.md`; the generated files "
        "intentionally depend on the source fingerprint, not on the commit "
        "that happens to contain these artifacts.")
    add(f"- Schema: `{data['schema']}`; generator: `{data['generator']['name']}` v{data['generator']['version']}")
    add("")
    add("This is a source-level inventory, not a runtime claim.  A resolved chain "
        "means only that a direct C call path reached a recognisable hardware or "
        "controller primitive.  It does not establish semantic equivalence, "
        "permission sufficiency, or safe removability.")
    add("")
    add("## Method and limitations")
    add("")
    add("The analyser is a lightweight lexical/structural scanner for the Plan 9 C "
        "dialect, not a compiler.  It follows observed direct C calls, splits "
        "visible Qid and Cmdtab branches, and retains indirect callback edges with "
        "known candidates.  It does not expand macros, prove reachability, or "
        "resolve a callback that is selected at runtime.")
    add("")
    for limitation in data["generator"].get("limitations", []):
        add(f"- {limitation}")
    add("")
    add("## What the counts mean")
    add("")
    add("| Term | Definition |")
    add("| --- | --- |")
    add("| Scanned file | Every regular file under `sys/src/9`, including headers, assembly, mkfiles/scripts and configuration files. |")
    add("| Registration | One `Dev`, `SDifc`, `PhysUart`, `VGAdev`, `VGAcur`, `PCArch`, `ADifc`, `addethercard` or USB `Hciimpl` linkage registration found in source. |")
    add("| Exposed operation | One leaf file callback, Qid branch, Cmdtab command, manual first-field command, or lower-level interface callback. A callback split into Qid cases is counted as its cases, not also as a base callback. |")
    add("| Mapped hardware primitive | Operation whose selected chain terminates at an exact hardware/port/MSR call such as `inb`/`outb`/`rdmsr`. |")
    add("| Mapped controller primitive | Chain terminates at an external controller-prefixed service; the scanner does not know its internal behaviour. |")
    add("| Partial mapping | Chain reached an indirect callback, a controller API, only kernel services, or an unclassified external call. |")
    add("| Unresolved | Handler, dispatcher case, symbol resolution or bounded chain could not be established. |")
    add("| Unique chain | Shared chain node referenced by operations (`op.chain_id` in JSON); duplicate graph paths are not recounted per operation. |")
    add("")

    add("## Coverage totals")
    add("")
    add("| Measure | Count |")
    add("| --- | ---: |")
    for key in (
        "scanned_files", "c_files", "parsed_c_files", "parse_failures",
        "files_with_registrations", "registrations", "dirtab_tables",
        "cmdtab_tables", "exposed_operations", "mapped_hardware_primitives",
        "mapped_controller_primitives", "partial_mappings",
        "unresolved_operations", "unique_chains", "native_entry_points",
        "unresolved_build_objects", "unsupported_declarations",
    ):
        add(f"| `{key}` | {cov.get(key, 0)} |")
    add("")
    add("Files by kind: " + ", ".join(f"`{k}` {v}" for k, v in cov["by_kind"].items()) + ".")
    add("")
    add("Operations by kind: " + ", ".join(f"`{k}` {v}" for k, v in cov["operations_by_kind"].items()) + ".")
    add("")
    add("Operations by status: " + ", ".join(f"`{k}` {v}" for k, v in cov["operations_by_status"].items()) + ".")
    add("")
    add("Unique chains by status: " + ", ".join(f"`{k}` {v}" for k, v in cov["chains_by_status"].items()) + ".")
    add("")

    add("## Build inclusion")
    add("")
    add("Inclusion is derived from each configuration file using the `mkdevlist` rules "
        "and the corresponding mkfile object lists.  Source presence is not activity.")
    add("")
    add("| Configuration | Kind | Arch | Status | Active C files | Unresolved objects | Shadowed objects |")
    add("| --- | --- | --- | --- | ---: | ---: | ---: |")
    for c in cov["per_config"]:
        add(f"| `{md_cell(c['name'])}` | {md_cell(c['kind'])} | {md_cell(c['arch'])} | "
            f"{md_cell(c['status'])} | {c['active_c_files']} | {c['unresolved_objects']} | "
            f"{c['shadowed_objects']} |")
    add("")
    add("The normal amd64 configuration is `pc64`.  `pc64mp` is a test-only "
        "configuration with the same selected source objects; `arm64/qemu` is a "
        "different, planned architecture.  `riscv64` is a future target with no "
        "source tree in this snapshot.  There is no separate `sys/src/9/pc` "
        "configuration file here: `pc/` sources are selected through `pc64`.  "
        "Objects not present in this source snapshot remain explicit below.")
    add("")
    unresolved_build = data["unresolved_work"]["unresolved_build_objects"]
    if unresolved_build:
        add("### Unresolved or ambiguous build objects")
        add("")
        add("| Configuration | Object stem | Reason |")
        add("| --- | --- | --- |")
        for item in unresolved_build:
            add(f"| `{md_cell(item['config'])}` | `{md_cell(item['stem'])}` | {md_cell(item['reason'])} |")
        add("")
    shadowed = []
    for cfg in data["configs"]:
        for item in cfg.get("shadowed_objects", []):
            shadowed.append((cfg["name"], item))
    if shadowed:
        add("### Same object stem found in more than one search root")
        add("")
        add("| Configuration | Object stem | Chosen | Shadowed |")
        add("| --- | --- | --- | --- |")
        for cfgname, item in shadowed:
            add(f"| `{cfgname}` | `{item['stem']}` | `{item['chosen']}` | "
                f"{md_cell(', '.join(item['shadowed']))} |")
        add("")

    add("## Registrations")
    add("")
    add("| ID | Type | Name | Device char | Source | Active configs | Callbacks |")
    add("| --- | --- | --- | --- | --- | --- | ---: |")
    for r in data["registrations"]:
        dc = r.get("dc")
        if dc is not None:
            dc = repr(dc)
        callbacks = sum(1 for v in r.get("callbacks", {}).values() if not v.get("nil") and v.get("symbol"))
        add(f"| `{md_cell(r['id'])}` | {md_cell(r['type'])} | {md_cell(r['name'])} | "
            f"{md_cell(dc)} | {md_cell(short_source(r))} | "
            f"{md_cell(', '.join(r.get('active_configs', [])))} | {callbacks} |")
    add("")

    add("## Per-subsystem summary")
    add("")
    add("Subsystem labels are a source/name grouping heuristic for navigation; they "
        "are not a proposed object schema.")
    add("")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for op in data["operations"]:
        groups[op["subsystem"]].append(op)
    add("| Subsystem | Operations | Resolved | Partial | Unresolved | Registrations |")
    add("| --- | ---: | ---: | ---: | ---: | ---: |")
    for sub in sorted(groups):
        ops = groups[sub]
        regs = [r for r in data["registrations"] if subsystem_for(r["path"], r["name"]) == sub]
        add(f"| `{sub}` | {len(ops)} | {sum(1 for o in ops if o['status'] == 'resolved')} | "
            f"{sum(1 for o in ops if o['status'] == 'partial')} | "
            f"{sum(1 for o in ops if o['status'] == 'unresolved')} | {len(regs)} |")
    add("")

    add("## Operations by subsystem")
    add("")
    add("Build legend: `N` active in the normal amd64 configuration, `O` active "
        "only in another discovered configuration, `-` not selected by a "
        "resolved configuration.  Behavior legend: `E` a Plan 9 error escalation "
        "was observed in the selected path, `A` queue/wait/sleep/wakeup primitives "
        "were observed, `-` neither.  Non-default architecture sources are included "
        "in the tables even when `O`/`-`.")
    add("")
    for sub in sorted(groups):
        add(f"### {sub}")
        add("")
        by_driver: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for op in groups[sub]:
            by_driver[op["driver"]].append(op)
        for driver in sorted(by_driver):
            add(f"#### `{driver}`")
            add("")
            add("| Operation | Entry | Handler | Terminal | Status | Behavior | Build | Source |")
            add("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for op in sorted(by_driver[driver], key=lambda o: o["id"]):
                ch = chains.get(op["chain_id"])
                handler = op.get("handler", {}).get("symbol") or ""
                acts = op.get("active_configs", [])
                bmark = "N" if normal_name in acts else ("O" if acts else "-")
                beh = ""
                if op.get("return_behavior") and "may raise" in op["return_behavior"]:
                    beh += "E"
                if op.get("async") and "observed" in op["async"]:
                    beh += "A"
                beh = beh or "-"
                add(f"| `{md_cell(op_label(op))}` | {md_cell(op['entry'].get('dispatch'))} | "
                    f"`{md_cell(handler)}` | {md_cell(terminal_text(ch))} | "
                    f"{md_cell(op['status'])} | {beh} | {bmark} | {md_cell(short_source(op['source']))} |")
            add("")

    add("## Qid and command dispatch")
    add("")
    add("### Static Dirtab/Qid tables")
    add("")
    add("| Table | Source | Entries (name -> qid symbol) | Status |")
    add("| --- | --- | --- | --- |")
    for tab in data["dirtab"]:
        entries = ", ".join(
            f"{e['name']} -> {e.get('qid_symbol') or e['qid']}"
            for e in tab.get("entries", [])
        )
        add(f"| `{md_cell(tab['name'])}` | {md_cell(tab['path'] + ':' + str(tab['line']))} | "
            f"{md_cell(entries)} | {md_cell(tab.get('status'))} |")
    add("")
    add("### Cmdtab control tables")
    add("")
    add("| Table | Source | Commands (index: command/narg) |")
    add("| --- | --- | --- |")
    for tab in data["cmdtab"]:
        entries = ", ".join(
            f"{e['index']}: {e['cmd']}/{e['narg']}" for e in tab.get("entries", [])
        )
        add(f"| `{md_cell(tab['name'])}` | {md_cell(tab['path'] + ':' + str(tab['line']))} | "
            f"{md_cell(entries)} |")
    add("")
    dynamic = data.get("dynamic_directories", [])
    if dynamic:
        add("### Dynamically generated directories")
        add("")
        add("| Generator | Source | Qid cases observed |")
        add("| --- | --- | --- |")
        for f in dynamic:
            cases = ", ".join(c["case"] for c in f.get("cases", []))
            add(f"| `{md_cell(f['name'])}` | {md_cell(f['path'] + ':' + str(f['line']))} | "
                f"{md_cell(cases)} |")
        add("")

    add("## Lower-level interfaces")
    add("")
    add("| Interface | Name | Source | Callback candidates |")
    add("| --- | --- | --- | --- |")
    for r in data["registrations"]:
        if r["type"] in ("Dev", "Dirtab", "Cmdtab"):
            continue
        cbs = [f"{k}={v.get('symbol')}" for k, v in r.get("callbacks", {}).items()
               if not v.get("nil") and v.get("symbol")]
        add(f"| `{md_cell(r['type'])}` | `{md_cell(r['name'])}` | {md_cell(short_source(r))} | "
            f"{md_cell(', '.join(cbs))} |")
    add("")
    add("Indirect-call candidates are retained by field name.  For example, every "
        "operation that reaches `unit->dev->ifc->bio` records the known `SDifc.bio` "
        "implementations rather than pretending one was selected.")
    add("")

    add("## Native entry points")
    add("")
    add("### GE/O and other non-file syscalls")
    add("")
    add("| Syscall | Number | Handler | Status | Source |")
    add("| --- | ---: | --- | --- | --- |")
    for n in data["native_entry_points"]:
        if not n.get("native_o"):
            continue
        add(f"| `{md_cell(n.get('syscall') or '(unregistered)')}` | {md_cell(n.get('number'))} | "
            f"`{md_cell(n.get('handler'))}` | {md_cell(n.get('status'))} | "
            f"{md_cell(short_source(n.get('source') or {'path': n.get('handler_path'), 'line': n.get('handler_line')}))} |")
    add("")
    add("All syscall-table entries discovered: "
        + ", ".join(f"`{n.get('syscall')}`" for n in data["native_entry_points"] if n.get("syscall"))
        + ".")
    add("")

    add("## Representative chains")
    add("")
    add("These are selected source paths, not proofs of complete behaviour.  Each "
        "edge below is a direct C call observed in source or an explicitly "
        "labelled indirect callback.  The separate manual cross-check notes are "
        "kept in `docs/KERNEL-OPMAP-NOTES.md`.")
    add("")
    for rep in data["representative_chains"]:
        add(f"### {rep['title']}")
        add("")
        add(f"- Status: **{rep['status']}**")
        for note in rep.get("notes", []):
            add(f"- {note}")
        if rep.get("terminal"):
            add(f"- Terminal: `{terminal_text({'terminal': rep['terminal']})}`")
        add("")
        if rep.get("nodes"):
            add("| Step | Function | Source |")
            add("| ---: | --- | --- |")
            for i, nid in enumerate(rep["nodes"], 1):
                f = funcs.get(nid)
                if f:
                    add(f"| {i} | `{md_cell(f['name'])}` | {md_cell(f['path'] + ':' + str(f['line']))} |")
                else:
                    add(f"| {i} | `{md_cell(nid)}` | |")
            add("")
        if rep.get("edges"):
            add("| Edge | From | To | Evidence |")
            add("| ---: | --- | --- | --- |")
            for i, e in enumerate(rep["edges"], 1):
                frm = funcs.get(e.get("from"), {})
                add(f"| {i} | `{md_cell(frm.get('name', e.get('from')))}` | "
                    f"`{md_cell(e.get('to'))}` | {md_cell(e.get('path', '') + ':' + str(e.get('line', '')))} |")
            add("")

    add("## File coverage appendix")
    add("")
    add("Status legend: `A` active object, `S` header/support file in that "
        "configuration's search roots, `-` not selected, `o` outside that "
        "configuration's search roots, `n/a` not a compilable source.  Every "
        "scanned file is present in the JSON `source.files` array with its "
        "SHA-256 and classification.")
    add("")
    normal = normal_name
    other = other_names[0] if other_names else None
    add(f"| File | Kind | Class | {md_cell(normal) or 'normal'} | {md_cell(other) or 'other'} | Parse | Registrations |")
    add("| --- | --- | --- | --- | --- | --- | ---: |")
    for f in data["source"]["files"]:
        def st(cfg: str | None) -> str:
            if not cfg:
                return ""
            return {
                "active": "A", "support": "S", "not-selected": "-",
                "outside-config-roots": "o", "not-applicable": "n/a",
            }.get(f["build"].get(cfg), "")
        parse = f["parse"]["status"]
        if parse != "ok":
            parse += f": {f['parse'].get('reason') or ''}"
        add(f"| `{md_cell(f['path'])}` | {f['kind']} | {md_cell(f['classification'])} | "
            f"{st(normal)} | {st(other)} | {md_cell(parse)} | {len(f['registrations'])} |")
    add("")

    add("## Unresolved work")
    add("")
    uw = data["unresolved_work"]
    add("### Parse and declaration issues")
    add("")
    add("| File | Line | Reason |")
    add("| --- | ---: | --- |")
    for item in uw["parse_failures"]:
        add(f"| `{md_cell(item['path'])}` | {md_cell(item.get('line'))} | {md_cell(item.get('reason'))} |")
    for item in uw["unsupported_declarations"]:
        add(f"| `{md_cell(item['path'])}` | | {md_cell(item['detail'])} |")
    if not uw["parse_failures"] and not uw["unsupported_declarations"]:
        add("| none | | |")
    add("")
    add("### Conditional registrations")
    add("")
    if uw["conditional_registrations"]:
        add("| Registration | Condition | Source |")
        add("| --- | --- | --- |")
        for item in uw["conditional_registrations"]:
            add(f"| `{md_cell(item['registration'])}` | {md_cell(' && '.join(item['conditions']))} | "
                f"{md_cell(short_source(item['source']))} |")
    else:
        add("None found.")
    add("")
    add("### Conditional Dirtab/Cmdtab entries")
    add("")
    ces = uw.get("conditional_entries", [])
    if ces:
        add("| Kind | Table | Entry | Condition | Source |")
        add("| --- | --- | --- | --- | --- |")
        for item in ces:
            add(f"| {md_cell(item['kind'])} | `{md_cell(item['table'])}` | "
                f"`{md_cell(item['entry'])}` | {md_cell(' && '.join(item['conditions']))} | "
                f"{md_cell(short_source(item['source']))} |")
    else:
        add("None found.")
    add("")
    add("### Partial and unresolved operations")
    add("")
    add("The machine-readable list is `unresolved_work.operations` in the JSON.  "
        "Reasons are grouped here so that a reviewer can see the unresolved edge "
        "rather than a false claim of completeness.")
    add("")
    by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in uw["operations"]:
        by_reason[item.get("reason") or "(unspecified)"].append(item)
    add("| Reason | Count | Example operations | Terminal evidence |")
    add("| --- | ---: | --- | --- |")
    for reason in sorted(by_reason):
        items = by_reason[reason]
        examples = ", ".join(f"`{i['operation']}`" for i in items[:4])
        if len(items) > 4:
            examples += f", ... ({len(items) - 4} more)"
        terms = sorted({
            f"{i.get('terminal_kind')}:{i.get('terminal_symbol')}"
            for i in items if i.get("terminal_kind")
        })
        add(f"| {md_cell(reason)} | {len(items)} | {md_cell(examples)} | {md_cell(', '.join(terms))} |")
    add("")

    add("## User-space kbdfs boundary")
    add("")
    add("`kbdfs` is a user-space 9P server used as the console helper.  The `pc64` "
        "configuration embeds its binary in the kernel image (`bootdir`), but the "
        "binary is not a kernel-mode driver and its own 9P server is outside this "
        "kernel inventory.  The relevant kernel endpoints are the console and "
        "input devices and the serial/display output callbacks: `#c` (`devcons`), "
        "`#b` (`devkbd`, pc64 only), `#t` (`devuart`), the `screenputs` hook and "
        "the `PhysUart.putc`/`getc` callbacks.  The embedded `kbdfs` entry is "
        "recorded in the configuration table only; it is not counted as a driver.")
    add("")

    add("## Manual cross-check notes")
    add("")
    add("The source-checked manual notes (separate from this generated report) are "
        "in `docs/KERNEL-OPMAP-NOTES.md`.")
    add("")
    add("## Evidence-based next extraction targets")
    add("")
    add("These are bounded candidates suggested by the generated chains.  They are "
        "not transformations performed by this task, and the list does not "
        "prescribe a universal syscall ABI or harmonise the drivers.")
    add("")
    add("1. **Keyboard scancode read/write (`devkbd`, `#b`).** The Qscancode read "
        "branch reaches `kbdpoll` -> `i8042intr` -> `inb`; the Qleds write branch "
        "reaches `setleds` -> `outdata` -> `outb`.  Prerequisite: preserve the "
        "input queue, IRQ/polling mode, access check in `kbdopen`, and the exact "
        "lock/acknowledgement sequence.")
    add("2. **RTC/CMOS read/write (`devrtc`, `#r`).** The value paths are small and "
        "reach port I/O directly.  Prerequisite: preserve binary/ASCII time formats, "
        "NVRAM bounds and the `iseve`/permission checks.")
    add("3. **Console write (`devcons`, `#c`, Qcons).** The path reaches "
        "`putstrn0` and the `screenputs`/`PhysUart.putc` callbacks.  Prerequisite: "
        "keep the kernel message ring, console ownership/locking and the serial "
        "polling fallback; decide explicitly whether the callback indirection is "
        "replaced by a plain C record.")
    add("4. **Block partition data path (`devsd`, `#S`, Qpart/Qraw).** This is the "
        "clearest storage backend boundary, but it is partial: `sdbio` reaches "
        "`unit->dev->ifc->bio` with NVMe/AHCI/virtio/loop/RAM candidates.  "
        "Prerequisite: select and carry a concrete controller handle instead of "
        "relying on `SDifc` lookup at call time, without changing partition "
        "offset/bounds or media-change semantics.")
    add("5. **GE/O volume open (`OVOLOPEN`).** `sysovolopen` is already a native "
        "syscall, but `gevolume` still uses `namec(\"#S\"...)`, `devtab[...]->read` "
        "and a `Chan` before `oopen`/`geopen`.  Prerequisite: give the storage "
        "backend a native block handle and preserve GPT discovery, O-profile "
        "validation and the existing handle lifetime; the native O object calls "
        "themselves already avoid Chan/Fid/Qid.")
    add("6. **Ethernet transmit (`devether`, `#l`).** `etherwrite` -> `etheroq` -> "
        "`ethermux` -> queue write reaches the `Ether.transmit` callback.  "
        "Prerequisite: preserve framing, MTU checks, bypass/bridge modes and the "
        "queue/kick ownership rules before replacing the callback.")
    add("")

    return "\n".join(lines) + "\n"


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Command line


def default_paths(root: Path) -> tuple[Path, Path]:
    return root / DEFAULT_JSON, root / DEFAULT_MD


def write_artifacts(root: Path, data: dict[str, Any], json_path: Path | None = None, md_path: Path | None = None) -> tuple[Path, Path]:
    jp, mp = default_paths(root)
    jp = json_path or jp
    mp = md_path or mp
    jp.parent.mkdir(parents=True, exist_ok=True)
    mp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(dumps_json(data), encoding="utf-8")
    mp.write_text(render_markdown(data), encoding="utf-8")
    return jp, mp


def check_artifacts(root: Path, data: dict[str, Any], json_path: Path | None = None, md_path: Path | None = None) -> list[str]:
    jp, mp = default_paths(root)
    jp = json_path or jp
    mp = md_path or mp
    problems: list[str] = []
    expected = {jp: dumps_json(data), mp: render_markdown(data)}
    for path, content in expected.items():
        if not path.is_file():
            problems.append(f"missing generated artifact: {path}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"stale generated artifact: {path}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="repository root (default: parent of tools/)")
    ap.add_argument("--write", action="store_true", help="regenerate the checked-in JSON and Markdown artifacts")
    ap.add_argument("--check", action="store_true", help="fail if the checked-in artifacts are stale")
    ap.add_argument("--json", type=Path, default=None, help="override JSON output path")
    ap.add_argument("--markdown", type=Path, default=None, help="override Markdown output path")
    ap.add_argument("--stats", action="store_true", help="print coverage totals without writing files")
    ap.add_argument("--generate-native", action="store_true",
                    help="emit the opt-in native-operation spec and reviewed pilot C")
    ap.add_argument("--config", default=NATIVE_DEFAULT_CONFIG,
                    help=f"build config for --generate-native (default: {NATIVE_DEFAULT_CONFIG})")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help=f"generated output directory (default depends on mode)")
    ap.add_argument("--propose-extraction", action="store_true",
                    help="propose reviewable source-to-source extraction patches")
    ap.add_argument("--selectors", default=None,
                    help="comma-separated driver:callback:qid selectors for proposals")
    ap.add_argument("--source-tree", type=Path, default=None,
                    help="source tree for proposals (default: --root)")
    ap.add_argument("--source-rev", default=None,
                    help="source revision to record in the proposal manifest")
    ap.add_argument("--expect-sha", action="append", default=[], metavar="PATH=SHA256",
                    help="override the pinned source SHA for proposals (repeatable)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if args.propose_extraction:
        if not args.selectors:
            print("proposal mode requires --selectors driver:callback:qid", file=sys.stderr)
            return 2
        source_root = args.source_tree
        if source_root is None:
            source_root = root
        elif not source_root.is_absolute():
            source_root = root / source_root
        source_root = source_root.resolve()
        if not (source_root / KERNEL_REL).is_dir():
            print(f"proposal source tree has no {KERNEL_REL}: {source_root}", file=sys.stderr)
            return 2
        out_dir = args.out_dir
        if out_dir is None:
            out_dir = root / EXTRACTION_DEFAULT_OUT
        elif not out_dir.is_absolute():
            out_dir = root / out_dir
        out_dir = out_dir.resolve()
        allowed = (root / "build" / "generated").resolve()
        try:
            out_dir.relative_to(allowed)
        except ValueError:
            print(f"proposal output must stay under {allowed}", file=sys.stderr)
            return 2
        selectors = [s.strip() for s in args.selectors.split(",") if s.strip()]
        expect_sha: dict[str, str] = {}
        for item in args.expect_sha:
            if "=" not in item:
                print(f"bad --expect-sha {item!r}; expected PATH=SHA256", file=sys.stderr)
                return 2
            path, sha = item.split("=", 1)
            expect_sha[path] = sha
        try:
            spec = propose_extractions(
                source_root, args.config, selectors,
                source_rev=args.source_rev, expect_sha=expect_sha,
            )
        except (ValueError, OSError) as exc:
            print(f"extraction proposal failed: {exc}", file=sys.stderr)
            return 2
        if args.check:
            problems = check_extraction_artifacts(spec, out_dir)
            if problems:
                for p in problems:
                    print(p, file=sys.stderr)
                return 1
            print(f"extraction proposals: up to date ({out_dir})")
            return 0
        paths = write_extraction_artifacts(spec, out_dir)
        for path in paths:
            print(f"wrote {path}")
        counts: dict[str, int] = {}
        for c in spec["candidates"]:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        print(f"candidates={len(spec['candidates'])} "
              + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              + f" patches={len(spec['patches'])}")
        return 0
    analyzer = Analyzer(root)
    data = analyzer.analyze()
    if args.generate_native:
        out_dir = args.out_dir
        if out_dir is None:
            out_dir = root / NATIVE_DEFAULT_OUT
        elif not out_dir.is_absolute():
            out_dir = root / out_dir
        try:
            spec = build_native_spec(analyzer, data, args.config)
        except NativeGenerationError as exc:
            print(f"native generator refused: {exc}", file=sys.stderr)
            return 1
        if args.check:
            problems = check_native_artifacts(spec, out_dir)
            if problems:
                for p in problems:
                    print(p, file=sys.stderr)
                return 1
            print(f"kernel native generation: up to date ({out_dir})")
            return 0
        paths = write_native_artifacts(spec, out_dir)
        for path in paths:
            print(f"wrote {path}")
        cov = spec["summary"]["conversion"]
        print(f"config={spec['config']} drivers={spec['summary']['active_dev_registrations']} "
              f"operations={spec['summary']['operations']} "
              f"direct={cov.get('DIRECT', 0)} bridge={cov.get('BRIDGE', 0)} "
              f"manual={cov.get('MANUAL', 0)} legacy={cov.get('LEGACY', 0)}")
        return 0
    if args.stats and not (args.write or args.check):
        print(json.dumps(data["coverage"], sort_keys=True, indent=2))
        return 0
    if args.check:
        problems = check_artifacts(root, data, args.json, args.markdown)
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            return 1
        print("kernel operation map: up to date")
        return 0
    if args.write:
        jp, mp = write_artifacts(root, data, args.json, args.markdown)
        cov = data["coverage"]
        print(f"wrote {jp}")
        print(f"wrote {mp}")
        print(f"files={cov['scanned_files']} registrations={cov['registrations']} "
              f"operations={cov['exposed_operations']} "
              f"resolved={cov['operations_by_status'].get('resolved', 0)} "
              f"partial={cov['operations_by_status'].get('partial', 0)} "
              f"unresolved={cov['operations_by_status'].get('unresolved', 0)}")
        return 0
    # Default: print a short summary, do not modify the tree.
    cov = data["coverage"]
    print(f"files={cov['scanned_files']} registrations={cov['registrations']} "
          f"operations={cov['exposed_operations']} "
          f"resolved={cov['operations_by_status'].get('resolved', 0)} "
          f"partial={cov['operations_by_status'].get('partial', 0)} "
          f"unresolved={cov['operations_by_status'].get('unresolved', 0)}")
    print("use --write to regenerate docs/KERNEL-OPMAP.json and docs/KERNEL-OPMAP.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
