/*
 * E7.3 native UDP6 datagram endpoint.
 *
 * The endpoint is a Conv from the existing UDP Proto, put in the inherited
 * Announced + headers=7 mode:
 *   - udpiput matches one local address/port, preserves peer address/port
 *     in the existing 52-byte envelope and qpasses one Qmsg datagram;
 *   - udpkick consumes the same envelope and builds the UDP6/IPv6 checksum
 *     through the inherited output path.
 *
 * No Chan/namec/devtab/IP file dispatch is used.  This is a kernel C
 * capability, not a userspace ABI.
 */
#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"../port/netif.h"
#include	"../port/etherif.h"

#include	"ip.h"
#include	"ipv6.h"
#include	"nativev6.h"
#include	"nativeudp6.h"

enum {
	UDP6_USEAD7 = 52,	/* udp.c headers=7 metadata envelope */
	UDP6_HDR = 8,
	UDP6_MAXPAYLOAD = 65535 - UDP6_HDR,
};

int
udp6_open(Ipv6Native *net, uchar *local, ushort port, Udp6Endpoint **out)
{
	Udp6Endpoint *ep;
	Proto *udp;
	Conv *c;
	char buf[64], *argv[1], *eargv[2], *e;

	if(out == nil)
		return Udp6ErrBadArg;
	*out = nil;
	if(net == nil || local == nil)
		return Udp6ErrBadArg;
	if(net->state != NvRunning || net->f == nil)
		return Udp6ErrNoNet;
	if(port == 0 || isv4(local) || ipcmp(local, IPnoaddr) == 0
	|| ipismulticast(local))
		return Udp6ErrFamily;

	udp = net->f->t2p[17];
	if(udp == nil || udp->announce == nil)
		return Udp6ErrNoProto;

	qlock(udp);
	if(lportinuse(udp, port)){
		qunlock(udp);
		return Udp6ErrInUse;
	}
	c = Fsprotoclone(udp, "udp6");
	qunlock(udp);
	if(c == nil)
		return Udp6ErrNoMem;

	argv[0] = "headers";
	e = udp->ctl(c, argv, 1);
	if(e != nil){
		closeconv(c);
		return Udp6ErrBind;
	}
	snprint(buf, sizeof(buf), "%I!%d", local, port);
	eargv[0] = "announce";
	eargv[1] = buf;
	c->state = Announcing;	/* announcectlmsg does this on the legacy path */
	e = udp->announce(c, eargv, 2);
	if(e != nil){
		c->state = Idle;
		closeconv(c);
		if(strstr(e, "in use") != nil)
			return Udp6ErrInUse;
		if(strstr(e, "local") != nil)
			return Udp6ErrFamily;
		return Udp6ErrBind;
	}

	ep = smalloc(sizeof(*ep));
	if(ep == nil){
		closeconv(c);
		return Udp6ErrNoMem;
	}
	ep->net = net;
	ep->f = net->f;
	ep->udp = udp;
	ep->conv = c;
	ipmove(ep->laddr, local);
	ep->lport = port;
	*out = ep;
	return Udp6Ok;
}

static int
udp6rxready(void *a)
{
	Udp6Endpoint *ep = a;

	return ep->closed || qcanread(ep->conv->rq);
}

static int
udp6recvzero(void *a)
{
	Udp6Endpoint *ep = a;

	return ep->recvactive == 0;
}

int
udp6_recv(Udp6Endpoint *ep, Udp6Msg *msg, ulong timeout_ms)
{
	Block *bp;
	uchar *p;
	ulong end;
	int rc;

	if(ep == nil || msg == nil)
		return Udp6ErrBadArg;
	memset(msg, 0, sizeof(*msg));
	ilock(&ep->rxlock);
	if(ep->closed){
		iunlock(&ep->rxlock);
		return Udp6ErrClosed;
	}
	ep->recvactive++;
	iunlock(&ep->rxlock);

	end = NOW + timeout_ms;
	for(;;){
		ilock(&ep->rxlock);
		if(ep->closed){
			iunlock(&ep->rxlock);
			rc = Udp6ErrClosed;
			goto out;
		}
		iunlock(&ep->rxlock);
		if(qcanread(ep->conv->rq))
			break;
		if(timeout_ms == 0){
			rc = Udp6ErrTimeout;
			goto out;
		}
		if(timeout_ms != ~0UL && NOW >= end){
			rc = Udp6ErrTimeout;
			goto out;
		}
		tsleep(&ep->rxr, udp6rxready, ep, 10);
	}

	bp = qbread(ep->conv->rq, UDP6_USEAD7 + 65535);
	if(bp == nil){
		ilock(&ep->rxlock);
		rc = ep->closed ? Udp6ErrClosed : Udp6ErrTimeout;
		iunlock(&ep->rxlock);
		goto out;
	}
	bp = concatblock(bp);
	if(bp == nil){
		rc = Udp6ErrNoMem;
		goto out;
	}

	ilock(&ep->rxlock);
	if(ep->closed){
		iunlock(&ep->rxlock);
		freeb(bp);
		rc = Udp6ErrClosed;
		goto out;
	}
	iunlock(&ep->rxlock);

	if(BLEN(bp) < UDP6_USEAD7){
		freeb(bp);
		rc = Udp6ErrBadArg;
		goto out;
	}
	p = bp->rp;
	ipmove(msg->src, p); p += IPaddrlen;
	ipmove(msg->dst, p); p += IPaddrlen;
	p += IPaddrlen;			/* interface address */
	msg->sport = nhgets(p); p += 2;
	msg->dport = nhgets(p); p += 2;
	bp->rp += UDP6_USEAD7;
	msg->bp = bp;
	ep->rxmsgs++;
	ep->rxbytes += BLEN(bp);
	rc = Udp6Ok;

out:
	ilock(&ep->rxlock);
	ep->recvactive--;
	wakeup(&ep->rxr);
	iunlock(&ep->rxlock);
	return rc;
}

