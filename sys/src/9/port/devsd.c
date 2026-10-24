/*
 * Storage Device.
 */
#include "u.h"
#include "../port/lib.h"
#include "mem.h"
#include "dat.h"
#include "fns.h"
#include "io.h"
#include "ureg.h"
#include "../port/error.h"

#include "../port/sd.h"

extern Dev sddevtab;
extern SDifc* sdifc[];

static SDunit topctlunit;

enum {
	Ahdrsz		= 2,
};

enum {
	Rawcmd,
	Rawdata,
	Rawstatus,
};

enum {
	Qtopdir		= 1,		/* top level directory */
	Qtopbase,
	Qtopctl		 = Qtopbase,

	Qunitdir,			/* directory per unit */
	Qunitbase,
	Qctl		= Qunitbase,
	Qraw,
	Qpart,
	Qextra,

	TypeLOG		= 4,
	NType		= (1<<TypeLOG),
	TypeMASK	= (NType-1),
	TypeSHIFT	= 0,

	PartLOG		= 8,
	NPart		= (1<<PartLOG),
	PartMASK	= (NPart-1),
	PartSHIFT	= TypeLOG,

	UnitLOG		= 8,
	NUnit		= (1<<UnitLOG),
	UnitMASK	= (NUnit-1),
	UnitSHIFT	= (PartLOG+TypeLOG),

	DevLOG		= 8,
	NDev		= (1 << DevLOG),
	DevMASK		= (NDev-1),
	DevSHIFT	 = (UnitLOG+PartLOG+TypeLOG),

	Ncmd = 20,
};

#define TYPE(q)		((((ulong)(q).path)>>TypeSHIFT) & TypeMASK)
#define PART(q)		((((ulong)(q).path)>>PartSHIFT) & PartMASK)
#define UNIT(q)		((((ulong)(q).path)>>UnitSHIFT) & UnitMASK)
#define DEV(q)		((((ulong)(q).path)>>DevSHIFT) & DevMASK)
#define QID(d,u, p, t)	(((d)<<DevSHIFT)|((u)<<UnitSHIFT)|\
					 ((p)<<PartSHIFT)|((t)<<TypeSHIFT))

static int
sd2gen(Chan* c, SDunit *unit, int i, Dir* dp)
{
	Qid q;
	uvlong l;
	SDfile *e;
	SDpart *pp;
	SDperm *perm;
	int t;

	switch(i){
	case Qctl:
		mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), PART(c->qid), Qctl),
			unit->vers, QTFILE);
		perm = &unit->ctlperm;
		if(emptystr(perm->user)){
			kstrdup(&perm->user, eve);
			perm->perm = 0640;
		}
		devdir(c, q, "ctl", 0, perm->user, perm->perm, dp);
		return 1;

	case Qraw:
		mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), PART(c->qid), Qraw),
			unit->vers, QTFILE);
		perm = &unit->rawperm;
		if(emptystr(perm->user)){
			kstrdup(&perm->user, eve);
			perm->perm = DMEXCL|0600;
		}
		devdir(c, q, "raw", 0, perm->user, perm->perm, dp);
		return 1;

	case Qpart:
		pp = &unit->part[PART(c->qid)];
		l = (pp->end - pp->start) * unit->secsize;
		mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), PART(c->qid), Qpart),
			unit->vers+pp->vers, QTFILE);
		if(emptystr(pp->user))
			kstrdup(&pp->user, eve);
		devdir(c, q, pp->name, l, pp->user, pp->perm, dp);
		return 1;

	case Qextra:
		t = PART(c->qid);
		if(t >= unit->nefile)
			break;
		mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), PART(c->qid), Qextra),
			unit->vers, QTFILE);
		e = unit->efile + t;
		if(emptystr(e->user))
			kstrdup(&e->user, eve);
		devdir(c, q, e->name, 0, e->user, e->perm, dp);
		return 1;
	}

	return -1;
}

static int
sd1gen(Chan* c, int i, Dir* dp)
{
	Qid q;
	SDperm *p;

	switch(i){
	case Qtopctl:
		mkqid(&q, QID(0, 0, 0, Qtopctl), 0, QTFILE);
		qlock(&topctlunit.ctl);
		p = &topctlunit.ctlperm;
		if(emptystr(p->user)){
			kstrdup(&p->name, "sdctl");
			kstrdup(&p->user, eve);
			p->perm = 0640;
		}
		devdir(c, q, p->name, 0, p->user, p->perm, dp);
		qunlock(&topctlunit.ctl);
		return 1;
	}
	return -1;
}

