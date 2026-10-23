/*
 * LEGACY FS/9P IMPLEMENTATION (#G): inherited GEFS root filesystem.
 * This path remains for compatibility and bootstrap tests; it is not the
 * native GE/O object interface (sysovolopen/sysospace* below).
 * gefs runs as kprocs and serves 9P on a pipe; rootmount mounts
 * the other end before / for plan9.ini's root=:
 *
 *	root=-w PARTUUID=guid		its tree main
 *	root=-w #S/sdE0/data!adm	another tree (snapshot label)
 *
 * A PARTUUID is looked for on the disks of #S: each GPT partition, read
 * from the disk's data file, so no partitions need be set up.  The
 * console (halt, check, show) is /srv/gefs.root.cmd, which fshalt halts.
 * /srv/gefs.root is its 9P (eve's): mount it with a tree's name (mount
 * /srv/gefs.root /n/adm adm), whose ctl file makes snapshots.  The device
 * has nothing of its own but the shutdown: at reboot gefs is halted
 * (synced).
 */
#include "u.h"
#include "../port/lib.h"
#include "mem.h"
#include "dat.h"
#include "fns.h"
#include "../port/error.h"
#include "../port/sd.h"

/*
 * Plan2001: a GE instance (../gefs, GE engine per-volume instance model (sys/src/9/gefs/kern.c)) is opaque here:
 * its type is gefs.h's, and 6c's cross-module signatures differ for an
 * incomplete struct, so the handle is a void*.
 */
Chan*	gefsserve(char*, Chan*, vlong, vlong, int, char*, void**);
void	gefspost(Chan*, char*);
void	gefsshutdown(void*);
void*	geopen(char*, Chan*, vlong, vlong, int);
void	gestart(void*);
void	geprobe(void*);
void*	oopen(char*, Chan*, vlong, vlong, int);
void*	oopenblk(char*, void*, vlong, vlong, int,
		long (*)(void*, void*, long, uvlong, int), int (*)(void*));
void	oprobe(void*);
void	oobjprobe(void*);
typedef struct Gefs Gefs;
typedef struct Ospace Ospace;
typedef struct Oblock Oblock;
struct Oblock {
	SDunit	*unit;
	vlong	start;		/* partition byte offset in the unit */
	vlong	size;		/* partition bytes, for bounds */
};
extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;
void*	onativeopen(void*, char*);
long	onativeget(void*, uvlong, void*, long, uvlong*);
void	onativeput(void*, uvlong, void*, long);
long	onativecreate(void*, void*, long, uvlong*);
uvlong	onativecommit(void*);
void	onativeclose(void*);

/*
 * Plan2001: the volumes this device has started, for the shutdown at
 * reboot.  Each is an independent GE instance with its own device,
 * console and allocation state (GE engine per-volume instance model (sys/src/9/gefs/kern.c)); the root's is the
 * first.
 */
enum {
	Maxvols	= 4,
};

static void *vols[Maxvols];
static int nvols;

static void
addvol(void *g)
{
	int i;

	for(i = 0; i < nvols; i++)
		if(vols[i] == g)
			return;
	if(nvols == Maxvols)
		error("gefs: too many volumes");
	vols[nvols++] = g;
}

static void
gefsdevshutdown(void)
{
	int i;

	for(i = 0; i < nvols; i++)
		gefsshutdown(vols[i]);
}

/* Has c, at off, gefs's superblock? */
static int
isgefs(Chan *c, vlong off)
{
	char sb[8];

	if(waserror())
		return 0;
	if(devtab[c->type]->read(c, sb, sizeof sb, off) != sizeof sb)
		error(Eio);
	poperror();
	return memcmp(sb, "gefs9.00", 8) == 0;
}

static uvlong
le(uchar *p, int n)
{
	uvlong v;

	v = 0;
	while(n-- > 0)
		v = v<<8 | p[n];
	return v;
}

/* "1b2c..." from a GPT GUID: its first three fields little-endian */
static void
guidstr(char *s, uchar *u)
{
	snprint(s, 37, "%.2ux%.2ux%.2ux%.2ux-%.2ux%.2ux-%.2ux%.2ux-%.2ux%.2ux-%.2ux%.2ux%.2ux%.2ux%.2ux%.2ux",
		u[3], u[2], u[1], u[0], u[5], u[4], u[7], u[6],
		u[8], u[9], u[10], u[11], u[12], u[13], u[14], u[15]);
}

