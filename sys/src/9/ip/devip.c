#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"../ip/ip.h"

#include	"ipdevqid.h"

static char network[] = "network";

static Fs	*ipfs[Nfs];	/* attached fs's */
static Queue	*qlog;

extern	void nullmediumlink(void);
extern	void pktmediumlink(void);

static void ndbopen(Ndb *ndb, int omode);
static long ndbwrite(Ndb *ndb, char *a, ulong off, int n);
static long ndbread(Ndb *ndb, char *a, ulong off, int n);

static int
ip3gen(Chan *c, int i, Dir *dp)
{
	Qid q;
	Conv *cv;
	char *p;

	cv = ipfs[c->dev]->p[PROTO(c->qid)]->conv[CONV(c->qid)];
	if(cv->owner == nil)
		kstrdup(&cv->owner, eve);
	mkqid(&q, QID(PROTO(c->qid), CONV(c->qid), i), 0, QTFILE);

	switch(i) {
	default:
		return -1;
	case Qctl:
		devdir(c, q, "ctl", 0, cv->owner, cv->perm, dp);
		goto done;
	case Qdata:
		devdir(c, q, "data", qlen(cv->rq), cv->owner, cv->perm, dp);
		goto done;
	case Qerr:
		devdir(c, q, "err", qlen(cv->eq), cv->owner, cv->perm, dp);
		goto done;
	case Qlisten:
		devdir(c, q, "listen", 0, cv->owner, cv->perm, dp);
		goto done;
	case Qlocal:
		p = "local";
		break;
	case Qremote:
		p = "remote";
		break;
	case Qsnoop:
		if(cv->p != ipfs[c->dev]->ipifc)
			return -1;
		devdir(c, q, "snoop", qlen(cv->sq), cv->owner, 0400, dp);
		goto done;
	case Qstatus:
		p = "status";
		break;
	}
	devdir(c, q, p, 0, cv->owner, 0444, dp);
done:
	dp->mtime = cv->ctime;
	return 1;
}

static int
ip2gen(Chan *c, int i, Dir *dp)
{
	Qid q;

	switch(i) {
	case Qclone:
		mkqid(&q, QID(PROTO(c->qid), 0, Qclone), 0, QTFILE);
		devdir(c, q, "clone", 0, network, 0666, dp);
		return 1;
	case Qstats:
		mkqid(&q, QID(PROTO(c->qid), 0, Qstats), 0, QTFILE);
		devdir(c, q, "stats", 0, network, 0444, dp);
		return 1;
	case Qtrans:
		i = transfsize(ipfs[c->dev]->p[PROTO(c->qid)]);
		if(i < 0)
			return -1;
		mkqid(&q, QID(PROTO(c->qid), 0, Qtrans), 0, QTFILE);
		devdir(c, q, "trans", i, network, 0664, dp);
		return 1;
	}
	return -1;
}

static int
ip1gen(Chan *c, int i, Dir *dp)
{
	Qid q;
	char *p;
	int prot;
	int len = 0;
	Fs *f;
	extern ulong	kerndate;

	f = ipfs[c->dev];

	prot = 0666;
	mkqid(&q, QID(0, 0, i), 0, QTFILE);
	switch(i) {
	default:
		return -1;
	case Qarp:
		p = "arp";
		prot = 0664;
		break;
	case Qbootp:
		p = "bootp";
		break;
	case Qndb:
		p = "ndb";
		len = f->ndb.len;
		q.vers = f->ndb.vers;
		break;
	case Qiproute:
		p = "iproute";
		prot = 0664;
		break;
	case Qipselftab:
		p = "ipselftab";
		prot = 0444;
		break;
	case Qlog:
		p = "log";
		break;
	}
	devdir(c, q, p, len, network, prot, dp);
	if(i == Qndb && f->ndb.mtime > kerndate)
		dp->mtime = f->ndb.mtime;
	return 1;
}

