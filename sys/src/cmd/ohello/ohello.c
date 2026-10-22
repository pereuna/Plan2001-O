#include <u.h>
#include <libc.h>

extern long ospaceget(int, uvlong, void*, long, uvlong*);

enum {
	ExecOid	= 0x4f45584543000001ULL,
};

static char marker[] = "ohello: native executable from O marker\n";
static char failmsg[] = "ohello: FAIL O handle survived native exec\n";

void
main(void)
{
	if(ospaceget(1, ExecOid, nil, 0, nil) >= 0){
		write(1, failmsg, sizeof failmsg-1);
		exits("handles");
	}
	write(1, marker, sizeof marker-1);
	exits(nil);
}
