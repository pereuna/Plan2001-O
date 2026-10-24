/*
 * E7.7 native-only route table.
 *
 * Generated from iproute.c with the E7_IPV6_ONLY branches selected: V4
 * lookup/source and the legacy #I route-file parser are absent.  Legacy
 * profiles still link iproute.c.
 */
#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"

#include	"ip.h"

static void	walkadd(Fs*, Route**, Route*);
static void	addnode(Fs*, Route**, Route*);
static void	calcd(Route*);

/* these are used for all instances of IP */
static Route*	v4freelist;
static Route*	v6freelist;
static RWLock	routelock;
static ulong	v4routegeneration, v6routegeneration;

static void
freeroute(Route *r)
{
	Route **l;

	r->ref = 0;
	r->left = nil;
	r->right = nil;
	if(r->type & Rv4)
		l = &v4freelist;
	else
		l = &v6freelist;
	r->mid = *l;
	*l = r;
}

static Route*
allocroute(int type)
{
	Route *r, **l;
	int n;

	if(type & Rv4){
		n = sizeof(RouteTree) + sizeof(V4route);
		l = &v4freelist;
	} else {
		n = sizeof(RouteTree) + sizeof(V6route);
		l = &v6freelist;
	}

	if((r = *l) != nil)
		*l = r->mid;
	else
		r = smalloc(n);
	memset(r, 0, n);
	r->type = type;
	r->ifc = nil;
	r->ref = 1;

	return r;
}

static void
addqueue(Route **q, Route *r)
{
	Route *l;

	if(r == nil)
		return;

	l = allocroute(r->type);
	l->left = r;
	l->mid = *q;
	*q = l;
}

/*
 *   compare 2 v6 addresses
 */
static int
lcmp(ulong *a, ulong *b)
{
	int i;

	for(i = 0; i < IPllen; i++){
		if(a[i] > b[i])
			return 1;
		if(a[i] < b[i])
			return -1;
	}
	return 0;
}

/*
 *  compare 2 v4 or v6 ranges
 */
enum
{
	Rpreceeds,	/* a left of b */
	Rfollows,	/* a right of b */
	Requals,	/* a equals b */
	Rcontains,	/* a contians b */
	Roverlaps,	/* a overlaps b */
};

static int
rangecompare(Route *a, Route *b)
{
	if(a->type & Rv4){
		if(a->v4.endaddress < b->v4.address)
			return Rpreceeds;
		if(a->v4.address > b->v4.endaddress)
			return Rfollows;
		if(a->v4.address <= b->v4.address
		&& a->v4.endaddress >= b->v4.endaddress){
			if(a->v4.address == b->v4.address
			&& a->v4.endaddress == b->v4.endaddress){
				if(a->v4.source <= b->v4.source
				&& a->v4.endsource >= b->v4.endsource){
					if(a->v4.source == b->v4.source
					&& a->v4.endsource == b->v4.endsource)
						return Requals;
					return Rcontains;
				}
				return Roverlaps;
			}
			return Rcontains;
		}
		return Roverlaps;
	}

	if(lcmp(a->v6.endaddress, b->v6.address) < 0)
		return Rpreceeds;
	if(lcmp(a->v6.address, b->v6.endaddress) > 0)
		return Rfollows;
	if(lcmp(a->v6.address, b->v6.address) <= 0
	&& lcmp(a->v6.endaddress, b->v6.endaddress) >= 0){
		if(lcmp(a->v6.address, b->v6.address) == 0
		&& lcmp(a->v6.endaddress, b->v6.endaddress) == 0){
			if(lcmp(a->v6.source, b->v6.source) <= 0
			&& lcmp(a->v6.endsource, b->v6.endsource) >= 0){
				if(lcmp(a->v6.source, b->v6.source) == 0
				&& lcmp(a->v6.endsource, b->v6.endsource) == 0)
					return Requals;
				return Rcontains;
			}
			return Roverlaps;
		}
		return Rcontains;
	}
	return Roverlaps;
}

/* return 1 if a matches b, otherwise 0 */
static int
matchroute(Route *a, Route *b)
{
	if(a == b)
		return 1;

	if((a->type^b->type) & (Rifc|Runi|Rmulti|Rbcast))
		return 0;

	if(a->type & Rv4){
		if(memcmp(a->v4.gate, IPnoaddr+IPv4off, IPv4addrlen) != 0
		&& memcmp(a->v4.gate, b->v4.gate, IPv4addrlen) != 0)
			return 0;
	} else {
		if(ipcmp(a->v6.gate, IPnoaddr) != 0
		&& ipcmp(a->v6.gate, b->v6.gate) != 0)
			return 0;
	}

	if(a->ifc != b->ifc)
		return 0;

	if(*a->tag != 0 && strncmp(a->tag, b->tag, sizeof(a->tag)) != 0)
		return 0;

	return 1;
}

