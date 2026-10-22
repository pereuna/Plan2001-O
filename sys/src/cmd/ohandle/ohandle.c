#include <u.h>
#include <libc.h>

extern long ovolopen(char*, int);
extern long ospaceopen(int, char*, int);
extern long ospaceget(int, uvlong, void*, long, uvlong*);
extern long ospaceput(int, uvlong, void*, long);
extern long ospacecommit(int, uvlong*);
extern long ospaceclose(int);

enum {
	Ospmax	= 8,
	TestOid	= 0x4f48414e444c4531ULL,
};

static char *volspec;
static int nfail;
static char self[] = "/boot/ohandle";

static void
fail(char *fmt, ...)
{
	char msg[256];
	va_list va;

	va_start(va, fmt);
	vsnprint(msg, sizeof msg, fmt, va);
	va_end(va);
	print("FAIL: %s\n", msg);
	nfail++;
}

static void
childfail(char *fmt, ...)
{
	char msg[256];
	va_list va;

	va_start(va, fmt);
	vsnprint(msg, sizeof msg, fmt, va);
	va_end(va);
	print("FAIL: child: %s\n", msg);
	exits("fail");
}

static void
reap(void)
{
	Waitmsg *w;

	if((w = wait()) == nil){
		fail("wait: %r");
		return;
	}
	if(w->msg != nil && w->msg[0] != 0)
		fail("child exited: %s", w->msg);
	free(w);
}

static int
openinit(void)
{
	int h;

	if((h = ospaceopen(1, "init", 4)) < 0)
		fail("ospaceopen: %r");
	return h;
}

static void
eperr(char *what, long r)
{
	char e[ERRMAX];

	if(r != -1){
		fail("%s: expected failure, got %ld", what, r);
		return;
	}
	errstr(e, sizeof e);
	if(e[0] == 0)
		fail("%s: failure without an error string", what);
}

static void
checkval(char *what, char *buf, long n, char *want)
{
	long nw;

	if(n < 0){
		fail("%s: read failed: %r", what);
		return;
	}
	nw = strlen(want);
	if(n != nw || memcmp(buf, want, nw) != 0)
		fail("%s: got %ld bytes '%.*s', want '%s'", what, n, (int)n, buf, want);
}

