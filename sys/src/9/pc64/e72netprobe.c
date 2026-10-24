/*
 * E7.2 opt-in native IPv6 probe (pc64e72 only).
 *
 * Runs after the scheduler so Fs/Proto/Ipifc setup and kprocs are legal.
 * It starts the one native Ethernet->IPv6 consumer, then lets the host
 * drive real VirtIO NDP/ICMPv6 traffic.  Synthetic Blocks are used only for
 * isolated filter/queue negatives, never as hardware RX evidence.
 */
#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"../port/netif.h"
#include	"../port/etherif.h"

#include	"../ip/ip.h"
#include	"../ip/ipv6.h"
#include	"../ip/nativev6.h"

extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

static Ether *edev;
static Ipv6Native *native;
static int fails;
static uvlong csnap[6];

static void
snapcounters(uvlong *v)
{
	v[0] = opath_namec;
	v[1] = opath_newchan;
	v[2] = opath_walk;
	v[3] = opath_devwalk;
	v[4] = opath_mount;
	v[5] = opath_exec;
}

static int
samecounters(uvlong *a, uvlong *b)
{
	int i;

	for(i = 0; i < 6; i++)
		if(a[i] != b[i])
			return 0;
	return 1;
}

static void
fail(char *what, int rc, int want)
{
	fails++;
	print("E72IPV6: FAIL %s rc=%d want=%d\n", what, rc, want);
}

static Block*
mketh(uchar *dst, ushort type, int len)
{
	Etherpkt *p;
	Block *bp;

	bp = allocb(len);
	if(bp == nil)
		return nil;
	memset(bp->wp, 0, len);
	p = (Etherpkt*)bp->wp;
	memmove(p->d, dst, Eaddrlen);
	memmove(p->s, edev->ea, Eaddrlen);
	p->type[0] = type>>8;
	p->type[1] = type;
	bp->wp += len;
	return bp;
}

static int
wait_positive(void)
{
	Ipv6NativeStats st;
	int i;

	for(i = 0; i < 1000; i++){
		ipv6native_stats(native, &st);
		if((i % 100) == 0)
			print("E72IPV6: WAIT rx=%llud tx=%llud calls=%llud held=%llud err=%llud outreq=%lud noroute=%lud outdisc=%lud ifcout=%lud ifcerr=%lud\n",
				st.rxdelivered, st.txframes, st.txcalls, st.txheld, st.txerrs,
				native->f->ip->stats[OutRequests], native->f->ip->stats[OutNoRoutes],
				native->f->ip->stats[OutDiscards], native->ifc->out, native->ifc->outerr);
		if(st.rxdelivered >= 2 && st.txframes >= 2)
			return 1;
		tsleep(&up->sleep, return0, nil, 10);
	}
	return 0;
}