static void
copygate(Route *old, Route *new)
{
	old->type = new->type;
	old->ifc = new->ifc;
	old->ifcid = new->ifcid;
	if(new->type & Rv4)
		memmove(old->v4.gate, new->v4.gate, IPv4addrlen);
	else
		ipmove(old->v6.gate, new->v6.gate);
	strncpy(old->tag, new->tag, sizeof(new->tag));
}

/*
 *  walk down a tree adding nodes back in
 */
static void
walkadd(Fs *f, Route **root, Route *p)
{
	Route *l, *r;

	l = p->left;
	r = p->right;
	p->left = nil;
	p->right = nil;
	addnode(f, root, p);
	if(l != nil)
		walkadd(f, root, l);
	if(r != nil)
		walkadd(f, root, r);
}

/*
 *  calculate depth
 */
static void
calcd(Route *p)
{
	Route *q;
	int d;

	if(p != nil) {
		d = 0;
		q = p->left;
		if(q != nil)
			d = q->depth;
		q = p->right;
		if(q != nil && q->depth > d)
			d = q->depth;
		q = p->mid;
		if(q != nil && q->depth > d)
			d = q->depth;
		p->depth = d+1;
	}
}

/*
 *  balance the tree at the current node
 */
static void
balancetree(Route **cur)
{
	Route *p, *l, *r;
	int dl, dr;

	/*
	 * if left and right are
	 * too out of balance,
	 * rotate tree node
	 */
	p = *cur;
	dl = 0; if((l = p->left) != nil) dl = l->depth;
	dr = 0; if((r = p->right) != nil) dr = r->depth;

	if(dl > dr+1) {
		p->left = l->right;
		l->right = p;
		*cur = l;
		calcd(p);
		calcd(l);
	} else
	if(dr > dl+1) {
		p->right = r->left;
		r->left = p;
		*cur = r;
		calcd(p);
		calcd(r);
	} else
		calcd(p);
}

/*
 *  add a new node to the tree
 */
static void
addnode(Fs *f, Route **cur, Route *new)
{
	Route *p;

	p = *cur;
	if(p == nil) {
		*cur = new;
		new->depth = 1;
		return;
	}

	switch(rangecompare(new, p)){
	case Rpreceeds:
		addnode(f, &p->left, new);
		break;
	case Rfollows:
		addnode(f, &p->right, new);
		break;
	case Rcontains:
		/*
		 *  if new node is superset
		 *  of tree node,
		 *  replace tree node and
		 *  queue tree node to be
		 *  merged into root.
		 */
		*cur = new;
		new->depth = 1;
		addqueue(&f->queue, p);
		break;
	case Requals:
		/*
		 *  supercede the old entry if the old one isn't
		 *  a local interface.
		 */
		if((p->type & Rifc) == 0)
			copygate(p, new);
		else if(new->type & Rifc){
			p->type = (p->type & ~(Rproxy|Rtrans)) | (new->type & (Rproxy|Rtrans));
			p->ref++;
		}
		freeroute(new);
		break;
	case Roverlaps:
		addnode(f, &p->mid, new);
		break;
	}
	
	balancetree(cur);
}

/*
 *  find node matching r
 */
static Route**
looknode(Route **cur, Route *r)
{
	Route *p;

	for(;;){
		p = *cur;
		if(p == nil)
			return nil;
		switch(rangecompare(r, p)){
		case Rcontains:
			return nil;
		case Rpreceeds:
			cur = &p->left;
			break;
		case Rfollows:
			cur = &p->right;
			break;
		case Roverlaps:
			cur = &p->mid;
			break;
		case Requals:
			if((p->type & Rifc) == 0 && !matchroute(r, p))
				return nil;
			return cur;
		}
	}
}

static Route*
looknodematch(Route *r, int (*match)(Route*, void*), void *arg)
{
	Route *x;

	if(r == nil)
		return nil;
	if((x = looknodematch(r->mid, match, arg)) != nil)
		return x;
	if((x = looknodematch(r->left, match, arg)) != nil)
		return x;
	if((x = looknodematch(r->right, match, arg)) != nil)
		return x;
	if((*match)(r, arg))
		return r;
	return nil;
}

static int
matchtag(Route *r, void *arg)
{
	char *tag = (char*)arg;

	if(r->type & Rifc)
		return 0;
	return tag == nil || strncmp(tag, r->tag, sizeof(r->tag)) == 0;
}

static int
matchifc(Route *r, void *arg)
{
	Ipifc *ifc = (Ipifc*)arg;

	return r->ifc == ifc;
}