/*
 * The disk c's GPT partition guid: its offset and size; 0 if none.
 * Logical blocks of 512 or 4096 bytes, as the header is found.
 */
static int
gptpart(Chan *c, char *guid, vlong *off, vlong *size)
{
	uchar h[92], *e, *ents;
	char s[37];
	vlong lb, elba;
	ulong ne, esz;
	int i, bs, found;

	bs = 0;
	for(lb = 512; lb <= 4096; lb *= 8){
		if(devtab[c->type]->read(c, h, sizeof h, lb) == sizeof h && memcmp(h, "EFI PART", 8) == 0){
			bs = lb;
			break;
		}
	}
	if(bs == 0)
		return 0;
	elba = le(h+72, 8);
	ne = le(h+80, 4);
	esz = le(h+84, 4);
	if(esz < 128 || esz > 1024 || ne == 0 || ne > 1024)
		return 0;
	ents = smalloc(ne*esz);
	if(waserror()){
		free(ents);
		return 0;
	}
	if(devtab[c->type]->read(c, ents, ne*esz, elba*bs) != ne*esz)
		error(Eio);
	poperror();
	found = 0;
	for(i = 0; i < ne && !found; i++){
		e = ents + i*esz;
		if(le(e, 8) == 0 && le(e+8, 8) == 0)	/* unused */
			continue;
		guidstr(s, e+16);
		if(cistrcmp(s, guid) == 0){
			*off = le(e+32, 8)*bs;
			*size = (le(e+40, 8) - le(e+32, 8) + 1)*bs;
			found = 1;
		}
	}
	free(ents);
	return found;
}

/*
 * Plan2001: the same GPT parse over a native SD unit, with no Chan and
 * no #S path.  The unit is read at absolute byte offsets; off and size
 * are the matching partition's bounds or nil if it is absent/malformed.
 */
static long
oblockrw(void *v, void *buf, long n, uvlong off, int write)
{
	Oblock *b;
	uvlong end;

	b = v;
	end = b->size;
	if(off > end || n < 0 || (uvlong)n > end - off){
		if(write)
			error(Eio);
		return 0;
	}
	if(n == 0)
		return 0;
	return sdblockrw(b->unit, write, buf, n, b->start + off);
}

static int
oblockflush(void *v)
{
	Oblock *b;

	b = v;
	return sdblockflush(b->unit);
}

static int
oblockgptpart(Oblock *b, char *guid, vlong *off, vlong *size)
{
	uchar h[92], *e, *ents;
	char s[37];
	vlong lb, elba;
	ulong ne, esz;
	int i, bs, found;
	uvlong first, last;

	bs = 0;
	for(lb = 512; lb <= 4096; lb *= 8){
		if(oblockrw(b, h, sizeof h, lb, 0) == sizeof h && memcmp(h, "EFI PART", 8) == 0){
			bs = lb;
			break;
		}
	}
	if(bs == 0)
		return 0;
	elba = le(h+72, 8);
	ne = le(h+80, 4);
	esz = le(h+84, 4);
	if(esz < 128 || esz > 1024 || ne == 0 || ne > 1024)
		return 0;
	ents = smalloc(ne*esz);
	if(waserror()){
		free(ents);
		return 0;
	}
	if(oblockrw(b, ents, ne*esz, elba*bs, 0) != ne*esz)
		error(Eio);
	poperror();
	found = 0;
	for(i = 0; i < ne && !found; i++){
		e = ents + i*esz;
		if(le(e, 8) == 0 && le(e+8, 8) == 0)
			continue;
		guidstr(s, e+16);
		if(cistrcmp(s, guid) == 0){
			first = le(e+32, 8);
			last = le(e+40, 8);
			if(last < first || last >= b->unit->sectors)
				continue;
			*off = first*bs;
			*size = (last - first + 1)*bs;
			found = 1;
		}
	}
	free(ents);
	return found;
}