static int
ipgen(Chan *c, char*, Dirtab*, int, int s, Dir *dp)
{
	Qid q;
	Conv *cv;
	Fs *f;

	f = ipfs[c->dev];

	switch(TYPE(c->qid)) {
	case Qtopdir:
		if(s == DEVDOTDOT || s == DEVDOT){
			mkqid(&q, QID(0, 0, Qtopdir), 0, QTDIR);
			snprint(up->genbuf, sizeof up->genbuf, "#I%lud", c->dev);
			devdir(c, q, up->genbuf, 0, network, 0555, dp);
			return 1;
		}
		if(s < f->np) {
	Protodir:
			if(f->p[s]->connect == nil)
				return 0;	/* protocol with no user interface */
			mkqid(&q, QID(s, 0, Qprotodir), 0, QTDIR);
			devdir(c, q, f->p[s]->name, 0, network, 0555, dp);
			return 1;
		}
		s -= f->np;
		return ip1gen(c, s+Qtopbase, dp);
	case Qarp:
	case Qbootp:
	case Qndb:
	case Qlog:
	case Qiproute:
	case Qipselftab:
		return ip1gen(c, TYPE(c->qid), dp);
	case Qprotodir:
		if(s == DEVDOTDOT){
			mkqid(&q, QID(0, 0, Qtopdir), 0, QTDIR);
			snprint(up->genbuf, sizeof up->genbuf, "#I%lud", c->dev);
			devdir(c, q, up->genbuf, 0, network, 0555, dp);
			return 1;
		}
		if(s == DEVDOT){
			s = PROTO(c->qid);
			goto Protodir;
		}
		if(s < f->p[PROTO(c->qid)]->ac) {
	Convdir:
			cv = f->p[PROTO(c->qid)]->conv[s];
			snprint(up->genbuf, sizeof up->genbuf, "%d", s);
			mkqid(&q, QID(PROTO(c->qid), s, Qconvdir), 0, QTDIR);
			devdir(c, q, up->genbuf, 0, cv->owner, 0555, dp);
			dp->mtime = cv->ctime;
			return 1;
		}
		s -= f->p[PROTO(c->qid)]->ac;
		return ip2gen(c, s+Qprotobase, dp);
	case Qclone:
	case Qstats:
	case Qtrans:
		return ip2gen(c, TYPE(c->qid), dp);
	case Qconvdir:
		if(s == DEVDOTDOT){
			s = PROTO(c->qid);
			mkqid(&q, QID(s, 0, Qprotodir), 0, QTDIR);
			devdir(c, q, f->p[s]->name, 0, network, 0555, dp);
			return 1;
		}
		if(s == DEVDOT){
			s = CONV(c->qid);
			goto Convdir;
		}
		return ip3gen(c, s+Qconvbase, dp);
	case Qctl:
	case Qdata:
	case Qerr:
	case Qlisten:
	case Qlocal:
	case Qremote:
	case Qstatus:
	case Qsnoop:
		return ip3gen(c, TYPE(c->qid), dp);
	}
	return -1;
}

static void
ipreset(void)
{
	nullmediumlink();
	pktmediumlink();

	fmtinstall('i', eipfmt);
	fmtinstall('I', eipfmt);
	fmtinstall('E', eipfmt);
	fmtinstall('V', eipfmt);
	fmtinstall('M', eipfmt);
}


#define ATTACHER(c) (((IPaux*)((c)->aux))->owner)

static Chan*
ipattach(char* spec)
{
	static QLock lk;
	Chan *c;
	ulong dev;

	dev = strtoul(spec, nil, 10);
	if(dev >= Nfs)
		error(Enodev);

	qlock(&lk);
	if(ipfs[dev] == nil){
		Fs *f;

		f = smalloc(sizeof(Fs));
		ipfsinit(f, dev);
		coherence();
		ipfs[dev] = f;
	}
	qunlock(&lk);

	c = devattach('I', spec);
	mkqid(&c->qid, QID(0, 0, Qtopdir), 0, QTDIR);
	c->dev = dev;

	c->aux = newipaux(commonuser(), "none");

	return c;
}

