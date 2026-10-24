/*
 * E7.1 opt-in native Ethernet probe (pc64e71 only).
 *
 * Runs as a kernel process after the scheduler starts, so device attach may
 * start driver workers and take QLocks.  It exercises the native Ether core
 * directly (no #l Chan on that path), then separately verifies that the
 * retained legacy #l/Netfile adapter still attaches and receives.
 *
 * Markers are single-line and stable for tools/test_e71_ether.py.
 */
#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"../port/netif.h"
#include	"../port/etherif.h"

extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

static Queue *rxq;
static Rendez rxr;
static Ether *edev;
static int fails;

static uvlong csnap[6];
static uvlong cdone[6];

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
	print("E71ETHER: FAIL %s rc=%d want=%d\n", what, rc, want);
}

static int
rxready(void *arg)
{
	USED(arg);
	return qcanread(rxq);
}

/*
 * Native RX sink: driver RX context (VirtIO rxproc or an IRQ).  It only
 * uses interrupt-safe operations: qpass and wakeup.  qpass frees the Block
 * on failure, so the sink always leaves exactly one owner.
 */
static void
rxsink(void *arg, Ether *e, Block *bp)
{
	USED(arg);
	USED(e);
	if(qpass(rxq, bp) < 0){
		/* qpass already released the Block */
	}
	wakeup(&rxr);
}

static Block*
mkframe(uchar *dst, ushort type, char *magic, int len)
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
	if(magic != nil && len > ETHERHDRSIZE)
		memmove(bp->wp + ETHERHDRSIZE, magic, strlen(magic));
	bp->wp += len;
	return bp;
}

static int
txexpect(char *what, ushort type, char *magic, int len, int want)
{
	Block *bp;
	int rc;

	bp = mkframe(edev->bcast, type, magic, len);
	if(bp == nil){
		fail(what, EtherErrNoMem, want);
		return 0;
	}
	rc = ethercore_tx(edev, bp);
	if(rc != want)
		fail(what, rc, want);
	else
		print("E71ETHER: CHECK %s rc=%d\n", what, rc);
	if(rc != EtherErrOk)
		freeb(bp);
	return rc == want;
}

static int
legacytest(Ether *e)
{
	Chan *volatile c, *volatile d;
	Block *bp;
	Etherpkt *p;
	char path[64], *msg;
	int rc, ok;

	c = d = nil;
	ok = 0;
	msg = "connect 0x86dd\n";
	if(waserror()){
		print("E71ETHER: LEGACY-ERR %s\n", up->errstr);
		if(d != nil)
			cclose(d);
		if(c != nil)
			cclose(c);
		return 0;
	}

	snprint(path, sizeof(path), "#l%d/%s/clone", e->ctlrno, e->name);
	c = namec(path, Aopen, ORDWR, 0);
	devtab[c->type]->write(c, msg, strlen(msg), 0);

	snprint(path, sizeof(path), "#l%d/%s/0/data", e->ctlrno, e->name);
	d = namec(path, Aopen, OREAD, 0);

	print("E71ETHER: LEGACY-READY\n");
	bp = devtab[d->type]->bread(d, 2048, 0);
	if(bp == nil)
		print("E71ETHER: LEGACY-ERR nil block\n");
	else {
		p = (Etherpkt*)bp->rp;
		rc = (p->type[0]<<8) | p->type[1];
		ok = BLEN(bp) >= 64
			&& rc == 0x86DD
			&& memcmp(bp->rp + ETHERHDRSIZE, "E71LEGACY", 9) == 0;
		print("E71ETHER: LEGACY len=%d type=0x%ux match=%d\n",
			BLEN(bp), rc, ok);
		freeb(bp);
	}
	poperror();
	cclose(d);
	cclose(c);
	return ok;
}

