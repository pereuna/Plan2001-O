#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"
#include	"../port/error.h"
#include	"tos.h"

#include	<a.out.h>

/*
 * Plan2001 Boot Experiment B: first real ring-3 process from an
 * already built flat byte image.  The image is linked into the kernel
 * by the ordinary build (sys/src/9/pc/obootuser.c -> obootuser.out ->
 * obootuser.i); it is not a /boot file and no pathname is involved.
 */
#include	"obootuser.i"

int	oboot_user;
int	oboot_userpid;
int	oboot_usernsys;

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
ouserimage(uintptr *entryp, ulong *textp)
{
	Exec *e;
	uvlong entry;
	ulong text;
	ulong hdr;

	hdr = sizeof(Exec)+sizeof(uvlong);
	if(sizeof(obootuser) < hdr)
		panic("OBOOT-B: user image too short: %lud", sizeof(obootuser));
	e = (Exec*)obootuser;
	if(beswal(e->magic) != AOUT_MAGIC)
		panic("OBOOT-B: user image bad magic %#lux", beswal(e->magic));
	entry = beswav(*(uvlong*)(e+1));
	text = beswal(e->text);
	if(entry != UTZERO+hdr)
		panic("OBOOT-B: user entry %#llux, want %#llux", entry, UTZERO+hdr);
	if((entry & (BY2WD-1)) != 0)
		panic("OBOOT-B: user entry misaligned %#llux", entry);
	if(text == 0 || text > BY2PG || sizeof(obootuser) > BY2PG)
		panic("OBOOT-B: user image text %lud, image %lud", text, sizeof(obootuser));
	if((uvlong)hdr+text > sizeof(obootuser))
		panic("OBOOT-B: user image truncated: header+text %lud, image %lud",
			hdr+text, sizeof(obootuser));
	if(beswal(e->data) != 0 || beswal(e->bss) != 0)
		panic("OBOOT-B: user image needs data/bss outside the text page");

	*entryp = entry;
	*textp = text;
}

static void
ouserproc(void *arg)
{
	KMap *k;
	Page *p;
	Segment *ts;
	uintptr entry, sp;
	ulong text;

	USED(arg);
	if(waserror())
		panic("OBOOT-B: bootstrap: %s", up->errstr);

	ouserimage(&entry, &text);

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
	memmove(VA(k), obootuser, sizeof(obootuser));
	memset((uchar*)VA(k)+sizeof(obootuser), 0, BY2PG-sizeof(obootuser));
	kunmap(k);
	segpage(ts, p);
	up->seg[TSEG] = ts;

	up->seg[SSEG] = newseg(SG_STACK|SG_NOEXEC, USTKTOP-USTKSIZE, USTKSIZE/BY2PG);

	up->kp = 0;
	up->noswap = 0;
	up->privatemem = 0;
	procpriority(up, PriNormal, 0);
	procsetup(up);

	flushmmu();
	poperror();

	oboot_userpid = up->pid;
	print("OBOOT-B: KERNEL-READY pid=%lud entry=%#p text=%lud image=%lud slash=%s dot=%s\n",
		up->pid, entry, text, (ulong)sizeof(obootuser),
		up->slash == nil ? "nil" : "set",
		up->dot == nil ? "nil" : "set");
	print("OBOOT-B: legacy-calls userinit=%llud proc0=%llud init0=%llud\n",
		oboot_legacy_userinit, oboot_legacy_proc0, oboot_legacy_init0);
	print("OBOOT-B: path-calls namec=%llud newchan=%llud walk=%llud devwalk=%llud mount=%llud exec=%llud\n",
		opath_namec, opath_newchan, opath_walk, opath_devwalk,
		opath_mount, opath_exec);

	sp = USTKTOP-sizeof(Tos)-64;
	print("OBOOT-B: KERNEL-TO-USER pid=%lud pc=%#p sp=%#p\n", up->pid, entry, sp);

	splhi();
	fpukexit(nil);
	touser((void*)sp);

	panic("OBOOT-B: touser returned");
}

void
o_user_bootstrap(void)
{
	up = nil;
	kstrdup(&eve, "");
	kproc("*ouser*", ouserproc, nil);
}
