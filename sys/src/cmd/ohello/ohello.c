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
static char afail[] = "ohello: FAIL argv[0]\n";
static char tfail[] = "ohello: FAIL Tos fields\n";
static char bfail[] = "ohello: FAIL BSS boundary\n";

static void
fail(char *msg, int n)
{
	write(1, msg, n);
	exits("fail");
}

void
main(int argc, char **argv)
{
	char *a, *p;
	Tos *t;
	int i;

	if(ospaceget(1, ExecOid, nil, 0, nil) >= 0)
		fail(hfail, sizeof hfail-1);
	if(argc != 1 || argv == nil || (a = argv[0]) == nil)
		fail(afail, sizeof afail-1);
	for(i = 0; i < 6; i++)
		if(a[i] != "oexec "[i])
			fail(afail, sizeof afail-1);
	t = _tos;
	if(t == nil || t->cyclefreq == 0 || t->pid == 0 ||
	   t->prof.pp != nil || t->prof.next != nil || t->prof.last != nil ||
	   t->prof.first != nil || t->prof.pid != 0 || t->prof.what != 0)
		fail(tfail, sizeof tfail-1);
	if((p = (char*)0x100000000ULL)[0] != 0)
		fail(bfail, sizeof bfail-1);
	p[0] = 1;
	if(p[0] != 1)
		fail(bfail, sizeof bfail-1);
	write(1, marker, sizeof marker-1);
	write(1, okmsg, sizeof okmsg-1);
	exits(nil);
}