static Oblock*
oblockopenpart(char *guid, char *dev, int ndev, vlong *off, vlong *size)
{
	Sditer it;
	SDunit *unit;
	Oblock *b;

	memset(&it, 0, sizeof it);
	while((unit = sdunititer(&it)) != nil){
		if(!sdunitready(unit)){
			sdunitput(unit);
			continue;
		}
		if((b = mallocz(sizeof *b, 1)) == nil){
			sdunitput(unit);
			error(Enomem);
		}
		b->unit = unit;
		b->start = 0;
		b->size = (uvlong)unit->sectors * unit->secsize;
		if(oblockgptpart(b, guid, off, size)){
			b->start = *off;
			b->size = *size;
			snprint(dev, ndev, "#S/%s/data", unit->name);
			return b;
		}
		free(b);
		sdunitput(unit);
	}
	return nil;
}

/* The disk of #S (#S/sdXX/data, in dev) with the partition guid */
static int
scandisks(char *guid, char *dev, int ndev, vlong *off, vlong *size)
{
	Chan *top, *c;
	uchar *buf;
	Dir d;
	char strs[256];
	vlong doff;
	long n, m;
	int i, found;

	found = 0;
	top = namec("#S", Aopen, OREAD, 0);
	buf = smalloc(8192);
	if(waserror()){
		cclose(top);
		free(buf);
		nexterror();
	}
	doff = 0;
	while(!found && (n = devtab[top->type]->read(top, buf, 8192, doff)) > 0){
		doff += n;
		for(i = 0; !found && i < n; i += m){
			m = BIT16SZ + GBIT16(buf+i);
			if(m > 8192-i || m - STATFIXLEN > sizeof strs || convM2D(buf+i, m, &d, strs) == 0)
				break;
			if(strncmp(d.name, "sd", 2) != 0 || strcmp(d.name, "sdctl") == 0)
				continue;
			snprint(dev, ndev, "#S/%s/data", d.name);
			if(waserror())
				continue;
			c = namec(dev, Aopen, OREAD, 0);
			poperror();
			found = gptpart(c, guid, off, size);
			cclose(c);
		}
	}
	poperror();
	cclose(top);
	free(buf);
	return found;
}

/*
 * root= without -w: DEVICE or PARTUUID=guid, then !tree; mounted
 * before / (the root's /rc and so on, not #/'s empty mount points of
 * those names; #/ gives those it lacks: /dev, /env, ...).
 */
static void
gefsroot(char *spec, int rw)
{
	char *s, *tree, dev[64];
	vlong off, size;
	Chan *c, *m, *r;
	void *v;
	Dir *d;

	s = smalloc(strlen(spec)+1);
	strcpy(s, spec);
	if(waserror()){
		free(s);
		nexterror();
	}
	tree = "main";
	if((spec = strchr(s, '!')) != nil){
		*spec++ = 0;
		if(*spec != 0)
			tree = spec;
	}
	off = 0;
	size = 0;
	if(cistrncmp(s, "PARTUUID=", 9) == 0){
		if(!scandisks(s+9, dev, sizeof dev, &off, &size))
			error("no disk has that partition");
	}else
		kstrcpy(dev, s, sizeof dev);
	c = namec(dev, Aopen, rw ? ORDWR : OREAD, 0);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	if(!isgefs(c, off))
		error("no gefs there");
	if(size == 0){
		d = dirchanstat(c);
		size = d->length;
		free(d);
	}
	m = gefsserve(dev, c, off, size, rw, "#s/gefs.root.cmd", &v);
	addvol(v);
	poperror();	/* c is gefs's now */
	if(!waserror()){
		gefspost(m, "#s/gefs.root");
		poperror();
	}
	r = mntattach(m, nil, tree, 0);
	cclose(m);
	if(waserror()){
		cclose(r);
		nexterror();
	}
	c = namec("/", Amount, 0, 0);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	cmount(r, c, MBEFORE, nil);
	poperror();
	cclose(c);
	poperror();
	cclose(r);
	poperror();
	free(s);
}

/* A GE partition by PARTUUID or device, open (the caller owns c). */
static Chan*
gevolume(char *spec, int rw, char *dev, int ndev, vlong *off, vlong *size)
{
	Chan *c;
	Dir *d;

	*off = 0;
	*size = 0;
	if(cistrncmp(spec, "PARTUUID=", 9) == 0){
		if(!scandisks(spec+9, dev, ndev, off, size))
			error("no disk has that partition");
	}else
		kstrcpy(dev, spec, ndev);
	c = namec(dev, Aopen, rw ? ORDWR : OREAD, 0);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	if(!isgefs(c, *off))
		error("no gefs there");
	if(*size == 0){
		d = dirchanstat(c);
		*size = d->length;
		free(d);
	}
	poperror();
	return c;
}

