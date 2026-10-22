#!/usr/bin/env python3
"""Focused tests for tools/kernel_opmap.py.

Run from the repository root with:

    python3 tools/test_kernel_opmap.py

These tests use small temporary source trees; they do not boot a kernel and
do not modify the checked-in inventory.
"""

from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
