#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"

#include	<authsrv.h>

/*
 * Legacy #c adapter.  The kernel services it exposes (console output and
 * log, time, entropy, process observations, configuration, monitoring and
 * control) live in cons.c, sysinfo.c, procobs.c, tod.c and random.c.  This
 * file owns only Plan 9 namespace plumbing, legacy text/binary encoding and
 * the two reviewed E4 text helpers.
 */

static int	readtime(ulong, char*, int);
static int	readbintime(char*, int);
static int	writetime(char*, int);
static int	writebintime(char*, int);

enum
{
	CMreboot,
	CMpanic,
	CMrdb,
};

Cmdtab rebootmsg[] =
{
	CMreboot,	"reboot",	0,
	CMpanic,	"panic",	0,
	CMrdb,		"rdb",		0,
};

enum
{
	CMchdev,
};

Cmdtab drivermsg[] = 
{
	CMchdev,	"chdev",	0,
};

enum{
	Qdir,
	Qbintime,
	Qcons,
	Qconsctl,
	Qcputime,
	Qdrivers,
	Qkmesg,
	Qkprint,
	Qhostdomain,
	Qhostowner,
	Qnull,
	Qosversion,
	Qpid,
	Qppid,
	Qrandom,
	Qreboot,
	Qsysname,
	Qsysstat,
	Qtime,
	Quser,
	Qzero,
	Qmordor,
	Qconfig,
};

enum
{
	VLNUMSIZE=	22,
};

static Dirtab consdir[]={
	".",	{Qdir, 0, QTDIR},	0,		DMDIR|0555,
	"bintime",	{Qbintime},	24,		0664,
	"cons",		{Qcons},	0,		0660,
	"consctl",	{Qconsctl},	0,		0220,
	"cputime",	{Qcputime},	6*NUMSIZE,	0444,
	"drivers",	{Qdrivers},	0,		0666,
	"hostdomain",	{Qhostdomain},	DOMLEN,		0664,
	"hostowner",	{Qhostowner},	0,		0664,
	"kmesg",	{Qkmesg},	0,		0440,
	"kprint",	{Qkprint, 0, QTEXCL},	0,	DMEXCL|0440,
	"null",		{Qnull},	0,		0666,
	"osversion",	{Qosversion},	0,		0444,
	"pid",		{Qpid},		NUMSIZE,	0444,
	"ppid",		{Qppid},	NUMSIZE,	0444,
	"random",	{Qrandom},	0,		0444,
	"reboot",	{Qreboot},	0,		0220,
	"sysname",	{Qsysname},	0,		0664,
	"sysstat",	{Qsysstat},	0,		0664,
	"time",		{Qtime},	NUMSIZE+3*VLNUMSIZE,	0664,
	"user",		{Quser},	0,		0666,
	"zero",		{Qzero},	0,		0444,
	"config",	{Qconfig},	0,		0444,
	"mordor",	{Qmordor},	0,		0666,
};

static Chan*
consattach(char *spec)
{
	return devattach('c', spec);
}

static Walkqid*
conswalk(Chan *c, Chan *nc, char **name, int nname)
{
	return devwalk(c, nc, name,nname, consdir, nelem(consdir), devgen);
}

static int
consstat(Chan *c, uchar *dp, int n)
{
	return devstat(c, dp, n, consdir, nelem(consdir), devgen);
}

static Chan*
consopen(Chan *c, int omode)
{
	int r;

	c->aux = nil;
	c = devopen(c, omode, consdir, nelem(consdir), devgen);
	switch((ulong)c->qid.path){
	case Qkprint:
		r = kprintacquire();
		if(r == -1){
			c->flag &= ~COPEN;
			error(Einuse);
		}
		if(r == -2){
			c->flag &= ~COPEN;
			error(Enomem);
		}
		c->iounit = qiomaxatomic;
		break;
	}
	return c;
}

static void
consclose(Chan *c)
{
	switch((ulong)c->qid.path){
	/* close of kprint allows other opens */
	case Qkprint:
		if(c->flag & COPEN)
			kprintrelease();
		break;
	}
}

