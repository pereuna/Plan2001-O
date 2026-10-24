#include	"u.h"
#include	"../port/lib.h"
#include	"mem.h"
#include	"dat.h"
#include	"fns.h"

/*
 * Normal pc64/pc64mp builds link this stub so main.c can call the same
 * hook without depending on generated native-probe files.  The opt-in
 * pc64native configuration links onativeprobe.c instead.
 */
int
onativeprobe_start(void)
{
	return 0;
}

int
e71etherprobe_start(void)
{
	return 0;
}

int
e72ipv6probe_start(void)
{
	return 0;
}

int
e73udpprobe_start(void)
{
	return 0;
}