static int
efilegen(Chan *c, SDunit *unit, int i, Dir *dp)
{
	Qid q;
	SDfile *e;

	i -= SDnpart;
	if(unit->nefile == 0 || i >= unit->nefile)
		return -1;
	if(i < 0)
		return 0;
	e = unit->efile + i;
	if(emptystr(e->user))
		kstrdup(&e->user, eve);
	mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), i, Qextra),
		unit->vers, QTFILE);
	devdir(c, q, e->name, 0, e->user, e->perm, dp);
	return 1;
}

static int
sdgen(Chan* c, char*, Dirtab*, int, int s, Dir* dp)
{
	Qid q;
	uvlong l;
	int i, r;
	SDpart *pp;
	SDunit *unit;
	SDev *sdev;

	switch(TYPE(c->qid)){
	case Qtopdir:
		if(s == DEVDOTDOT){
			mkqid(&q, QID(0, 0, 0, Qtopdir), 0, QTDIR);
			sprint(up->genbuf, "#%C", sddevtab.dc);
			devdir(c, q, up->genbuf, 0, eve, 0555, dp);
			return 1;
		}

		if(s+Qtopbase < Qunitdir)
			return sd1gen(c, s+Qtopbase, dp);
		s -= (Qunitdir-Qtopbase);

		qlock(&sddevslock);
		for(i=0; i<nelem(sddevs); i++){
			if(sddevs[i]){
				if(s < sddevs[i]->nunit)
					break;
				s -= sddevs[i]->nunit;
			}
		}

		if(i == nelem(sddevs)){
			/* Run off the end of the list */
			qunlock(&sddevslock);
			return -1;
		}

		if((sdev = sddevs[i]) == nil){
			qunlock(&sddevslock);
			return 0;
		}

		incref(&sdev->r);
		qunlock(&sddevslock);

		if((unit = sdgetunit(sdev, s)) == nil){
			decref(&sdev->r);
			return 0;
		}

		mkqid(&q, QID(sdev->idno, s, 0, Qunitdir), 0, QTDIR);
		if(emptystr(unit->user))
			kstrdup(&unit->user, eve);
		devdir(c, q, unit->name, 0, unit->user, unit->perm, dp);
		decref(&sdev->r);
		return 1;

	case Qunitdir:
		if(s == DEVDOTDOT){
			mkqid(&q, QID(0, 0, 0, Qtopdir), 0, QTDIR);
			sprint(up->genbuf, "#%C", sddevtab.dc);
			devdir(c, q, up->genbuf, 0, eve, 0555, dp);
			return 1;
		}

		if((sdev = sdgetdev(DEV(c->qid))) == nil)
			return -1;
		unit = sdev->unit[UNIT(c->qid)];
		qlock(&unit->ctl);
		if(waserror()){
			r = -1;
			goto ReleaseUnit;
		}

		/*
		 * Check for media change.
		 * If one has already been detected, sectors will be zero.
		 * If there is one waiting to be detected, online
		 * will return > 1.
		 * Online is a bit of a large hammer but does the job.
		 */
		if(unit->sectors == 0
		|| (unit->dev->ifc->online != nil && (*unit->dev->ifc->online)(unit) > 1))
			sdinitpart(unit);

		i = s+Qunitbase;
		if(i < Qpart){
			r = sd2gen(c, unit, i, dp);
			poperror();
			goto ReleaseUnit;
		}
		i -= Qpart;
		if(unit->part == nil || i >= unit->npart){
			r = efilegen(c, unit, i, dp);
			poperror();
			goto ReleaseUnit;
		}
		poperror();

		pp = &unit->part[i];
		if(!pp->valid || unit->sectors == 0){
			r = 0;
			goto ReleaseUnit;
		}
		l = (pp->end - pp->start) * (uvlong)unit->secsize;
		mkqid(&q, QID(DEV(c->qid), UNIT(c->qid), i, Qpart),
			unit->vers+pp->vers, QTFILE);
		if(emptystr(pp->user))
			kstrdup(&pp->user, eve);
		devdir(c, q, pp->name, l, pp->user, pp->perm, dp);
		r = 1;
		goto ReleaseUnit;
	case Qraw:
	case Qctl:
	case Qpart:
	case Qextra:
		if((sdev = sdgetdev(DEV(c->qid))) == nil)
			return -1;
		unit = sdev->unit[UNIT(c->qid)];
		qlock(&unit->ctl);
		if(!waserror()){
			r = sd2gen(c, unit, TYPE(c->qid), dp);
			poperror();
		} else {
			r = -1;
		}
	ReleaseUnit:
		qunlock(&unit->ctl);
		decref(&sdev->r);
		return r;
	case Qtopctl:
		return sd1gen(c, TYPE(c->qid), dp);
	default:
		break;
	}

	return -1;
}