static Walkqid*
ipwalk(Chan* c, Chan *nc, char **name, int nname)
{
	IPaux *a = c->aux;
	Walkqid* w;

	w = devwalk(c, nc, name, nname, nil, 0, ipgen);
	if(w != nil && w->clone != nil)
		w->clone->aux = newipaux(a->owner, a->tag);
	return w;
}


static int
ipstat(Chan* c, uchar* db, int n)
{
	Dir d;

	if(c->qid.type == QTDIR){
		ipgen(c, nil, nil, 0, DEVDOT, &d);
		n = convD2M(&d, db, n);
		if(n == 0)
			error(Ebadarg);
		return n;
	}

	return devstat(c, db, n, nil, 0, ipgen);
}

static int
incoming(void* arg)
{
	Conv *conv;

	conv = arg;
	return conv->incall != nil;
}

static int m2p[] = {
	[OREAD]		4,
	[OWRITE]	2,
	[ORDWR]		6
};

static Chan*
ipopen(Chan* c, int omode)
{
	Conv *cv, *nc;
	Proto *p;
	int perm;
	Fs *f;

	perm = m2p[omode&3];

	f = ipfs[c->dev];

	switch(TYPE(c->qid)) {
	default:
		break;
	case Qndb:
		ndbopen(&f->ndb, omode);
		break;
	case Qlog:
		netlogopen(f);
		break;
	case Qiproute:
	case Qarp:
		if(omode != OREAD && !iseve())
			error(Eperm);
		break;
	case Qtrans:
		if(omode != OREAD && !iseve())
			error(Eperm);
		if(omode & OTRUNC)
			transwrite(f->p[PROTO(c->qid)], nil, 0, 0);
		break;
	case Qtopdir:
	case Qprotodir:
	case Qconvdir:
	case Qstatus:
	case Qremote:
	case Qlocal:
	case Qstats:
	case Qbootp:
	case Qipselftab:
		if(omode != OREAD)
			error(Eperm);
		break;
	case Qsnoop:
		if(omode != OREAD)
			error(Eperm);
		p = f->p[PROTO(c->qid)];
		cv = p->conv[CONV(c->qid)];
		if(strcmp(ATTACHER(c), cv->owner) != 0 && !iseve())
			error(Eperm);
		incref(&cv->snoopers);
		break;
	case Qclone:
		p = f->p[PROTO(c->qid)];
		qlock(p);
		cv = Fsprotoclone(p, ATTACHER(c));
		qunlock(p);
		if(cv == nil) {
			error(Enodev);
			break;
		}
		mkqid(&c->qid, QID(p->x, cv->x, Qctl), 0, QTFILE);
		break;
	case Qdata:
	case Qctl:
	case Qerr:
		p = f->p[PROTO(c->qid)];
		qlock(p);
		cv = p->conv[CONV(c->qid)];
		qlock(cv);
		if(waserror()) {
			qunlock(cv);
			qunlock(p);
			nexterror();
		}
		if(strcmp(ATTACHER(c), cv->owner) == 0)
			perm <<= 6;
		if((perm & cv->perm) != perm && !iseve())
			error(Eperm);

		if(++cv->inuse == 1){
			kstrdup(&cv->owner, ATTACHER(c));
			cv->perm = 0660;
		}
		qunlock(cv);
		qunlock(p);
		poperror();
		break;
	case Qlisten:
		cv = f->p[PROTO(c->qid)]->conv[CONV(c->qid)];
		qlock(cv);
		if(waserror()){
			qunlock(cv);
			nexterror();
		}
		if(strcmp(ATTACHER(c), cv->owner) == 0)
			perm <<= 6;
		if((perm & cv->perm) != perm && !iseve())
			error(Eperm);

		if(cv->state != Announced)
			error("not announced");

		cv->inuse++;
		qunlock(cv);
		poperror();
		if(waserror()){
			closeconv(cv);
			nexterror();
		}

		nc = nil;
		while(nc == nil) {
			/* give up if we got a hangup */
			if(qisclosed(cv->rq))
				error("listen hungup");

			qlock(&cv->listenq);
			if(waserror()) {
				qunlock(&cv->listenq);
				nexterror();
			}

			/* wait for a connect */
			sleep(&cv->listenr, incoming, cv);

			qlock(cv);
			nc = cv->incall;
			if(nc != nil){
				cv->incall = nc->next;
				mkqid(&c->qid, QID(PROTO(c->qid), nc->x, Qctl), 0, QTFILE);
			}
			qunlock(cv);

			qunlock(&cv->listenq);
			poperror();
		}
		closeconv(cv);
		poperror();
		break;
	}
	c->mode = openmode(omode);
	c->flag |= COPEN;
	c->offset = 0;
	return c;
}

