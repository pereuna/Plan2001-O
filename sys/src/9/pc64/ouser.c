#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"tos.h"

#include	<a.out.h>

/*
 * Plan2001 Boot Experiments B and C.
 *
 * B: a kernel-embedded flat image performs alarm/sleep user syscalls.
 * C: a second embedded image uses the existing user native-O syscalls
 *    (OVOLOPEN/OSPACEOPEN/OEXECUTE) to replace itself with an executable
 *    fetched from a disposable GE/O volume.
 *
 * Both images are linked into the kernel by the ordinary build
 * (sys/src/9/pc/oboot*.c -> oboot*.out -> oboot*.i); neither is a /boot
 * file and no pathname is involved.
 */
#include	"obootuser.i"
#include	"obootoid.i"

enum {
	Maxargv		= 8,
	CExecOid	= 0x4f45584543000004ULL,	/* C fixture OID */
	MpOid		= 0x4f45584543000003ULL,	/* OID_MP_EXEC, unchanged */
};

typedef struct Oargs Oargs;
typedef struct Oenter Oenter;
struct Oenter
{
	uintptr	sp;
	uintptr	arg;
};

struct Oargs
{
	uvlong	oid;
	long	argc;
	long	vollen;
	char	volspec[128];
	char	space[8];
	char	argv[Maxargv][128];
};

int	oboot_user;
int	oboot_oid;
int	oboot_mp;
int	oboot_userpid;
int	oboot_usernsys;

static char obootvol[128];
static int obootvollen;

extern uvlong oboot_legacy_userinit, oboot_legacy_proc0, oboot_legacy_init0;
extern uvlong opath_namec, opath_newchan, opath_walk, opath_devwalk;
extern uvlong opath_mount, opath_exec;

/*
 * The image is the plan9 amd64 a.out produced by 6l: a 32-byte Exec
 * header, an eight-byte expanded entry, then text and data.  The
 * kernel copies the whole image to UTZERO; the established touser()
 * entry point is UTZERO+0x28, exactly the linked entry address.
 */
static void
ouserimage(uchar *img, ulong n, char *tag, uintptr *entryp, ulong *textp)
{
	Exec *e;
	uvlong entry;
	ulong text;
	ulong hdr;

	hdr = sizeof(Exec)+sizeof(uvlong);
	if(n < hdr)
		panic("%s: user image too short: %lud", tag, n);
	e = (Exec*)img;
	if(beswal(e->magic) != AOUT_MAGIC)
		panic("%s: user image bad magic %#lux", tag, beswal(e->magic));
	entry = beswav(*(uvlong*)(e+1));
	text = beswal(e->text);
	if(entry != UTZERO+hdr)
		panic("%s: user entry %#llux, want %#llux", tag, entry, UTZERO+hdr);
	if((entry & (BY2WD-1)) != 0)
		panic("%s: user entry misaligned %#llux", tag, entry);
	if(text == 0 || text > BY2PG || n > BY2PG)
		panic("%s: user image text %lud, image %lud", tag, text, n);
	if((uvlong)hdr+text > n)
		panic("%s: user image truncated: header+text %lud, image %lud",
			tag, hdr+text, n);
	if(beswal(e->data) != 0 || beswal(e->bss) != 0)
		panic("%s: user image needs data/bss outside the text page", tag);

	*entryp = entry;
	*textp = text;
}

static void
stackpage(Segment *s, uintptr va, void *data, ulong n)
{
	KMap *k;
	Page *p;

	p = newpage(va, nil);
	k = kmap(p);
	memset(VA(k), 0, BY2PG);
	if(data != nil && n > 0)
		memmove(VA(k), data, n);
	kunmap(k);
	segpage(s, p);
}