int
udp6_sendto(Udp6Endpoint *ep, uchar *peer, ushort peerport, Block *payload)
{
	Block *nb;
	uchar *p;
	int maxpayload, len;

	if(ep == nil || peer == nil || payload == nil)
		return Udp6ErrBadArg;
	if(payload->next != nil)
		return Udp6ErrBadArg;
	if(peerport == 0 || isv4(peer) || ipcmp(peer, IPnoaddr) == 0)
		return Udp6ErrBadArg;
	if(ep->net == nil || ep->net->ifc == nil || ep->net->ifc->m == nil)
		return Udp6ErrNoNet;
	maxpayload = ep->net->ifc->maxtu - ep->net->ifc->m->hsize
		- IP6HDR - UDP6_HDR;
	if(maxpayload < 0 || maxpayload > UDP6_MAXPAYLOAD)
		maxpayload = UDP6_MAXPAYLOAD;
	len = BLEN(payload);
	if(len > maxpayload)
		return Udp6ErrTooBig;

	nb = allocb(UDP6_USEAD7 + len);
	if(nb == nil)
		return Udp6ErrNoMem;
	p = nb->wp;
	ipmove(p, peer); p += IPaddrlen;
	ipmove(p, ep->laddr); p += IPaddrlen;
	ipmove(p, ep->laddr); p += IPaddrlen;
	hnputs(p, peerport); p += 2;
	hnputs(p, ep->lport); p += 2;
	memmove(p, payload->rp, len);
	nb->wp += UDP6_USEAD7 + len;

	qlock(&ep->lk);
	if(ep->closed || ep->conv->state != Announced){
		qunlock(&ep->lk);
		freeb(nb);
		return ep->closed ? Udp6ErrClosed : Udp6ErrNotBound;
	}
	/*
	 * c->wq is qbypass(udpkick, c).  qbwrite invokes udpkick
	 * synchronously; udpkick consumes nb and constructs the UDP6/IPv6
	 * checksum through the inherited output path.  A positive return is
	 * "accepted for delivery", not a hardware completion claim.
	 */
	qbwrite(ep->conv->wq, nb);
	qunlock(&ep->lk);

	ep->txaccepted++;
	freeb(payload);
	return Udp6Ok;
}

int
udp6_close(Udp6Endpoint *ep)
{
	int i;

	if(ep == nil)
		return Udp6ErrBadArg;
	qlock(&ep->lk);
	if(ep->closed){
		qunlock(&ep->lk);
		return Udp6ErrClosed;
	}
	ep->closed = 1;
	qunlock(&ep->lk);

	wakeup(&ep->rxr);
	closeconv(ep->conv);	/* qclose wakes a blocked qbread */
	for(i = 0; i < 300; i++){
		ilock(&ep->rxlock);
		if(ep->recvactive == 0){
			iunlock(&ep->rxlock);
			return Udp6Ok;
		}
		iunlock(&ep->rxlock);
		tsleep(&ep->rxr, udp6recvzero, ep, 10);
	}
	return Udp6ErrBusy;
}

void
udp6_stats(Udp6Endpoint *ep, Udp6Stats *st)
{
	if(st == nil)
		return;
	memset(st, 0, sizeof(*st));
	if(ep == nil)
		return;
	st->bound = ep->conv != nil && ep->conv->state == Announced;
	st->closed = ep->closed;
	st->rxmsgs = ep->rxmsgs;
	st->rxbytes = ep->rxbytes;
	st->txaccepted = ep->txaccepted;
	st->txerrors = ep->txerrors;
	st->pending = ep->conv != nil ? qlen(ep->conv->rq) : 0;
	st->convstate = ep->conv != nil ? ep->conv->state : 0;
}

int
udp6_setlimit(Udp6Endpoint *ep, int limit)
{
	if(ep == nil || ep->conv == nil || ep->closed)
		return Udp6ErrBadArg;
	qsetlimit(ep->conv->rq, limit);
	return Udp6Ok;
}

int
udp6_pending(Udp6Endpoint *ep)
{
	if(ep == nil || ep->conv == nil)
		return -1;
	return qlen(ep->conv->rq);
}
