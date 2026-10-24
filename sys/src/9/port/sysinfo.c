#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"

extern uchar	configfile[];

char*
sysnameget(void)
{
	return sysname;
}

void
sysnameset(char *s)
{
	kstrdup(&sysname, s);
}

char*
hostownerget(void)
{
	return eve;
}

char*
hostdomainget(void)
{
	return hostdomain;
}

char*
configget(void)
{
	return (char*)configfile;
}

char*
osversionget(void)
{
	return "2000";
}

/*
 * Privileged clock/control boundary.  Kernel callers with no process
 * context are trusted; a process-context caller must be the host owner.
 * This preserves the inherited iseve policy without dereferencing eve when
 * an O-only boot has no user namespace.
 */
int
timecontrolallowed(void)
{
	if(up == nil)
		return 1;
	if(eve == nil || up->user == nil)
		return 0;
	return strcmp(eve, up->user) == 0;
}

int
sysstatget(int id, Sysstat *v)
{
	Mach *mp;
	ulong l;

	if(id < 0 || id >= MAXMACH || !active.machs[id])
		return 0;
	mp = MACHP(id);
	v->id = id;
	v->cs = mp->cs;
	v->intr = mp->intr;
	v->syscall = mp->syscall;
	v->pfault = mp->pfault;
	v->tlbfault = mp->tlbfault;
	v->tlbpurge = mp->tlbpurge;
	v->load = mp->load;
	l = mp->perf.period;
	if(l == 0)
		l = 1;
	v->idle = (mp->perf.avg_inidle*100)/l;
	v->inintr = (mp->perf.avg_inintr*100)/l;
	return 1;
}

void
sysstatreset(void)
{
	int id;
	Mach *mp;

	for(id = 0; id < MAXMACH; id++) {
		if(!active.machs[id])
			continue;
		mp = MACHP(id);
		mp->cs = 0;
		mp->intr = 0;
		mp->syscall = 0;
		mp->pfault = 0;
		mp->tlbfault = 0;
		mp->tlbpurge = 0;
	}
}

/* /dev/null write semantics, without a file or Qid. */
long
nulldiscard(void *va, long n)
{
	(void)va;
	return n;
}

/* /dev/zero read semantics, without a file or Qid. */
long
zerofill(void *va, long n)
{
	memset(va, 0, n);
	return n;
}