static Chan*
sdattach(char* spec)
{
	Chan *c;
	char *p;
	SDev *sdev;
	int idno, subno;

	if(*spec == '\0'){
		c = devattach(sddevtab.dc, spec);
		mkqid(&c->qid, QID(0, 0, 0, Qtopdir), 0, QTDIR);
		return c;
	}

	if(spec[0] != 's' || spec[1] != 'd')
		error(Ebadspec);
	idno = spec[2];
	subno = strtol(&spec[3], &p, 10);
	if(subno < 0 || p == &spec[3])
		error(Ebadspec);

	if((sdev = sdgetdev(idno)) == nil)
		error(Enonexist);
	if(waserror()){
		decref(&sdev->r);
		nexterror();
	}
	if(sdgetunit(sdev, subno) == nil)
		error(Enonexist);
	c = devattach(sddevtab.dc, spec);
	mkqid(&c->qid, QID(sdev->idno, subno, 0, Qunitdir), 0, QTDIR);
	c->dev = (sdev->idno << UnitLOG) + subno;
	decref(&sdev->r);
	poperror();
	return c;
}

static Walkqid*
sdwalk(Chan* c, Chan* nc, char** name, int nname)
{
	return devwalk(c, nc, name, nname, nil, 0, sdgen);
}

static int
sdstat(Chan* c, uchar* db, int n)
{
	return devstat(c, db, n, nil, 0, sdgen);
}

static Chan*
sdopen(Chan* c, int omode)
{
	SDpart *pp;
	SDunit *unit;
	SDev *sdev;

	c = devopen(c, omode, 0, 0, sdgen);
	if(TYPE(c->qid) < Qunitbase)
		return c;
	if(waserror()){
		c->flag &= ~COPEN;
		nexterror();
	}
	sdev = sdgetdev(DEV(c->qid));
	if(sdev == nil)
		error(Enonexist);
	if(waserror()){
		decref(&sdev->r);
		nexterror();
	}
	unit = sdev->unit[UNIT(c->qid)];
	switch(TYPE(c->qid)){
	case Qctl:
	case Qextra:
		c->qid.vers = unit->vers;
		break;
	case Qraw:
		qlock(&unit->raw);
		if(unit->rawinuse){
			qunlock(&unit->raw);
			error(Einuse);
		}
		unit->state = Rawcmd;
		c->qid.vers = unit->vers;
		qunlock(&unit->raw);
		break;
	case Qpart:
		qlock(&unit->ctl);
		pp = &unit->part[PART(c->qid)];
		c->qid.vers = unit->vers+pp->vers;
		qunlock(&unit->ctl);
		break;
	}
	poperror();
	poperror();
	/* keep the reference to unit->dev (sdev) */
	c->aux = unit;
	return c;
}

static void
sdclose(Chan* c)
{
	SDunit *unit;

	if(!(c->flag & COPEN))
		return;
	if(TYPE(c->qid) < Qunitbase)
		return;
	unit = c->aux;
	switch(TYPE(c->qid)){
	case Qraw:
		qlock(&unit->raw);
		unit->rawinuse = 0;
		qunlock(&unit->raw);
		break;
	}
	decref(&unit->dev->r);
}

#define iskaddr(a)	((uintptr)(a) > KZERO)