/*
 * E2: shared Chan-free Qpid read body.  consread's Qpid branch and the
 * generated native entry both call this; copyin/name/Qid dispatch stays in
 * consread.
 */
long
consqpidread(void *buf, long n, vlong off)
{
	if(n <= 0)
		return n;
	return readnum((ulong)off, buf, n, up->pid, NUMSIZE);
}

/*
 * E3 proposal: cons read Qppid extraction candidate.
 * Kernel-internal only; review before applying.  Not an approved ABI.
 */
long
consread_qppid_read(void *buf, long n, vlong off)
{
	if(n <= 0) return n;
	vlong offset = off;
	return readnum((ulong)offset, buf, n, up->parentpid, NUMSIZE);
}

static long
consread(Chan *c, void *buf, long n, vlong off)
{
	ulong l;
	char *b, *bp;
	char *str;
	char tmp[256];
	int i, k, id;
	vlong offset = off;
	uvlong ct[6];
	Sysstat st;

	if(n <= 0)
		return n;

	switch((ulong)c->qid.path){
	case Qdir:
		return devdirread(c, buf, n, consdir, nelem(consdir), devgen);

	case Qcons:
		error(Egreg);

	case Qcputime:
		k = offset;
		if(k >= 6*NUMSIZE)
			return 0;
		if(k+n > 6*NUMSIZE)
			n = 6*NUMSIZE - k;
		/* easiest to format in a separate buffer and copy out */
		memset(ct, 0, sizeof ct);
		proccputimes(ct, 6);
		for(i=0; i<6 && NUMSIZE*i<k+n; i++){
			l = ct[i];
			readnum(0, tmp+NUMSIZE*i, NUMSIZE, l, NUMSIZE);
		}
		memmove(buf, tmp+k, n);
		return n;

	case Qkmesg:
		return kmesgreadat(buf, n, off);

	case Qkprint:
		return kprintread(buf, n);

	case Qpid:
		return consqpidread(buf, n, off);

	case Qppid:
		return consread_qppid_read(buf, n, off);

	case Qtime:
		return readtime((ulong)offset, buf, n);

	case Qbintime:
		return readbintime(buf, n);

	case Qhostowner:
		return readstr((ulong)offset, buf, n, hostownerget());

	case Qhostdomain:
		return readstr((ulong)offset, buf, n, hostdomainget());

	case Quser:
		str = procusername();
		if(str == nil)
			return 0;
		return readstr((ulong)offset, buf, n, str);

	case Qnull:
		return 0;

	case Qconfig:
		return readstr((ulong)offset, buf, n, configget());

	case Qsysstat:
		b = smalloc(conf.nmach*(NUMSIZE*11+1) + 1);	/* +1 for NUL */
		bp = b;
		for(id = 0; id < MAXMACH; id++) {
			if(!sysstatget(id, &st))
				continue;
			readnum(0, bp, NUMSIZE, st.id, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.cs, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.intr, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.syscall, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.pfault, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.tlbfault, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.tlbpurge, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.load, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.idle, NUMSIZE);
			bp += NUMSIZE;
			readnum(0, bp, NUMSIZE, st.inintr, NUMSIZE);
			bp += NUMSIZE;
			*bp++ = '\n';
		}
		if(waserror()){
			free(b);
			nexterror();
		}
		n = readstr((ulong)offset, buf, n, b);
		free(b);
		poperror();
		return n;

	case Qsysname:
		str = sysnameget();
		if(str == nil)
			return 0;
		return readstr((ulong)offset, buf, n, str);

	case Qrandom:
		return randomread(buf, n);

	case Qdrivers:
		b = smalloc(READSTR);
		k = 0;
		for(i = 0; devtab[i] != nil; i++){
			if(devmasked(up->pgrp, i))
				continue;
			k += snprint(b+k, READSTR-k, "#%C %s\n",
				devtab[i]->dc, devtab[i]->name);
		}
		if(waserror()){
			free(b);
			nexterror();
		}
		n = readstr((ulong)offset, buf, n, b);
		poperror();
		free(b);
		return n;

	case Qzero:
		return zerofill(buf, n);
	
	case Qmordor:
		error("one does not simply read from mordor");

	case Qosversion:
		str = osversionget();
		snprint(tmp, sizeof tmp, "%s", str);
		n = readstr((ulong)offset, buf, n, tmp);
		return n;

	default:
		print("consread %#llux\n", c->qid.path);
		error(Egreg);
	}
}