/*
 * Plan2001 stage 1's gate (docs/POC.md 1): getest=
 * PARTUUID=guid|DEVICE opens an existing GE volume, starts the storage
 * engine and reads and writes a raw key/value record.  No root, FS
 * mount, user metadata or 9P server is involved.
 */
static void
geprobevol(char *spec)
{
	char dev[64];
	vlong off, size;
	Chan *c;
	void *v;

	c = gevolume(spec, 1, dev, sizeof dev, &off, &size);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	v = geopen(dev, c, off, size, 1);
	poperror();	/* c is the GE volume's now */
	print("getest: GE volume %s@%lld, %lld MiB, opened without FS\n",
		dev, off, size/MiB);
	gestart(v);
	geprobe(v);
	gefsshutdown(v);
}

/*
 * Plan2001 stage 2's gate (docs/POC.md 2): otest=
 * PARTUUID=guid|DEVICE opens an O-profile GE volume by name, checks its
 * version and init catalog entry, and writes a plain O record.  No FS.
 */
static void
oprobevol(char *spec)
{
	char dev[64];
	vlong off, size;
	Chan *c;
	void *v;

	c = gevolume(spec, 1, dev, sizeof dev, &off, &size);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	v = oopen(dev, c, off, size, 1);
	poperror();	/* c is the O volume's now */
	print("otest: O volume %s@%lld, %lld MiB, opened without FS\n",
		dev, off, size/MiB);
	gestart(v);
	if(waserror())
		print("otest: %s\n", up->errstr);
	else{
		oprobe(v);
		poperror();
	}
	gefsshutdown(v);
}

/*
 * Plan2001 stage 3's gate (docs/POC.md 3): oobj=
 * PARTUUID=guid|DEVICE opens the same native O volume and uses the
 * object API directly: two objects with stable OIDs, one commit, then
 * a reboot fetches both.  No FS, 9P or fid is involved.
 */
static void
oobjprobevol(char *spec)
{
	char dev[64];
	vlong off, size;
	Chan *c;
	void *v;

	c = gevolume(spec, 1, dev, sizeof dev, &off, &size);
	if(waserror()){
		cclose(c);
		nexterror();
	}
	v = oopen(dev, c, off, size, 1);
	poperror();	/* c is the O volume's now */
	print("oobj: O volume %s@%lld, %lld MiB, opened without FS\n",
		dev, off, size/MiB);
	gestart(v);
	if(waserror())
		print("oobj: %s\n", up->errstr);
	else{
		oobjprobe(v);
		poperror();
	}
	gefsshutdown(v);
}

/*
 * NATIVE GE/O OBJECT IMPLEMENTATION: direct syscalls, not filesystem
 * operations. These are
 * system calls, not files: no #G, 9P, Fid, qid or /dev entry carries an
 * object.  OVOLOPEN opens the one native O volume (a PARTUUID or a
 * device, as root= takes it) and starts its GE instance; OSPACEOPEN
 * gives a Space handle from the flat catalog, and the rest are the
 * native object calls of docs/O-FORMAT.md.  The handles are
 * kernel-side: a process never sees an Ospace pointer.
 */
enum {
	Ospmax	= 8,
};

typedef struct Ohand Ohand;
typedef struct Ohtab Ohtab;
struct Ohand
{
	Ref;
	Ospace	*sp;
};
struct Ohtab
{
	Lock;
	Ohand	*h[Ospmax];
};

static Gefs *ovol;

/*
 * Plan2001: meter the legacy namespace/Chan entry points on the executed
 * boot path.  Instrumentation is only printed when plan9.ini has opath=.
 */
static void
opathdump(char *tag)
{
	print("opath: %s namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud\n",
		tag, opath_namec, opath_newchan, opath_walk, opath_devwalk,
		opath_mount, opath_exec);
}

/*
 * Plan2001: gated block-range diagnostics for the pathless gate.  A
 * write past the partition must fail in oblockrw before any driver call;
 * an oversized read is clamped to SDmaxio.
 */