static long
sdbio(Chan* c, int write, char* a, long len, uvlong off)
{
	int nchange, hard, allocd, locked;
	long l;
	uchar *b;
	SDpart *pp;
	SDunit *unit;
	ulong max, nb, offset;
	uvlong bno;

	unit = c->aux;
	qlock(&unit->ctl);
	nchange = 0;
	while(waserror()){
		/* notification of media change; go around again */
		if(strcmp(up->errstr, Eio) == 0 && unit->sectors == 0 && nchange++ == 0){
			sdinitpart(unit);
			continue;
		}

		/* other errors; give up */
		qunlock(&unit->ctl);
		nexterror();
	}
	pp = &unit->part[PART(c->qid)];
	if(unit->vers+pp->vers != c->qid.vers)
		error(Echange);

	/*
	 * Check the request is within bounds.
	 * Removeable drives are locked throughout the I/O
	 * in case the media changes unexpectedly.
	 * Non-removeable drives are not locked during the I/O
	 * to allow the hardware to optimise if it can; this is
	 * a little fast and loose.
	 * It's assumed that non-removeable media parameters
	 * (sectors, secsize) can't change once the drive has
	 * been brought online.
	 */
	bno = (off/unit->secsize) + pp->start;
	nb = ((off+len+unit->secsize-1)/unit->secsize) + pp->start - bno;
	max = SDmaxio/unit->secsize;
	if(nb > max)
		nb = max;
	if(bno+nb > pp->end)
		nb = pp->end - bno;
	if(bno >= pp->end || nb == 0){
		if(write)
			error(Eio);
		qunlock(&unit->ctl);
		poperror();
		return 0;
	}
	locked = (unit->inquiry[1] & 0x80) != 0;
	if(!locked){
		qunlock(&unit->ctl);
		poperror();
	}

	offset = off%unit->secsize;
	if(offset+len > nb*unit->secsize)
		len = nb*unit->secsize - offset;
	hard = offset || write && len%unit->secsize;

	if(iskaddr(a) && ((uintptr)a & (BY2PG-1))==0 && !hard) {
		b = (uchar*)a;
		allocd = 0;
	}else{
		while((b = sdmalloc(nb*unit->secsize)) == nil)
			resrcwait("no memory for sdbio");
		if(waserror()){
			sdfree(b);
			nexterror();
		}
		allocd = 1;
	}

	if(write){
		if(hard){
			l = (*unit->dev->ifc->bio)(unit, 0, 0, b, nb, bno);
			if(l < 0)
				error(Eio);
			if(l < (nb*unit->secsize)){
				nb = l/unit->secsize;
				l = nb*unit->secsize - offset;
				if(len > l)
					len = l;
			}
		}
		if(allocd)
			memmove(b+offset, a, len);
		l = (*unit->dev->ifc->bio)(unit, 0, 1, b, nb, bno);
		if(l < 0)
			error(Eio);
		if(l < offset)
			len = 0;
		else if(len > l - offset)
			len = l - offset;
	}
	else{
		l = (*unit->dev->ifc->bio)(unit, 0, 0, b, nb, bno);
		if(l < 0)
			error(Eio);
		if(l < offset)
			len = 0;
		else if(len > l - offset)
			len = l - offset;
		if(allocd)
			memmove(a, b+offset, len);
	}

	if(allocd){
		sdfree(b);
		poperror();
	}
	if(locked){
		qunlock(&unit->ctl);
		poperror();
	}

	return len;
}

static long
extrarw(Chan *c, int write, void *a, long n, vlong off)
{
	SDunit *unit = c->aux;
	SDrw *f;
	int i;

	if(unit->vers != c->qid.vers)
		error(Echange);
	i = PART(c->qid);
	if(i >= unit->nefile)
		error(Enonexist);
	f = write ? unit->efile[i].w : unit->efile[i].r;
	if(f == nil)
		error(Eperm);
	return f(unit, c, a, n, off);
}

static char*
deftopctl(SDev *s, char *p, char *e)
{
	return seprint(p, e, "sd%c %s %d units\n", s->idno, s->ifc->name, s->nunit);
}