#define	V4H(a)	((a&0x07ffffff)>>(32-Lroot-5))
#define	V6H(a)	(((a)[0]&0x80000000)>>(32-Lroot) | ((a)[(IPllen/2)-1]&(0xffff>>(16-Lroot))))

static void
routeadd(Fs *f, Route *r)
{
	Route **h, **e, *p, *q;
	if(r->type & Rv4)
		return;

	{
		h = &f->v6root[V6H(r->v6.address)];
		e = &f->v6root[V6H(r->v6.endaddress)];
	}

	for(; h <= e; h++) {
		p = allocroute(r->type);

		p->ifc = r->ifc;
		p->ifcid = r->ifcid;

			memmove(&p->v6, &r->v6, sizeof(r->v6));

		memmove(p->tag, r->tag, sizeof(r->tag));

		addnode(f, h, p);
		while((p = f->queue) != nil) {
			f->queue = p->mid;
			q = p->left;
			freeroute(p);
			walkadd(f, h, q);
		}
	}

		v6routegeneration++;
}

static void
routedel(Fs *f, Route *r)
{
	Route **h, **e, **l, *p, *q;
	if(r->type & Rv4)
		return;

	{
		h = &f->v6root[V6H(r->v6.address)];
		e = &f->v6root[V6H(r->v6.endaddress)];
	}

	for(; h <= e; h++) {
		if((l = looknode(h, r)) == nil)
			continue;
		p = *l;
		if(--(p->ref) != 0)
			continue;
		*l = nil;
		addqueue(&f->queue, p->left);
		addqueue(&f->queue, p->mid);
		addqueue(&f->queue, p->right);
		freeroute(p);

		while((p = f->queue) != nil) {
			f->queue = p->mid;
			q = p->left;
			freeroute(p);
			walkadd(f, h, q);
		}
	}

		v6routegeneration++;
}

static Route
mkroute(uchar *a, uchar *mask, uchar *s, uchar *smask, uchar *gate, int type, Ipifc *ifc, uchar ifcid, char *tag)
{
	ulong x, y;
	Route r;
	int h;

	assert(ifc != nil);

	memset(&r, 0, sizeof(r));

	r.type = type;
	r.ifc = ifc;
	r.ifcid = ifcid;

	if(type & Rv4)
		panic("mkroute: ipv4 disabled");
	{
		for(h = 0; h < IPllen; h++){
			x = nhgetl(a+4*h);
			y = nhgetl(mask+4*h);
			r.v6.address[h] = x & y;
			r.v6.endaddress[h] = x | ~y;

			x = nhgetl(s+4*h);
			y = nhgetl(smask+4*h);
			if(y != 0)
				r.type |= Rsrc;
			r.v6.source[h] = x & y;
			r.v6.endsource[h] = x | ~y;
		}

		memmove(r.v6.gate, gate, IPaddrlen);
	}

	if(tag != nil)
		strncpy(r.tag, tag, sizeof(r.tag));

	return r;
}

void
addroute(Fs *f, uchar *a, uchar *mask, uchar *s, uchar *smask, uchar *gate, int type, Ipifc *ifc, char *tag)
{
	Route r = mkroute(a, mask, s, smask, gate, type, ifc, ifc->ifcid, tag);
	wlock(&routelock);
	routeadd(f, &r);
	wunlock(&routelock);
}

void
delroute(Fs *f, uchar *a, uchar *mask, uchar *s, uchar *smask, uchar *gate, int type, Ipifc *ifc, char *tag)
{
	Route r = mkroute(a, mask, s, smask, gate, type, ifc, ifc->ifcid, tag);
	wlock(&routelock);
	routedel(f, &r);
	wunlock(&routelock);
}

static void
flushroutematch(Fs *f, int (*match)(Route*, void*), void *arg)
{
	Route r, *x;
	int h;

	wlock(&routelock);
	for(h = 0; h < nelem(f->v6root); h++)
		while((x = looknodematch(f->v6root[h], match, arg)) != nil){
			memmove(&r, x, sizeof(RouteTree) + sizeof(V6route));
			routedel(f, &r);
		}
	wunlock(&routelock);
}

/*
 * flushrouteifc:
 *   remove all routes associated with ifc (wlock()'ed).
 */
void
flushrouteifc(Fs *f, Ipifc *ifc)
{
	flushroutematch(f, matchifc, ifc);
	ifc->ifcid++;	/* invalidate all routes */
}

/*
 * v4lookup, v6lookup:
 *  lookup a route to destination address a from source address s
 *  and return the route. returns nil if no route was found.
 *  an optional Routehint can be passed in rh to cache the lookup.
 *
 *  for v4lookup, addresses are in 4 byte format.
 */