static void
e71etherprobe_proc(void *arg)
{
	Ether *e;
	EtherCoreStats st;
	Block *bp;
	Etherpkt *p;
	Queue *priv, *oldoq;
	void (*oldtx)(Ether*);
	int i, n, p1, p2, rc, oldlink, ok;

	USED(arg);
	print("E71ETHER: PROBE begin\n");
	fails = 0;

	rxq = qopen(64*1024, Qmsg, nil, nil);
	if(rxq == nil){
		print("E71ETHER: FAIL rxq alloc\n");
		fails++;
	}

	p1 = ethercore_probecalls();
	n = ethercore_init();
	p2 = ethercore_probecalls();
	print("E71ETHER: INIT rc=%d inits=%d probes=%d idempotent=%d\n",
		n, ethercore_initcalls(), p2, p1 == p2);
	if(p1 != p2){
		print("E71ETHER: FAIL init re-probed controllers\n");
		fails++;
	}
	if(n <= 0){
		print("E71ETHER: NODEV n=%d\n", n);
		print("E71ETHER: DONE pass=%d fails=%d\n", fails == 0, fails);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}

	e = ethercore_lookup(0);
	if(e == nil)
		e = ethercore_byindex(0);
	if(e == nil){
		print("E71ETHER: FAIL no controller lookup\n");
		print("E71ETHER: DONE pass=0 fails=%d\n", fails+1);
		for(;;)
			tsleep(&up->sleep, return0, nil, 60000);
	}
	edev = e;
	print("E71ETHER: CTLR ctlrno=%d name=%s ea=%E mbps=%d maxmtu=%d link=%d\n",
		e->ctlrno, e->name, e->ea, e->mbps, e->maxmtu, e->link);

	snapcounters(csnap);

	/* Negative: valid frame before attach. */
	txexpect("preattach", 0x88B6, "E71TXTX", 64, EtherErrNotReady);

	/* Negative: invalid lengths (short and over maxmtu). */
	bp = allocb(10);
	if(bp != nil){
		memset(bp->wp, 0, 10);
		bp->wp += 10;
		rc = ethercore_tx(e, bp);
		if(rc != EtherErrBadLen)
			fail("shortlen", rc, EtherErrBadLen);
		else
			print("E71ETHER: NEG shortlen rc=%d\n", rc);
		freeb(bp);
	}
	bp = allocb(e->maxmtu+1);
	if(bp != nil){
		memset(bp->wp, 0, e->maxmtu+1);
		bp->wp += e->maxmtu+1;
		rc = ethercore_tx(e, bp);
		if(rc != EtherErrBadLen)
			fail("longlen", rc, EtherErrBadLen);
		else
			print("E71ETHER: NEG longlen rc=%d\n", rc);
		freeb(bp);
	}

	/* Native RX registration contract. */
	rc = ethercore_rxregister(e, rxsink, nil);
	if(rc != EtherErrOk)
		fail("rxregister", rc, EtherErrOk);
	rc = ethercore_rxregister(e, rxsink, nil);
	if(rc != EtherErrBusy)
		fail("rxregister-twice", rc, EtherErrBusy);
	else
		print("E71ETHER: NEG rxregister-busy rc=%d\n", rc);
	rc = ethercore_rxunregister(e, nil, nil);
	if(rc != EtherErrBadArg)
		fail("rxunregister-mismatch", rc, EtherErrBadArg);
	else
		print("E71ETHER: NEG rxunregister-mismatch rc=%d\n", rc);
	rc = ethercore_rxregister(e, nil, nil);
	if(rc != EtherErrBadArg)
		fail("rxregister-nil", rc, EtherErrBadArg);
	else
		print("E71ETHER: NEG rxregister-nil rc=%d\n", rc);

	rc = ethercore_attach(e);
	print("E71ETHER: ATTACH rc=%d\n", rc);
	if(rc != EtherErrOk)
		fail("attach", rc, EtherErrOk);

	/* Let VirtIO's rxproc fill its receive ring. */
	tsleep(&up->sleep, return0, nil, 200);

	print("E71ETHER: READY\n");

	/* Native TX: a complete frame with an experimental EtherType. */
	ok = txexpect("tx", 0x88B6, "E71TXTX", 64, EtherErrOk);
	print("E71ETHER: TX rc=%d len=64 type=0x88b6 ok=%d\n", ok ? 0 : -1, ok);

	/* Native RX from the real NIC: host injects this after READY. */
	for(i = 0; i < 100 && !qcanread(rxq); i++)
		tsleep(&rxr, rxready, nil, 100);
	if(!qcanread(rxq)){
		print("E71ETHER: FAIL rx-timeout\n");
		fails++;
	}else{
		bp = qbread(rxq, 2048);
		if(bp == nil){
			print("E71ETHER: FAIL rx-nil\n");
			fails++;
		}else{
			p = (Etherpkt*)bp->rp;
			rc = (p->type[0]<<8) | p->type[1];
			ok = BLEN(bp) >= 64
				&& rc == 0x88B5
				&& memcmp(bp->rp + ETHERHDRSIZE, "E71RXRX", 7) == 0;
			print("E71ETHER: RX len=%d type=0x%ux match=%d\n", BLEN(bp), rc, ok);
			if(!ok)
				fails++;
			freeb(bp);
		}
	}

	ethercore_stats(e, &st);
	print("E71ETHER: STATS tx=%llud rx=%llud drop=%llud attached=%d registered=%d\n",
		st.txpackets, st.rxpackets, st.rxdropped, st.attached, st.registered);

	snapcounters(cdone);
	print("E71ETHER: CHAN-NATIVE namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud clean=%d\n",
		cdone[0]-csnap[0], cdone[1]-csnap[1], cdone[2]-csnap[2],
		cdone[3]-csnap[3], cdone[4]-csnap[4], cdone[5]-csnap[5],
		samecounters(csnap, cdone));

	/* Negative: down link is rejected without consuming the Block. */
	oldlink = e->link;
	e->link = 0;
	txexpect("down", 0x88B6, "E71TXTX", 64, EtherErrDown);
	e->link = oldlink;

	/*
	 * Negative: full output queue, isolated from the NIC using a private
	 * Queue with limit 0 and no kick.  This is a core backpressure test,
	 * not a hardware TX observation.
	 */
	oldoq = e->oq;
	oldtx = e->transmit;
	priv = qopen(0, Qmsg, nil, nil);
	if(priv != nil){
		e->oq = priv;
		e->transmit = nil;
		rc = txexpect("queue1", 0x88B6, "E71TXTX", 64, EtherErrOk);
		rc = txexpect("queue-full", 0x88B6, "E71TXTX", 64, EtherErrQueue);
		e->oq = oldoq;
		e->transmit = oldtx;
		qfree(priv);
	}

	/* Unbind the native sink; the legacy Netfile path must still work. */
	rc = ethercore_rxunregister(e, rxsink, nil);
	print("E71ETHER: RXUNREGISTER rc=%d\n", rc);
	if(rc != EtherErrOk)
		fail("rxunregister", rc, EtherErrOk);
	rc = ethercore_rxunregister(e, rxsink, nil);
	if(rc != EtherErrBadArg)
		fail("rxunregister-twice", rc, EtherErrBadArg);
	else
		print("E71ETHER: NEG rxunregister-twice rc=%d\n", rc);

	ok = legacytest(e);
	if(!ok)
		fails++;

	print("E71ETHER: DONE pass=%d fails=%d\n", fails == 0, fails);
	for(;;)
		tsleep(&up->sleep, return0, nil, 60000);
}

int
e71etherprobe_start(void)
{
	char *p;

	p = getconf("e71ether");
	if(p == nil || strcmp(p, "1") != 0)
		return 0;
	up = nil;
	kstrdup(&eve, "");
	kproc("*e71ether*", e71etherprobe_proc, nil);
	return 1;
}

int
onativeprobe_start(void)
{
	return 0;
}