static long
sdread(Chan *c, void *a, long n, vlong off)
{
	char *p, *e, *buf;
	SDev *sdev;
	SDpart *pp;
	SDreq *r;
	SDunit *unit;
	ulong offset;
	int i, l, m, status;

	offset = off;
	switch(TYPE(c->qid)){
	default:
		error(Eperm);
	case Qtopctl:
		m = 64*1024;	/* room for register dumps */
		p = buf = smalloc(m);
		e = p + m;
		if(waserror()){
			free(buf);
			nexterror();
		}
		qlock(&sddevslock);
		if(waserror()){
			qunlock(&sddevslock);
			nexterror();
		}
		for(i = 0; i < nelem(sddevs); i++){
			sdev = sddevs[i];
			if(sdev == nil)
				continue;
			if(sdev->ifc->rtopctl != nil)
				p = (*sdev->ifc->rtopctl)(sdev, p, e);
			else
				p = deftopctl(sdev, p, e);
		}
		qunlock(&sddevslock);
		poperror();
		n = readstr(off, a, n, buf);
		free(buf);
		poperror();
		return n;

	case Qtopdir:
	case Qunitdir:
		return devdirread(c, a, n, 0, 0, sdgen);

	case Qctl:
		m = 16*1024;	/* room for register dumps */
		p = buf = smalloc(m);
		e = p + m;
		if(waserror()){
			free(buf);
			nexterror();
		}
		unit = c->aux;
		qlock(&unit->ctl);
		if(waserror()){
			qunlock(&unit->ctl);
			nexterror();
		}
		p = seprint(p, e, "inquiry %.48s\n", (char*)unit->inquiry+8);
		/*
		 * If there's a device specific routine it must
		 * provide all information pertaining to night geometry
		 * and the garscadden trains.
		 */
		if(unit->dev->ifc->rctl != nil)
			p = (*unit->dev->ifc->rctl)(unit, p, e);
		if(unit->sectors == 0)
			sdinitpart(unit);
		if(unit->sectors){
			if(unit->dev->ifc->rctl == nil)
				p = seprint(p, e, "geometry %llud %lud\n",
					unit->sectors, unit->secsize);
			for(i = 0; i < unit->npart; i++){
				pp = &unit->part[i];
				if(pp->valid)
					p = seprint(p, e, "part %s %llud %llud\n",
						pp->name, pp->start, pp->end);
			}
		}
		qunlock(&unit->ctl);
		poperror();
		l = readstr(offset, a, n, buf);
		free(buf);
		poperror();
		return l;

	case Qraw:
		unit = c->aux;
		qlock(&unit->raw);
		if(waserror()){
			qunlock(&unit->raw);
			nexterror();
		}
		if(unit->state == Rawdata){
			unit->state = Rawstatus;
			r = unit->req;
			i = sdrio(r, a, n);
		}
		else if(unit->state == Rawstatus){
			r = unit->req;
			unit->req = nil;
			unit->state = Rawcmd;
			status = r->status;
			if(r->proto == SData){
				p = a;
				i = 16 + Ahdrsz;
				if(n < i)
					i = n;
				if(i > 0)
					p[0] = status;
				if(i > Ahdrsz)
					memmove(p + Ahdrsz, r->cmd, i - Ahdrsz);
			}else
				i = readnum(0, a, n, status, NUMSIZE);
			free(r);
		} else
			i = 0;
		qunlock(&unit->raw);
		poperror();
		return i;

	case Qpart:
		return sdbio(c, 0, a, n, off);
	case Qextra:
		return extrarw(c, 0, a, n, off);
	}
}

static void legacytopctl(Cmdbuf*);

