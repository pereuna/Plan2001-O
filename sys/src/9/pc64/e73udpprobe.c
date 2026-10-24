/*
 * E7.3 opt-in native UDP6 datagram probe (pc64e73 only).
 *
 * One echo worker consumes complete datagrams from the native UDP6 endpoint
 * and returns them with the existing udpkick/ipoput6/native-medium path.
 * Host bytes remain the primary proof; these markers identify the kernel
 * code path and lifecycle state.
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
#include	"../ip/nativeudp6.h"

extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

static Ether *edev;
static Ipv6Native *net;
static Udp6Endpoint *uep, *sat;
static int fails;
static int echo_exited;
static int echo_stop;
static Rendez echo_done;
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

static ulong
udpstat(char *buf, char *name)
{
	char *p, *e;
	int n;

	n = strlen(name);
	for(p = buf; *p != 0; ){
		while(*p == ' ' || *p == '\n' || *p == '\t')
			p++;
		if(strncmp(p, name, n) == 0 && p[n] == ':'){
			p += n+1;
			while(*p == ' ')
				p++;
			return strtoul(p, &e, 10);
		}
		p = strchr(p, '\n');
		if(p == nil)
			break;
		p++;
	}
	return 0;
}

static void
udpstatsline(char *tag)
{
	Proto *udp;
	char b[256], line[256];
	int i, j;

	if(net == nil || net->f == nil || (udp = net->f->t2p[17]) == nil
	|| udp->stats == nil){
		print("E73UDP: UDPSTATS %s unavailable\n", tag);
		return;
	}
	(*udp->stats)(udp, b, sizeof(b));
	for(i = j = 0; b[i] != 0 && j < sizeof(line)-1; i++)
		line[j++] = b[i] == '\n' ? ' ' : b[i];
	line[j] = 0;
	print("E73UDP: UDPSTATS %s %s\n", tag, line);
}

static void
failsym(char *what, int rc, int want)
{
	fails++;
	print("E73UDP: FAIL %s rc=%d want=%d\n", what, rc, want);
}

static void
echoproc(void *arg)
{
	Udp6Msg msg;
	int len, rc;

	USED(arg);
	for(;;){
		if(echo_stop)
			break;
		rc = udp6_recv(uep, &msg, 100);
		if(rc == Udp6ErrTimeout)
			continue;
		if(rc == Udp6ErrClosed)
			break;
		if(rc != Udp6Ok){
			print("E73UDP: FAIL recv rc=%d\n", rc);
			fails++;
			continue;
		}
		len = BLEN(msg.bp);
		rc = udp6_sendto(uep, msg.src, msg.sport, msg.bp);
		if(rc != Udp6Ok){
			print("E73UDP: TXFAIL rc=%d len=%d\n", rc, len);
			freeb(msg.bp);
			fails++;
		}
	}
	echo_exited = 1;
	wakeup(&echo_done);
}

static int
echodone(void *a)
{
	USED(a);
	return echo_exited;
}


static uchar hostll[IPaddrlen] =
	{0xfe,0x80,0,0,0,0,0,0,0,0,0,0,0,0,0,0x02};
static uchar noroute6[IPaddrlen] =
	{0x20,0x01,0x0d,0xb8,0,0,0,0,0,0,0,0,0,0,0,0x01};


typedef struct Race Race;
typedef struct RaceArg RaceArg;
struct RaceArg {
	Race	*r;
	int	i;
};
struct Race {
	Udp6Endpoint	*ep;
	Lock		lk;
	int		nready;
	int		ndone;
	int		want;
	int		rc[2];
	int		len[2];
	ushort		sport[2];
	uvlong		elapsed[2];
	uchar		payload[2][32];
	RaceArg		args[2];
};



static void
raceread(void *arg)
{
	RaceArg *ra = arg;
	Race *r = ra->r;
	Udp6Msg m;
	int i, rc, len;

	i = ra->i;
	lock(&r->lk);
	r->nready++;
	unlock(&r->lk);
	{
		ulong t0 = NOW;
		rc = udp6_recv(r->ep, &m, 600);
		r->elapsed[i] = (ulong)(NOW - t0);
	}
	lock(&r->lk);
	r->rc[i] = rc;
	if(rc == Udp6Ok){
		len = BLEN(m.bp);
		r->len[i] = len;
		r->sport[i] = m.sport;
		if(len > (int)sizeof(r->payload[i]))
			len = sizeof(r->payload[i]);
		memmove(r->payload[i], m.bp->rp, len);
		freeb(m.bp);
	}
	r->ndone++;
	unlock(&r->lk);
}

static int
racestart(Race *r, Udp6Endpoint *ep, int want)
{
	int i, ready;
	Udp6Stats ust;

	memset(r, 0, sizeof(*r));
	r->ep = ep;
	r->want = want;
	for(i = 0; i < 2; i++){
		r->args[i].r = r;
		r->args[i].i = i;
		kproc("*e73race*", raceread, &r->args[i]);
	}
	for(i = 0; i < 300; i++){
		lock(&r->lk);
		ready = r->nready;
		unlock(&r->lk);
		if(ready == 2){
			udp6_stats(ep, &ust);
			if(ust.recvactive >= 2)
				return 0;
		}
		tsleep(&up->sleep, return0, nil, 10);
	}
	return -1;
}

static int
racerun(Race *r, int ms)
{
	int i;

	tsleep(&up->sleep, return0, nil, ms);
	for(i = 0; i < 300; i++){
		lock(&r->lk);
		if(r->ndone >= r->want){
			unlock(&r->lk);
			return 0;
		}
		unlock(&r->lk);
		tsleep(&up->sleep, return0, nil, 10);
	}
	return -1;
}

static int
racematch(Race *r, int n, uchar *want, int len)
{
	int i;

	for(i = 0; i < 2; i++)
		if(r->rc[i] == Udp6Ok && r->len[i] == len
		&& memcmp(r->payload[i], want, len) == 0
		&& r->sport[i] == n)
			return 1;
	return 0;
}

static int
racematchany(Race *r, uchar *want, int len)
{
	int i;

	for(i = 0; i < 2; i++)
		if(r->rc[i] == Udp6Ok && r->len[i] == len
		&& memcmp(r->payload[i], want, len) == 0)
			return 1;
	return 0;
}

static Udp6Endpoint *cwep;
static int cw_rc, cw_done;
static Rendez cwq;
static Lock cwlk;

static int
cwdone(void *a)
{
	int v;

	USED(a);
	lock(&cwlk);
	v = cw_done;
	unlock(&cwlk);
	return v;
}

static void
cwread(void *arg)
{
	Udp6Msg m;
	int rc;

	USED(arg);
	rc = udp6_recv(cwep, &m, 5000);
	if(rc == Udp6Ok)
		freeb(m.bp);
	lock(&cwlk);
	cw_rc = rc;
	cw_done = 1;
	wakeup(&cwq);
	unlock(&cwlk);
}

static Udp6Endpoint *srep;
static int sr_done;
static uvlong sr_ok, sr_err;
static Rendez srq;
static Lock srlk;

static int
srdone(void *a)
{
	int v;

	USED(a);
	lock(&srlk);
	v = sr_done;
	unlock(&srlk);
	return v;
}

static void
srsend(void *arg)
{
	Block *bp;
	int rc;

	USED(arg);
	for(;;){
		bp = allocb(4);
		if(bp == nil)
			break;
		bp->wp += 4;
		memset(bp->rp, 0, 4);
		rc = udp6_sendto(srep, noroute6, 9, bp);
		if(rc == Udp6Ok)
			sr_ok++;
		else {
			sr_err++;
			freeb(bp);
			if(rc == Udp6ErrClosed)
				break;
		}
	}
	lock(&srlk);
	sr_done = 1;
	wakeup(&srq);
	unlock(&srlk);
}

static void
testkick(void *arg, Block *bp)
{
	USED(arg);
	freeb(bp);
	error("E73 fake send failure");
}

static void
testok(void *arg, Block *bp)
{
	USED(arg);
	freeb(bp);
}

static int
convcount(Proto *udp)
{
	int i, n;

	n = 0;
	for(i = 0; i < udp->nc; i++)
		if(udp->conv[i] != nil)
			n++;
	return n;
}

static void
e73udpprobe_proc(void *arg)
{
	Ether *e;
	Ipv6Native *ni2;
	Ipv6NativeStats st;
	Udp6Endpoint *dup, *tmp;
	Udp6Stats ust;
	Udp6AllocStats a0, a1, af;
	Block *bp;
	Proto *udp;
	Race r1, r2;
	uchar bad[IPaddrlen];
	uvlong cdone[6], rxbase, rxb;
	ulong ind, outd, nop, inerr, dropfull;
	char sbuf[256];
	int i, n, p1, p2, rc, oldlink;
	int c0, c1, ac0, ac1, ok, to;

	USED(arg);
	print("E73UDP: PROBE begin\n");
	fails = 0;

	p1 = ethercore_probecalls();
	n = ethercore_init();
	p2 = ethercore_probecalls();
	print("E73UDP: INIT rc=%d inits=%d probes=%d idempotent=%d\n",
		n, ethercore_initcalls(), p2, p1 == p2);
	if(p1 != p2){
		print("E73UDP: FAIL init reprobed\n");
		fails++;
	}
	if(n <= 0){
		print("E73UDP: NODEV n=%d\n", n);
		print("E73UDP: DONE pass=%d fails=%d\n", fails == 0, fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	e = ethercore_lookup(0);
	if(e == nil)
		e = ethercore_byindex(0);
	if(e == nil){
		print("E73UDP: FAIL no controller\n");
		print("E73UDP: DONE pass=0 fails=%d\n", fails+1);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	edev = e;
	print("E73UDP: CTLR ctlrno=%d name=%s ea=%E link=%d\n",
		e->ctlrno, e->name, e->ea, e->link);

	rc = ethercore_attach(e);
	if(rc != EtherErrOk)
		failsym("attach", rc, EtherErrOk);
	rc = ethercore_attach(e);
	if(rc != EtherErrOk)
		failsym("attach-twice", rc, EtherErrOk);

	snapcounters(csnap);
	rc = ipv6native_start(e, "e73", &net);
	if(rc != EtherErrOk){
		failsym("ipv6native-start", rc, EtherErrOk);
		print("E73UDP: DONE pass=0 fails=%d\n", fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	print("E73UDP: LLADDR %I\n", ipv6native_lladdr(net));

	rc = udp6_open(net, ipv6native_lladdr(net), 20001, &uep);
	print("E73UDP: CHECK open rc=%d\n", rc);
	if(rc != Udp6Ok)
		failsym("open", rc, Udp6Ok);

	/* IPv4-mapped address must not be accepted by the native UDP6 API. */
	ipmove(bad, v4prefix);
	bad[12] = 127; bad[13] = 0; bad[14] = 0; bad[15] = 1;
	dup = nil;
	rc = udp6_open(net, bad, 20003, &dup);
	print("E73UDP: CHECK v4-open rc=%d\n", rc);
	if(rc != Udp6ErrFamily)
		failsym("v4-open", rc, Udp6ErrFamily);
	if(dup != nil)
		udp6_close(dup);

	/* Duplicate bind: same local address/port must be rejected. */
	dup = nil;
	rc = udp6_open(net, ipv6native_lladdr(net), 20001, &dup);
	print("E73UDP: CHECK dupbind rc=%d\n", rc);
	if(rc != Udp6ErrInUse)
		failsym("dupbind", rc, Udp6ErrInUse);
	if(dup != nil)
		udp6_close(dup);

	rc = udp6_open(net, ipv6native_lladdr(net), 20002, &sat);
	print("E73UDP: CHECK open-sat rc=%d\n", rc);
	if(rc != Udp6Ok)
		failsym("open-sat", rc, Udp6Ok);
	if(sat != nil)
		udp6_setlimit(sat, 1000);

	kproc("*e73echo*", echoproc, nil);
	print("E73UDP: READY\n");

	/* Positive: host sends six datagrams, two source ports, four lengths. */
	for(i = 0; i < 1500; i++){
		if(uep != nil && uep->rxmsgs >= 6 && uep->txaccepted >= 6)
			break;
		tsleep(&up->sleep, return0, nil, 10);
	}
	if(uep == nil || uep->rxmsgs < 6 || uep->txaccepted < 6){
		print("E73UDP: FAIL positive-timeout rx=%llud tx=%llud\n",
			uep ? uep->rxmsgs : 0, uep ? uep->txaccepted : 0);
		fails++;
	}else
		print("E73UDP: POSITIVE rx=%llud tx=%llud bytes=%llud\n",
			uep->rxmsgs, uep->txaccepted, uep->rxbytes);

	udpstatsline("POS");

	snapcounters(cdone);
	print("E73UDP: CHAN-NATIVE namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud clean=%d\n",
		cdone[0]-csnap[0], cdone[1]-csnap[1], cdone[2]-csnap[2],
		cdone[3]-csnap[3], cdone[4]-csnap[4], cdone[5]-csnap[5],
		samecounters(csnap, cdone));
	if(!samecounters(csnap, cdone))
		fails++;

	/* Host sends malformed/unbound traffic and then one ALIVE datagram. */
	rxbase = uep != nil ? uep->rxmsgs : 0;
	print("E73UDP: NEG-READY\n");
	tsleep(&up->sleep, return0, nil, 3500);
	udpstatsline("NEG");
	print("E73UDP: NEG-RESULT rx=%llud tx=%llud\n",
		uep ? uep->rxmsgs : 0, uep ? uep->txaccepted : 0);
	if(uep != nil && uep->rxmsgs > rxbase)
		print("E73UDP: ALIVE rx=%llud\n", uep->rxmsgs);
	else {
		print("E73UDP: FAIL alive-missing\n");
		fails++;
	}

	/* Host sends 20 datagrams to the bounded, unread 20002 endpoint. */
	udpstatsline("PRE-SAT");
	print("E73UDP: SAT-READY\n");
	tsleep(&up->sleep, return0, nil, 2500);
	udpstatsline("SAT");
	print("E73UDP: SAT pending=%d\n",
		sat != nil ? udp6_pending(sat) : -1);
	{
		Proto *udp = net->f->t2p[17];
		(*udp->stats)(udp, sbuf, sizeof(sbuf));
		dropfull = udpstat(sbuf, "DropFull");
		if(dropfull < 1){
			print("E73UDP: FAIL sat-dropfull=%lud\n", dropfull);
			fails++;
		}else
			print("E73UDP: CHECK sat-dropfull=%lud\n", dropfull);
	}
	if(sat != nil){
		rc = udp6_close(sat);
		print("E73UDP: CHECK sat-close rc=%d\n", rc);
		if(rc != Udp6Ok)
			failsym("sat-close", rc, Udp6Ok);
		rc = udp6_destroy(&sat);
		if(rc != Udp6Ok)
			failsym("sat-destroy", rc, Udp6Ok);
	}

	/* Host sends one datagram while the native link is down. */
	oldlink = e->link;
	e->link = 0;
	print("E73UDP: TXDOWN-READY\n");
	tsleep(&up->sleep, return0, nil, 2500);
	e->link = oldlink;
	ipv6native_stats(net, &st);
	print("E73UDP: TXDOWN txdown=%llud\n", st.txdown);
	if(st.txdown < 1)
		failsym("txdown", (int)st.txdown, 1);

	/* ipv6native_stop must refuse while a live endpoint still uses Fs. */
	rc = ipv6native_stop(net);
	print("E73UDP: CHECK stop-live rc=%d\n", rc);
	if(rc != EtherErrBusy)
		failsym("stop-live", rc, EtherErrBusy);

	/* Destroy is only legal after CLOSED; an OPEN wrapper stays allocated. */
	{
		Udp6Endpoint *save = uep;
		rc = udp6_destroy(&uep);
		print("E73UDP: CHECK destroy-open rc=%d\n", rc);
		if(rc != Udp6ErrBusy)
			failsym("destroy-open", rc, Udp6ErrBusy);
		if(uep != save)
			failsym("destroy-open-alias", 1, 0);
	}

	/*
	 * Two simultaneous receivers, one real datagram, repeated ten times.
	 * racestart waits until both readers are inside udp6_recv, so the
	 * interleaving is real, not a scheduling artefact.
	 */
	tmp = nil;
	rc = udp6_open(net, ipv6native_lladdr(net), 20004, &tmp);
	if(rc == Udp6Ok){
		int round, rounds_ok, rounds_to;
		uvlong maxelapsed;
		char pay[16];

		rounds_ok = rounds_to = 0;
		maxelapsed = 0;
		for(round = 0; round < 10; round++){
			memset(&r1, 0, sizeof(r1));
			if(racestart(&r1, tmp, 2) != 0){
				failsym("race1-start", -1, 0);
				break;
			}
			print("E73UDP: RACE1-READY n=%d\n", round);
			if(racerun(&r1, 300) != 0){
				failsym("race1-run", -1, 0);
				break;
			}
			snprint(pay, sizeof(pay), "race-%02d", round);
			ok = to = 0;
			for(i = 0; i < 2; i++){
				if(r1.rc[i] == Udp6Ok)
					ok++;
				else if(r1.rc[i] == Udp6ErrTimeout){
					to++;
					if(r1.elapsed[i] > maxelapsed)
						maxelapsed = r1.elapsed[i];
				}
			}
			if(ok == 1 && to == 1)
				rounds_ok++;
			if(to == 1)
				rounds_to++;
			if(ok != 1 || to != 1)
				fails++;
			if(!racematch(&r1, 40201 + round, (uchar*)pay, 7))
				failsym("race1-payload", 0, 1);
		}
		print("E73UDP: CHECK race1 rounds=10 ok=%d timeout=%d max_timeout=%llud\n",
			rounds_ok, rounds_to, maxelapsed);
		if(rounds_ok != 10 || rounds_to != 10)
			fails++;
	}else
		failsym("race1-open", rc, Udp6Ok);
	udp6_close(tmp);
	udp6_destroy(&tmp);

	/* Two receivers, two distinct real datagrams, each delivered once. */
	memset(&r2, 0, sizeof(r2));
	tmp = nil;
	rc = udp6_open(net, ipv6native_lladdr(net), 20005, &tmp);
	if(rc == Udp6Ok){
		if(racestart(&r2, tmp, 2) != 0)
			failsym("race2-start", -1, 0);
		else {
			print("E73UDP: RACE2-READY\n");
			if(racerun(&r2, 300) != 0)
				failsym("race2-run", -1, 0);
			ok = 0;
			for(i = 0; i < 2; i++)
				if(r2.rc[i] == Udp6Ok)
					ok++;
			print("E73UDP: CHECK race2 ok=%d\n", ok);
			if(ok != 2)
				fails++;
			if(!racematchany(&r2, (uchar*)"race-A", 6)
			|| !racematchany(&r2, (uchar*)"race-B", 6))
				failsym("race2-payload", 0, 1);
		}
	}else
		failsym("race2-open", rc, Udp6Ok);
	udp6_close(tmp);
	udp6_destroy(&tmp);

	/* Close must wake a blocked receiver and quiesce before Conv recycle. */
	cwep = nil;
	rc = udp6_open(net, ipv6native_lladdr(net), 20006, &cwep);
	if(rc == Udp6Ok){
		cw_rc = 0;
		cw_done = 0;
		kproc("*e73closewait*", cwread, nil);
		for(i = 0; i < 200; i++){
			udp6_stats(cwep, &ust);
			if(ust.recvactive >= 1)
				break;
			tsleep(&up->sleep, return0, nil, 10);
		}
		print("E73UDP: CLOSEWAIT-READY\n");
		rc = udp6_close(cwep);
		print("E73UDP: CHECK close-wake rc=%d\n", rc);
		if(rc != Udp6Ok)
			failsym("close-wake", rc, Udp6Ok);
		for(i = 0; i < 200 && !cw_done; i++)
			tsleep(&cwq, cwdone, nil, 10);
		if(!cw_done || cw_rc != Udp6ErrClosed)
			failsym("close-wake-status", cw_rc, Udp6ErrClosed);
		rc = udp6_destroy(&cwep);
		if(rc != Udp6Ok)
			failsym("close-wake-destroy", rc, Udp6Ok);
	}else
		failsym("close-wake-open", rc, Udp6Ok);

	/* Close racing a live sender: accepted-before or rejected-after. */
	srep = nil;
	rc = udp6_open(net, ipv6native_lladdr(net), 20007, &srep);
	if(rc == Udp6Ok){
		sr_ok = sr_err = 0;
		sr_done = 0;
		kproc("*e73sendrace*", srsend, nil);
		tsleep(&up->sleep, return0, nil, 50);
		rc = udp6_close(srep);
		print("E73UDP: CHECK close-send rc=%d\n", rc);
		if(rc != Udp6Ok)
			failsym("close-send", rc, Udp6Ok);
		for(i = 0; i < 300 && !sr_done; i++)
			tsleep(&srq, srdone, nil, 10);
		print("E73UDP: CHECK close-send-results done=%d ok=%llud err=%llud\n",
			sr_done, sr_ok, sr_err);
		if(!sr_done || sr_err < 1)
			fails++;
		rc = udp6_destroy(&srep);
		if(rc != Udp6Ok)
			failsym("close-send-destroy", rc, Udp6Ok);
	}else
		failsym("close-send-open", rc, Udp6Ok);

	/*
	 * Private-queue exception injection: testkick frees the envelope and
	 * raises, exercising udp6_sendto's waserror unwind and lock release.
	 * This is not NIC evidence.
	 */
	{
		Udp6Endpoint fake;
		Conv fc;
		Queue *qw;
		Block *bp;

		memset(&fake, 0, sizeof(fake));
		memset(&fc, 0, sizeof(fc));
		fc.state = Announced;
		qw = qbypass(testkick, nil);
		fc.wq = qw;
		fake.net = net;
		fake.f = net->f;
		fake.udp = net->f->t2p[17];
		fake.conv = &fc;
		fake.state = U6Open;
		ipmove(fake.laddr, ipv6native_lladdr(net));
		fake.lport = 20001;

		bp = allocb(4);
		if(bp != nil){
			bp->wp += 4;
			memset(bp->rp, 0, 4);
			rc = udp6_sendto(&fake, hostll, 20001, bp);
			print("E73UDP: CHECK fake-exc rc=%d\n", rc);
			if(rc != Udp6ErrSend)
				failsym("fake-exc", rc, Udp6ErrSend);
			if(fake.txerrors < 1 || fake.txuncertain < 1)
				failsym("fake-exc-counters", (int)fake.txerrors, 1);
			freeb(bp);	/* reported failure leaves caller payload */
		}
		if(canqlock(&fake.sendlk)){
			print("E73UDP: CHECK fake-unlock=1\n");
			qunlock(&fake.sendlk);
		}else
			failsym("fake-unlock", 0, 1);
		qfree(qw);
		fc.wq = qbypass(testok, nil);
		bp = allocb(4);
		if(bp != nil){
			bp->wp += 4;
			memset(bp->rp, 0, 4);
			rc = udp6_sendto(&fake, hostll, 20001, bp);
			print("E73UDP: CHECK fake-ok rc=%d\n", rc);
			if(rc != Udp6Ok)
				failsym("fake-ok", rc, Udp6Ok);
		}
		qfree(fc.wq);
	}

	/* Synchronous no-route error, then a real host datagram must succeed. */
	bp = allocb(4);
	if(bp != nil){
		bp->wp += 4;
		memset(bp->rp, 0, 4);
		rc = udp6_sendto(uep, noroute6, 9, bp);
		print("E73UDP: CHECK send-noroute rc=%d\n", rc);
		if(rc != Udp6ErrNoRoute)
			failsym("send-noroute", rc, Udp6ErrNoRoute);
		freeb(bp);
	}
	rxb = uep->rxmsgs;
	print("E73UDP: SENDFAIL\n");
	for(i = 0; i < 300 && uep->rxmsgs <= rxb; i++)
		tsleep(&up->sleep, return0, nil, 10);
	print("E73UDP: SENDFAIL-ALIVE rx=%llud\n", uep->rxmsgs);
	if(uep->rxmsgs <= rxb)
		failsym("sendfail-alive", (int)uep->rxmsgs, (int)rxb+1);

	/* 200 sequential open/close/destroy/rebind cycles on four ports. */
	udp = net->f->t2p[17];
	udp6_allocstats(&a0);
	c0 = convcount(udp);
	ac0 = udp->ac;
	for(i = 0; i < 200; i++){
		Udp6Endpoint *t = nil;
		if(udp6_open(net, ipv6native_lladdr(net), 21000 + (i % 4), &t) != Udp6Ok){
			failsym("loop-open", -1, Udp6Ok);
			break;
		}
		if((i % 50) == 0){
			Udp6Msg m;
			rc = udp6_recv(t, &m, 0);
			if(rc != Udp6ErrTimeout)
				failsym("loop-poll", rc, Udp6ErrTimeout);
		}
		if((i % 50) == 0){
			bp = allocb(52);
			if(bp != nil){
				memset(bp->wp, 0, 52);
				bp->wp += 52;
				qpass(t->conv->rq, bp);
			}
		}
		rc = udp6_close(t);
		if(rc != Udp6Ok)
			failsym("loop-close", rc, Udp6Ok);
		rc = udp6_destroy(&t);
		if(rc != Udp6Ok || t != nil)
			failsym("loop-destroy", rc, Udp6Ok);
	}
	udp6_allocstats(&a1);
	c1 = convcount(udp);
	ac1 = udp->ac;
	print("E73UDP: CHECK loop-alloc opens=%llud closes=%llud destroys=%llud live_delta=%lld\n",
		a1.opens - a0.opens, a1.closes - a0.closes, a1.destroys - a0.destroys,
		(long long)(a1.live - a0.live));
	if(a1.opens - a0.opens != 200 || a1.closes - a0.closes != 200
	|| a1.destroys - a0.destroys != 200 || a1.live != a0.live)
		fails++;
	print("E73UDP: CHECK conv-slots before=%d after=%d ac_before=%d ac_after=%d\n",
		c0, c1, ac0, ac1);
	if(c1 > c0 + 4 || ac1 > ac0 + 4)
		fails++;

	/* Close and destroy the old endpoint, then rebind the same port. */
	rc = udp6_close(uep);
	print("E73UDP: CLOSE rc=%d\n", rc);
	if(rc != Udp6Ok)
		failsym("close", rc, Udp6Ok);
	for(i = 0; i < 300 && !echo_exited; i++)
		tsleep(&echo_done, echodone, nil, 10);
	print("E73UDP: ECHO-EXIT exited=%d\n", echo_exited);
	if(!echo_exited)
		fails++;
	rc = udp6_close(uep);
	print("E73UDP: CHECK repeat-close rc=%d\n", rc);
	if(rc != Udp6ErrClosed)
		failsym("repeat-close", rc, Udp6ErrClosed);
	{
		Udp6Msg m;
		Block *bp = allocb(4);
		rc = udp6_recv(uep, &m, 0);
		print("E73UDP: CHECK post-close-recv rc=%d\n", rc);
		if(rc != Udp6ErrClosed)
			failsym("post-close-recv", rc, Udp6ErrClosed);
		if(bp != nil){
			bp->wp += 4;
			memset(bp->rp, 0, 4);
			rc = udp6_sendto(uep, ipv6native_lladdr(net), 20001, bp);
			print("E73UDP: CHECK post-close-send rc=%d\n", rc);
			if(rc != Udp6ErrClosed)
				failsym("post-close-send", rc, Udp6ErrClosed);
			freeb(bp);
		}
	}
	udp6_stats(uep, &ust);
	print("E73UDP: CHECK closed-stats state=%d bound=%d pending=%d\n",
		ust.state, ust.bound, ust.pending);
	if(ust.state != U6Closed || ust.bound != 0 || ust.pending != 0)
		fails++;
	print("E73UDP: CHECK closed-aux pending=%d setlimit=%d\n",
		udp6_pending(uep), udp6_setlimit(uep, 1024));
	rc = udp6_destroy(&uep);
	print("E73UDP: CHECK destroy rc=%d nil=%d\n", rc, uep == nil);
	if(rc != Udp6Ok || uep != nil)
		failsym("destroy", rc, Udp6Ok);

	/* Same IPv6 address/port must rebind and echo from the reused Conv. */
	rc = udp6_open(net, ipv6native_lladdr(net), 20001, &uep);
	print("E73UDP: CHECK rebind-open rc=%d\n", rc);
	if(rc != Udp6Ok)
		failsym("rebind-open", rc, Udp6Ok);
	if(uep != nil){
		echo_stop = 0;
		echo_exited = 0;
		kproc("*e73echo*", echoproc, nil);
		print("E73UDP: REBIND-READY\n");
		for(i = 0; i < 300 && (uep->rxmsgs < 1 || uep->txaccepted < 1); i++)
			tsleep(&up->sleep, return0, nil, 10);
		print("E73UDP: CHECK rebind rx=%llud tx=%llud\n",
			uep->rxmsgs, uep->txaccepted);
		if(uep->rxmsgs < 1 || uep->txaccepted < 1)
			fails++;
		echo_stop = 1;
		rc = udp6_close(uep);
		if(rc != Udp6Ok)
			failsym("rebind-close", rc, Udp6Ok);
		for(i = 0; i < 300 && !echo_exited; i++)
			tsleep(&echo_done, echodone, nil, 10);
		if(!echo_exited)
			fails++;
		rc = udp6_destroy(&uep);
		if(rc != Udp6Ok)
			failsym("rebind-destroy", rc, Udp6Ok);
	}

	snapcounters(cdone);
	print("E73UDP: CHAN-HARDEN namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud clean=%d\n",
		cdone[0]-csnap[0], cdone[1]-csnap[1], cdone[2]-csnap[2],
		cdone[3]-csnap[3], cdone[4]-csnap[4], cdone[5]-csnap[5],
		samecounters(csnap, cdone));
	if(!samecounters(csnap, cdone))
		fails++;

	udp6_allocstats(&af);
	print("E73UDP: ALLOC-FINAL opens=%llud closes=%llud destroys=%llud live=%llud peak=%llud\n",
		af.opens, af.closes, af.destroys, af.live, af.peak);
	if(af.live != 0)
		failsym("alloc-live", (int)af.live, 0);

	rc = ipv6native_stop(net);
	print("E73UDP: STOP rc=%d\n", rc);
	if(rc != EtherErrOk)
		failsym("stop", rc, EtherErrOk);
	rc = ipv6native_stop(net);
	print("E73UDP: CHECK repeat-stop rc=%d\n", rc);
	if(rc != EtherErrBadArg)
		failsym("repeat-stop", rc, EtherErrBadArg);
	ni2 = nil;
	rc = ipv6native_start(e, "e73", &ni2);
	print("E73UDP: CHECK restart-after-stop rc=%d\n", rc);
	if(rc != EtherErrBusy)
		failsym("restart-after-stop", rc, EtherErrBusy);
	if(ni2 != nil)
		failsym("restart-returned-net", 1, 0);

	/* Derived counters, printed once for host correlation. */
	{
		Proto *udp = net->f->t2p[17];
		(*udp->stats)(udp, sbuf, sizeof(sbuf));
		ind = udpstat(sbuf, "InDatagrams");
		outd = udpstat(sbuf, "OutDatagrams");
		nop = udpstat(sbuf, "NoPorts");
		inerr = udpstat(sbuf, "InErrors");
		print("E73UDP: COUNTERS in=%lud out=%lud noports=%lud inerrors=%lud\n",
			ind, outd, nop, inerr);
	}

	print("E73UDP: DONE pass=%d fails=%d\n", fails == 0, fails);
	for(;;)
		tsleep(&up->sleep, return0, nil, 60000);
}

int
e73udpprobe_start(void)
{
	char *p;

	p = getconf("e73udp");
	if(p == nil || strcmp(p, "1") != 0)
		return 0;
	up = nil;
	kstrdup(&eve, "");
	kproc("*e73udp*", e73udpprobe_proc, nil);
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
e72ipv6probe_start(void)
{
	return 0;
}