/*
 * Plan2001: skip, if not nil, is a medium whose interfaces the route must
 * not go out of - a tunnel's own (outer) packets must not be routed into
 * it (#W, ip/devwg.c).  The route found is left in rh, for ipoput4/6.
 */

static Route*
v6lookup0(Fs *f, uchar *a, uchar *s, Routehint *rh, Medium *skip)
{
	ulong la[IPllen], ls[IPllen];
	ulong x, y;
	Route *p, *q;
	Ipifc *ifc;
	int h;

	if(isv4(s))
		return nil;

	if(skip == nil && rh != nil
	&& rh->rgen == v6routegeneration
	&& (q = rh->r) != nil
	&& (ifc = q->ifc) != nil
	&& q->ifcid == ifc->ifcid
	&& q->ref > 0)
		return q;

	q = nil;
	for(h = 0; h < IPllen; h++){
		la[h] = nhgetl(a+4*h);
		ls[h] = nhgetl(s+4*h);
	}

	rlock(&routelock);
	for(p = f->v6root[V6H(la)]; p != nil;){
		for(h = 0; h < IPllen; h++){
			x = la[h];
			y = p->v6.address[h];
			if(x == y)
				continue;
			if(x < y){
				p = p->left;
				goto next;
			}
			break;
		}
		for(h = 0; h < IPllen; h++){
			x = la[h];
			y = p->v6.endaddress[h];
			if(x == y)
				continue;
			if(x > y){
				p = p->right;
				goto next;
			}
			break;
		}
		if((p->type & Rsrc) && (skip == nil || ipcmp(s, IPnoaddr) != 0)){
			for(h = 0; h < IPllen; h++){
				x = ls[h];
				y = p->v6.source[h];
				if(x == y)
					continue;
				if(x < y){
					p = p->mid;
					goto next;
				}
				break;
			}
			for(h = 0; h < IPllen; h++){
				x = ls[h];
				y = p->v6.endsource[h];
				if(x == y)
					continue;
				if(x > y){
					p = p->mid;
					goto next;
				}
				break;
			}
		}
		if(skip == nil || p->ifc == nil || p->ifc->m != skip)
			q = p;
		p = p->mid;
next:		;
	}
	if(rh != nil){
		rh->r = q;
		rh->rgen = v6routegeneration;
	}
	runlock(&routelock);
	return q;
}

Route*
v6lookup(Fs *f, uchar *a, uchar *s, Routehint *rh)
{
	return v6lookup0(f, a, s, rh, nil);
}

Route*
v6lookupskip(Fs *f, uchar *a, uchar *s, Routehint *rh, Medium *skip)
{
	return v6lookup0(f, a, s, rh, skip);
}

/*
 * v4source, v6source:
 *  lookup a route to destination address a and also find
 *  a suitable source address s on the outgoing interface.
 *  return the route on success or nil when no route
 *  was found.
 *
 *  for v4source, addresses are in 4 byte format.
 */

Route*
v6source(Fs *f, uchar *a, uchar *s)
{
	uchar src[IPaddrlen];
	int splen, h;
	ulong x, y, la[IPllen];
	Route *p, *q;
	Ipifc *ifc;

	for(h = 0; h < IPllen; h++)
		la[h] = nhgetl(a+4*h);
again:
	q = nil;
	rlock(&routelock);
	for(p = f->v6root[V6H(la)]; p != nil;){
		for(h = 0; h < IPllen; h++){
			x = la[h];
			y = p->v6.address[h];
			if(x == y)
				continue;
			if(x < y){
				p = p->left;
				goto next;
			}
			break;
		}
		for(h = 0; h < IPllen; h++){
			x = la[h];
			y = p->v6.endaddress[h];
			if(x == y)
				continue;
			if(x > y){
				p = p->right;
				goto next;
			}
			break;
		}
		ifc = p->ifc;
		if(!canrlock(ifc)){
			int gen = v6routegeneration;
			runlock(&routelock);
			rlock(ifc);
			rlock(&routelock);
			if(v6routegeneration != gen){
				runlock(&routelock);
				runlock(ifc);
				goto again;
			}
		}
		splen = 0;
		if(p->type & Rsrc){
			/* calculate local prefix length for source specific routes */
			for(h = 0; h < IPllen; h++){
				hnputl(src+4*h, p->v6.source[h]);
				if((x = ~(p->v6.endsource[h] ^ p->v6.source[h])) != ~0UL){
					for(; x & 0x80000000UL; x <<= 1)
						splen++;
					break;
				}
				splen += 32;
			}
		}
		if(!ipv6local(ifc, src, splen, a)){
			runlock(ifc);
			p = p->mid;
			continue;
		}
		ipmove(s, src);
		runlock(ifc);
		q = p;
		p = p->mid;
next:		;
	}
	runlock(&routelock);
	return q;
}