static long
sdwrite(Chan* c, void* a, long n, vlong off)
{
	char *f0;
	int i, atacdb, proto, ataproto;
	uchar *u;
	uvlong end, start;
	Cmdbuf *cb;
	SDifc *ifc;
	SDreq *req;
	SDunit *unit;
	SDev *sdev;

	switch(TYPE(c->qid)){
	default:
		error(Eperm);
	case Qtopctl:
		cb = parsecmd(a, n);
		if(waserror()){
			free(cb);
			nexterror();
		}
		if(cb->nf == 0)
			error("empty control message");
		f0 = cb->f[0];
		cb->f++;
		cb->nf--;
		if(strcmp(f0, "config") == 0){
			/* wormhole into ugly legacy interface */
			legacytopctl(cb);
			poperror();
			free(cb);
			break;
		}
		/*
		 * "ata arg..." invokes sdifc[i]->wtopctl(nil, cb),
		 * where sdifc[i]->name=="ata" and cb contains the args.
		 */
		for(i=0; sdifc[i] != nil; i++){
			if(strcmp(sdifc[i]->name, f0) == 0){
				ifc = sdifc[i];
				sdev = nil;
				goto subtopctl;
			}
		}
		/*
		 * "sd1 arg..." invokes sdifc[i]->wtopctl(sdev, cb),
		 * where sdifc[i] and sdev match controller letter "1",
		 * and cb contains the args.
		 */
		if(f0[0]=='s' && f0[1]=='d' && f0[2] && f0[3] == 0){
			if((sdev = sdgetdev(f0[2])) != nil){
				ifc = sdev->ifc;
				goto subtopctl;
			}
		}
		error("unknown interface");

	subtopctl:
		if(waserror()){
			if(sdev != nil)
				decref(&sdev->r);
			nexterror();
		}
		if(ifc->wtopctl != nil)
			(*ifc->wtopctl)(sdev, cb);
		else
			error(Ebadctl);
		if(sdev != nil)
			decref(&sdev->r);
		poperror();
		poperror();
		free(cb);
		break;

	case Qctl:
		cb = parsecmd(a, n);
		unit = c->aux;
		qlock(&unit->ctl);
		if(waserror()){
			qunlock(&unit->ctl);
			free(cb);
			nexterror();
		}
		if(unit->vers != c->qid.vers)
			error(Echange);

		if(cb->nf < 1)
			error(Ebadctl);
		if(strcmp(cb->f[0], "part") == 0){
			if(cb->nf != 4)
				error(Ebadctl);
			if(unit->sectors == 0 && !sdinitpart(unit))
				error(Eio);
			start = strtoull(cb->f[2], 0, 0);
			end = strtoull(cb->f[3], 0, 0);
			sdaddpart(unit, cb->f[1], start, end);
		}
		else if(strcmp(cb->f[0], "delpart") == 0){
			if(cb->nf != 2 || unit->part == nil)
				error(Ebadctl);
			sddelpart(unit, cb->f[1]);
		}
		else if(unit->dev->ifc->wctl != nil)
			(*unit->dev->ifc->wctl)(unit, cb);
		else
			error(Ebadctl);
		qunlock(&unit->ctl);
		poperror();
		free(cb);
		break;

	case Qraw:
		proto = SDcdb;
		ataproto = 0;
		atacdb = 0;
		unit = c->aux;
		qlock(&unit->raw);
		if(waserror()){
			qunlock(&unit->raw);
			nexterror();
		}
		switch(unit->state){
		case Rawcmd:
			/* sneaky ata commands */
			u = a;
			if(n > 1 && *u == 0xff){
				proto = SData;
				ataproto = u[1];
				a = u + 2;
				atacdb = Ahdrsz;
				n -= Ahdrsz;
			}		
			if(n < 6 || n > sizeof(req->cmd))
				error(Ebadarg);
			req = smalloc(sizeof(SDreq));
			req->unit = unit;
			if(waserror()){
				free(req);
				nexterror();
			}
			memmove(req->cmd, a, n);
			poperror();
			req->clen = n;
		/*	req->flags = SDnosense;	*/
			req->status = ~0;
			req->proto = proto;
			req->ataproto = ataproto;
			unit->req = req;
			unit->state = Rawdata;
			n += atacdb;
			break;

		case Rawstatus:
			unit->state = Rawcmd;
			free(unit->req);
			unit->req = nil;
			error(Ebadusefd);

		case Rawdata:
			unit->state = Rawstatus;
			req = unit->req;
			req->write = 1;
			n = sdrio(req, a, n);
		}
		qunlock(&unit->raw);
		poperror();
		break;
	case Qpart:
		return sdbio(c, 1, a, n, off);
	case Qextra:
		return extrarw(c, 1, a, n, off);
	}

	return n;
}