static void
runmain(void)
{
	char buf[64], ebuf[ERRMAX];
	long r, h, pid;
	int i, cycle, a[Ospmax];
	uvlong v0, v1, ver;

	if(ovolopen(volspec, strlen(volspec)) != 1){
		fail("ovolopen: %r");
		exits("fail");
	}
	if((h = openinit()) != 1)
		fail("baseline handle is %ld, want 1", h);
	if(ospaceput(h, TestOid, "baseline", 8) < 0)
		fail("baseline put: %r");
	if(ospacecommit(h, &v0) < 0)
		fail("baseline commit: %r");
	r = ospaceget(h, TestOid, buf, sizeof buf, &ver);
	checkval("baseline read", buf, r, "baseline");
	if(ver != v0)
		fail("baseline version %llud, want %llud", ver, v0);

	pid = rfork(RFPROC|RFMEM);
	if(pid < 0)
		fail("rfork RFMEM: %r");
	else if(pid == 0){
		r = ospaceget(1, TestOid, buf, sizeof buf, nil);
		if(r != -1)
			childfail("RFMEM child used the parent's handle 1");
		errstr(ebuf, sizeof ebuf);
		if(ebuf[0] == 0)
			childfail("RFMEM child handle read failed without an error");
		r = ospaceclose(1);
		if(r != -1)
			childfail("RFMEM child closed the parent's handle 1");
		if((h = openinit()) != 1)
			childfail("RFMEM child got handle %ld, want its own 1", h);
		r = ospaceget(h, TestOid, buf, sizeof buf, nil);
		checkval("RFMEM child read", buf, r, "baseline");
		if(ospaceclose(h) < 0)
			childfail("RFMEM child close: %r");
		exits(nil);
	}else
		reap();
	if(nfail == 0)
		print("ohandle: isolation and separate sessions PASS\n");
	r = ospaceget(1, TestOid, buf, sizeof buf, nil);
	checkval("parent after RFMEM child", buf, r, "baseline");

	if(ospaceclose(1) < 0)
		fail("close baseline handle: %r");

	for(cycle = 0; cycle < 3; cycle++){
		for(i = 0; i < Ospmax; i++){
			if((a[i] = ospaceopen(1, "init", 4)) != i+1)
				fail("explicit cycle %d slot %d: handle %d", cycle, i, a[i]);
		}
		eperr("ninth explicit open", ospaceopen(1, "init", 4));
		for(i = Ospmax-1; i >= 0; i--)
			if(ospaceclose(a[i]) < 0)
				fail("explicit cycle %d close %d: %r", cycle, a[i]);
	}
	print("ohandle: explicit close capacity PASS\n");

	for(cycle = 0; cycle < 4; cycle++){
		pid = rfork(RFPROC|RFFDG);
		if(pid < 0){
			fail("rfork exit cycle %d: %r", cycle);
			break;
		}
		if(pid == 0){
			for(i = 0; i < Ospmax; i++)
				if(ospaceopen(1, "init", 4) != i+1)
					childfail("exit cycle %d slot %d", cycle, i);
			eperr("ninth child open", ospaceopen(1, "init", 4));
			exits(nil);
		}
		reap();
	}
	print("ohandle: process exit capacity PASS\n");

	eperr("get handle 0", ospaceget(0, TestOid, buf, sizeof buf, nil));
	eperr("get handle 9", ospaceget(Ospmax+1, TestOid, buf, sizeof buf, nil));
	eperr("close handle 0", ospaceclose(0));
	eperr("close handle 9", ospaceclose(Ospmax+1));
	if((h = openinit()) < 0)
		exits("fail");
	if(ospaceclose(h) < 0)
		fail("double-close setup: %r");
	eperr("double close", ospaceclose(h));
	eperr("get after close", ospaceget(h, TestOid, buf, sizeof buf, nil));
	print("ohandle: invalid and double close PASS\n");

	if((h = openinit()) < 0)
		exits("fail");
	if(ospaceput(h, TestOid, "closed-uncommitted", 18) < 0)
		fail("close-abort put: %r");
	if(ospaceclose(h) < 0)
		fail("close-abort close: %r");
	if((h = openinit()) < 0)
		exits("fail");
	r = ospaceget(h, TestOid, buf, sizeof buf, &ver);
	checkval("after close abort", buf, r, "baseline");
	if(ver != v0)
		fail("after close abort version %llud, want %llud", ver, v0);
	if(ospaceclose(h) < 0)
		fail("after close abort close: %r");
	print("ohandle: explicit close aborts unfinished transaction PASS\n");

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0)
		fail("rfork exit-abort: %r");
	else if(pid == 0){
		if((h = openinit()) < 0)
			exits("fail");
		if(ospaceput(h, TestOid, "exit-uncommitted", 16) < 0)
			childfail("exit-abort put: %r");
		r = ospaceget(h, TestOid, buf, sizeof buf, nil);
		checkval("exit-abort unpublished read", buf, r, "baseline");
		exits(nil);
	}else
		reap();
	if((h = openinit()) < 0)
		exits("fail");
	r = ospaceget(h, TestOid, buf, sizeof buf, &ver);
	checkval("after exit abort", buf, r, "baseline");
	if(ver != v0)
		fail("after exit abort version %llud, want %llud", ver, v0);
	if(ospaceput(h, TestOid, "later", 5) < 0)
		fail("later put: %r");
	if(ospacecommit(h, &v1) < 0)
		fail("later commit: %r");
	if(v1 <= v0)
		fail("later version %llud is not after %llud", v1, v0);
	r = ospaceget(h, TestOid, buf, sizeof buf, nil);
	checkval("later read", buf, r, "later");
	if(ospaceclose(h) < 0)
		fail("later close: %r");
	print("ohandle: exit aborts unfinished transaction PASS\n");

	if((h = openinit()) != 1)
		fail("exec parent handle is %ld, want 1", h);
	pid = rfork(RFPROC|RFFDG);
	if(pid < 0)
		fail("rfork exec: %r");
	else if(pid == 0){
		char *av[] = { self, "-exec-check", volspec, nil };

		if((h = openinit()) < 0)
			exits("fail");
		exec(self, av);
		childfail("exec %s: %r", self);
	}else
		reap();
	r = ospaceget(h, TestOid, buf, sizeof buf, nil);
	checkval("parent after successful exec child", buf, r, "later");
	if(ospaceclose(h) < 0)
		fail("exec parent close: %r");

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0)
		fail("rfork failed-exec: %r");
	else if(pid == 0){
		char *av[] = { "/nonexistent/ohandle", nil };

		if((h = openinit()) < 0)
			exits("fail");
		if(exec(av[0], av) == 0)
			childfail("exec of a missing file succeeded");
		r = ospaceget(h, TestOid, buf, sizeof buf, nil);
		checkval("failed exec child", buf, r, "later");
		if(ospaceclose(h) < 0)
			childfail("failed exec close: %r");
		exits(nil);
	}else
		reap();
	print("ohandle: failed exec preserves handles PASS\n");

	if(nfail == 0)
		print("PASS: process-local O handles: isolation, sharing, close, exit, abort, exec, errors\n");
	else
		print("FAIL: process-local O handles: %d checks failed\n", nfail);
	for(;;)
		sleep(1000);
}

static void
runexeccheck(void)
{
	char buf[64];
	long r, h;

	if(ovolopen(volspec, strlen(volspec)) != 1){
		fail("exec-check ovolopen: %r");
		exits("fail");
	}
	r = ospaceget(1, TestOid, buf, sizeof buf, nil);
	eperr("exec-check get handle 1", r);
	r = ospaceclose(1);
	eperr("exec-check close handle 1", r);
	if((h = openinit()) != 1)
		fail("exec-check new handle is %ld, want 1", h);
	r = ospaceget(h, TestOid, buf, sizeof buf, nil);
	checkval("exec-check read", buf, r, "later");
	if(ospaceclose(h) < 0)
		fail("exec-check close: %r");
	if(nfail != 0)
		exits("fail");
	print("ohandle: successful exec released handles PASS\n");
	exits(nil);
}

void
main(int argc, char *argv[])
{
	if(argc == 3 && strcmp(argv[1], "-vol") == 0){
		volspec = argv[2];
		runmain();
	}
	if(argc == 3 && strcmp(argv[1], "-exec-check") == 0){
		volspec = argv[2];
		runexeccheck();
	}
	fprint(2, "usage: %s -vol SPEC | -exec-check SPEC\n", argv[0]);
	exits("usage");
}
