#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"

/*
 * The initcode array contains the binary text of the first
 * user process. Its job is to invoke the exec system call
 * for /boot/boot.
 * Initcode does not link with standard plan9 libc _main()
 * trampoline due to size constrains. Instead it is linked
 * with a small machine specific trampoline init9.s that
 * only sets the base address register and passes arguments
 * to startboot() (see port/initcode.c).
 */
#include	"initcode.i"

/*
 * Plan2001 Boot Experiment A: opt-in kernel-only first task
 * (plan9.ini oboot=probe).  The counters distinguish the legacy
 * user-bootstrap path from the experimental one on the executed boot.
 */
int	oboot_probe;
uvlong	oboot_legacy_userinit, oboot_legacy_proc0, oboot_legacy_init0;

extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

/*
 * The first process kernel process starts here.
 */
static void
proc0(void*)
{
	KMap *k;
	Page *p;

	oboot_legacy_proc0++;
	spllo();
	if(waserror())
		panic("proc0: %s", up->errstr);

	up->pgrp = newpgrp();
	up->egrp = smalloc(sizeof(Egrp));
	up->egrp->ref = 1;
	up->fgrp = dupfgrp(nil);
	up->rgrp = newrgrp();

	/*
	 * These are o.k. because rootinit is null.
	 * Then early kproc's will have a root and dot.
	 */
	up->slash = namec("#/", Atodir, 0, 0);
	pathclose(up->slash->path);
	up->slash->path = newpath("/");
	up->dot = cclone(up->slash);

	/*
	 * Setup Text and Stack segments for initcode.
	 */
	up->seg[SSEG] = newseg(SG_STACK | SG_NOEXEC, USTKTOP-USTKSIZE, USTKSIZE / BY2PG);
	up->seg[TSEG] = newseg(SG_TEXT | SG_RONLY, UTZERO, 1);
	up->seg[TSEG]->flushme = 1;
	p = newpage(UTZERO, nil);
	k = kmap(p);
	memmove((uchar*)VA(k), initcode, sizeof(initcode));
	memset((uchar*)VA(k)+sizeof(initcode), 0, BY2PG-sizeof(initcode));
	kunmap(k);
	segpage(up->seg[TSEG], p);

	/*
	 * Become a user process.
	 */
	up->kp = 0;
	up->noswap = 0;
	up->privatemem = 0;
	procpriority(up, PriNormal, 0);
	procsetup(up);

	flushmmu();

	poperror();

	/*
	 * init0():
	 *	call chandevinit()
	 *	setup environment variables
	 *	prepare the stack for initcode
	 *	switch to usermode to run initcode
	 */
	init0();

	/* init0 will never return */
	panic("init0");
}

void
userinit(void)
{
	oboot_legacy_userinit++;
	up = nil;
	kstrdup(&eve, "");
	kproc("*init*", proc0, nil);
}

/*
 * Boot Experiment A: a kernel-only first task.  It deliberately does
 * not call chandevinit, init0, touser, namec, bind, mount or exec, and
 * it never constructs a user-mode namespace.  The task runs only after
 * schedinit() has entered the scheduler, then stays asleep.
 */
static Rendez obootr;

static void
oprobesched(void *arg)
{
	int i;

	USED(arg);
	print("OBOOT-A: KPROC-RUNNING pid=%lud slash=%s dot=%s\n",
		up->pid, up->slash == nil ? "nil" : "set",
		up->dot == nil ? "nil" : "set");
	print("OBOOT-A: legacy-calls userinit=%llud proc0=%llud init0=%llud\n",
		oboot_legacy_userinit, oboot_legacy_proc0, oboot_legacy_init0);
	print("OBOOT-A: path-calls namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud\n",
		opath_namec, opath_newchan, opath_walk, opath_devwalk,
		opath_mount, opath_exec);
	for(i = 0; i < 2; i++){
		tsleep(&obootr, return0, nil, 1000);
		print("OBOOT-A: HEARTBEAT %d pid=%lud ticks=%lud\n",
			i+1, up->pid, MACHP(0)->ticks);
	}
	for(;;)
		tsleep(&obootr, return0, nil, 60000);
}

void
ouserinit(void)
{
	up = nil;
	kstrdup(&eve, "");
	kproc("*oprobes*", oprobesched, nil);
}