static Chan*
ipcreate(Chan*, char*, int, ulong)
{
	error(Eperm);
}

static void
ipremove(Chan*)
{
	error(Eperm);
}

static int
ipwstat(Chan *c, uchar *dp, int n)
{
	Dir *dir;
	Conv *cv;
	Fs *f;

	f = ipfs[c->dev];
	switch(TYPE(c->qid)) {
	default:
		error(Eperm);
		break;
	case Qctl:
	case Qdata:
		break;
	}

	dir = smalloc(sizeof(Dir)+n);
	if(waserror()){
		free(dir);
		nexterror();
	}
	n = convM2D(dp, n, &dir[0], (char*)&dir[1]);
	if(n == 0)
		error(Eshortstat);

	cv = f->p[PROTO(c->qid)]->conv[CONV(c->qid)];
	qlock(cv);
	if(waserror()){
		qunlock(cv);
		nexterror();
	}
	if(strcmp(ATTACHER(c), cv->owner) != 0 && !iseve())
		error(Eperm);
	if(!emptystr(dir->uid)){
		if(strcmp(dir->uid, commonuser()) != 0 && !iseve())
			error(Eperm);
		kstrdup(&cv->owner, dir->uid);
	}
	if(dir->mode != ~0UL)
		cv->perm = dir->mode & 0666;
	qunlock(cv);
	poperror();

	free(dir);
	poperror();

	return n;
}


static void
ipclose(Chan* c)
{
	Fs *f;

	f = ipfs[c->dev];
	switch(TYPE(c->qid)) {
	default:
		break;
	case Qlog:
		if(c->flag & COPEN)
			netlogclose(f);
		break;
	case Qdata:
	case Qctl:
	case Qerr:
		if(c->flag & COPEN)
			closeconv(f->p[PROTO(c->qid)]->conv[CONV(c->qid)]);
		break;
	case Qsnoop:
		if(c->flag & COPEN)
			decref(&f->p[PROTO(c->qid)]->conv[CONV(c->qid)]->snoopers);
		break;
	}
	free(((IPaux*)c->aux)->owner);
	free(c->aux);
}

enum
{
	Maxstring=	128,
	Maxstate=	32*1024,
	Maxstats=	32*1024,
};

