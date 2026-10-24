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
