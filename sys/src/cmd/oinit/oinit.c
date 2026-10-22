/*
 * Plan2001: the small embedded bootstrap for the normal O-only boot path
 * (docs/O-FORMAT.md 5.2, 7).  It opens the O volume and the flat "init"
 * Space and executes the MicroPython object by OID, passing the arguments
 * main.c actually needs:
 *
 *	micropython -O SPEC -S init -B
 *
 * The interpreter is in O, not in this image and not in a file: this
 * program carries no MicroPython copy and uses no pathname exec.  The O
 * handle does not cross exec; MicroPython opens its own O session from
 * the arguments below.  This harness is not a general program catalog or
 * loader; it uses one fixed experimental OID.
 *
 *	oinit -vol SPEC		execute MicroPython at OID_MP_EXEC
 *	oinit -repl -vol SPEC	the same, but no -S: an interactive REPL
 *	oinit -test -vol SPEC	missing/malformed object error checks
 *
 * The test mode stays alive so that the kernel's init process does not
 * exit; the QEMU gate stops the machine after the markers.
 */
#include <u.h>
#include <libc.h>
#include <libsec.h>

extern long ovolopen(char*, int);
extern long ospaceopen(int, char*, int);
extern long ospaceget(int, uvlong, void*, long, uvlong*);
extern long ospaceclose(int);
extern long oexecute(int, uvlong, char**, int);

enum {
	MpOid		= 0x4f45584543000003ULL,
	BadOid		= 0x4f45584543000002ULL,
	MissingOid	= 0x4f4558454300deadULL,
	Objexecmax	= 8*1024*1024,
	Maxargs		= 8,
};

static char *volspec;
static int repl, test;

static void
fail(char *fmt, ...)
{
	char msg[256];
	va_list va;

	va_start(va, fmt);
	vsnprint(msg, sizeof msg, fmt, va);
	va_end(va);
	print("FAIL: oinit: %s\n", msg);
	exits("fail");
}

static int
openvolume(void)
{
	if(volspec == nil)
		fail("no -vol");
	if(ovolopen(volspec, strlen(volspec)) != 1)
		fail("ovolopen: %r");
	return ospaceopen(1, "init", 4);
}

static void
hashobject(int h)
{
	uchar *buf, digest[SHA2_256dlen];
	long n;
	int i;

	if((n = ospaceget(h, MpOid, nil, 0, nil)) <= 0)
		fail("MicroPython object %#llux is missing from O: %r; "
			"prepare a fresh image with tools/mkovol", MpOid);
	if(n > Objexecmax)
		fail("MicroPython object is %ld bytes, over the %d limit", n, Objexecmax);
	if((buf = malloc(n)) == nil)
		fail("malloc: %r");
	if(ospaceget(h, MpOid, buf, n, nil) != n)
		fail("MicroPython object read: %r");
	sha2_256(buf, n, digest, nil);
	print("oinit: micropython object %ld bytes sha256 ", n);
	for(i = 0; i < SHA2_256dlen; i++)
		print("%.2ux", digest[i]);
	print("\n");
	free(buf);
}

static int
argvec(char **argv)
{
	int argc;

	argv[0] = "micropython";
	argv[1] = "-O";
	argv[2] = volspec;
	argc = 3;
	if(repl){
		/* -B without -S: boot.py sets up the console, then the REPL */
		argv[argc++] = "-B";
	}else{
		argv[argc++] = "-S";
		argv[argc++] = "init";
		argv[argc++] = "-B";
	}
	argv[argc] = nil;
	return argc;
}

static void
checkfail(int h, uvlong oid, char *what)
{
	char *argv[Maxargs];
	int argc;

	argc = argvec(argv);
	if(oexecute(h, oid, argv, argc) != -1)
		fail("%s did not return an error", what);
	print("oinit: %s returned an error PASS\n", what);
	if(ospaceget(h, MpOid, nil, 0, nil) <= 0)
		fail("handle unusable after %s: %r", what);
	print("oinit: handle usable after %s PASS\n", what);
}

static void
usage(void)
{
	fprint(2, "usage: oinit [-repl|-test] -vol SPEC\n");
	exits("usage");
}

void
main(int argc, char **argv)
{
	char *args[Maxargs];
	int h, i;

	for(i = 0; i < argc; i++){
		if(strcmp(argv[i], "-vol") == 0 && i+1 < argc)
			volspec = argv[++i];
		else if(strcmp(argv[i], "-repl") == 0)
			repl = 1;
		else if(strcmp(argv[i], "-test") == 0)
			test = 1;
		else if(i != 0)
			usage();
	}

	h = openvolume();
	if(h < 0)
		fail("ospaceopen: %r");
	if(test){
		checkfail(h, MissingOid, "missing interpreter");
		checkfail(h, BadOid, "malformed interpreter");
		if(ospaceclose(h) < 0)
			fail("close: %r");
		print("PASS: oinit object error handling\n");
		for(;;)
			sleep(1000);
	}
	hashobject(h);
	i = argvec(args);
	oexecute(h, MpOid, args, i);
	fail("MicroPython object %#llux could not be executed: %r", MpOid);
}
