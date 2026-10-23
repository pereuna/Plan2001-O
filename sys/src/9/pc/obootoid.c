/*
 * Plan2001 Boot Experiment C: the embedded first userspace loader.
 *
 * The kernel supplies a pointer (in BP via otouser) to this argument block
 * in the user stack: the exact plan9.ini obootvol PARTUUID string, the
 * native O Space name, the target OID and the target argv[0].  The loader
 * uses only the existing user native-O syscalls; it has no pathname, FD,
 * console or writable global state.
 */
#include <u.h>
#include <libc.h>

struct Oargs
{
	uvlong	oid;
	long	vollen;
	char	volspec[128];
	char	space[8];
	char	target[64];
};

extern long ovolopen(char*, int);
extern long ospaceopen(int, char*, int);
extern long ospaceget(int, uvlong, void*, long, uvlong*);
extern long oexecute(int, uvlong, char**, int);

void
_main(struct Oargs *a)
{
	char *av[2];
	long h;

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
	av[0] = a->target;
	av[1] = nil;
	oexecute(h, a->oid, av, 1);
	/* Failed load: the process-local handle must still be usable. */
	if(ospaceget(1, 0xffffffff00000000ULL, nil, 0, nil) >= 0)
		alarm(0x0baf);
	else
		alarm(0x0bae);
	for(;;)
		sleep(1000);
}
