#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"

#include	"kernel_native.h"

/*
 * E2 opt-in native read probe.  This file is linked only in the
 * pc64native configuration; normal pc64/pc64mp link onativeprobe_stub.c.
 * The probe runs in a kernel process after the scheduler has started.
 * It does not create a user namespace, Chan, Fgrp or path.
 */

extern void rtcinit(void);
extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

static Rendez prober;

static void
probecounters(char *tag)
{
	print("ONATIVEPROBE: %s pid=%lud namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud\n",
		tag, up->pid,
		opath_namec, opath_newchan, opath_walk,
		opath_devwalk, opath_mount, opath_exec);
}

static void
probetext(char *label, char *buf, long n)
{
	char tmp[128];

	if(n < 0)
		n = 0;
	if(n >= sizeof tmp)
		n = sizeof tmp - 1;
	memmove(tmp, buf, n);
	tmp[n] = 0;
	print("%s=[%s]", label, tmp);
}

static int
probeaccept(char *who, ulong selector, void *buf, long n, vlong off, long want)
{
	long ret;

	if(waserror()){
		/* error()/nexterror() has already popped the error label. */
		print("ONATIVEPROBE: %s selector=%lud caught=1 err=%s\n",
			who, selector, up->errstr);
		return 0;
	}
	if(strcmp(who, "rtc") == 0)
		ret = native_rtc_read(selector, buf, n, off);
	else
		ret = native_cons_read(selector, buf, n, off);
	poperror();
	print("ONATIVEPROBE: %s selector=%lud n=%ld off=%lld ret=%ld want=%ld match=%d\n",
		who, selector, n, off, ret, want, ret == want);
	return ret == want;
}

