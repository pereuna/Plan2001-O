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

	Oargmax		= 32,
	Oargbytes	= 16*1024,
	PGSZ		= 4096,
};

static char *volspec;
static int nfail;

/* RFMEM race test: the peer shares these, never the stack. */
static char rbuf1[256], rbuf2[256];
static char *rargv[2];
static volatile int rgo;

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

static void
reapclean(char *what)
{
	Waitmsg *w;

	if((w = wait()) == nil){
		fail("%s: wait: %r", what);
		return;
	}
	if(w->msg != nil && w->msg[0] != 0 && strcmp(w->msg, "clean") != 0)
		fail("%s: child exited: %s", what, w->msg);
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

static void
tryexec(char **args, int argc, char *what)
{
	long pid, h;

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0){
		fail("rfork %s: %r", what);
		return;
	}
	if(pid == 0){
		h = childopen();
		oexecute(h, ExecOid, args, argc);
		childfail("%s: oexecute success returned: %r", what);
	}
	reap();
	print("oexec: %s child PASS\n", what);
}

static void
tryfailargs(char **args, int argc, char *what)
{
	long r, pid, h;

	pid = rfork(RFPROC|RFFDG);
	if(pid < 0){
		fail("rfork %s: %r", what);
		return;
	}
	if(pid == 0){
		h = childopen();
		r = oexecute(h, ExecOid, args, argc);
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

static void
bulkfill(char *b, long n, int nul)
{
	memset(b, 'A', n);
	memmove(b, "BULK:", 5);
	if(nul)
		b[n] = 0;
}

static void
racetest(int h)
{
	char *b;
	long pid;
	int i, j, k, bad;
	Waitmsg *w;

	memset(rbuf1, 0, sizeof rbuf1);
	memset(rbuf2, 0, sizeof rbuf2);
	rbuf1[0] = 'm'; rbuf1[1] = 'u'; rbuf1[2] = 't'; rbuf1[255] = 0;
	rbuf2[0] = 'm'; rbuf2[1] = 'u'; rbuf2[2] = 't'; rbuf2[255] = 0;
	rargv[0] = "ohello";
	rargv[1] = rbuf1;
	bad = 0;
	for(i = 0; i < 32; i++){
		rgo = 0;
		pid = rfork(RFPROC|RFMEM|RFFDG);
		if(pid < 0){
			fail("race rfork: %r");
			break;
		}
		if(pid == 0){
			long ch;

			rgo = 1;
			ch = childopen();
			if(oexecute(ch, ExecOid, rargv, 2) == -1)
				exits("clean");
			exits("bad");
		}
		while(rgo == 0)
			sleep(0);
		for(j = 0; j < 2000; j++){
			b = (j & 1) ? rbuf1 : rbuf2;
			rargv[1] = b;
			for(k = 3; k < 255; k++)
				b[k] = 'a' + (j + k) % 26;
			b[4 + (j % 240)] = 0;
			b[0] = 'm'; b[1] = 'u'; b[2] = 't'; b[255] = 0;
		}
		if((w = wait()) == nil){
			fail("race wait: %r");
			break;
		}
		if(w->msg != nil && w->msg[0] != 0 && strcmp(w->msg, "clean") != 0){
			fail("race child exited: %s", w->msg);
			bad++;
		}
		free(w);
		if(ospaceget(h, ExecOid, nil, 0, nil) <= 0)
			fail("race: parent O handle unusable");
	}
	if(bad == 0)
		print("oexec: RFMEM argument mutation bounded PASS\n");
}

static void
argtests(int h)
{
	char *valid[] = { "ohello", "alpha", "", "gamma", "delta" };
	char *max[Oargmax], m[Oargmax][8];
	char *bulk[2], *no[2], *bad[2], *cross[2], **mis;
	char *b, *n, *pg;
	int i;
	long blen;

	for(i = 1; i < Oargmax; i++){
		snprint(m[i], sizeof m[i], "m%d", i);
		max[i] = m[i];
	}
	max[0] = "ohello";

	tryexec(nil, 0, "synthetic argc 0");
	tryexec(valid, 5, "valid argv");
	tryexec(max, Oargmax, "maximum argv");

	blen = Oargbytes - 8;	/* "ohello" NUL + string NUL */
	if((b = malloc(blen+1)) == nil)
		fail("bulk malloc: %r");
	else{
		bulkfill(b, blen, 1);
		bulk[0] = "ohello";
		bulk[1] = b;
		tryexec(bulk, 2, "bulk boundary accepted");
		free(b);
	}

	blen = Oargbytes - 7;	/* one byte past the aggregate limit */
	if((b = malloc(blen+1)) == nil)
		fail("over malloc: %r");
	else{
		bulkfill(b, blen, 1);
		bulk[0] = "ohello";
		bulk[1] = b;
		tryfailargs(bulk, 2, "aggregate over limit");
		free(b);
	}

	if((n = malloc(Oargbytes)) == nil)
		fail("nonul malloc: %r");
	else{
		memset(n, 'A', Oargbytes);
		no[0] = "ohello";
		no[1] = n;
		tryfailargs(no, 2, "missing NUL");
		free(n);
	}

	for(i = 0; i < 4; i++)
		tryfailargs(valid, -1, "negative argc");
	for(i = 0; i < 4; i++)
		tryfailargs(valid, Oargmax+1, "excessive argc");
	tryfailargs(nil, 1, "nil argv");
	mis = (char**)((uintptr)valid + 1);
	tryfailargs(mis, 5, "misaligned argv");

	bad[0] = "ohello";
	bad[1] = (char*)0xdeadbeef;
	for(i = 0; i < 4; i++)
		tryfailargs(bad, 2, "invalid string pointer");

	if((pg = segattach(0, "memory", nil, PGSZ)) == (void*)-1)
		fail("cross-page segattach: %r");
	else{
		pg[PGSZ-1] = 'X';
		cross[0] = "ohello";
		cross[1] = pg + PGSZ - 1;
		for(i = 0; i < 4; i++)
			tryfailargs(cross, 2, "cross-page string");
		if(segdetach(pg) < 0)
			fail("cross-page segdetach: %r");
	}

	racetest(h);
}

void
main(int argc, char *argv[])
{
	long pid, h;
	int i, argsmode;

	argsmode = 0;
	for(i = 1; i < argc; i++){
		if(strcmp(argv[i], "-args") == 0)
			argsmode = 1;
		else if(strcmp(argv[i], "-vol") == 0 && i+1 < argc)
			volspec = argv[++i];
		else{
			fprint(2, "usage: %s [-args] -vol SPEC\n", argv[0]);
			exits("usage");
		}
	}
	if(volspec == nil){
		fprint(2, "usage: %s [-args] -vol SPEC\n", argv[0]);
		exits("usage");
	}

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

	if(argsmode){
		argtests(h);
		if(ospaceget(h, ExecOid, nil, 0, nil) <= 0)
			fail("parent handle unusable after argv tests: %r");
		if(ospaceclose(h) < 0)
			fail("parent close: %r");
		if(nfail == 0)
			print("PASS: native O argv bounds, rollback and race\n");
		else
			print("FAIL: native O argv tests: %d checks failed\n", nfail);
		for(;;)
			sleep(1000);
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