static void
oblockprobe(Oblock *b, vlong size)
{
	uchar *buf;
	long r;

	if(size < 3*MiB)
		return;
	buf = smalloc(3*MiB);
	if(waserror()){
		free(buf);
		nexterror();
	}
	r = oblockrw(b, buf, 4096, size-4096, 0);
	if(r != 4096){
		print("oblocktest: FAIL in-range read returned %ld\n", r);
		error("oblocktest: in-range read");
	}
	print("oblocktest: PASS in-range-read\n");
	r = oblockrw(b, buf, 512, size, 0);
	if(r != 0){
		print("oblocktest: FAIL read at end returned %ld\n", r);
		error("oblocktest: read at end");
	}
	print("oblocktest: PASS read-at-end\n");
	r = oblockrw(b, buf, 3*MiB, 0, 0);
	if(r != SDmaxio){
		print("oblocktest: FAIL oversized read returned %ld\n", r);
		error("oblocktest: oversized read");
	}
	print("oblocktest: PASS oversized-read-clamped\n");
	if(waserror()){
		print("oblocktest: PASS write-past-end\n");
	}else{
		r = oblockrw(b, buf, 512, size, 1);
		print("oblocktest: FAIL write-past-end returned %ld\n", r);
		poperror();
	}
	free(buf);
	poperror();
}

static void*
ovolopenblk(char *spec, char *dev, int ndev, vlong *off, vlong *size, int rw)
{
	Oblock *b;

	if(cistrncmp(spec, "PARTUUID=", 9) != 0)
		return nil;
	b = oblockopenpart(spec+9, dev, ndev, off, size);
	if(b == nil)
		error("no disk has that partition");
	if(getconf("oblocktest") != nil)
		oblockprobe(b, *size);
	return oopenblk(dev, b, *off, *size, rw, oblockrw, oblockflush);
}

uintptr
sysovolopen(va_list list)
{
	char *p, *spec, dev[64];
	vlong off, size;
	Chan *c;
	void *v;
	int n, trace;

	p = va_arg(list, char*);
	n = va_arg(list, int);
	if(n <= 0 || n > 256)
		error(Ebadarg);
	validaddr((uintptr)p, n, 0);
	spec = smalloc(n+1);
	if(waserror()){
		free(spec);
		nexterror();
	}
	memmove(spec, p, n);
	spec[n] = 0;
	if(ovol != nil){
		free(spec);
		poperror();
		return 1;
	}
	trace = getconf("opath") != nil;
	if(trace)
		opathdump("volopen-enter");
	if(cistrncmp(spec, "PARTUUID=", 9) == 0){
		if(trace){
			if(waserror()){
				opathdump("volopen-error");
				nexterror();
			}
			v = ovolopenblk(spec, dev, sizeof dev, &off, &size, 1);
			poperror();
		}else
			v = ovolopenblk(spec, dev, sizeof dev, &off, &size, 1);
		print("o: O volume %s@%lld, %lld MiB, opened without FS (native SD block)\n",
			dev, off, size/MiB);
	}else{
		c = gevolume(spec, 1, dev, sizeof dev, &off, &size);
		if(waserror()){
			cclose(c);
			nexterror();
		}
		v = oopen(dev, c, off, size, 1);
		poperror();	/* c is the O volume's now */
		print("o: O volume %s@%lld, %lld MiB, opened without FS\n",
			dev, off, size/MiB);
	}
	if(trace)
		opathdump("volopen-opened");
	gestart(v);
	addvol(v);
	ovol = v;
	if(trace)
		opathdump("volopen-started");
	free(spec);
	poperror();
	return 1;
}

static void
ohandput(Ohand *oh)
{
	if(oh == nil)
		return;
	if(decref((Ref*)oh) != 0)
		return;
	onativeclose(oh->sp);
	free(oh);
}

static Ohtab*
ogettab(void)
{
	Ohtab *ht;

	if((ht = up->ohandles) != nil)
		return ht;
	ht = smalloc(sizeof *ht);
	up->ohandles = ht;
	return ht;
}

static Ohand*
ogetspace(int h)
{
	Ohtab *ht;
	Ohand *oh;

	if((ht = up->ohandles) == nil || h <= 0 || h > Ospmax)
		error(Ebadarg);
	lock(&ht->Lock);
	oh = ht->h[h-1];
	if(oh != nil)
		incref((Ref*)oh);
	unlock(&ht->Lock);
	if(oh == nil)
		error(Ebadarg);
	return oh;
}

