/*
 * Plan2001 Boot Experiment C: O-resident post-exec target.
 *
 * This program exists only as bytes in the disposable GE/O volume.  It is
 * replaced into the Boot-C process by OEXECUTE and must not use fd 0/1/2,
 * the console or a pathname.  Distinct alarm/sleep arguments identify the
 * post-exec image in the kernel's ring-3 syscall trace.
 */
#include <u.h>
#include <libc.h>

extern long ospaceget(int, uvlong, void*, long, uvlong*);

void
main(int argc, char **argv)
{
	USED(argc);
	USED(argv);
	/* The pre-exec O handle must not survive the image replacement. */
	if(ospaceget(1, 0x4f45584543000004ULL, nil, 0, nil) >= 0)
		alarm(0x0f00);
	alarm(0x42);
	sleep(0x1234);
	sleep(0x5678);
	for(;;)
		sleep(1000);
}
