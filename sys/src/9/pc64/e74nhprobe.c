/*
 * E7.4 opt-in experimental IPv6 Next Header probe (pc64e74 only).
 *
 * Host frames are the primary proof: Neighbor Solicitation, ICMPv6 Echo,
 * native UDP6 and a direct Next Header 253 payload are all answered through
 * the real VirtIO path.  A fixed echo callback is registered with the
 * E7.4 native consumer; it never handles UDP/ICMP/NDP.  Synthetic Blocks
 * are used only for isolated queue/ownership negatives.
 *
 * Next Header 253 is an experiment selector (RFC 3692), not WireGuard and
 * not an authenticated transport.
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
#include	"../ip/nativeinh6.h"

extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

enum {
	E74UdpPort = 20001,
};

static Ether *edev;
static Ipv6Native *net;
static Udp6Endpoint *uep;
static int fails;
static int echo_exited;
static int echo_stop;
static Rendez echo_done;
static uvlong csnap[6];

/*
 * E7.4.3 deterministic unregister/re-register race regression.
 * The 8 s pre-callback delay is the existing test-only admission window;
 * the probe checks active>=1 before unregistering, so the ordering is
 * established by the barrier, not by a sleep-only guess.
 */
enum {
	E743DelayMs	= 8000,
	E743Max		= 64,
};

typedef struct E743Ctx E743Ctx;
struct E743Ctx {
	int	id;
	int	calls;
	int	len;
	int	sendrc;
	uchar	data[E743Max];
};

static E743Ctx e743a;
static E743Ctx e743b;

typedef struct E743Unreg E743Unreg;
struct E743Unreg {
	Rendez	r;
	int	done;
	int	rc;
};

static E743Unreg e743u;

static int
e743udone(void *a)
{
	USED(a);
	return e743u.done;
}

static void
e743uproc(void *arg)
{
	USED(arg);
	e743u.rc = nativeip6_unregister(net);
	e743u.done = 1;
	wakeup(&e743u.r);
}

static char *e743A = "E743-A-ORIGINAL";
static char *e743C = "E743-C-STALE";

static int
e743cb(void *arg, NativeIp6Msg *m)
{
	E743Ctx *x = arg;

	x->calls++;
	x->len = BLEN(m->bp);
	if(x->len > E743Max)
		x->len = E743Max;
	memmove(x->data, m->bp->rp, x->len);
	if(x->id == 1){
		/* Callback -> nativeip6_send while teardown is draining. */
		Block *tb;

		x->sendrc = NativeIp6ErrNoMem;
		tb = allocb(BLEN(m->bp));
		if(tb != nil){
			memmove(tb->rp, m->bp->rp, BLEN(m->bp));
			tb->wp += BLEN(m->bp);
			x->sendrc = nativeip6_send(net, m->src, NativeIp6Proto,
				tb, 64);
			if(x->sendrc != NativeIp6Ok)
				freeb(tb);
		}
	}
	freeb(m->bp);
	return 0;
}

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
	print("E74IP: FAIL %s rc=%d want=%d\n", what, rc, want);
}