static void
odropall(Proc *p)
{
	Ohtab *ht;
	Ohand *h[Ospmax];
	int i;

	if((ht = p->ohandles) == nil)
		return;
	p->ohandles = nil;
	lock(&ht->Lock);
	for(i = 0; i < Ospmax; i++){
		h[i] = ht->h[i];
		ht->h[i] = nil;
	}
	unlock(&ht->Lock);
	for(i = 0; i < Ospmax; i++)
		ohandput(h[i]);
	free(ht);
}

void
oprocexit(Proc *p)
{
	odropall(p);
}

void
oprocexec(Proc *p)
{
	odropall(p);
}

uintptr
sysospaceopen(va_list list)
{
	char *p, *name;
	Ospace *sp;
	Ohand *oh;
	Ohtab *ht;
	int h, n, i;

	h = va_arg(list, int);
	p = va_arg(list, char*);
	n = va_arg(list, int);
	if(h != 1 || ovol == nil)
		error(Ebadarg);
	if(n <= 0 || n > 255)
		error(Ebadarg);
	validaddr((uintptr)p, n, 0);
	name = smalloc(n+1);
	if(waserror()){
		free(name);
		nexterror();
	}
	memmove(name, p, n);
	name[n] = 0;
	sp = onativeopen(ovol, name);
	free(name);
	poperror();
	oh = smalloc(sizeof *oh);
	oh->sp = sp;
	oh->ref = 1;
	ht = ogettab();
	lock(&ht->Lock);
	for(i = 0; i < Ospmax; i++)
		if(ht->h[i] == nil){
			ht->h[i] = oh;
			unlock(&ht->Lock);
			return i+1;
		}
	unlock(&ht->Lock);
	ohandput(oh);
	error("too many O Spaces");
}

uintptr
sysospaceget(va_list list)
{
	Ohand *oh;
	char *buf;
	uvlong oid, v, *ver;
	long n, r;
	int h;

	h = va_arg(list, int);
	oid = va_arg(list, uvlong);
	buf = va_arg(list, char*);
	n = va_arg(list, long);
	ver = va_arg(list, uvlong*);
	oh = ogetspace(h);
	if(waserror()){
		ohandput(oh);
		nexterror();
	}
	if(n < 0 || n > 64*MiB)
		error(Ebadarg);
	if(n > 0)
		validaddr((uintptr)buf, n, 1);	/* written */
	if(ver != nil)
		validaddr((uintptr)ver, sizeof *ver, 1);
	v = 0;
	r = onativeget(oh->sp, oid, buf, n, &v);
	if(ver != nil)
		memmove(ver, &v, sizeof v);
	poperror();
	ohandput(oh);
	return r;
}

uintptr
sysospaceput(va_list list)
{
	Ohand *oh;
	char *buf;
	uvlong oid;
	long n;
	int h;

	h = va_arg(list, int);
	oid = va_arg(list, uvlong);
	buf = va_arg(list, char*);
	n = va_arg(list, long);
	oh = ogetspace(h);
	if(waserror()){
		ohandput(oh);
		nexterror();
	}
	if(n < 0 || n > 64*MiB)
		error(Ebadarg);
	if(n > 0)
		validaddr((uintptr)buf, n, 0);	/* read */
	onativeput(oh->sp, oid, buf, n);
	poperror();
	ohandput(oh);
	return 0;
}

uintptr
sysospacecreate(va_list list)
{
	Ohand *oh;
	char *buf;
	uvlong oid, *p;
	long n;
	int h;

	h = va_arg(list, int);
	buf = va_arg(list, char*);
	n = va_arg(list, long);
	p = va_arg(list, uvlong*);
	oh = ogetspace(h);
	if(waserror()){
		ohandput(oh);
		nexterror();
	}
	if(n < 0 || n > 64*MiB)
		error(Ebadarg);
	if(n > 0)
		validaddr((uintptr)buf, n, 0);	/* read */
	if(p == nil)
		error(Ebadarg);
	validaddr((uintptr)p, sizeof *p, 1);	/* written */
	oid = 0;
	onativecreate(oh->sp, buf, n, &oid);
	memmove(p, &oid, sizeof oid);
	poperror();
	ohandput(oh);
	return 0;
}

