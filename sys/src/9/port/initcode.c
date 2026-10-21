/*
 * IMPORTANT!  DO NOT ADD LIBRARY CALLS TO THIS FILE.
 * The entire text image must fit on one page
 * (and there's no data segment, so any read/write data must be on the stack).
 *
 * Runs argv[1], the initial userspace program selected by init0.
 * LEGACY FS boot may first mount plan9.ini root= via rootmount;
 * native O-only PoC boots /boot/mp without an FS root (docs/POC.md).
 * argv[0] is argv0's slot, filled from a register by init9.c's _main.
 */

#include <u.h>
#include <libc.h>

char cons[] = "/dev/cons";
char dev[] = "/dev";
char c[] = "#c";
char d[] = "#d";
char e[] = "#e";
char ec[] = "#ec";
char p[] = "#p";
char s[] = "#s";
char σ[] = "#σ";
char env[] = "/env";
char fd[] = "/fd";
char proc[] = "/proc";
char srv[] = "/srv";
char shr[] = "/shr";

void
startboot(char*, char **argv)
{
	char buf[200];	/* keep this fairly large to capture error details */

	bind(c, dev, MAFTER);
	bind(d, fd, MREPL);
	bind(e, env, MREPL|MCREATE);
	bind(ec, env, MAFTER);
	bind(p, proc, MREPL);
	bind(s, srv, MREPL|MCREATE);
	bind(σ, shr, MREPL);

	open(cons, OREAD);
	open(cons, OWRITE);
	open(cons, OWRITE);

	exec(argv[1], argv+1);

	rerrstr(buf, sizeof buf);
	buf[sizeof buf - 1] = '\0';
	_exits(buf);
}