static void
echoproc(void *arg)
{
	Udp6Msg m;
	int rc;

	USED(arg);
	for(;;){
		if(echo_stop)
			break;
		rc = udp6_recv(uep, &m, 100);
		if(rc == Udp6ErrTimeout)
			continue;
		if(rc == Udp6ErrClosed)
			break;
		if(rc != Udp6Ok){
			print("E74IP: FAIL udp-recv rc=%d\n", rc);
			fails++;
			continue;
		}
		rc = udp6_sendto(uep, m.src, m.sport, m.bp);
		if(rc != Udp6Ok){
			print("E74IP: FAIL udp-send rc=%d\n", rc);
			freeb(m.bp);
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

/*
 * Fixed Next Header 253 echo.  Runs in the native IPv6 worker after the
 * inherited validation.  nativeip6_send consumes m->bp on success; on
 * failure the callback still owns and frees it.
 */
static int
ip6echo(void *arg, NativeIp6Msg *m)
{
	int rc;

	USED(arg);
	rc = nativeip6_send(net, m->src, m->proto, m->bp, 64);
	if(rc != NativeIp6Ok){
		/*
		 * An in-flight callback may lose the unregister race; NotReg
		 * is the expected, tested outcome, not a failure.
		 */
		if(rc != NativeIp6ErrNotReg){
			print("E74IP: FAIL ip6-echo rc=%d len=%d\n", rc, BLEN(m->bp));
			fails++;
		}
		freeb(m->bp);
		return -1;
	}
	return 0;
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
waitpositive(void)
{
	NativeIp6Stats ns;
	Ipv6NativeStats st;
	Udp6Stats us;
	int i;

	for(i = 0; i < 1500; i++){
		nativeip6_stats(net, &ns);
		ipv6native_stats(net, &st);
		if(uep != nil)
			udp6_stats(uep, &us);
		else
			memset(&us, 0, sizeof(us));
		if((i % 200) == 0)
			print("E74IP: WAIT iprx=%llud iptx=%llud udprx=%llud udptx=%llud rx=%llud\n",
				ns.rxframes, ns.txaccepted, us.rxmsgs, us.txaccepted,
				st.rxdelivered);
		if(ns.rxframes >= 1 && ns.txaccepted >= 1
		&& us.rxmsgs >= 1 && us.txaccepted >= 1
		&& st.rxdelivered >= 4)
			return 1;
		tsleep(&up->sleep, return0, nil, 10);
	}
	return 0;
}

static void
e74ipprobe_proc(void *arg)
{
	Ether *e;
	NativeIp6Stats ns, ns0;
	Ipv6NativeStats st;
	Udp6Stats us;
	Block *bp;
	uchar bad[IPaddrlen];
	uvlong cdone[6];
	ulong unk0, unk1, hdr0, hdr1;
	int i, n, p1, p2, rc, oldlink, ok;

	USED(arg);
	print("E74IP: PROBE begin\n");
	fails = 0;
	ipfmtinstall();	/* native-only profile has no #I/#l Dev reset */

	p1 = ethercore_probecalls();
	n = ethercore_init();
	p2 = ethercore_probecalls();
	print("E74IP: INIT rc=%d inits=%d probes=%d\n",
		n, ethercore_initcalls(), p2 - p1);
	if(ethercore_initcalls() > 1 && p1 != p2){
		print("E74IP: FAIL init reprobed controllers\n");
		fails++;
	}
	/*
	 * A legacy #l profile initializes the core at boot; the native-only
	 * profile does not.  Verify the idempotency property explicitly.
	 */
	p1 = ethercore_probecalls();
	n = ethercore_init();
	p2 = ethercore_probecalls();
	print("E74IP: INIT-IDEMP rc=%d probes=%d idempotent=%d\n",
		n, p2 - p1, p1 == p2);
	if(p1 != p2){
		print("E74IP: FAIL repeat init reprobed\n");
		fails++;
	}
	if(n <= 0){
		print("E74IP: NODEV n=%d\n", n);
		print("E74IP: DONE pass=%d fails=%d\n", fails == 0, fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	e = ethercore_lookup(0);
	if(e == nil)
		e = ethercore_byindex(0);
	if(e == nil){
		print("E74IP: FAIL no controller\n");
		print("E74IP: DONE pass=0 fails=%d\n", fails+1);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	edev = e;
	print("E74IP: CTLR ctlrno=%d name=%s ea=%E link=%d\n",
		e->ctlrno, e->name, e->ea, e->link);

	rc = ethercore_attach(e);
	if(rc != EtherErrOk)
		fail("attach", rc, EtherErrOk);

	snapcounters(csnap);
	rc = ipv6native_start(e, "e74", &net);
	if(rc != EtherErrOk){
		fail("ipv6native-start", rc, EtherErrOk);
		print("E74IP: DONE pass=0 fails=%d\n", fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	print("E74IP: LLADDR %I\n", ipv6native_lladdr(net));

	/* Invalid registration arguments before the one real consumer. */
	rc = nativeip6_register(nil, ip6echo, nil);
	print("E74IP: CHECK reg-nilnet rc=%d\n", rc);
	if(rc != NativeIp6ErrBadArg)
		fail("reg-nilnet", rc, NativeIp6ErrBadArg);
	rc = nativeip6_register(net, nil, nil);
	print("E74IP: CHECK reg-nilcb rc=%d\n", rc);
	if(rc != NativeIp6ErrBadArg)
		fail("reg-nilcb", rc, NativeIp6ErrBadArg);

	rc = nativeip6_register(net, ip6echo, nil);
	print("E74IP: REG rc=%d proto=%d\n", rc, NativeIp6Proto);
	if(rc != NativeIp6Ok)
		fail("register", rc, NativeIp6Ok);

	rc = nativeip6_register(net, ip6echo, nil);
	print("E74IP: CHECK dup-reg rc=%d\n", rc);
	if(rc != NativeIp6ErrBusy)
		fail("dup-reg", rc, NativeIp6ErrBusy);

#ifdef E7_IPV6_ONLY
	ipmove(bad, v4prefix);
	bad[12] = 127; bad[13] = 0; bad[14] = 0; bad[15] = 1;
	{
		Udp6Endpoint *tmp = nil;
		rc = udp6_open(net, bad, E74UdpPort+1, &tmp);
		print("E74IP: CHECK udp6-open-v4 rc=%d\n", rc);
		if(rc != Udp6ErrFamily)
			fail("udp6-open-v4", rc, Udp6ErrFamily);
	}
#endif

	rc = udp6_open(net, ipv6native_lladdr(net), E74UdpPort, &uep);
	print("E74IP: CHECK udp-open rc=%d\n", rc);
	if(rc != Udp6Ok)
		fail("udp-open", rc, Udp6Ok);
	kproc("*e74echo*", echoproc, nil);

#ifdef E7_IPV6_ONLY
	{
		uvlong oth0, fr0;
		ipv6native_stats(net, &st);
		oth0 = st.rxother;
		fr0 = st.rxframes;
		bp = mketh(e->ea, 0x0800, 64);
		if(bp != nil)
			ipv6native_inject(net, bp);
		ipv6native_stats(net, &st);
		print("E74IP: CHECK ipv4-drop other=%llud rxframes=%llud\n",
			st.rxother-oth0, st.rxframes-fr0);
		if(st.rxother-oth0 != 1 || st.rxframes != fr0)
			fail("ipv4-drop", (int)(st.rxother-oth0), 1);
	}
#endif

	print("E74IP: READY\n");

	if(!waitpositive()){
		nativeip6_stats(net, &ns);
		udp6_stats(uep, &us);
		print("E74IP: FAIL positive-timeout iprx=%llud iptx=%llud udprx=%llud udptx=%llud\n",
			ns.rxframes, ns.txaccepted, us.rxmsgs, us.txaccepted);
		fails++;
	}else{
		nativeip6_stats(net, &ns);
		udp6_stats(uep, &us);
		print("E74IP: POSITIVE iprx=%llud iptx=%llud ipbytes=%llud udprx=%llud udptx=%llud\n",
			ns.rxframes, ns.txaccepted, ns.rxbytes, us.rxmsgs, us.txaccepted);
	}

	snapcounters(cdone);
	print("E74IP: CHAN-NATIVE namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud clean=%d\n",
		cdone[0]-csnap[0], cdone[1]-csnap[1], cdone[2]-csnap[2],
		cdone[3]-csnap[3], cdone[4]-csnap[4], cdone[5]-csnap[5],
		samecounters(csnap, cdone));
	if(!samecounters(csnap, cdone))
		fails++;

	/* Host sends unhandled/malformed frames and then one ALIVE 253 now. */
	nativeip6_stats(net, &ns0);
	ipv6native_stats(net, &st);
	unk0 = net->f->ip->stats[InUnknownProtos];
	hdr0 = net->f->ip->stats[InHdrErrors];
	{
		uvlong oth0 = st.rxother;
		print("E74IP: NEG-READY\n");
		tsleep(&up->sleep, return0, nil, 3500);
		nativeip6_stats(net, &ns);
		ipv6native_stats(net, &st);
		unk1 = net->f->ip->stats[InUnknownProtos];
		hdr1 = net->f->ip->stats[InHdrErrors];
		print("E74IP: NEG-RESULT iprx=%llud iptx=%llud unhandled=%lud badhdr=%lud other=%llud\n",
			ns.rxframes, ns.txaccepted, unk1-unk0, hdr1-hdr0, st.rxother-oth0);
	}
	if(unk1 <= unk0){
		print("E74IP: FAIL unhandled-not-counted\n");
		fails++;
	}
	if(hdr1 <= hdr0){
		print("E74IP: FAIL badhdr-not-counted\n");
		fails++;
	}
	if(ns.rxframes > ns0.rxframes && ns.txaccepted > ns0.txaccepted)
		print("E74IP: ALIVE iprx=%llud iptx=%llud\n", ns.rxframes, ns.txaccepted);
	else {
		print("E74IP: FAIL alive-missing\n");
		fails++;
	}

	/* Send-side validation and fixed-protocol restriction. */
	bp = allocb(2000);
	if(bp != nil){
		bp->wp += 2000;
		memset(bp->rp, 0, 2000);
		rc = nativeip6_send(net, ipv6native_lladdr(net), NativeIp6Proto, bp, 64);
		print("E74IP: CHECK send-big rc=%d\n", rc);
		if(rc != NativeIp6ErrTooBig)
			fail("send-big", rc, NativeIp6ErrTooBig);
		freeb(bp);
	}
	ipmove(bad, v4prefix);
	bad[12] = 127; bad[13] = 0; bad[14] = 0; bad[15] = 1;
	bp = allocb(4);
	if(bp != nil){
		bp->wp += 4;
		memset(bp->rp, 0, 4);
		rc = nativeip6_send(net, bad, NativeIp6Proto, bp, 64);
		print("E74IP: CHECK send-v4 rc=%d\n", rc);
		if(rc != NativeIp6ErrFamily)
			fail("send-v4", rc, NativeIp6ErrFamily);
		freeb(bp);
	}
	bp = allocb(4);
	if(bp != nil){
		bp->wp += 4;
		memset(bp->rp, 0, 4);
		rc = nativeip6_send(net, ipv6native_lladdr(net), 254, bp, 64);
		print("E74IP: CHECK send-proto rc=%d\n", rc);
		if(rc != NativeIp6ErrBadArg)
			fail("send-proto", rc, NativeIp6ErrBadArg);
		freeb(bp);
	}
	rc = nativeip6_send(net, ipv6native_lladdr(net), NativeIp6Proto, nil, 64);
	print("E74IP: CHECK send-nil rc=%d\n", rc);
	if(rc != NativeIp6ErrBadArg)
		fail("send-nil", rc, NativeIp6ErrBadArg);

	/*
	 * Bounded native RX queue saturation.  Limit 0 rejects the synthetic
	 * copies; this is an isolated queue check, never NIC RX evidence.
	 */
	ipv6native_stats(net, &st);
	{
		uvlong drop0 = st.rxdrop;
		ipv6native_setlimit(net, 0);
		for(i = 0; i < 128; i++){
			bp = mketh(e->ea, ETIP6, 64);
			if(bp != nil)
				ipv6native_inject(net, bp);
		}
		ipv6native_stats(net, &st);
		print("E74IP: CHECK queue-sat drop=%llud\n", st.rxdrop - drop0);
		if(st.rxdrop <= drop0)
			fail("queue-sat", (int)st.rxdrop, (int)drop0+1);
		ipv6native_setlimit(net, 64*1024);
	}

	/*
	 * Unregister with a callback in flight: the callback sleeps 400 ms
	 * after the registered check; the host sends one 253 frame.  The
	 * unregister must wait for it, then re-registration must work.
	 */
	nativeip6_setdelay(net, 400);
	print("E74IP: UNREG-READY\n");
	for(i = 0; i < 400; i++){
		nativeip6_stats(net, &ns);
		if(ns.active >= 1)
			break;
		tsleep(&up->sleep, return0, nil, 10);
	}
	print("E74IP: UNREG-WAIT active=%d\n", ns.active);
	if(ns.active < 1)
		fail("unreg-inflight-active", ns.active, 1);
	rc = nativeip6_unregister(net);
	nativeip6_stats(net, &ns);
	print("E74IP: UNREG rc=%d active=%d registered=%d\n",
		rc, ns.active, ns.registered);
	if(rc != NativeIp6Ok || ns.active != 0 || ns.registered != 0)
		fail("unregister-inflight", rc, NativeIp6Ok);
	nativeip6_setdelay(net, 0);

	rc = nativeip6_unregister(net);
	print("E74IP: CHECK unreg-twice rc=%d\n", rc);
	if(rc != NativeIp6ErrNotReg)
		fail("unreg-twice", rc, NativeIp6ErrNotReg);

	nativeip6_stats(net, &ns0);
	rc = nativeip6_register(net, ip6echo, nil);
	print("E74IP: REARM rc=%d\n", rc);
	if(rc != NativeIp6Ok)
		fail("rearm", rc, NativeIp6Ok);
	print("E74IP: REARM-READY\n");
	for(i = 0; i < 500; i++){
		nativeip6_stats(net, &ns);
		if(ns.rxframes > ns0.rxframes && ns.txaccepted > ns0.txaccepted)
			break;
		tsleep(&up->sleep, return0, nil, 10);
	}
	print("E74IP: REARM-OK iprx=%llud iptx=%llud\n",
		ns.rxframes, ns.txaccepted);
	if(ns.rxframes <= ns0.rxframes || ns.txaccepted <= ns0.txaccepted)
		fail("rearm-echo", (int)ns.rxframes, (int)ns0.rxframes+1);

	rc = nativeip6_unregister(net);
	print("E74IP: UNREG-FINAL rc=%d\n", rc);
	if(rc != NativeIp6Ok)
		fail("unreg-final", rc, NativeIp6Ok);

	/*
	 * E7.4.3: hold an admitted callback beyond the unregister timeout,
	 * require Busy to latch DRAINING, reject re-register, drain the old
	 * callback, retry to completion, then rearm and verify only fresh
	 * packets reach the new callback.
	 */
	{
		NativeIp6Stats nst;
		Ipv6NativeStats vst;
		E743Ctx *a = &e743a, *b = &e743b;
		uvlong rd0;
		int i, j, rca, rcb, oldbug;
		char expect[32];

		memset(a, 0, sizeof(*a));
		memset(b, 0, sizeof(*b));
		a->id = 1;
		a->sendrc = 999;
		b->id = 2;
		nativeip6_setdelay(net, E743DelayMs);
		rca = nativeip6_register(net, e743cb, a);
		print("E743IP: A-REG rc=%d\n", rca);
		if(rca != NativeIp6Ok)
			fail("e743-a-register", rca, NativeIp6Ok);
		print("E743IP: A-READY\n");
		for(i = 0; i < 1000; i++){
			nativeip6_stats(net, &nst);
			if(nst.active >= 1)
				break;
			tsleep(&up->sleep, return0, nil, 10);
		}
		print("E743IP: A-ADMITTED active=%d registered=%d\n",
			nst.active, nst.registered);
		if(nst.active < 1)
			fail("e743-a-admitted", nst.active, 1);

		/* Two concurrent unregister callers: exactly one owner waits. */
		memset(&e743u, 0, sizeof(e743u));
		kproc("*e743unreg*", e743uproc, nil);
		tsleep(&up->sleep, return0, nil, 50);
		rc = nativeip6_unregister(net);
		nativeip6_stats(net, &nst);
		print("E743IP: BUSY rc=%d registered=%d draining=%d active=%d\n",
			rc, nst.registered, nst.draining, nst.active);
		if(rc != NativeIp6ErrBusy || nst.registered != 0 || nst.draining != 1)
			fail("e743-busy", rc, NativeIp6ErrBusy);
		for(i = 0; i < 700 && !e743u.done; i++)
			tsleep(&e743u.r, e743udone, nil, 10);
		print("E743IP: CONCUR-OWNER rc=%d done=%d\n", e743u.rc,
			e743u.done);
		if(!e743u.done || e743u.rc != NativeIp6ErrBusy)
			fail("e743-concurrent-unreg", e743u.rc, NativeIp6ErrBusy);

		nativeip6_setdelay(net, 0);
		rcb = nativeip6_register(net, e743cb, b);
		print("E743IP: REG-B rc=%d\n", rcb);
		oldbug = rcb == NativeIp6Ok;
		if(rcb != NativeIp6ErrBusy)
			fail("e743-reg-draining", rcb, NativeIp6ErrBusy);

		if(oldbug){
			print("E743IP: OLD-BUG-REGISTER\n");
			for(i = 0; i < 1500; i++){
				nativeip6_stats(net, &nst);
				if(nst.active == 0)
					break;
				tsleep(&up->sleep, return0, nil, 10);
			}
			print("E743IP: A-DONE callsA=%d callsB=%d active=%d\n",
				a->calls, b->calls, nst.active);
			rc = nativeip6_unregister(net);
			print("E743IP: OLD-UNREG rc=%d\n", rc);
			rc = nativeip6_unregister(net);
			print("E743IP: OLD-NOTREG rc=%d\n", rc);
			print("E743IP: DONE callsA=%d callsB=%d\n",
				a->calls, b->calls);
		}else{
			ipv6native_stats(net, &vst);
			rd0 = vst.rxdelivered;
			print("E743IP: C-READY\n");
			for(i = 0; i < 1500; i++){
				nativeip6_stats(net, &nst);
				if(nst.active == 0)
					break;
				tsleep(&up->sleep, return0, nil, 10);
			}
			print("E743IP: A-DONE callsA=%d callsB=%d active=%d\n",
				a->calls, b->calls, nst.active);
			if(a->calls != 1 || b->calls != 0 || nst.active != 0)
				fail("e743-a-drain", a->calls, 1);
			print("E743IP: A-SEND rc=%d\n", a->sendrc);
			if(a->sendrc != NativeIp6ErrNotReg)
				fail("e743-a-send", a->sendrc, NativeIp6ErrNotReg);
			for(i = 0; i < 1000; i++){
				ipv6native_stats(net, &vst);
				if(vst.rxdelivered >= rd0 + 2)
					break;
				tsleep(&up->sleep, return0, nil, 10);
			}
			print("E743IP: C-DRAINED delivered=%llud\n",
				vst.rxdelivered - rd0);
			if(vst.rxdelivered < rd0 + 2)
				fail("e743-c-drained", (int)(vst.rxdelivered - rd0), 2);

			rc = nativeip6_unregister(net);
			print("E743IP: RETRY rc=%d\n", rc);
			if(rc != NativeIp6Ok)
				fail("e743-retry", rc, NativeIp6Ok);
			rc = nativeip6_unregister(net);
			print("E743IP: NOTREG rc=%d\n", rc);
			if(rc != NativeIp6ErrNotReg)
				fail("e743-notreg", rc, NativeIp6ErrNotReg);

			for(j = 0; j < 5; j++){
				memset(b, 0, sizeof(*b));
				b->id = 100 + j;
				snprint(expect, sizeof expect, "E743-D-%d", j);
				rc = nativeip6_register(net, e743cb, b);
				print("E743IP: CYCLE %d REG rc=%d\n", j, rc);
				if(rc != NativeIp6Ok){
					fail("e743-cycle-register", rc, NativeIp6Ok);
					break;
				}
				print("E743IP: CYCLE %d READY\n", j);
				for(i = 0; i < 1000; i++){
					if(b->calls >= 1)
						break;
					tsleep(&up->sleep, return0, nil, 10);
				}
				print("E743IP: CYCLE %d GOT callsB=%d len=%d\n",
					j, b->calls, b->len);
				if(b->calls != 1 || b->len != strlen(expect)
				|| memcmp(b->data, expect, b->len) != 0)
					fail("e743-cycle-payload", b->calls, 1);
				rc = nativeip6_unregister(net);
				print("E743IP: CYCLE %d UNREG rc=%d\n", j, rc);
				if(rc != NativeIp6Ok)
					fail("e743-cycle-unreg", rc, NativeIp6Ok);
			}
			print("E743IP: DONE callsA=%d callsB=%d\n",
				a->calls, b->calls);
		}
	}

	/* Link-down must drop an attempted 253 frame, not panic. */
	oldlink = e->link;
	e->link = 0;
	rc = nativeip6_register(net, ip6echo, nil);
	if(rc != NativeIp6Ok)
		fail("txdown-register", rc, NativeIp6Ok);
	ipv6native_stats(net, &st);
	{
		uvlong down0 = st.txdown;
		print("E74IP: TXDOWN-READY\n");
		tsleep(&up->sleep, return0, nil, 2500);
		ipv6native_stats(net, &st);
		print("E74IP: TXDOWN txdown=%llud\n", st.txdown - down0);
		if(st.txdown <= down0)
			fail("txdown", (int)st.txdown, (int)down0+1);
	}
	e->link = oldlink;
	nativeip6_unregister(net);

	/* Close UDP, then stop the IPv6 instance. */
	echo_stop = 1;
	rc = udp6_close(uep);
	print("E74IP: UDP-CLOSE rc=%d\n", rc);
	if(rc != Udp6Ok)
		fail("udp-close", rc, Udp6Ok);
	for(i = 0; i < 300 && !echo_exited; i++)
		tsleep(&echo_done, echodone, nil, 10);
	print("E74IP: ECHO-EXIT exited=%d\n", echo_exited);
	if(!echo_exited)
		fails++;
	rc = udp6_destroy(&uep);
	if(rc != Udp6Ok)
		fail("udp-destroy", rc, Udp6Ok);

	rc = ipv6native_stop(net);
	print("E74IP: STOP rc=%d\n", rc);
	if(rc != EtherErrOk)
		fail("stop", rc, EtherErrOk);
	rc = ipv6native_stop(net);
	print("E74IP: CHECK repeat-stop rc=%d\n", rc);
	if(rc != EtherErrBadArg)
		fail("repeat-stop", rc, EtherErrBadArg);

	ok = fails == 0;
	print("E74IP: DONE pass=%d fails=%d\n", ok, fails);
	for(;;)
		tsleep(&up->sleep, return0, nil, 60000);
}

int
e74ipprobe_start(void)
{
	char *p;

	p = getconf("e74ip");
	if(p == nil || strcmp(p, "1") != 0)
		return 0;
	up = nil;
	kstrdup(&eve, "");
	kproc("*e74ip*", e74ipprobe_proc, nil);
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

int
e73udpprobe_start(void)
{
	return 0;
}