static long
conswrite(Chan *c, void *va, long n, vlong off)
{
	char buf[256];
	long l, bp;
	char *a;
	ulong offset;
	Cmdbuf *cb;
	Cmdtab *ct;

	a = va;
	offset = off;

	switch((ulong)c->qid.path){
	case Qcons:
		/*
		 * Can't page fault in putstrn, so copy the data locally.
		 */
		l = n;
		while(l > 0){
			bp = l;
			if(bp > sizeof buf)
				bp = sizeof buf;
			memmove(buf, a, bp);
			consputstr(buf, bp, 1);
			a += bp;
			l -= bp;
		}
		break;

	case Qconsctl:
		error(Egreg);

	case Qtime:
		if(!timecontrolallowed())
			error(Eperm);
		return writetime(a, n);

	case Qbintime:
		if(!timecontrolallowed())
			error(Eperm);
		return writebintime(a, n);

	case Qhostowner:
		return hostownerwrite(a, n);

	case Qhostdomain:
		return hostdomainwrite(a, n);

	case Quser:
		return userwrite(a, n);

	case Qnull:
		break;

	case Qconfig:
		error(Eperm);
		break;

	case Qdrivers:
		cb = parsecmd(a, n);
		if(waserror()) {
			free(cb);
			nexterror();
		}

		ct = lookupcmd(cb, drivermsg, nelem(drivermsg));
		if(ct == nil)
			error(Ebadarg);
		if(ct->index != CMchdev)
			error(Ebadarg);
		if(cb->nf == 1)
			error(Ebadarg);
		switch(cb->f[1][0]){
		case '&':
			if(cb->nf != 3)
				error(Ebadarg);
			devmask(up->pgrp, cb->f[1][1] != '~', cb->f[2]);
			break;
		case '~':
			if(cb->nf != 2)
				error(Ebadarg);
			devmask(up->pgrp, 1, "");
			break;
		default:
			error(Ebadarg);
			break;
		}
		poperror();
		free(cb);
		break;

	case Qreboot:
		if(!timecontrolallowed())
			error(Eperm);
		cb = parsecmd(a, n);

		if(waserror()) {
			free(cb);
			nexterror();
		}
		ct = lookupcmd(cb, rebootmsg, nelem(rebootmsg));
		switch(ct->index) {
		case CMreboot:
			rebootcmd(cb->nf-1, cb->f+1);
			break;
		case CMpanic:
			*(ulong*)0=0;
			panic("/dev/reboot");
		case CMrdb:
			if(consdebug == nil)
				consdebug = rdb;
			consdebug();
			break;
		}
		poperror();
		free(cb);
		break;

	case Qsysstat:
		sysstatreset();
		break;

	case Qsysname:
		if(offset != 0)
			error(Ebadarg);
		if(n <= 0 || n >= sizeof buf)
			error(Ebadarg);
		strncpy(buf, a, n);
		buf[n] = 0;
		if(buf[n-1] == '\n')
			buf[n-1] = 0;
		sysnameset(buf);
		break;
	
	case Qmordor:
		error("one does not simply write into mordor");

	default:
		print("conswrite: %#llux\n", c->qid.path);
		error(Egreg);
	}
	return n;
}

Dev consdevtab = {
	'c',
	"cons",

	devreset,
	consinit,
	devshutdown,
	consattach,
	conswalk,
	consstat,
	consopen,
	devcreate,
	consclose,
	consread,
	devbread,
	conswrite,
	devbwrite,
	devremove,
	devwstat,
};

static uvlong uvorder = 0x0001020304050607ULL;

static uchar*
be2vlong(vlong *to, uchar *f)
{
	uchar *t, *o;
	int i;

	t = (uchar*)to;
	o = (uchar*)&uvorder;
	for(i = 0; i < sizeof(vlong); i++)
		t[o[i]] = f[i];
	return f+sizeof(vlong);
}