static void
e72ipv6probe_proc(void *arg)
{
	Ether *e;
	Ipv6NativeStats st;
	Block *bp;
	uvlong cdone[6], tbase;
	int i, n, p1, p2, rc, oldlink, ok;

	USED(arg);
	print("E72IPV6: PROBE begin\n");
	fails = 0;

	p1 = ethercore_probecalls();
	n = ethercore_init();
	p2 = ethercore_probecalls();
	print("E72IPV6: INIT rc=%d inits=%d probes=%d idempotent=%d\n",
		n, ethercore_initcalls(), p2, p1 == p2);
	if(p1 != p2){
		print("E72IPV6: FAIL init re-probed controllers\n");
		fails++;
	}
	if(n <= 0){
		print("E72IPV6: NODEV n=%d\n", n);
		print("E72IPV6: DONE pass=%d fails=%d\n", fails == 0, fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}

	e = ethercore_lookup(0);
	if(e == nil)
		e = ethercore_byindex(0);
	if(e == nil){
		print("E72IPV6: FAIL no controller\n");
		print("E72IPV6: DONE pass=0 fails=%d\n", fails+1);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	edev = e;
	print("E72IPV6: CTLR ctlrno=%d name=%s ea=%E link=%d\n",
		e->ctlrno, e->name, e->ea, e->link);

	rc = ethercore_attach(e);
	if(rc != EtherErrOk)
		fail("attach", rc, EtherErrOk);
	rc = ethercore_attach(e);
	if(rc != EtherErrOk)
		fail("attach-twice", rc, EtherErrOk);

	snapcounters(csnap);
	rc = ipv6native_start(e, "e72", &native);
	if(rc != EtherErrOk){
		fail("ipv6native-start", rc, EtherErrOk);
		print("E72IPV6: DONE pass=0 fails=%d\n", fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	print("E72IPV6: LLADDR %I\n", ipv6native_lladdr(native));
	print("E72IPV6: READY\n");

	if(!wait_positive()){
		ipv6native_stats(native, &st);
		print("E72IPV6: FAIL positive-timeout rx=%llud tx=%llud\n",
			st.rxdelivered, st.txframes);
		fails++;
	}else{
		ipv6native_stats(native, &st);
		print("E72IPV6: POSITIVE rx=%llud tx=%llud drop=%llud bad=%llud other=%llud\n",
			st.rxdelivered, st.txframes, st.rxdrop, st.rxbad, st.rxother);
	}

	snapcounters(cdone);
	print("E72IPV6: CHAN-NATIVE namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud clean=%d\n",
		cdone[0]-csnap[0], cdone[1]-csnap[1], cdone[2]-csnap[2],
		cdone[3]-csnap[3], cdone[4]-csnap[4], cdone[5]-csnap[5],
		samecounters(csnap, cdone));
	if(!samecounters(csnap, cdone))
		fails++;

	/* Host sends malformed ND/ICMPv6 and non-IPv6 frames now. */
	ipv6native_stats(native, &st);
	tbase = st.txframes;
	print("E72IPV6: NEG-READY\n");
	tsleep(&up->sleep, return0, nil, 3000);
	ipv6native_stats(native, &st);
	print("E72IPV6: NEG-RESULT rx=%llud drop=%llud bad=%llud other=%llud tx=%llud\n",
		st.rxdelivered, st.rxdrop, st.rxbad, st.rxother, st.txframes);
	if(st.rxother < 1)
		fail("neg-ipv4-not-filtered", st.rxother, 1);
	if(st.txframes > tbase)
		print("E72IPV6: ALIVE tx=%llud\n", st.txframes);
	else {
		print("E72IPV6: FAIL alive-echo-missing tx=%llud\n", st.txframes);
		fails++;
	}

	/* Isolated L2 truncation filter check (never NIC RX evidence). */
	{
		Etherpkt *p;
		uvlong bad0 = st.rxbad;
		bp = allocb(30);
		if(bp != nil){
			memset(bp->wp, 0, 30);
			p = (Etherpkt*)bp->wp;
			memmove(p->d, e->ea, Eaddrlen);
			p->type[0] = ETIP6>>8;
			p->type[1] = ETIP6;
			bp->wp += 30;
			ipv6native_inject(native, bp);
		}
		ipv6native_stats(native, &st);
		print("E72IPV6: CHECK truncated-filter bad=%llud\n", st.rxbad);
		if(st.rxbad <= bad0)
			fail("truncated-filter", st.rxbad, bad0+1);
	}

	/*
	 * Native RX queue saturation: pause the worker, force limit 0, inject
	 * four synthetic IPv6-looking frames.  The first may queue, the rest
	 * must be dropped by qpass.  This is an isolated queue test, not NIC RX.
	 */
	ipv6native_setlimit(native, 0);
	for(i = 0; i < 128; i++){
		bp = mketh(e->ea, ETIP6, 64);
		if(bp != nil)
			ipv6native_inject(native, bp);
	}
	ipv6native_stats(native, &st);
	print("E72IPV6: CHECK queue-sat drop=%llud\n", st.rxdrop);
	if(st.rxdrop < 1)
		fail("queue-sat", st.rxdrop, 1);
	ipv6native_setlimit(native, 64*1024);
	tsleep(&up->sleep, return0, nil, 500);

	/* Host sends an Echo while the link is down; native TX must drop it. */
	oldlink = e->link;
	e->link = 0;
	print("E72IPV6: TXDOWN-READY\n");
	tsleep(&up->sleep, return0, nil, 2500);
	e->link = oldlink;
	ipv6native_stats(native, &st);
	print("E72IPV6: TXDOWN n=%llud\n", st.txdown);
	if(st.txdown < 1)
		fail("txdown", st.txdown, 1);

	/* Isolated queue ownership/backpressure contract used by ethercore_tx. */
	bp = mketh(e->ea, ETIP6, 64);
	if(bp != nil){
		Queue *q = qopen(2*BALLOC(bp) - 1, Qmsg, nil, nil);
		if(q != nil){
			rc = qpasstry(q, bp);
			print("E72IPV6: CHECK txq-first rc=%d\n", rc);
			bp = mketh(e->ea, ETIP6, 64);
			rc = qpasstry(q, bp);
			print("E72IPV6: CHECK txq-full rc=%d\n", rc);
			if(rc != -2)
				fail("txq-full", rc, -2);
			freeb(bp);
			qclose(q);
			bp = mketh(e->ea, ETIP6, 64);
			rc = qpasstry(q, bp);
			print("E72IPV6: CHECK txq-closed rc=%d\n", rc);
			if(rc != -1)
				fail("txq-closed", rc, -1);
			freeb(bp);
			qfree(q);
		}else
			freeb(bp);
	}

	/* Repeat init/attach must not duplicate Fs/Proto or re-run attach. */
	{
		Ipv6Native *ni2 = nil;
		rc = ipv6native_start(e, "e72", &ni2);
		print("E72IPV6: CHECK repeat-start rc=%d\n", rc);
		if(rc != EtherErrBusy)
			fail("repeat-start", rc, EtherErrBusy);
		rc = ethercore_attach(e);
		print("E72IPV6: CHECK repeat-attach rc=%d\n", rc);
		if(rc != EtherErrOk)
			fail("repeat-attach", rc, EtherErrOk);
	}

	rc = ipv6native_stop(native);
	print("E72IPV6: STOP rc=%d\n", rc);
	if(rc != EtherErrOk)
		fail("stop", rc, EtherErrOk);
	rc = ipv6native_stop(native);
	print("E72IPV6: CHECK repeat-stop rc=%d\n", rc);
	if(rc != EtherErrBadArg)
		fail("repeat-stop", rc, EtherErrBadArg);
	ipv6native_stats(native, &st);
	print("E72IPV6: FINAL worker_exited=%d rx=%llud tx=%llud drop=%llud\n",
		st.worker_exited, st.rxdelivered, st.txframes, st.rxdrop);

	ok = fails == 0;
	print("E72IPV6: DONE pass=%d fails=%d\n", ok, fails);
	for(;;)
		tsleep(&up->sleep, return0, nil, 60000);
}

int
e72ipv6probe_start(void)
{
	char *p;

	p = getconf("e72ipv6");
	if(p == nil || strcmp(p, "1") != 0)
		return 0;
	up = nil;
	kstrdup(&eve, "");
	kproc("*e72ipv6*", e72ipv6probe_proc, nil);
	return 1;
}

int
onativeprobe_start(void)
{
	return 0;
}

int
e71etherprobe_start(void)
{
	return 0;
}

int
e73udpprobe_start(void)
{
	return 0;
}