static void
ouserproc(void *arg)
{
	KMap *k;
	Page *p;
	Segment *ts;
	uintptr entry, sp, argp;
	uchar *img;
	ulong text, imglen;
	char *tag;
	Oargs oa;
	Oenter oe;

	USED(arg);
	if(waserror())
		panic("%s: bootstrap: %s",
			oboot_mp ? "OBOOT-D1" : oboot_oid ? "OBOOT-C" : "OBOOT-B",
			up->errstr);

	img = (oboot_oid || oboot_mp) ? obootoid : obootuser;
	imglen = (oboot_oid || oboot_mp) ? sizeof(obootoid) : sizeof(obootuser);
	tag = oboot_mp ? "OBOOT-D1" : oboot_oid ? "OBOOT-C" : "OBOOT-B";
	ouserimage(img, imglen, tag, &entry, &text);

	/*
	 * Only the objects needed to execute user code are initialized.
	 * proc0's Egrp, Fgrp, Rgrp, namec("#/"), cclone and init0 are
	 * deliberately absent.  kproc has already supplied the shared
	 * Pgrp; it remains initialized but unused here.
	 */
	memset(&up->sleep, 0, sizeof up->sleep);
	up->tt = nil;
	up->trend = nil;
	up->alarm = 0;
	up->fgrp = nil;
	up->egrp = nil;
	up->rgrp = nil;
	up->parent = nil;
	up->parentpid = 0;

	ts = newseg(SG_TEXT|SG_RONLY, UTZERO, 1);
	ts->flushme = 1;
	p = newpage(UTZERO, nil);
	k = kmap(p);
	memmove(VA(k), img, imglen);
	memset((uchar*)VA(k)+imglen, 0, BY2PG-imglen);
	kunmap(k);
	segpage(ts, p);
	up->seg[TSEG] = ts;

	up->seg[SSEG] = newseg(SG_STACK|SG_NOEXEC, USTKTOP-USTKSIZE, USTKSIZE/BY2PG);
	/* Fault in and zero the top stack page so the Tos slot is valid. */
	stackpage(up->seg[SSEG], USTKTOP-BY2PG, nil, 0);

	argp = 0;
	sp = USTKTOP-sizeof(Tos)-64;
	if(oboot_oid || oboot_mp){
		memset(&oa, 0, sizeof oa);
		oa.vollen = obootvollen;
		memmove(oa.volspec, obootvol, obootvollen);
		memmove(oa.space, "init", 4);
		if(oboot_mp){
			oa.oid = MpOid;
			oa.argc = 6;
			memmove(oa.argv[0], "micropython", 12);
			memmove(oa.argv[1], "-O", 3);
			memmove(oa.argv[2], obootvol, obootvollen+1);
			memmove(oa.argv[3], "-S", 3);
			memmove(oa.argv[4], "init", 5);
			memmove(oa.argv[5], "-B", 3);
		}else{
			oa.oid = CExecOid;
			oa.argc = 1;
			memmove(oa.argv[0], "obootctarget", 13);
		}
		argp = USTKTOP-2*BY2PG;
		stackpage(up->seg[SSEG], argp, &oa, sizeof oa);
		/* The block lives above the initial stack and is not grown into. */
		sp = argp-256;
	}

	up->kp = 0;
	up->noswap = 0;
	up->privatemem = 0;
	procpriority(up, PriNormal, 0);
	procsetup(up);

	flushmmu();
	poperror();

	oboot_userpid = up->pid;
	print("%s: KERNEL-READY pid=%lud entry=%#p text=%lud image=%lud slash=%s dot=%s\n",
		tag, up->pid, entry, text, imglen,
		up->slash == nil ? "nil" : "set",
		up->dot == nil ? "nil" : "set");
	if(oboot_oid || oboot_mp)
		print("%s: VOLSPEC len=%d %s\n", tag, obootvollen, obootvol);
	if(oboot_mp){
		print("OBOOT-D1: ARGV argc=%d", oa.argc);
		{
			int i;
			for(i = 0; i < oa.argc; i++)
				print(" <%s>", oa.argv[i]);
		}
		print("\nOBOOT-D1: OID=%#llux\n", oa.oid);
	}
	print("%s: legacy-calls userinit=%llud proc0=%llud init0=%llud\n",
		tag, oboot_legacy_userinit, oboot_legacy_proc0, oboot_legacy_init0);
	print("%s: path-calls namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud\n",
		tag, opath_namec, opath_newchan, opath_walk, opath_devwalk,
		opath_mount, opath_exec);
	if(oboot_oid || oboot_mp)
		print("%s: KERNEL-TO-USER pid=%lud pc=%#p sp=%#p arg=%#p\n",
			tag, up->pid, entry, sp, argp);
	else
		print("%s: KERNEL-TO-USER pid=%lud pc=%#p sp=%#p\n",
			tag, up->pid, entry, sp);

	splhi();
	fpukexit(nil);
	if(oboot_oid || oboot_mp){
		oe.sp = sp;
		oe.arg = argp;
		otouser(&oe);
	}else
		touser((void*)sp);

	panic("%s: touser returned", tag);
}

void
o_user_bootstrap(void)
{
	char *p;
	int n;

	if(oboot_oid || oboot_mp){
		p = getconf("obootvol");
		if(p == nil || strncmp(p, "PARTUUID=", 9) != 0){
			print("%s: bad obootvol\n", oboot_mp ? "OBOOT-D1" : "OBOOT-C");
			panic("%s: obootvol must be PARTUUID=...",
				oboot_mp ? "OBOOT-D1" : "OBOOT-C");
		}
		n = strlen(p);
		if(n <= 0 || n >= sizeof obootvol){
			print("%s: obootvol length %d\n",
				oboot_mp ? "OBOOT-D1" : "OBOOT-C", n);
			panic("%s: obootvol too long",
				oboot_mp ? "OBOOT-D1" : "OBOOT-C");
		}
		memmove(obootvol, p, n);
		obootvol[n] = 0;
		obootvollen = n;
	}
	up = nil;
	kstrdup(&eve, "");
	kproc("*ouser*", ouserproc, nil);
}