static int
sdwstat(Chan* c, uchar* dp, int n)
{
	Dir *d;
	SDpart *pp;
	SDperm *perm;
	SDunit *unit;
	SDev *sdev;

	if(c->qid.type & QTDIR)
		error(Eperm);
	if(TYPE(c->qid) == Qtopctl){
		unit = &topctlunit;
		sdev = nil;
	}else{
		sdev = sdgetdev(DEV(c->qid));
		if(sdev == nil)
			error(Enonexist);
		unit = sdev->unit[UNIT(c->qid)];
	}
	qlock(&unit->ctl);
	if(waserror()){
		qunlock(&unit->ctl);
		if(sdev != nil)
			decref(&sdev->r);
		nexterror();
	}

	switch(TYPE(c->qid)){
	default:
		error(Eperm);
	case Qtopctl:
	case Qctl:
		perm = &unit->ctlperm;
		break;
	case Qraw:
		perm = &unit->rawperm;
		break;
	case Qpart:
		pp = &unit->part[PART(c->qid)];
		if(unit->vers+pp->vers != c->qid.vers)
			error(Enonexist);
		perm = &pp->SDperm;
		break;
	}

	if(strcmp(up->user, perm->user) && !iseve())
		error(Eperm);

	d = smalloc(sizeof(Dir)+n);
	if(waserror()){
		free(d);
		nexterror();
	}
	n = convM2D(dp, n, &d[0], (char*)&d[1]);
	if(n == 0)
		error(Eshortstat);
	if(d->atime != ~0 ||  d->mtime  != ~0 ||  d->length  != ~0)
		error(Eperm);
	if(!emptystr(d[0].muid) || !emptystr(d[0].name))
		error(Eperm);
	if(!emptystr(d[0].gid) && strcmp(d[0].gid, eve) != 0)
		error(Eperm);
	/* committed */
	if(!emptystr(d[0].uid))
		kstrdup(&perm->user, d[0].uid);
	if(d[0].mode != ~0UL)
		perm->perm = (perm->perm & ~0777) | (d[0].mode & 0777);
	qunlock(&unit->ctl);
	if(sdev != nil)
		decref(&sdev->r);
	free(d);
	poperror();
	poperror();
	return n;
}

static int
configure(char* spec, DevConf* cf)
{
	SDev *s, *sdev;
	char *p;
	int i;

	if(sdindex(*spec) < 0)
		error("bad sd spec");

	if((p = strchr(cf->type, '/')) != nil)
		*p++ = '\0';

	for(i = 0; sdifc[i] != nil; i++)
		if(strcmp(sdifc[i]->name, cf->type) == 0)
			break;
	if(sdifc[i] == nil)
		error("sd type not found");
	if(p != nil)
		*(p-1) = '/';

	if(sdifc[i]->probe == nil)
		error("sd type cannot probe");

	sdev = sdifc[i]->probe(cf);
	for(s = sdev; s != nil; s = s->next)
		s->idno = *spec;
	sdadddevs(sdev);
	return 0;
}

static int
unconfigure(char* spec)
{
	int i;
	SDev *sdev;

	if((i = sdindex(*spec)) < 0)
		error(Enonexist);

	qlock(&sddevslock);
	if((sdev = sddevs[i]) == nil){
		qunlock(&sddevslock);
		error(Enonexist);
	}
	if(sdev->r.ref){
		qunlock(&sddevslock);
		error(Einuse);
	}
	sddevs[i] = nil;
	qunlock(&sddevslock);

	/* make sure no interrupts arrive anymore before removing resources */
	if(sdev->enabled && sdev->ifc->disable != nil)
		(*sdev->ifc->disable)(sdev);

	/* free controller specific info */
	if(sdev->ifc->clear != nil)
		(*sdev->ifc->clear)(sdev);

	sdfreedev(sdev);

	return 0;
}

static int
sdconfig(int on, char* spec, DevConf* cf)
{
	if(on)
		return configure(spec, cf);
	return unconfigure(spec);
}

static void
sdshutdown(void)
{
	int i;
	SDev *sdev;

	for(i = 0; i < nelem(sddevs); i++){
		sdev = sddevs[i];
		if(sdev == nil)
			continue;
		if(sdev->ifc->disable == nil){
			print("#S/sd%c: no disable function\n", sddevletters[i]);
			continue;
		}
		(*sdev->ifc->disable)(sdev);
	}
}

/*
 *  find a SDdev, make sure its enabled and free it,
 *  returning its controller. This is used by
 *  annexsdio() to take over sdio from devsd.
 */
