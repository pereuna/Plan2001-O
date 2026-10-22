#include <u.h>
#include <libc.h>

extern long ovolopen(char*, int);
extern long ospaceopen(int, char*, int);
extern long ospaceget(int, uvlong, void*, long, uvlong*);
extern long ospaceclose(int);
extern long oexecute(int, uvlong, char**, int);

enum {
	ExecOid		= 0x4f45584543000001ULL,
	BadOid		= 0x4f45584543000002ULL,
	MissingOid	= 0x4f4558454300deadULL,
};

static char *volspec;
static int nfail;

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
childopen(void)
{
	long h;

	if(ovolopen(volspec, strlen(volspec)) != 1)
		childfail("ovolopen: %r");
	if((h = ospaceopen(1, "init", 4)) < 0)
		childfail("ospaceopen: %r");
	return h;
}

static void
stillusable(int h, char *what)
{
	if(ospaceget(h, ExecOid, nil, 0, nil) <= 0)
		childfail("%s: O handle unusable after failed load: %r", what);
}

static void
tryfail(uvlong oid, char *what)
{
	long r, pid, h;

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0){
		fail("rfork %s: %r", what);
		return;
	}
	if(pid == 0){
		h = childopen();
		r = oexecute(h, oid, nil, 0);
		if(r != -1)
			childfail("%s: oexecute returned %ld, want an error", what, r);
		stillusable(h, what);
		if(ospaceclose(h) < 0)
			childfail("%s: close after failure: %r", what);
		print("oexec: %s returned an error and preserved the handle PASS\n", what);
		exits(nil);
	}
	reap();
}

void
main(int argc, char *argv[])
{
	long pid, h;

	if(argc != 3 || strcmp(argv[1], "-vol") != 0){
		fprint(2, "usage: %s -vol SPEC\n", argv[0]);
		exits("usage");
	}
	volspec = argv[2];
	if(ovolopen(volspec, strlen(volspec)) != 1){
		fail("ovolopen: %r");
		exits("fail");
	}
	if((h = ospaceopen(1, "init", 4)) < 0){
		fail("parent ospaceopen: %r");
		exits("fail");
	}
	if(ospaceget(h, ExecOid, nil, 0, nil) < 0){
		fail("native executable object is missing: %r");
		exits("fail");
	}

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0)
		fail("rfork success: %r");
	else if(pid == 0){
		long ch;

		ch = childopen();
		oexecute(ch, ExecOid, nil, 0);
		childfail("oexecute success returned: %r");
	}else{
		reap();
		print("oexec: parent observed native child completion PASS\n");
	}
	if(ospaceget(h, ExecOid, nil, 0, nil) <= 0)
		fail("parent handle unusable after native exec: %r");

	tryfail(MissingOid, "missing OID");
	tryfail(BadOid, "malformed executable");

	if(ospaceclose(h) < 0)
		fail("parent close: %r");
	if(nfail == 0)
		print("PASS: native O executable loading, child execution and rollback\n");
	else
		print("FAIL: native O executable loading: %d checks failed\n", nfail);
	for(;;)
		sleep(1000);
}
