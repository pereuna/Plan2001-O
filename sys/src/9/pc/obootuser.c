/*
 * Plan2001 Boot Experiment B: the smallest userspace proof image.
 *
 * This is linked into a flat a.out image and copied into the first user
 * text page by the kernel; it is not a /boot program and does not use a
 * pathname, file descriptor, console or C startup.  It performs two
 * distinct non-file syscalls (alarm and sleep), then sleeps forever so
 * the scheduler and the user/kernel transitions remain observable.
 */
#include	<u.h>
#include	<libc.h>

void
_main(void)
{
	alarm(0);
	sleep(100);
	sleep(100);
	for(;;)
		sleep(1000);
}