void*
sdannexctlr(char *spec, SDifc *ifc)
{
	int i;
	SDev *sdev;
	void *ctlr;

	if((i = sdindex(*spec)) < 0)
		error(Enonexist);

	qlock(&sddevslock);
	if((sdev = sddevs[i]) == nil){
		qunlock(&sddevslock);
		error(Enonexist);
	}
	if(sdev->ifc != ifc){
		qunlock(&sddevslock);
		error(Enonexist);
	}
	if(sdev->r.ref){
		qunlock(&sddevslock);
		error(Einuse);
	}
	sddevs[i] = nil;
	qunlock(&sddevslock);

	if(!sdev->enabled && ifc->enable != nil)
		(*ifc->enable)(sdev);

	ctlr = sdev->ctlr;
	sdfreedev(sdev);

	return ctlr;
}

Dev sddevtab = {
	'S',
	"sd",

	sdreset,
	devinit,
	sdshutdown,
	sdattach,
	sdwalk,
	sdstat,
	sdopen,
	devcreate,
	sdclose,
	sdread,
	devbread,
	sdwrite,
	devbwrite,
	devremove,
	sdwstat,
	devpower,
	sdconfig,
};

/*
 * This is wrong for so many reasons.  This code must go.
 */
typedef struct Confdata Confdata;
struct Confdata {
	int	on;
	char*	spec;
	DevConf	cf;
};

static void
parseswitch(Confdata* cd, char* option)
{
	if(!strcmp("on", option))
		cd->on = 1;
	else if(!strcmp("off", option))
		cd->on = 0;
	else
		error(Ebadarg);
}

static void
parsespec(Confdata* cd, char* option)
{
	if(strlen(option) > 1)
		error(Ebadarg);
	cd->spec = option;
}

static Devport*
getnewport(DevConf* dc)
{
	Devport *p;

	p = malloc((dc->nports + 1) * sizeof(Devport));
	if(p == nil)
		panic("sd: no memory for Devport");
	if(dc->nports > 0){
		memmove(p, dc->ports, dc->nports * sizeof(Devport));
		free(dc->ports);
	}
	dc->ports = p;
	p = &dc->ports[dc->nports++];
	p->size = -1;
	p->port = (ulong)-1;
	return p;
}

static void
parseport(Confdata* cd, char* option)
{
	char *e;
	Devport *p;

	if(cd->cf.nports == 0 || cd->cf.ports[cd->cf.nports-1].port != (ulong)-1)
		p = getnewport(&cd->cf);
	else
		p = &cd->cf.ports[cd->cf.nports-1];
	p->port = strtol(option, &e, 0);
	if(e == nil || *e != '\0')
		error(Ebadarg);
}

static void
parsesize(Confdata* cd, char* option)
{
	char *e;
	Devport *p;

	if(cd->cf.nports == 0 || cd->cf.ports[cd->cf.nports-1].size != -1)
		p = getnewport(&cd->cf);
	else
		p = &cd->cf.ports[cd->cf.nports-1];
	p->size = (int)strtol(option, &e, 0);
	if(e == nil || *e != '\0')
		error(Ebadarg);
}

static void
parseirq(Confdata* cd, char* option)
{
	char *e;

	cd->cf.intnum = strtoul(option, &e, 0);
	if(e == nil || *e != '\0')
		error(Ebadarg);
}

static void
parsetype(Confdata* cd, char* option)
{
	cd->cf.type = option;
}

static struct {
	char	*name;
	void	(*parse)(Confdata*, char*);
} options[] = {
	"switch",	parseswitch,
	"spec",		parsespec,
	"port",		parseport,
	"size",		parsesize,
	"irq",		parseirq,
	"type",		parsetype,
};

static void
legacytopctl(Cmdbuf *cb)
{
	char *opt;
	int i, j;
	Confdata cd;

	memset(&cd, 0, sizeof cd);
	cd.on = -1;
	for(i=0; i<cb->nf; i+=2){
		if(i+2 > cb->nf)
			error(Ebadarg);
		opt = cb->f[i];
		for(j=0; j<nelem(options); j++)
			if(strcmp(opt, options[j].name) == 0){
				options[j].parse(&cd, cb->f[i+1]);
				break;
			}
		if(j == nelem(options))
			error(Ebadarg);
	}
	if(cd.on < 0 || cd.spec == 0)
		error(Ebadarg);
	if(cd.on && cd.cf.type == nil)
		error(Ebadarg);
	sdconfig(cd.on, cd.spec, &cd.cf);
}
