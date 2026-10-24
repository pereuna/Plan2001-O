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

static void
e73udpprobe_proc(void *arg)
{
	Ether *e;
	Ipv6Native *ni2;
	Ipv6NativeStats st;
	Udp6Endpoint *dup;
	uchar bad[IPaddrlen];
	uvlong cdone[6], rxbase;
	ulong ind, outd, nop, inerr, dropfull;
	char sbuf[256];
	int i, n, p1, p2, rc, oldlink;

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

	/* Close the UDP endpoint before tearing down the IPv6 medium/Fs. */
	echo_stop = 1;
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
