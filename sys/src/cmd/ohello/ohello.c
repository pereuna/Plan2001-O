#include <u.h>
#include <libc.h>
#include <tos.h>

extern long ospaceget(int, uvlong, void*, long, uvlong*);

enum {
	ExecOid		= 0x4f45584543000001ULL,
};

static char marker[] = "ohello: native executable from O marker\n";
static char okmsg[] = "ohello: argv, Tos and BSS boundary PASS\n";
static char hfail[] = "ohello: FAIL O handle survived native exec\n";
static char afail[] = "ohello: FAIL argv\n";
static char tfail[] = "ohello: FAIL Tos fields\n";
static char bfail[] = "ohello: FAIL BSS boundary\n";

static void
fail(char *msg, int n)
{
	write(1, msg, n);
	exits("fail");
}

static void
checktos(void)
{
	Tos *t;

	t = _tos;
	if(t == nil || t->cyclefreq == 0 || t->pid == 0 ||
	   t->prof.pp != nil || t->prof.next != nil || t->prof.last != nil ||
	   t->prof.first != nil || t->prof.pid != 0 || t->prof.what != 0)
		fail(tfail, sizeof tfail-1);
}

void
main(int argc, char **argv)
{
	char *a, *p;
	int i;

	if(ospaceget(1, ExecOid, nil, 0, nil) >= 0)
		fail(hfail, sizeof hfail-1);
	if(argc <= 0 || argv == nil || argv[argc] != nil)
		fail(afail, sizeof afail-1);
	checktos();

	if(argc == 1 && (a = argv[0]) != nil && strncmp(a, "oexec ", 6) == 0){
		if((p = (char*)0x100000000ULL)[0] != 0)
			fail(bfail, sizeof bfail-1);
		p[0] = 1;
		if(p[0] != 1)
			fail(bfail, sizeof bfail-1);
		write(1, marker, sizeof marker-1);
		write(1, okmsg, sizeof okmsg-1);
		exits(nil);
	}

	if(argc == 2 && strncmp(argv[1], "BULK:", 5) == 0){
		print("ohello: bulk len %ld\n", strlen(argv[1]));
		print("ohello: argv PASS\n");
		exits(nil);
	}
	if(argc >= 2 && strncmp(argv[1], "mut", 3) == 0){
		print("ohello: mut argv PASS\n");
		exits(nil);
	}
	print("ohello: argc %d\n", argc);
	for(i = 0; i < argc; i++)
		print("ohello: arg[%d]=<%s>\n", i, argv[i]);
	print("ohello: argv PASS\n");
	exits(nil);
}