uintptr
sysospacecommit(va_list list)
{
	Ohand *oh;
	uvlong v, *ver;
	int h;

	h = va_arg(list, int);
	ver = va_arg(list, uvlong*);
	oh = ogetspace(h);
	if(waserror()){
		ohandput(oh);
		nexterror();
	}
	if(ver != nil)
		validaddr((uintptr)ver, sizeof *ver, 1);
	v = onativecommit(oh->sp);
	if(ver != nil)
		memmove(ver, &v, sizeof v);
	poperror();
	ohandput(oh);
	return 0;
}

uintptr
sysospaceclose(va_list list)
{
	Ohtab *ht;
	Ohand *oh;
	int h;

	h = va_arg(list, int);
	if((ht = up->ohandles) == nil || h <= 0 || h > Ospmax)
		error(Ebadarg);
	lock(&ht->Lock);
	oh = ht->h[h-1];
	if(oh != nil)
		ht->h[h-1] = nil;
	unlock(&ht->Lock);
	if(oh == nil)
		error(Ebadarg);
	ohandput(oh);
	return 0;
}

enum {
	Objexecmax	= 8*MiB,
};

uintptr
sysoexecute(va_list list)
{
	Ohand *oh;
	uchar *buf;
	char **argv;
	long n;
	uvlong oid, ver;
	int h, argc;

	h = va_arg(list, int);
	oid = va_arg(list, uvlong);
	argv = va_arg(list, char**);
	argc = va_arg(list, int);
	if(argc < 0 || argc > 32)
		error(Ebadarg);
	if(argc > 0 && argv == nil)
		error(Ebadarg);
	oh = ogetspace(h);
	if((buf = malloc(Objexecmax)) == nil){
		ohandput(oh);
		error(Enomem);
	}
	if(waserror()){
		free(buf);
		ohandput(oh);
		nexterror();
	}
	n = onativeget(oh->sp, oid, buf, Objexecmax, &ver);
	if(n < 0)
		error("oexec: no such object");
	ohandput(oh);
	poperror();
	return execo(oid, buf, n, argv, argc);
}

/*
 * plan9.ini's root= ([-w] PARTUUID=guid|DEVICE [!tree]): the kernel's
 * gefs mounted before / in the first process, before it runs init
 * (init0; legacy filesystem boot path). The host owner is user= (as factotum -u would
 * make it).  1 if done.
 */
int
rootmount(void)
{
	char *s, *u;
	int rw;

	if((u = getconf("user")) != nil && *u != 0){
		kstrdup(&eve, u);
		kstrdup(&up->user, u);
	}
	if((s = getconf("getest")) != nil && *s != 0){
		if(waserror()){
			print("getest=%s: %s\n", s, up->errstr);
			return 0;
		}
		geprobevol(s);
		poperror();
	}
	if((s = getconf("otest")) != nil && *s != 0){
		if(waserror()){
			print("otest=%s: %s\n", s, up->errstr);
			return 0;
		}
		oprobevol(s);
		poperror();
	}
	if((s = getconf("oobj")) != nil && *s != 0){
		if(waserror()){
			print("oobj=%s: %s\n", s, up->errstr);
			return 0;
		}
		oobjprobevol(s);
		poperror();
	}
	if((s = getconf("root")) == nil)
		return 0;
	rw = strncmp(s, "-w ", 3) == 0;
	if(waserror()){
		print("root=%s: %s\n", s, up->errstr);
		return 0;
	}
	gefsroot(rw ? s+3 : s, rw);
	poperror();
	return 1;
}

static Chan*
gefsattach(char*)
{
	error(Enoattach);
}

static Walkqid*
gefswalk(Chan*, Chan*, char**, int)
{
	error(Egreg);
}

static int
gefsstat(Chan*, uchar*, int)
{
	error(Egreg);
}

static Chan*
gefsopen(Chan*, int)
{
	error(Egreg);
}

static void
gefsclose(Chan*)
{
}

static long
gefsread(Chan*, void*, long, vlong)
{
	error(Egreg);
}

static long
gefswrite(Chan*, void*, long, vlong)
{
	error(Egreg);
}

Dev gefsdevtab = {
	'G',
	"gefs",

	devreset,
	devinit,
	gefsdevshutdown,
	gefsattach,
	gefswalk,
	gefsstat,
	gefsopen,
	devcreate,
	gefsclose,
	gefsread,
	devbread,
	gefswrite,
	devbwrite,
	devremove,
	devwstat,
};