static uchar*
vlong2be(uchar *t, vlong from)
{
	uchar *f, *o;
	int i;

	f = (uchar*)&from;
	o = (uchar*)&uvorder;
	for(i = 0; i < sizeof(vlong); i++)
		t[i] = f[o[i]];
	return t+sizeof(vlong);
}

static long order = 0x00010203;

static uchar*
be2long(long *to, uchar *f)
{
	uchar *t, *o;
	int i;

	t = (uchar*)to;
	o = (uchar*)&order;
	for(i = 0; i < sizeof(long); i++)
		t[o[i]] = f[i];
	return f+sizeof(long);
}

char *Ebadtimectl = "bad time control";

/*
 *  like the old #c/time but with added info.  Return
 *
 *	secs	nanosecs	fastticks	fasthz
 */
static int
readtime(ulong off, char *buf, int n)
{
	vlong	nsec, ticks, mono;
	long sec;
	char str[9*NUMSIZE];

	nsec = todget(&ticks, &mono);
	if(fasthz == 0LL)
		fastticks((uvlong*)&fasthz);
	sec = nsec/1000000000ULL;
	snprint(str, sizeof(str), "%*lud %*llud %*llud %*llud %*llud ",
		NUMSIZE-1, sec,
		VLNUMSIZE-1, nsec,
		VLNUMSIZE-1, ticks,
		VLNUMSIZE-1, fasthz,
		VLNUMSIZE-1, mono);
	return readstr(off, buf, n, str);
}

/*
 *  set the time in seconds
 */
static int
writetime(char *buf, int n)
{
	char b[13];
	long i;
	vlong now;

	if(n >= sizeof(b))
		error(Ebadtimectl);
	strncpy(b, buf, n);
	b[n] = 0;
	i = strtol(b, 0, 0);
	if(i <= 0)
		error(Ebadtimectl);
	now = i*1000000000LL;
	todset(now, 0, 0);
	return n;
}

/*
 *  read binary time info.  all numbers are little endian.
 *  ticks and nsec are syncronized.
 */
static int
readbintime(char *buf, int n)
{
	int i;
	vlong nsec, ticks, mono;
	uchar *b = (uchar*)buf;

	i = 0;
	if(fasthz == 0LL)
		fastticks((uvlong*)&fasthz);
	nsec = todget(&ticks, &mono);
	if(n >= 4*sizeof(uvlong)){
		vlong2be(b+3*sizeof(uvlong), mono);
		i += sizeof(uvlong);
	}
	if(n >= 3*sizeof(uvlong)){
		vlong2be(b+2*sizeof(uvlong), fasthz);
		i += sizeof(uvlong);
	}
	if(n >= 2*sizeof(uvlong)){
		vlong2be(b+sizeof(uvlong), ticks);
		i += sizeof(uvlong);
	}
	if(n >= 8){
		vlong2be(b, nsec);
		i += sizeof(vlong);
	}
	return i;
}

/*
 *  set any of the following
 *	- time in nsec
 *	- nsec trim applied over some seconds
 *	- clock frequency
 */
static int
writebintime(char *buf, int n)
{
	uchar *p;
	vlong delta;
	long period;

	if(--n <= 0)
		error(Ebadtimectl);
	p = (uchar*)buf + 1;
	switch(*buf){
	case 'n':
		if(n < sizeof(vlong))
			error(Ebadtimectl);
		be2vlong(&delta, p);
		todset(delta, 0, 0);
		break;
	case 'd':
		if(n < sizeof(vlong)+sizeof(long))
			error(Ebadtimectl);
		p = be2vlong(&delta, p);
		be2long(&period, p);
		todset(-1, delta, period);
		break;
	case 'f':
		if(n < sizeof(uvlong))
			error(Ebadtimectl);
		be2vlong(&fasthz, p);
		if(fasthz <= 0)
			error(Ebadtimectl);
		todsetfreq(fasthz);
		break;
	}
	return n+1;
}