static void
onativeprobe_proc(void *arg)
{
	char rbuf[64], pbuf[64], full[64], part[64], tmp[64];
	char rtext[64], ptext[64];
	long ret, ret2;
	ulong rtcval, pidval, ppid;

	USED(arg);

	/* chandevinit() has not run on this opt-in path; do the one RTC init. */
	consinit();
	rtcinit();
	print("ONATIVEPROBE: INIT rtcinit=done chandevinit=not-run\n");

	probecounters("BEGIN");

	memset(rbuf, 0, sizeof rbuf);
	ret = native_rtc_read(NATIVE_RTC_QRTC, rbuf, 32, 0);
	memmove(rtext, rbuf, sizeof rtext);
	rtext[sizeof rtext - 1] = 0;
	rtcval = strtoul(rtext, 0, 0);
	print("ONATIVEPROBE: RTC symbol=native_rtc_qrtc_read source=rtcqread selector=%d n=32 off=0 ret=%ld value=%lud\n",
		NATIVE_RTC_QRTC, ret, rtcval);
	print("ONATIVEPROBE: RTC ");
	probetext("text", rbuf, ret);
	print(" plausible=%d\n", rtcval > 1000000000UL && rtcval < 4000000000UL);

	ret = native_rtc_read(NATIVE_RTC_QRTC, full, NATIVE_RTC_QRTC_SIZE, 0);
	ret2 = native_rtc_read(NATIVE_RTC_QRTC, part, 4, 2);
	print("ONATIVEPROBE: RTC OFFSET fullret=%ld partret=%ld match=%d\n",
		ret, ret2, ret2 == 4 && memcmp(part, full + 2, 4) == 0);
	probeaccept("rtc", NATIVE_RTC_QRTC, rbuf, 64, 0, NATIVE_RTC_QRTC_SIZE);
	probeaccept("rtc", NATIVE_RTC_QRTC, rbuf, 0, 0, 0);
	probeaccept("rtc", NATIVE_RTC_QRTC, rbuf, 8, 4096, 0);

	memset(pbuf, 0, sizeof pbuf);
	ret = native_cons_read(NATIVE_CONS_QPID, pbuf, 32, 0);
	memmove(ptext, pbuf, sizeof ptext);
	ptext[sizeof ptext - 1] = 0;
	pidval = strtoul(ptext, 0, 0);
	print("ONATIVEPROBE: PID symbol=native_cons_qpid_read source=consqpidread selector=%d n=32 off=0 ret=%ld value=%lud pid=%lud match=%d\n",
		NATIVE_CONS_QPID, ret, pidval, (ulong)up->pid, pidval == (ulong)up->pid);
	print("ONATIVEPROBE: PID ");
	probetext("text", pbuf, ret);
	print(" pid_match=%d\n", pidval == (ulong)up->pid);

	ret = native_cons_read(NATIVE_CONS_QPID, full, NATIVE_CONS_QPID_SIZE, 0);
	ret2 = native_cons_read(NATIVE_CONS_QPID, part, 4, 2);
	print("ONATIVEPROBE: PID OFFSET fullret=%ld partret=%ld match=%d\n",
		ret, ret2, ret2 == 4 && memcmp(part, full + 2, 4) == 0);
	probeaccept("cons", NATIVE_CONS_QPID, pbuf, 64, 0, NATIVE_CONS_QPID_SIZE);
	probeaccept("cons", NATIVE_CONS_QPID, pbuf, 0, 0, 0);
	probeaccept("cons", NATIVE_CONS_QPID, pbuf, -5, 0, -5);
	probeaccept("cons", NATIVE_CONS_QPID, pbuf, 8, 4096, 0);

	/* Qppid is process context, including a valid parentpid of zero. */
	ppid = up->parentpid;
	memset(pbuf, 0, sizeof pbuf);
	ret = native_cons_read(NATIVE_CONS_QPPID, pbuf, 32, 0);
	pidval = strtoul(pbuf, 0, 10);
	snprint(ptext, sizeof ptext, "%11lud ", ppid);
	print("ONATIVEPROBE: PPID symbol=native_cons_qppid_read source=consread_qppid_read selector=%d n=32 off=0 ret=%ld value=%lud ppid=%lud match=%d\n",
		NATIVE_CONS_QPPID, ret, pidval, ppid, pidval == ppid);
	print("ONATIVEPROBE: PPID ");
	probetext("text", pbuf, ret);
	print(" format_match=%d\n", ret == NATIVE_CONS_QPPID_SIZE && memcmp(pbuf, ptext, NATIVE_CONS_QPPID_SIZE) == 0);
	ret = native_cons_read(NATIVE_CONS_QPPID, full, NATIVE_CONS_QPPID_SIZE, 0);
	ret2 = native_cons_read(NATIVE_CONS_QPPID, part, 4, 8);
	print("ONATIVEPROBE: PPID OFFSET fullret=%ld partret=%ld match=%d\n",
		ret, ret2, ret2 == 4 && memcmp(part, full + 8, 4) == 0);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, 64, 0, NATIVE_CONS_QPPID_SIZE);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, 0, 0, 0);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, -5, 0, -5);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, 8, 4096, 0);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, 8, -1, 0);
	probeaccept("cons", NATIVE_CONS_QPPID, pbuf, 8, 0x100000000LL, 8);

	print("ONATIVEPROBE: AUTH rtc=kernel-internal-only cons=kernel-internal-only up=set\n");
	probeaccept("rtc", NATIVE_RTC_QRTC + 100, tmp, 8, 0, 0);
	probeaccept("cons", NATIVE_CONS_QPID + 100, tmp, 8, 0, 0);

	/*
	 * E5 native-service probes.  These call the same kernel C operations
	 * that the legacy #c adapter delegates to; they do not create a Chan,
	 * namespace or userspace ABI, and they do not execute panic/reboot.
	 */
	{
		char log[192], kb[384], zb[8], r1[32], r2[32];
		char *saveuser, *sv;
		vlong now;
		uvlong ct[6];
		Sysstat st;
		long off, lret;
		int pid, ppid, nct, a1, a2, a3, have, i;
		int logmark, kprintmark, denied, zok;

		/* console output and kernel log ring snapshot */
		print("ONATIVEPROBE: E5-LOG-MARK alpha\n");
		off = kmesg.n > 160 ? kmesg.n - 160 : 0;
		memset(log, 0, sizeof log);
		lret = kmesgreadat(log, sizeof log - 1, off);
		if(lret < 0)
			lret = 0;
		log[lret] = 0;
		logmark = strstr(log, "E5-LOG-MARK alpha") != nil;
		print("ONATIVEPROBE: E5 CONSOLE logret=%ld logmark=%d\n", lret, logmark);

		/* time and entropy are initialized by consinit() in this kernel process */
		now = todget(nil, nil);
		randomread(r1, sizeof r1);
		randomread(r2, sizeof r2);
		print("ONATIVEPROBE: E5 TIME now=%lld plausible=%d random_diff=%d\n",
			now, now > 1000000000LL, memcmp(r1, r2, sizeof r1) != 0);

		/* typed process observations */
		pid = procpid();
		ppid = procppid();
		memset(ct, 0, sizeof ct);
		nct = proccputimes(ct, 6);
		sv = procusername();
		print("ONATIVEPROBE: E5 PROC pid=%d up_pid=%lud match=%d ppid=%d up_ppid=%lud match=%d ct=%d user_match=%d\n",
			pid, up->pid, pid == (int)up->pid,
			ppid, up->parentpid, ppid == (int)up->parentpid,
			nct, sv != nil && up->user != nil && strcmp(sv, up->user) == 0);

		/* read-only configuration getters and safe sysname set/get */
		print("ONATIVEPROBE: E5 CONFIG config=%d osversion=%d sysname_set=%d\n",
			configget() != nil, osversionget() != nil && strcmp(osversionget(), "2000") == 0,
			(sysnameset("e5probe"), sysnameget() != nil && strcmp(sysnameget(), "e5probe") == 0));

		/* privileged clock gate: an unprivileged process context is denied */
		saveuser = up->user;
		up->user = "e5-unprivileged";
		denied = !timecontrolallowed();
		up->user = saveuser;
		print("ONATIVEPROBE: E5 DENIED time_control=%d\n", denied);

		/* exclusive console reader and close/reopen semantics */
		a1 = kprintacquire();
		a2 = kprintacquire();
		print("ONATIVEPROBE: E5-KPRINT-MARK beta\n");
		memset(kb, 0, sizeof kb);
		lret = kprintread(kb, sizeof kb - 1);
		if(lret < 0)
			lret = 0;
		kb[lret] = 0;
		kprintmark = strstr(kb, "E5-KPRINT-MARK beta") != nil;
		kprintrelease();
		a3 = kprintacquire();
		kprintrelease();
		print("ONATIVEPROBE: E5 KPRINT acquire=%d busy=%d read=%ld mark=%d reopen=%d\n",
			a1, a2, lret, kprintmark, a3);

		/* typed monitoring and synthetic semantics */
		have = sysstatget(0, &st);
		memset(zb, 1, sizeof zb);
		lret = zerofill(zb, sizeof zb);
		zok = lret == sizeof zb;
		for(i = 0; i < sizeof zb; i++)
			if(zb[i] != 0)
				zok = 0;
		print("ONATIVEPROBE: E5 MONITOR sysstat=%d id=%d nulldiscard=%ld zero=%d\n",
			have, have ? st.id : -1, nulldiscard(zb, sizeof zb), zok);
	}

	probecounters("END");

	/*
	 * Legacy-adapter control, after the pathless measured window above.
	 * This exercises the real consdevtab walk/read/write callbacks and
	 * the shared cputime formatting plus the privileged Qtime refusal.
	 * It intentionally uses a legacy Chan; the native paths above do not.
	 */
	{
		Dev *d;
		Chan *c, *nc;
		Walkqid *wq;
		char *name, *saveuser;
		char lbuf[128];
		long lr;
		int fmtok, denied;

		d = devtab[devno('c')];
		c = d->attach("");
		name = "cputime";
		wq = d->walk(c, nil, &name, 1);
		nc = wq->clone;
		lr = d->read(nc, lbuf, sizeof lbuf, 0);
		fmtok = lr == 6*NUMSIZE;
		cclose(nc);
		free(wq);
		cclose(c);

		denied = 0;
		c = d->attach("");
		name = "time";
		wq = d->walk(c, nil, &name, 1);
		nc = wq->clone;
		saveuser = up->user;
		up->user = "e5-unprivileged";
		if(waserror())
			denied = 1;
		else {
			d->write(nc, "0", 1, 0);
			poperror();
		}
		up->user = saveuser;
		cclose(nc);
		free(wq);
		cclose(c);
		print("ONATIVEPROBE: E5 LEGACY cputime=%ld fmt=%d time_denied=%d\n",
			lr, fmtok, denied);
	}

	print("ONATIVEPROBE: DONE\n");
	for(;;)
		tsleep(&prober, return0, nil, 60000);
}

int
onativeprobe_start(void)
{
	char *p;

	p = getconf("onativeprobe");
	if(p == nil || strcmp(p, "1") != 0)
		return 0;
	up = nil;
	kstrdup(&eve, "");
	kproc("*onativeprobe*", onativeprobe_proc, nil);
	return 1;
}

int
e71etherprobe_start(void)
{
	return 0;
}

int
e72ipv6probe_start(void)
{
	return 0;
}

int
e73udpprobe_start(void)
{
	return 0;
}

int
e74ipprobe_start(void)
{
	return 0;
}