static long
ipread(Chan *ch, void *a, long n, vlong off)
{
	Conv *c;
	Proto *x;
	char *buf, *p;
	long rv;
	Fs *f;
	ulong offset = off;

	f = ipfs[ch->dev];

	p = a;
	switch(TYPE(ch->qid)) {
	default:
		error(Eperm);
	case Qtopdir:
	case Qprotodir:
	case Qconvdir:
		return devdirread(ch, a, n, 0, 0, ipgen);
	case Qarp:
		return arpread(f->arp, a, offset, n);
 	case Qbootp:
 		return bootpread(a, offset, n);
 	case Qndb:
		return ndbread(&f->ndb, a, offset, n);
	case Qiproute:
		return routeread(f, a, offset, n);
	case Qipselftab:
		return ipselftabread(f, a, offset, n);
	case Qlog:
		return netlogread(f, a, offset, n);
	case Qctl:
		buf = smalloc(16);
		if(waserror()){
			free(buf);
			nexterror();
		}
		snprint(buf, 16, "%lud", CONV(ch->qid));
	Readstr:
		rv = readstr(offset, p, n, buf);
		free(buf);
		poperror();
		return rv;
	case Qremote:
		buf = smalloc(Maxstring);
		if(waserror()){
			free(buf);
			nexterror();
		}
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];
		if(x->remote == nil) {
			snprint(buf, Maxstring, "%I!%d\n", c->raddr, c->rport);
		} else {
			(*x->remote)(c, buf, Maxstring);
		}
		goto Readstr;
	case Qlocal:
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];
		if(x == f->ipifc && x->local != nil){
			buf = smalloc(Maxstate);
			if(waserror()){
				free(buf);
				nexterror();
			}
			(*x->local)(c, buf, Maxstate);
			goto Readstr;
		}
		buf = smalloc(Maxstring);
		if(waserror()){
			free(buf);
			nexterror();
		}
		if(x->local == nil) {
			snprint(buf, Maxstring, "%I!%d\n", c->laddr, c->lport);
		} else {
			(*x->local)(c, buf, Maxstring);
		}
		goto Readstr;
	case Qstatus:
		buf = smalloc(Maxstate);
		if(waserror()){
			free(buf);
			nexterror();
		}
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];
		(*x->state)(c, buf, Maxstate);
		goto Readstr;
	case Qdata:
		c = f->p[PROTO(ch->qid)]->conv[CONV(ch->qid)];
		return qread(c->rq, a, n);
	case Qerr:
		c = f->p[PROTO(ch->qid)]->conv[CONV(ch->qid)];
		return qread(c->eq, a, n);
	case Qsnoop:
		c = f->p[PROTO(ch->qid)]->conv[CONV(ch->qid)];
		return qread(c->sq, a, n);
	case Qstats:
		x = f->p[PROTO(ch->qid)];
		if(x->stats == nil)
			error("stats not implemented");
		buf = smalloc(Maxstats);
		if(waserror()){
			free(buf);
			nexterror();
		}
		(*x->stats)(x, buf, Maxstats);
		goto Readstr;
	case Qtrans:
		return transread(f->p[PROTO(ch->qid)], a, offset, n);
	}
}

static Block*
ipbread(Chan* ch, long n, ulong offset)
{
	Conv *c;
	Proto *x;
	Fs *f;

	switch(TYPE(ch->qid)){
	case Qdata:
		f = ipfs[ch->dev];
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];
		return qbread(c->rq, n);
	default:
		return devbread(ch, n, offset);
	}
}

/*
 *  set local address to be that of the ifc closest to remote address
 */

/*
 *  set a local port making sure the quad of raddr,rport,laddr,lport is unique
 */

/*
 * is lport in use by anyone?
 */

/* 
 *  find a unused local port for a protocol.
 *
 *  p needs to be locked
 */

/*
 *  pick a local port and set it
 */

/*
 *  set a local address and port from a string of the form
 *	[address!]port[!r]
 */


/*
 *  called by protocol connect routine to set addresses
 */
/*
 *  initiate connection and sleep till its set up
 */
static int
connected(void* a)
{
	return ((Conv*)a)->state == Connected;
}
static void
connectctlmsg(Proto *x, Conv *c, Cmdbuf *cb)
{
	char *p;

	if(c->state != Idle)
		error(Econinuse);
	if(x->connect == nil)
		error("connect not supported");
	c->cerr[0] = '\0';
	c->state = Connecting;
	p = x->connect(c, cb->f, cb->nf);
	if(p != nil){
		c->state = Idle;
		error(p);
	}
	qunlock(c);
	if(waserror()){
		qlock(c);
		nexterror();
	}
	sleep(&c->cr, connected, c);
	qlock(c);
	poperror();

	if(c->cerr[0] != '\0')
		error(c->cerr);
}

