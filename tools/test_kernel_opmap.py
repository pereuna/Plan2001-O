#!/usr/bin/env python3
"""Focused tests for tools/kernel_opmap.py.

Run from the repository root with:

    python3 tools/test_kernel_opmap.py

These tests use small temporary source trees; they do not boot a kernel and
do not modify the checked-in inventory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kernel_opmap as om  # noqa: E402


BASE_TARGET = """\
status=supported
objtype=amd64
kdir=testarch
kconf=testconf
kernel=9test
ksrc=(port testarch)
"""

BASE_MKFILE = """\
CONF=testconf
CONFLIST=testconf
PORT=
"""

BASE_CONF = """\
dev
\ttest
"""

BASE_DEVTEST = """\
static long
testread(Chan *c, void *a, long n, vlong o)
{
\treturn 0;
}

Dev testdevtab = {
\t'T',
\t"test",
\tdevreset,
\tdevinit,
\tdevshutdown,
\tdevattach,
\tdevwalk,
\tdevstat,
\tdevopen,
\tdevcreate,
\tdevclose,
\ttestread,
\tdevbread,
\tdevwrite,
\tdevbwrite,
\tdevremove,
\tdevwstat,
};
"""


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fixture(extra: dict[str, str] | None = None) -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="opmap-test-")
    root = Path(td.name)
    write(root, "tools/targets/amd64", BASE_TARGET)
    write(root, "sys/src/9/testarch/mkfile", BASE_MKFILE)
    write(root, "sys/src/9/testarch/testconf", BASE_CONF)
    write(root, "sys/src/9/port/devtest.c", BASE_DEVTEST)
    for rel, text in (extra or {}).items():
        write(root, "sys/src/9/" + rel, text)
    return td


def analyze(root: Path) -> dict:
    return om.Analyzer(root).analyze()


class OperationMapTests(unittest.TestCase):
    def test_comments_and_strings_do_not_create_registrations(self) -> None:
        src = r'''
/* Dev commenteddevtab = { 'x', "commented", devreset }; */
static char *decoy = "Dev stringdevtab = { 'y', \"string\" };";
static long
realread(Chan *c, void *a, long n, vlong o)
{
	return 0;
}
Dev realdevtab = {
	'r',
	"real",
	devreset,
	devinit,
	devshutdown,
	devattach,
	devwalk,
	devstat,
	devopen,
	devcreate,
	devclose,
	realread,
	devbread,
	devwrite,
	devbwrite,
	devremove,
	devwstat,
};
'''
        with fixture({"port/devcomment.c": src}) as td:
            data = analyze(Path(td))
        names = [r["name"] for r in data["registrations"] if r["type"] == "Dev"]
        self.assertIn("real", names)
        self.assertNotIn("commented", names)
        self.assertNotIn("string", names)
        real = next(r for r in data["registrations"] if r["name"] == "real")
        self.assertEqual(real["dc"], "r")
        self.assertEqual(real["callbacks"]["read"]["symbol"], "realread")

    def test_multiline_qid_and_command_branches(self) -> None:
        src = r'''
enum { Qdir, Qctl, Qdata };
static Dirtab tdir[] = {
	".",	{Qdir, 0, QTDIR},	0,	DMDIR|0555,
	"ctl",	{Qctl},			0,	0660,
	"data",	{Qdata},		0,	0660,
};
enum { CMstart, CMstop };
static Cmdtab tcmd[] = {
	CMstart,	"start",	1,
	CMstop,		"stop",		1,
};
static long do_ctl(void *a, long n) { return n; }
static long do_data(void *a, long n) { return n; }
static long do_start(void *a, long n) { return n; }
static long do_stop(void *a, long n) { return n; }
static long
tread(Chan *c, void *a, long n, vlong o)
{
	switch((ulong)c->qid.path){
	case Qctl:
		return do_ctl(a, n);
	case Qdata:
		return do_data(a, n);
	default:
		error("bad");
	}
}
static long
twrite(Chan *c, void *a, long n, vlong o)
{
	Cmdtab *ct;
	Cmdbuf *cb;

	switch((ulong)c->qid.path){
	case Qctl:
		return do_ctl(a, n);
	default:
		break;
	}
	cb = parsecmd(a, n);
	ct = lookupcmd(cb, tcmd, nelem(tcmd));
	switch(ct->index){
	case CMstart:
		return do_start(a, n);
	case CMstop:
		return do_stop(a, n);
	default:
		error("bad");
	}
}
Dev branchdevtab = {
	'B', "branch",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, tread, devbread, twrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({"port/devbranch.c": src}) as td:
            data = analyze(Path(td))
        ops = data["operations"]
        ids = {o["id"] for o in ops}
        self.assertTrue(any(":read:Qctl" in i for i in ids))
        self.assertTrue(any(":read:Qdata" in i for i in ids))
        self.assertTrue(any(":write:Qctl" in i for i in ids))
        starts = [o for o in ops if o.get("entry", {}).get("command") == "start"]
        self.assertTrue(starts)
        # The dispatcher and its case must be resolved, not reported as a
        # missing switch case.
        self.assertNotIn("no matching switch case", starts[0]["reason"] or "")
        self.assertIn("twrite", starts[0]["handler"]["symbol"])

    def test_indirect_callback_keeps_candidates_without_fabricating_target(self) -> None:
        src = r'''
typedef struct SDunit SDunit;
static long
onebio(SDunit *u, int lun, int w, void *a, long n, uvlong lba)
{
	return n;
}
static SDifc oneifc = {
	.name = "one",
	.bio = onebio,
};
static long
tread(Chan *c, void *a, long n, vlong o)
{
	SDunit *unit = c->aux;
	return (*unit->dev->ifc->bio)(unit, 0, 0, a, n, 0);
}
Dev indirectdevtab = {
	'i', "indirect",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, tread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({"port/devindirect.c": src}) as td:
            data = analyze(Path(td))
        op = next(o for o in data["operations"] if o["driver"] == "indirect" and o["entry"]["callback"] == "read")
        chain = data["chains"][op["chain_id"]]
        self.assertEqual(chain["status"], "partial")
        self.assertEqual(chain["terminal"]["kind"], "interface")
        self.assertEqual(chain["terminal"]["symbol"], "bio")
        self.assertIn("onebio", chain["terminal"]["candidates"])
        # The scanner must not pretend that the indirect target is a resolved
        # concrete node in the chain.
        self.assertEqual(chain["nodes"], ["func:" + op["handler"]["path"] + "#" + op["handler"]["symbol"]])

    def test_duplicate_symbols_in_separate_files_resolve_locally(self) -> None:
        a = r'''
static long
helper(Chan *c, void *a, long n, vlong o) { return 1; }
Dev dupdevtab = {
	'a', "dup",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, helper, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        b = a.replace("static long\nhelper", "static long\nhelper").replace("return 1;", "return 2;").replace("'a'", "'b'")
        c = r'''
static long
caller(Chan *c, void *a, long n, vlong o) { return helper(c, a, n, o); }
Dev callerdevtab = {
	'c', "caller",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, caller, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({
            "port/devdup_a.c": a,
            "pc/devdup_b.c": b,
            "port/devcaller.c": c,
        }) as td:
            data = analyze(Path(td))
        self.assertEqual(len([r for r in data["registrations"] if r["name"] == "dup"]), 2)
        dup_ops = [o for o in data["operations"] if o["driver"] == "dup" and o["entry"]["callback"] == "read"]
        self.assertEqual(len(dup_ops), 2)
        self.assertEqual(len({o["handler"]["path"] for o in dup_ops}), 2)
        caller_op = next(o for o in data["operations"] if o["driver"] == "caller" and o["entry"]["callback"] == "read")
        caller_chain = data["chains"][caller_op["chain_id"]]
        self.assertEqual(caller_chain["status"], "unresolved")
        self.assertEqual(caller_chain["terminal"]["kind"], "ambiguous-symbol")

    def test_conditional_registration_is_visible_and_unresolved(self) -> None:
        src = r'''
#ifdef FOO
Dev foodevtab = {
	'f', "foo",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, devread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
#endif
'''
        with fixture({"port/devcond.c": src}) as td:
            data = analyze(Path(td))
        foo = next(r for r in data["registrations"] if r["name"] == "foo")
        self.assertTrue(foo["conditions"])
        self.assertIn("defined(FOO)", " && ".join(foo["conditions"]))
        conds = data["unresolved_work"]["conditional_registrations"]
        self.assertTrue(any(c["registration"] == foo["id"] for c in conds))

    def test_deliberately_broken_input_is_reported_not_dropped(self) -> None:
        src = "Dev brokendevtab = { 'b', \"broken\",\n"
        with fixture({"port/devbroken.c": src}) as td:
            data = analyze(Path(td))
        rec = next(f for f in data["source"]["files"] if f["path"].endswith("devbroken.c"))
        self.assertEqual(rec["parse"]["status"], "error")
        self.assertIn("devbroken.c", rec["path"])
        self.assertTrue(any("devbroken.c" in p["path"] for p in data["unresolved_work"]["parse_failures"]))
        # The file still appears in coverage accounting.
        self.assertEqual(data["coverage"]["scanned_files"], len(data["source"]["files"]))



    def test_if_based_qid_branches_are_split(self) -> None:
        src = r'''
enum { Qscancode, Qdir };
static long hwread(long n) { return n; }
static long
tifread(Chan *c, void *a, long n, vlong o)
{
	if(c->qid.path == Qscancode){
		return hwread(n);
	}
	if(c->qid.path == Qdir)
		return hwread(n);
	return 0;
}
Dev ifdevtab = {
	'j', "ifqid",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, tifread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({"port/devifqid.c": src}) as td:
            data = analyze(Path(td))
        ids = {o["id"] for o in data["operations"]}
        self.assertTrue(any(":read:Qscancode" in i for i in ids))
        self.assertTrue(any(":read:Qdir" in i for i in ids))

    def test_manual_first_field_command_without_cmdtab(self) -> None:
        src = r'''
static long do_reset(void *a, long n) { return n; }
static long
tmanualwrite(Chan *c, void *a, long n, vlong o)
{
	Cmdbuf *cb;

	cb = parsecmd(a, n);
	if(strcmp(cb->f[0], "reset") == 0)
		return do_reset(a, n);
	if(strcmp(cb->f[1], "on") == 0)
		return n;
	return n;
}
Dev manualdevtab = {
	'm', "manual",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, devread, devbread, tmanualwrite, devbwrite,
	devremove, devwstat,
};
'''
        with fixture({"port/devmanual.c": src}) as td:
            data = analyze(Path(td))
        manual = [o for o in data["operations"] if o["kind"] == "manual-control-command"]
        self.assertTrue(manual)
        self.assertEqual([o["entry"]["command"] for o in manual], ["reset"])
        self.assertEqual(manual[0]["handler"]["symbol"], "tmanualwrite")

    def test_determinism_and_no_allowlist(self) -> None:
        extra = {
            "port/devnew.c": r'''
Dev newdevtab = {
	'n', "new",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, devread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        }
        with fixture(extra) as td:
            root = Path(td)
            d1 = analyze(root)
            d2 = analyze(root)
            j1, j2 = om.dumps_json(d1), om.dumps_json(d2)
            m1, m2 = om.render_markdown(d1), om.render_markdown(d2)
            self.assertEqual(j1, j2)
            self.assertEqual(m1, m2)
            self.assertTrue(any(r["name"] == "new" for r in d1["registrations"]))
            out = root / "out"
            p1 = om.write_artifacts(root, d1, out / "a.json", out / "a.md")
            p2 = om.write_artifacts(root, d2, out / "b.json", out / "b.md")
            self.assertEqual(p1[0].read_bytes(), p2[0].read_bytes())
            self.assertEqual(p1[1].read_bytes(), p2[1].read_bytes())

    def test_every_scanned_file_is_accounted_for(self) -> None:
        with fixture({"port/helper.c": "static int helper(void){return 0;}\n"}) as td:
            root = Path(td)
            data = analyze(root)
        listed = {f["path"] for f in data["source"]["files"]}
        expected = {
            "sys/src/9/port/devtest.c",
            "sys/src/9/port/helper.c",
            "sys/src/9/testarch/mkfile",
            "sys/src/9/testarch/testconf",
        }
        self.assertTrue(expected.issubset(listed))
        for f in data["source"]["files"]:
            self.assertIn("classification", f)
            self.assertIn("sha256", f)
            self.assertIn("build", f)


REPO = HERE.parent


def real_native_spec() -> tuple[dict, dict]:
    analyzer = om.Analyzer(REPO)
    data = analyzer.analyze()
    return data, om.build_native_spec(analyzer, data)


class NativeGeneratorTests(unittest.TestCase):
    def test_rtc_and_cons_share_the_same_readnum_extraction(self) -> None:
        data, spec = real_native_spec()
        self.assertEqual(spec["schema"], om.NATIVE_SCHEMA)
        self.assertEqual(spec["config"], "pc64")
        rtc = next(d for d in spec["drivers"] if d["driver"] == "rtc")
        cons = next(d for d in spec["drivers"] if d["driver"] == "cons")
        self.assertEqual(rtc["generated_files"], ["kernel_native.h", "kernel_native.c"])
        self.assertEqual(cons["generated_files"], ["kernel_native.h", "kernel_native.c"])

        rtc_op = next(
            o for o in rtc["operations"]
            if o["selector"].get("symbol") == "Qrtc"
            and o["semantics"].get("callback") == "read"
        )
        cons_op = next(
            o for o in cons["operations"]
            if o["selector"].get("symbol") == "Qpid"
            and o["semantics"].get("callback") == "read"
        )
        self.assertEqual(rtc_op["conversion"], "DIRECT")
        self.assertEqual(cons_op["conversion"], "DIRECT")
        rn = rtc_op["native"]
        cn = cons_op["native"]
        self.assertEqual(rn["rule"], "readnum")
        self.assertEqual(cn["rule"], "readnum")
        self.assertEqual(rn["helper"], "rtcqread")
        self.assertEqual(cn["helper"], "consqpidread")
        self.assertEqual(rn["value_expression"], "(ulong) rtctime()")
        self.assertEqual(cn["value_expression"], "up->pid")
        self.assertEqual(rn["size_expression"], "12")
        self.assertEqual(rn["size_value"], 12)
        self.assertEqual(cn["size_expression"], "NUMSIZE")
        self.assertEqual(cn["size_value"], 12)
        self.assertEqual(rn["return_shape"], "assign-return")
        self.assertEqual(cn["return_shape"], "direct-return")
        self.assertIsNone(rn["guard"])
        self.assertEqual(cn["guard"]["condition"], "n <= 0")
        self.assertEqual(cn["entry_guard"]["condition"], "n <= 0")
        self.assertEqual(rn["selector_constant"], "NATIVE_RTC_QRTC")
        self.assertEqual(cn["selector_constant"], "NATIVE_CONS_QPID")
        self.assertIn("any user read", rn["authorization"])
        self.assertIn("0444", cn["authorization"])
        self.assertIn("kernel-internal-only", cn["authorization"])
        self.assertEqual(rtc_op["dependencies"]["selected_branch"]["chan"], [])
        self.assertEqual(cons_op["dependencies"]["selected_branch"]["chan"], [])

        self.assertEqual(rtc_op["source"]["helper"], "rtcqread")
        self.assertEqual(cons_op["source"]["helper"], "consqpidread")
        self.assertIn("rtcqread(buf, n, off)", rtc_op["source"]["branch_call"])
        self.assertIn("consqpidread(buf, n, off)", cons_op["source"]["branch_call"])
        analyzer = om.Analyzer(REPO)
        analyzer.analyze()
        rtc_fn = analyzer._find_function("rtcqread", "sys/src/9/pc/devrtc.c")
        cons_fn = analyzer._find_function("consqpidread", "sys/src/9/port/devcons.c")
        self.assertIn("readnum(", rtc_fn.text)
        self.assertIn("readnum(", cons_fn.text)
        rtc_read = analyzer._find_function("rtcread", "sys/src/9/pc/devrtc.c")
        cons_read = analyzer._find_function("consread", "sys/src/9/port/devcons.c")
        rtc_case, _ = om._find_case(rtc_read, "Qrtc")
        cons_case, _ = om._find_case(cons_read, "Qpid")
        rtc_branch = om.join_tokens(rtc_read.body[rtc_case.start:rtc_case.end])
        cons_branch = om.join_tokens(cons_read.body[cons_case.start:cons_case.end])
        self.assertIn("rtcqread(buf, n, off)", rtc_branch)
        self.assertIn("consqpidread(buf, n, off)", cons_branch)
        self.assertNotIn("readnum(", rtc_branch)
        self.assertNotIn("readnum(", cons_branch)

        for cb in ("read", "write"):
            op = next(
                o for o in rtc["operations"]
                if o["selector"].get("symbol") == "Qnvram"
                and o["semantics"].get("callback") == cb
            )
            self.assertEqual(op["conversion"], "MANUAL")
            self.assertIn("downgraded", " ".join(op["reasons"]))

        outputs = om._native_outputs(spec)
        header = outputs["kernel_native.h"]
        source = outputs["kernel_native.c"]
        self.assertIn("NATIVE_RTC_QRTC = 1", header)
        self.assertIn("NATIVE_CONS_QPID = 12", header)
        self.assertIn("NATIVE_RTC_QRTC_SIZE = 12", header)
        self.assertIn("NATIVE_CONS_QPID_SIZE = 12", header)
        self.assertIn("native_rtc_qrtc_read", source)
        self.assertIn("native_cons_qpid_read", source)
        self.assertIn("return rtcqread(buf, n, off);", source)
        self.assertIn("return consqpidread(buf, n, off);", source)
        self.assertIn('error("native rtc: unsupported selector")', source)
        self.assertIn('error("native cons: unsupported selector")', source)
        for text in (header, source):
            self.assertIn(rtc["sha256"], text)
            self.assertIn(cons["sha256"], text)
        self.assertNotIn("Chan *", source)
        self.assertNotIn("qid.path", source)
        self.assertNotIn("devwalk(", source)
        self.assertNotIn("devdirread(", source)
        self.assertNotIn("namec(", source)
        self.assertNotIn("readnum(", source)

    def _synthetic_spec(
        self,
        helper_body: str,
        *,
        binding_helper: str = "synread",
        require_up: bool = False,
        preprocessor: str = "",
    ) -> dict:
        src = preprocessor + r'''
enum { Qdir, Qsyn };
static Dirtab syndir[] = {
	".",	{Qdir, 0, QTDIR},	0,	DMDIR|0555,
	"syn",	{Qsyn},			8,	0444,
};
long
synread(void *buf, long n, vlong off)
{
''' + helper_body + r'''
}
static long
syread(Chan *c, void *buf, long n, vlong off)
{
	switch((ulong)c->qid.path){
	case Qsyn:
		return synread(buf, n, off);
	}
	return 0;
}
Dev syndevtab = {
	's', "synd",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, syread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        rel = "port/devsynd.c"
        path = "sys/src/9/" + rel
        with fixture({
            rel: src,
            "testarch/testconf": "dev\n\ttest\n\tsynd\n",
        }) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            rec = om._file_record(data, path)
            self.assertIsNotNone(rec)
            bindings = {
                path: {
                    "sha256": rec["sha256"],
                    "driver": "synd",
                    "device": "s",
                    "dirtab": "syndir",
                    "selector_values": {"Qsyn": 1},
                    "constants": {},
                    "operations": {
                        "read:Qsyn": {
                            "kind": "readnum",
                            "conversion": "DIRECT",
                            "helper": binding_helper,
                            "allowed_calls": [],
                            "allowed_idents": [],
                            "allowed_constants": {},
                            "require_up": require_up,
                            "authorization": "kernel-internal-only synthetic test",
                            "context": ["synthetic"],
                            "reason": "synthetic generic readnum fixture",
                        }
                    },
                }
            }
            return om.build_native_spec(analyzer, data, "testconf", bindings)

    def test_synthetic_static_dev_uses_same_renderer(self) -> None:
        spec = self._synthetic_spec(
            "\treturn readnum((ulong)off, buf, n, 4242, 8);\n"
        )
        driver = next(d for d in spec["drivers"] if d["driver"] == "synd")
        op = next(o for o in driver["operations"] if o.get("native"))
        self.assertEqual(op["conversion"], "DIRECT")
        self.assertEqual(op["native"]["rule"], "readnum")
        self.assertEqual(op["native"]["value_expression"], "4242")
        self.assertEqual(op["native"]["size_value"], 8)
        self.assertEqual(op["native"]["generated_symbol"], "native_synd_qsyn_read")
        outputs = om._native_outputs(spec)
        self.assertIn("NATIVE_SYND_QSYN = 1", outputs["kernel_native.h"])
        self.assertIn("NATIVE_SYND_QSYN_SIZE = 8", outputs["kernel_native.h"])
        self.assertIn("native_synd_qsyn_read", outputs["kernel_native.c"])
        self.assertIn("return synread(buf, n, off);", outputs["kernel_native.c"])
        self.assertNotIn("rtc", outputs["kernel_native.c"].lower())
        self.assertNotIn("cons", outputs["kernel_native.c"].lower())

    def test_assign_and_direct_readnum_shapes_both_extract(self) -> None:
        assign = self._synthetic_spec(
            "\tulong offset = off;\n"
            "\tn = readnum(offset, buf, n, 4242, 8);\n"
            "\treturn n;\n"
        )
        direct = self._synthetic_spec(
            "\tif(n <= 0)\n\t\treturn n;\n"
            "\treturn readnum((ulong)off, buf, n, 4242, 8);\n"
        )
        aop = next(o for d in assign["drivers"] for o in d["operations"] if o.get("native"))
        dop = next(o for d in direct["drivers"] for o in d["operations"] if o.get("native"))
        self.assertEqual(aop["native"]["return_shape"], "assign-return")
        self.assertEqual(dop["native"]["return_shape"], "direct-return")
        self.assertEqual(dop["native"]["guard"]["condition"], "n <= 0")

    def test_unsafe_source_shapes_are_refused(self) -> None:
        cases = {
            "goto": "\tgoto out;\n\treturn readnum((ulong)off, buf, n, 4242, 8);\n",
            "local": "\tint x = 1;\n\treturn readnum((ulong)off, buf, n, x, 8);\n",
            "extra": "\treturn n;\n\treturn readnum((ulong)off, buf, n, 4242, 8);\n",
            "macro-value": "\treturn readnum((ulong)off, buf, n, BADMACRO(), 8);\n",
        }
        for label, body in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(om.NativeGenerationError):
                    self._synthetic_spec(body)
        with self.assertRaises(om.NativeGenerationError):
            self._synthetic_spec(
                "\treturn readnum((ulong)off, buf, n, 4242, 8);\n",
                binding_helper="missinghelper",
            )
        with self.assertRaises(om.NativeGenerationError):
            self._synthetic_spec(
                "\treturn readnum((ulong)off, buf, n, 4242, 8);\n",
                require_up=True,
            )
        with self.assertRaises(om.NativeGenerationError):
            self._synthetic_spec(
                "\treturn readnum((ulong)off, buf, n, 4242, 8);\n",
                preprocessor="#ifdef SYNTHETIC\n",
            )

    def test_pipe_is_manual_with_blockers(self) -> None:
        _, spec = real_native_spec()
        pipe = next(d for d in spec["drivers"] if d["driver"] == "pipe")
        self.assertFalse(pipe["generated_files"])
        self.assertEqual(pipe["classification"], "MANUAL")
        self.assertTrue(any("ref/qref" in b for b in pipe["blockers"]))
        self.assertTrue(any("c->aux" in b for b in pipe["blockers"]))
        data_ops = [
            o for o in pipe["operations"]
            if o["selector"].get("symbol") in ("Qdata0", "Qdata1")
            and o["semantics"]["operation"] in ("read", "write")
        ]
        self.assertTrue(data_ops)
        for op in data_ops:
            self.assertEqual(op["conversion"], "MANUAL")
            self.assertIn("no reviewed Chan-free binding", op["reasons"][0])

    def test_native_generation_is_deterministic_and_checkable(self) -> None:
        _, spec = real_native_spec()
        with tempfile.TemporaryDirectory(prefix="native-out-") as td:
            out = Path(td)
            first = om.write_native_artifacts(spec, out)
            snapshot = {p.name: p.read_bytes() for p in first}
            second = om.write_native_artifacts(spec, out)
            self.assertEqual(snapshot, {p.name: p.read_bytes() for p in second})
            self.assertEqual(om.check_native_artifacts(spec, out), [])
            (out / "kernel_native.c").write_text("tampered\n", encoding="utf-8")
            problems = om.check_native_artifacts(spec, out)
            self.assertTrue(any("kernel_native.c" in p for p in problems))

    def test_stale_reviewed_binding_fails_closed(self) -> None:
        with fixture({"pc/devrtc.c": BASE_DEVTEST}) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            bindings = {
                "sys/src/9/pc/devrtc.c": {
                    "sha256": "0" * 64,
                    "driver": "rtc",
                    "device": "r",
                    "dirtab": "rtcdir",
                    "selector_values": {},
                    "constants": {},
                    "operations": {},
                }
            }
            with self.assertRaises(om.NativeGenerationError):
                om.build_native_spec(analyzer, data, "testconf", bindings)

    def test_qid_mapping_from_enum_and_dirtab(self) -> None:
        src = r'''
enum { Qbase = 10, Qctl, Qdata };
static Dirtab ndir[] = {
	".",	{Qbase, 0, QTDIR},	0,	DMDIR|0555,
	"ctl",	{Qctl},			0,	0600,
	"data",	{Qdata},		0,	0644,
};
static long
nread(Chan *c, void *a, long n, vlong o)
{
	switch((ulong)c->qid.path){
	case Qctl: return n;
	case Qdata: return n;
	}
	return 0;
}
Dev ndevtab = {
	'n', "nqid",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, nread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({
            "port/devnqid.c": src,
            "testarch/testconf": "dev\n\ttest\n\tnqid\n",
        }) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            spec = om.build_native_spec(analyzer, data, "testconf", bindings={})
        driver = next(d for d in spec["drivers"] if d["driver"] == "nqid")
        symbols = {
            o["selector"]["symbol"]: o["selector"]["value"]
            for o in driver["operations"] if o["selector"]["kind"] == "qid"
        }
        self.assertEqual(symbols, {"Qctl": 11, "Qdata": 12})
        names = {
            o["selector"]["symbol"]: o["selector"]["name"]
            for o in driver["operations"] if o["selector"]["kind"] == "qid"
        }
        self.assertEqual(names, {"Qctl": "ctl", "Qdata": "data"})
        for op in driver["operations"]:
            self.assertIn(op["conversion"], ("MANUAL", "LEGACY"))

    def test_conditional_branch_is_explicit_in_manifest(self) -> None:
        src = r'''
#ifdef FOO
enum { Qdata };
static long
cread(Chan *c, void *a, long n, vlong o)
{
	switch((ulong)c->qid.path){
	case Qdata: return n;
	}
	return 0;
}
Dev cdevtab = {
	'c', "conditional",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, cread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
#endif
'''
        with fixture({
            "port/devconditional.c": src,
            "testarch/testconf": "dev\n\ttest\n\tconditional\n",
        }) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            spec = om.build_native_spec(analyzer, data, "testconf", bindings={})
        driver = next(d for d in spec["drivers"] if d["driver"] == "conditional")
        op = next(o for o in driver["operations"] if o["selector"].get("symbol") == "Qdata")
        self.assertTrue(op["conditional"]["ambiguous_alternatives"])
        self.assertIn("FOO", " ".join(op["conditional"]["preprocessor_conditions"]))
        self.assertEqual(op["conversion"], "MANUAL")

    def test_macro_alias_and_indirect_callback_are_refused(self) -> None:
        alias = r'''
#define Chan GChan
enum { Qdata };
static long
aread(Chan *c, void *a, long n, vlong o)
{
	switch((ulong)c->qid.path){
	case Qdata: return n;
	}
	return 0;
}
Dev adevtab = {
	'a', "alias",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, aread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        indirect = r'''
typedef struct SDunit SDunit;
static long
ibio(SDunit *u, int lun, int w, void *a, long n, uvlong lba)
{
	return n;
}
static SDifc iifc = {
	.name = "i",
	.bio = ibio,
};
static long
iread(Chan *c, void *a, long n, vlong o)
{
	SDunit *unit = c->aux;
	return (*unit->dev->ifc->bio)(unit, 0, 0, a, n, 0);
}
Dev idevtab = {
	'i', "indirect",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, iread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''
        with fixture({
            "port/devalias.c": alias,
            "port/devindirect.c": indirect,
            "testarch/testconf": "dev\n\ttest\n\talias\n\tindirect\n",
        }) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            spec = om.build_native_spec(analyzer, data, "testconf", bindings={})
        aop = next(
            o for d in spec["drivers"] if d["driver"] == "alias"
            for o in d["operations"] if o["semantics"].get("callback") == "read"
        )
        self.assertEqual(aop["conversion"], "MANUAL")
        self.assertTrue(any("macro alias" in r for r in aop["state_risks"]))
        iop = next(
            o for d in spec["drivers"] if d["driver"] == "indirect"
            for o in d["operations"] if o["semantics"].get("callback") == "read"
        )
        self.assertEqual(iop["conversion"], "MANUAL")
        self.assertIn("indirect callback", iop["reasons"][0])

    def test_parse_failure_is_refused_in_native_manifest(self) -> None:
        with fixture({
            "port/devbroken2.c": "Dev brokendevtab = { 'b', \"broken\",\n",
            "testarch/testconf": "dev\n\ttest\n\tbroken2\n",
        }) as td:
            root = Path(td)
            analyzer = om.Analyzer(root)
            data = analyzer.analyze()
            spec = om.build_native_spec(analyzer, data, "testconf", bindings={})
        refused = {r["path"] for r in spec["source_refusals"]}
        self.assertIn("sys/src/9/port/devbroken2.c", refused)
        rec = next(r for r in spec["source_refusals"]
                   if r["path"] == "sys/src/9/port/devbroken2.c")
        self.assertEqual(rec["parse_status"], "error")
        self.assertTrue(rec["reason"])


E3_PRE_REV = "7b4dfac4903e909dc2a00f37e9320335808029ac"
E3_TARGET = '''\
status=supported
objtype=amd64
kdir=testarch
kconf=testconf
kernel=9test
ksrc=(port pc testarch)
'''
E3_CONF = "dev\n\ttest\n\trtc\n\tcons\n"


def e3_git_show(rev: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{rev}:{path}"],
        text=True,
    )


def e3_pre_fixture() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="e3-pre-")
    root = Path(td.name)
    write(root, "tools/targets/amd64", E3_TARGET)
    write(root, "sys/src/9/testarch/mkfile", BASE_MKFILE)
    write(root, "sys/src/9/testarch/testconf", E3_CONF)
    write(root, "sys/src/9/port/devtest.c", BASE_DEVTEST)
    write(root, "sys/src/9/port/portdat.h", "enum { NUMSIZE = 12 };\n")
    write(root, "sys/src/9/pc/devrtc.c", e3_git_show(E3_PRE_REV, "sys/src/9/pc/devrtc.c"))
    write(root, "sys/src/9/port/devcons.c", e3_git_show(E3_PRE_REV, "sys/src/9/port/devcons.c"))
    return td


def e3_copy_paths(root: Path, paths: list[str]) -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="e3-apply-")
    dest = Path(td.name)
    for path in paths:
        write(dest, path, (root / path).read_text())
    return td


def e3_apply_check(dest: Path, patch_name: str, patch: str) -> None:
    p = dest / patch_name
    p.write_text(patch, encoding="utf-8")
    subprocess.run(
        ["git", "apply", "--check", str(p)],
        cwd=dest, check=True, capture_output=True, text=True,
    )


def e3_apply(dest: Path, patch_name: str, patch: str) -> None:
    p = dest / patch_name
    subprocess.run(
        ["git", "apply", str(p)],
        cwd=dest, check=True, capture_output=True, text=True,
    )


SYNTH_SRC = r'''enum { Qdir, Qsyn };
static Dirtab syndir[] = {
	".",	{Qdir, 0, QTDIR},	0,	DMDIR|0555,
	"syn",	{Qsyn},			8,	0444,
};
static long
syndread(Chan *c, void *buf, long n, vlong off)
{
	ulong offset = off;
	if(n <= 0)
		return n;
	switch((ulong)c->qid.path){
	case Qsyn:
%s
	}
	return 0;
}
Dev syndevtab = {
	's', "synd",
	devreset, devinit, devshutdown, devattach, devwalk, devstat, devopen,
	devcreate, devclose, syndread, devbread, devwrite, devbwrite, devremove,
	devwstat,
};
'''


def e3_synthetic_source(
    branch: str = "\t\treturn readnum((ulong)offset, buf, n, 4242, 8);",
    prefix: str = "",
    preprocessor: str = "",
    local: str = "ulong offset = off;",
    guard: str = "if(n <= 0)\n\t\treturn n;",
) -> str:
    body = SYNTH_SRC % branch
    body = body.replace("\tulong offset = off;\n", f"\t{local}\n")
    body = body.replace("\tif(n <= 0)\n\t\treturn n;", "\t" + guard if guard else "")
    if prefix:
        body = body.replace("\n\tswitch((ulong)c->qid.path){", f"\n\t{prefix}\n\tswitch((ulong)c->qid.path){{")
    return preprocessor + body


def e3_synthetic_spec(
    branch: str = "\t\treturn readnum((ulong)offset, buf, n, 4242, 8);",
    *,
    prefix: str = "",
    preprocessor: str = "",
    local: str = "ulong offset = off;",
    selector: str = "synd:read:Qsyn",
    expect_sha: str | None = None,
    extra_files: dict[str, str] | None = None,
    extra_config: str = "",
    guard: str = "if(n <= 0)\n\t\treturn n;",
) -> dict:
    path = "sys/src/9/port/devsynd.c"
    src = e3_synthetic_source(branch, prefix, preprocessor, local, guard)
    extra = {
        "port/devsynd.c": src,
        "testarch/testconf": "dev\n\ttest\n\tsynd\n" + extra_config,
    }
    extra.update(extra_files or {})
    with fixture(extra) as td:
        root = Path(td)
        sha = hashlib.sha256((root / path).read_text().encode()).hexdigest()
        expected = {path: expect_sha if expect_sha is not None else sha}
        return om.propose_extractions(
            root, "testconf", [selector], expect_sha=expected
        )


class ExtractionProposalTests(unittest.TestCase):
    def test_pre_e2_rtc_and_cons_generate_reviewable_patches(self) -> None:
        with e3_pre_fixture() as td:
            root = Path(td)
            sources = ["sys/src/9/pc/devrtc.c", "sys/src/9/port/devcons.c"]
            before = {p: (root / p).read_bytes() for p in sources}
            spec = om.propose_extractions(
                root, "testconf", ["rtc:read:Qrtc", "cons:read:Qpid"],
                source_rev=E3_PRE_REV,
            )
            self.assertEqual(spec["source_rev"], E3_PRE_REV)
            self.assertEqual([c["status"] for c in spec["candidates"]],
                             ["DIRECT-CANDIDATE", "DIRECT-CANDIDATE"])
            self.assertEqual(len(spec["patches"]), 2)
            rtc = spec["candidates"][0]
            cons = spec["candidates"][1]
            self.assertEqual(rtc["generated_helper"]["name"], "rtcread_qrtc_read")
            self.assertEqual(cons["generated_helper"]["name"], "consread_qpid_read")
            self.assertEqual(rtc["value_expression"], "(ulong) rtctime()")
            self.assertEqual(rtc["size_expression"], "12")
            self.assertEqual(rtc["return_shape"], "assign-return")
            self.assertEqual(cons["value_expression"], "up->pid")
            self.assertEqual(cons["size_expression"], "NUMSIZE")
            self.assertEqual(cons["entry_guard"]["condition"], "n <= 0")
            self.assertEqual(cons["permission"]["perm"], "0444")
            self.assertEqual(rtc["permission"]["perm"], "0664")

            outputs = om._extraction_outputs(spec, root)
            rtc_patch = outputs["devrtc.c.patch"]
            cons_patch = outputs["devcons.c.patch"]
            self.assertEqual(
                hashlib.sha256(rtc_patch.encode()).hexdigest(),
                "7b715be660380e5f75d323d38b5f0067c158508691e7e33e8c05e3102402b524",
            )
            self.assertEqual(
                hashlib.sha256(cons_patch.encode()).hexdigest(),
                "ce6672282fead3da4f6ac49d393e05c4822f2e1fa597d9f8fa125abf188de324",
            )
            self.assertIn("ulong offset = off;", rtc_patch)
            self.assertIn("case Qnvram:", rtc_patch)
            self.assertIn("if(n <= 0) return n;", cons_patch)
            self.assertIn("case Qppid:", cons_patch)
            self.assertNotIn("case Qppid:\n-\t\treturn readnum", cons_patch)

            spec2 = om.propose_extractions(
                root, "testconf", ["rtc:read:Qrtc", "cons:read:Qpid"],
                source_rev=E3_PRE_REV,
            )
            self.assertEqual(outputs, om._extraction_outputs(spec2, root))
            with tempfile.TemporaryDirectory(prefix="e3-out-") as out_td:
                out = Path(out_td)
                om.write_extraction_artifacts(spec, out)
                self.assertEqual(om.check_extraction_artifacts(spec, out), [])
                (out / "devrtc.c.patch").write_text("tampered\n", encoding="utf-8")
                self.assertTrue(om.check_extraction_artifacts(spec, out))

            # Apply only to a disposable copy of the exact base.
            with e3_copy_paths(root, sources) as copy_td:
                copy = Path(copy_td)
                e3_apply_check(copy, "devrtc.c.patch", rtc_patch)
                e3_apply_check(copy, "devcons.c.patch", cons_patch)
                e3_apply(copy, "devrtc.c.patch", rtc_patch)
                e3_apply(copy, "devcons.c.patch", cons_patch)
                rtc_after = (copy / sources[0]).read_text()
                cons_after = (copy / sources[1]).read_text()
                self.assertIn("long\nrtcread_qrtc_read(void *buf", rtc_after)
                self.assertIn("return rtcread_qrtc_read(buf, n, off);", rtc_after)
                self.assertIn("case Qnvram:", rtc_after)
                self.assertIn("offset >= Nvsize", rtc_after)
                self.assertIn("long\nconsread_qpid_read(void *buf", cons_after)
                self.assertIn("if(n <= 0) return n;", cons_after)
                self.assertIn("return consread_qpid_read(buf, n, off);", cons_after)
                self.assertIn("case Qppid:", cons_after)
                self.assertIn("case Qkmesg:", cons_after)
                self.assertIn("case Qdir:", cons_after)
                self.assertIn("return readnum((ulong)offset, buf, n, up->parentpid, NUMSIZE);", cons_after)
            self.assertEqual(before, {p: (root / p).read_bytes() for p in sources})

    def test_head_qppid_proposal_and_already_extracted(self) -> None:
        devcons = REPO / "sys/src/9/port/devcons.c"
        before = devcons.read_bytes()
        spec = om.propose_extractions(REPO, "pc64", ["cons:read:Qppid"])
        self.assertEqual(len(spec["patches"]), 1)
        cand = spec["candidates"][0]
        self.assertEqual(cand["status"], "DIRECT-CANDIDATE")
        self.assertEqual(cand["generated_helper"]["name"], "consread_qppid_read")
        self.assertEqual(cand["value_expression"], "up->parentpid")
        self.assertEqual(cand["entry_guard"]["condition"], "n <= 0")
        self.assertEqual(cand["permission"]["perm"], "0444")
        self.assertIn("up->parentpid", cand["context"])
        patch = om._extraction_outputs(spec, REPO)["devcons.c.patch"]
        self.assertEqual(
            hashlib.sha256(patch.encode()).hexdigest(),
            "abb253408f780ef4955fe3759da74dcf7ba3389ae5d83c3a38ecbfa6f2119ee3",
        )
        with e3_copy_paths(REPO, ["sys/src/9/port/devcons.c"]) as copy_td:
            copy = Path(copy_td)
            e3_apply_check(copy, "devcons.c.patch", patch)
        self.assertEqual(before, devcons.read_bytes())

        extracted = om.propose_extractions(
            REPO, "pc64", ["rtc:read:Qrtc", "cons:read:Qpid"]
        )
        self.assertEqual(
            [c["status"] for c in extracted["candidates"]],
            ["ALREADY-EXTRACTED", "ALREADY-EXTRACTED"],
        )
        self.assertEqual(extracted["patches"], [])
        self.assertEqual(before, devcons.read_bytes())

    def test_synthetic_driver_uses_same_proposal_rule(self) -> None:
        spec = e3_synthetic_spec()
        cand = spec["candidates"][0]
        self.assertEqual(cand["status"], "DIRECT-CANDIDATE")
        self.assertEqual(cand["generated_helper"]["name"], "syndread_qsyn_read")
        self.assertEqual(cand["value_expression"], "4242")
        self.assertEqual(cand["size_value"], 8)
        self.assertEqual(cand["entry_guard"]["condition"], "n <= 0")
        patch = om._extraction_outputs(spec, Path("."))["devsynd.c.patch"]
        self.assertIn("syndread_qsyn_read", patch)
        self.assertIn("ulong offset = off;", patch)
        self.assertIn("return readnum((ulong)offset, buf, n, 4242, 8);", patch)
        self.assertNotIn("rtc", patch.lower())
        self.assertNotIn("cons", patch.lower())

    def test_pre_dispatch_mutations_and_unknowns_are_refused(self) -> None:
        normal = "\t\treturn readnum((ulong)offset, buf, n, 4242, 8);"

        def assert_refused(prefix: str, needle: str) -> None:
            spec = e3_synthetic_spec(normal, prefix=prefix)
            cand = spec["candidates"][0]
            self.assertEqual(cand["status"], "REFUSED", (prefix, cand))
            self.assertIsNone(cand.get("patch"), prefix)
            self.assertEqual(spec["patches"], [], prefix)
            self.assertTrue(
                any(needle.lower() in r.lower() for r in cand["reasons"]),
                (prefix, cand["reasons"]),
            )

        for op in ("+=", "-=", "*=", "/=", "%=", "<<=", ">>=", "&=", "|=", "^="):
            assert_refused(f"offset {op} 1;", "compound assignment")
        cases = {
            "offset = off + 1;": "assignment to 'offset'",
            "offset = 4;": "assignment to 'offset'",
            "n = n / 2;": "assignment to 'n'",
            "n += 1;": "compound assignment",
            "off += 1;": "compound assignment",
            "buf = (void*)0;": "assignment to 'buf'",
            "*buf = 0;": "assignment to 'buf'",
            "c->offset = 0;": "write through",
            "up->pid = 1;": "write through",
            "buf[0] = 0;": "assignment to 'buf'",
            "return n;": "control flow 'return'",
            "sideeffect();": "call statement",
            "ulong x = sideeffect();": "initializer with a call",
            "ulong x = y = 1;": "chained",
            "ulong *p = &offset;": "pointer-typed pre-dispatch initializer",
            "ulong *p;\n\tp = &offset;": "assignment to 'p'",
            "ulong x = 0;": "not proven harmless",
            "foo;": "unrecognized",
            "if(n < 0)\n\t\treturn n;": "unsupported pre-dispatch",
            "if(foo())\n\t\treturn n;": "unsupported pre-dispatch",
            "#ifdef INNER\n\tint x;\n#endif": "preprocessor-conditional",
            "#define X 1": "inner macro definition",
            "ulong offset = off;\n\tulong offset;": "duplicated",
        }
        for prefix, needle in cases.items():
            with self.subTest(prefix=prefix):
                assert_refused(prefix, needle)

        # Innocuous comparisons inside an approved guard remain supported.
        spec = e3_synthetic_spec(normal, guard="if(n == 0)\n\t\treturn n;")
        cand = spec["candidates"][0]
        self.assertEqual(cand["status"], "DIRECT-CANDIDATE", cand)
        self.assertEqual(cand["entry_guard"]["condition"], "n == 0")
        self.assertIsNotNone(cand.get("patch"))

    def test_fail_closed_cases(self) -> None:
        normal = "\t\treturn readnum((ulong)offset, buf, n, 4242, 8);"

        def refused(spec: dict, needle: str) -> None:
            cand = spec["candidates"][0]
            self.assertEqual(cand["status"], "REFUSED", cand)
            self.assertIsNone(cand.get("patch"), cand)
            self.assertEqual(spec.get("patches"), [], cand)
            self.assertTrue(
                any(needle.lower() in r.lower() for r in cand["reasons"]),
                cand["reasons"],
            )

        refused(e3_synthetic_spec(expect_sha="0" * 64), "SHA-256 changed")
        refused(e3_synthetic_spec(normal, preprocessor="#define off 0\n"), "macro alias")
        refused(e3_synthetic_spec(normal, local="void (*fn)(void);"), "function-pointer")
        refused(e3_synthetic_spec(normal, preprocessor="#ifdef FOO\n"), "preprocessor")
        refused(e3_synthetic_spec("\t\treturn /* inner */ readnum((ulong)offset, buf, n, 4242, 8);"), "comments")
        refused(e3_synthetic_spec("\t\treturn readnum((ulong)offset, buf, n, (Chan*)up->pid, 8);"), "value")
        refused(e3_synthetic_spec(
            "\t\treturn readnum((ulong)buf, buf, n, 4242, 8);",
            local="ulong buf = off;",
        ), "assignment to 'buf'")
        refused(e3_synthetic_spec("\t\tn = readnum((ulong)offset, buf, n, 4242, 8);"), "no supported readnum result")
        refused(e3_synthetic_spec(
            "\t\tn = readnum((ulong)offset, buf, n, 4242, 8);\n"
            "\t\tn = readnum((ulong)offset, buf, n, 4243, 8);\n"
            "\t\treturn n;"
        ), "multiple readnum")
        refused(e3_synthetic_spec("\t\treturn readnum((ulong)offset, buf, n, BADMACRO(), 8);"), "no resolvable definition")
        refused(e3_synthetic_spec("\t\treturn readnum((ulong)offset, buf, n, \"literal\", 8);"), "value")
        with fixture({
            "port/devsynd.c": e3_synthetic_source().replace(
                "Dev syndevtab",
                "long\nsyndread_qsyn_read(void *buf, long n, vlong off)\n{\n\treturn n;\n}\nDev syndevtab",
            ),
            "testarch/testconf": "dev\n\ttest\n\tsynd\n",
        }) as td:
            root = Path(td)
            sha = hashlib.sha256((root / "sys/src/9/port/devsynd.c").read_text().encode()).hexdigest()
            refused_spec = om.propose_extractions(
                root, "testconf", ["synd:read:Qsyn"],
                expect_sha={"sys/src/9/port/devsynd.c": sha},
            )
        refused(refused_spec, "collides with an existing symbol")
        refused(e3_synthetic_spec("\t\treturn readnum((ulong)offset, buf, n, up->pid, 8);"), "not visible")
        refused(e3_synthetic_spec(normal, prefix="sideeffect();"), "call statement")
        refused(e3_synthetic_spec(normal, prefix="if(n < 0)\n\t\treturn n;"), "unsupported pre-dispatch")
        refused(e3_synthetic_spec(normal, selector="synd:read:Qnope"), "not found")
        with self.assertRaises(om.ExtractionRefusal):
            om._e3_apply_edits("abcdef", [(1, 3, "X"), (2, 4, "Y")])
        with e3_pre_fixture() as td:
            with self.assertRaises(ValueError):
                om.propose_extractions(
                    Path(td), "testconf", ["rtc:read:Qrtc"],
                    source_rev="deadbeef",
                )
        with self.assertRaises(ValueError):
            om.propose_extractions(
                REPO, "pc64", ["cons:read:Qppid"],
                source_rev="deadbeef",
            )

        crlf = e3_synthetic_source(normal).replace("\n", "\r\n")
        with fixture({
            "port/devsynd.c": crlf,
            "testarch/testconf": "dev\n\ttest\n\tsynd\n",
        }) as td:
            root = Path(td)
            sha = hashlib.sha256((root / "sys/src/9/port/devsynd.c").read_text().encode()).hexdigest()
            spec = om.propose_extractions(
                root, "testconf", ["synd:read:Qsyn"],
                expect_sha={"sys/src/9/port/devsynd.c": sha},
            )
        refused(spec, "CR/CRLF")

    def test_ambiguous_selector_is_refused(self) -> None:
        source = e3_synthetic_source()
        with fixture({
            "port/devsynd.c": source,
            "port/devsynd2.c": source,
            "testarch/testconf": "dev\n\ttest\n\tsynd\nmisc\n\tdevsynd2\n",
        }) as td:
            root = Path(td)
            sha1 = hashlib.sha256((root / "sys/src/9/port/devsynd.c").read_text().encode()).hexdigest()
            sha2 = hashlib.sha256((root / "sys/src/9/port/devsynd2.c").read_text().encode()).hexdigest()
            spec = om.propose_extractions(
                root, "testconf", ["synd:read:Qsyn"],
                expect_sha={
                    "sys/src/9/port/devsynd.c": sha1,
                    "sys/src/9/port/devsynd2.c": sha2,
                },
            )
        cand = spec["candidates"][0]
        self.assertEqual(cand["status"], "REFUSED")
        self.assertTrue(any("ambiguous" in r.lower() for r in cand["reasons"]), cand["reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
