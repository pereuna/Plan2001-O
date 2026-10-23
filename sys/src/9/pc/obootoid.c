/*
 * Plan2001 Boot Experiments C and D1: the embedded first userspace loader.
 *
 * The kernel supplies a pointer (in BP via otouser) to this argument block
 * in the user stack: the OID, the exact argv count and strings, the volume
 * spec and the native O Space name.  C passes one target argument; D1
 * passes the real six MicroPython arguments.  The loader uses only the
 * existing user native-O syscalls; it has no pathname, FD, console or
 * writable global state.
 */
#include <u.h>
#include <libc.h>

enum {
	Maxargv	= 8,
};

struct Oargs
{
	uvlong	oid;
	long	argc;
	long	vollen;
	char	volspec[128];
	char	space[8];
	char	argv[Maxargv][128];
};

extern long ovolopen(char*, int);
extern long ospaceopen(int, char*, int);
extern long ospaceget(int, uvlong, void*, long, uvlong*);
extern long oexecute(int, uvlong, char**, int);

void
_main(struct Oargs *a)
{
	char *av[Maxargv+1];
	long h;
	int i;

	if(ovolopen(a->volspec, a->vollen) != 1){
		alarm(0x0bad);
		for(;;)
			sleep(1000);
	}
	h = ospaceopen(1, a->space, 4);
	if(h < 0){
		alarm(0x0bae);
		for(;;)
			sleep(1000);
	}
	if(a->argc < 0 || a->argc > Maxargv){
		alarm(0x0bae);
		for(;;)
			sleep(1000);
	}
	for(i = 0; i < a->argc; i++)
		av[i] = a->argv[i];
	av[a->argc] = nil;
	oexecute(h, a->oid, av, a->argc);
	/* Failed load: the process-local handle must still be usable. */
	if(ospaceget(1, 0xffffffff00000000ULL, nil, 0, nil) >= 0)
		alarm(0x0baf);
	else
		alarm(0x0bae);
	for(;;)
		sleep(1000);
}