/*
 *  called by protocol announce routine to set addresses
 */

/*
 *  initiate announcement and sleep till its set up
 */
static int
announced(void* a)
{
	return ((Conv*)a)->state == Announced;
}
static void
announcectlmsg(Proto *x, Conv *c, Cmdbuf *cb)
{
	char *p;

	if(c->state != Idle)
		error(Econinuse);
	if(x->announce == nil)
		error("announce not supported");
	c->cerr[0] = '\0';
	c->state = Announcing;
	p = x->announce(c, cb->f, cb->nf);
	if(p != nil){
		c->state = Idle;
		error(p);
	}
	qunlock(c);
	if(waserror()){
		qlock(c);
		nexterror();
	}
	sleep(&c->cr, announced, c);
	qlock(c);
	poperror();

	if(c->cerr[0] != '\0')
		error(c->cerr);
}

/*
 *  called by protocol bind routine to set addresses
 */

static void
bindctlmsg(Proto *x, Conv *c, Cmdbuf *cb)
{
	char *p;

	if(x->bind == nil)
		p = Fsstdbind(c, cb->f, cb->nf);
	else
		p = (*x->bind)(c, cb->f, cb->nf);
	if(p != nil)
		error(p);
}

static void
tosctlmsg(Conv *c, Cmdbuf *cb)
{
	if(cb->nf < 2)
		c->tos = 0;
	else
		c->tos = atoi(cb->f[1]);
}

static void
ttlctlmsg(Conv *c, Cmdbuf *cb)
{
	if(cb->nf < 2)
		c->ttl = MAXTTL;
	else
		c->ttl = atoi(cb->f[1]);
}

static long
ipwrite(Chan* ch, void *v, long n, vlong off)
{
	Conv *c;
	Proto *x;
	char *p;
	Cmdbuf *cb;
	uchar ia[IPaddrlen], ma[IPaddrlen];
	Fs *f;
	char *a;
	ulong offset = off;

	a = v;
	f = ipfs[ch->dev];

	switch(TYPE(ch->qid)){
	default:
		error(Eperm);
	case Qdata:
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];

		if(c->wq == nil)
			error(Eperm);

		qwrite(c->wq, a, n);
		break;
	case Qarp:
		return arpwrite(f, a, n);
	case Qiproute:
		return routewrite(f, ch, a, n);
	case Qtrans:
		return transwrite(f->p[PROTO(ch->qid)], a, offset, n);
	case Qlog:
		netlogctl(f, a, n);
		return n;
	case Qndb:
		return ndbwrite(&f->ndb, a, offset, n);
		break;
	case Qctl:
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];
		cb = parsecmd(a, n);

		qlock(c);
		if(waserror()) {
			qunlock(c);
			free(cb);
			nexterror();
		}
		if(cb->nf < 1)
			error("short control request");
		if(strcmp(cb->f[0], "connect") == 0)
			connectctlmsg(x, c, cb);
		else if(strcmp(cb->f[0], "announce") == 0)
			announcectlmsg(x, c, cb);
		else if(strcmp(cb->f[0], "bind") == 0)
			bindctlmsg(x, c, cb);
		else if(strcmp(cb->f[0], "ttl") == 0)
			ttlctlmsg(c, cb);
		else if(strcmp(cb->f[0], "tos") == 0)
			tosctlmsg(c, cb);
		else if(strcmp(cb->f[0], "ignoreadvice") == 0)
			c->ignoreadvice = 1;
		else if(strcmp(cb->f[0], "addmulti") == 0){
			if(cb->nf < 2)
				error("addmulti needs interface address");
			if(cb->nf == 2){
				if (parseip(ia, cb->f[1]) == -1)
					error(Ebadip);
				if(ipcmp(c->raddr, IPnoaddr) == 0 || ipismulticast(c->laddr))
					ipifcaddmulti(c, c->laddr, ia);
				else
					ipifcaddmulti(c, c->raddr, ia);
			} else {
				if (parseip(ia, cb->f[1]) == -1 ||
				    parseip(ma, cb->f[2]) == -1)
					error(Ebadip);
				ipifcaddmulti(c, ma, ia);
			}
		} else if (strcmp(cb->f[0], "delmulti") == 0
			|| strcmp(cb->f[0], "remmulti") == 0){
			if(cb->nf < 2)
				error("delmulti needs interface address");
			if (parseip(ia, cb->f[1]) == -1)
				error(Ebadip);
			if(ipcmp(c->raddr, IPnoaddr) == 0 || ipismulticast(c->laddr))
				ipifcdelmulti(c, c->laddr, ia);
			else
				ipifcdelmulti(c, c->raddr, ia);
		} else if(x->ctl != nil) {
			p = (*x->ctl)(c, cb->f, cb->nf);
			if(p != nil)
				error(p);
		} else
			error("unknown control request");
		qunlock(c);
		free(cb);
		poperror();
	}
	return n;
}

static long
ipbwrite(Chan* ch, Block* bp, ulong offset)
{
	Conv *c;
	Proto *x;
	Fs *f;

	switch(TYPE(ch->qid)){
	case Qdata:
		f = ipfs[ch->dev];
		x = f->p[PROTO(ch->qid)];
		c = x->conv[CONV(ch->qid)];

		if(c->wq == nil)
			error(Eperm);

		return qbwrite(c->wq, bp);
	default:
		return devbwrite(ch, bp, offset);
	}
}

Dev ipdevtab = {
	'I',
	"ip",

	ipreset,
	devinit,
	devshutdown,
	ipattach,
	ipwalk,
	ipstat,
	ipopen,
	ipcreate,
	ipclose,
	ipread,
	ipbread,
	ipwrite,
	ipbwrite,
	ipremove,
	ipwstat,
};


/*
 *  return true if this protocol is
 *  built in
 */

/*
 *  called with protocol locked
 */


/*
 *  called with protocol locked
 */

static void
ndbopen(Ndb *ndb, int omode)
{
	int trunc;

	trunc = omode & OTRUNC;
	omode = openmode(omode);

	if((omode == OWRITE || omode == ORDWR || trunc) && !iseve())
		error(Eperm);

	if(trunc){
		qlock(ndb);
		free(ndb->buf);
		ndb->buf = nil;
		ndb->len = 0;
		ndb->vers++;
		ndb->mtime = seconds();
		qunlock(ndb);
	}
}

static long
ndbwrite(Ndb *ndb, char *a, ulong off, int n)
{
	qlock(ndb);
	if(waserror()){
		qunlock(ndb);
		nexterror();
	}
	if(off > ndb->len || off+n >= 32*1024)
		error(Eio);
	if(n > 0){
		if(off+n > ndb->len){
			char *nb = realloc(ndb->buf, off+n);
			if(nb == nil)
				error(Enomem);
			ndb->buf = nb;
			ndb->len = off+n;
		}
		memmove(ndb->buf+off, a, n);
		ndb->vers++;
		ndb->mtime = seconds();
	}
	qunlock(ndb);
	poperror();
	return n;
}

static long
ndbread(Ndb *ndb, char *a, ulong off, int n)
{
	qlock(ndb);
	if(waserror()){
		qunlock(ndb);
		nexterror();
	}
	if(off >= ndb->len)
		n = 0;
	else {
		if(off+n > ndb->len)
			n = ndb->len - off;
		memmove(a, ndb->buf+off, n);
	}
	qunlock(ndb);
	poperror();
	return n;
}
