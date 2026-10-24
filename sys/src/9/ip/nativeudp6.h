/*
 * E7.3 native UDP6 endpoint: a small kernel C capability backed by the
 * inherited UDP Proto/Conv and its headers=7 datagram metadata mode.
 * Not a userspace socket, fd, Handle or file namespace object.
 */
typedef struct Udp6Endpoint Udp6Endpoint;
typedef struct Udp6Msg Udp6Msg;
typedef struct Udp6Stats Udp6Stats;

enum {
	Udp6Ok = 0,
	Udp6ErrBadArg = -1,
	Udp6ErrNoNet = -2,
	Udp6ErrNoProto = -3,
	Udp6ErrFamily = -4,
	Udp6ErrBind = -5,
	Udp6ErrInUse = -6,
	Udp6ErrClosed = -7,
	Udp6ErrNotBound = -8,
	Udp6ErrTooBig = -9,
	Udp6ErrNoMem = -10,
	Udp6ErrTimeout = -11,
	Udp6ErrBusy = -12,
};

struct Udp6Msg {
	uchar	src[IPaddrlen];
	ushort	sport;
	uchar	dst[IPaddrlen];
	ushort	dport;
	Block	*bp;		/* caller-owned payload, one complete datagram */
};

struct Udp6Endpoint {
	Ipv6Native	*net;
	Fs		*f;
	Proto		*udp;
	Conv		*conv;
	uchar		laddr[IPaddrlen];
	ushort		lport;

	QLock		lk;		/* serializes send vs close */
	Lock		rxlock;
	Rendez		rxr;
	int		closed;
	int		recvactive;

	uvlong		rxmsgs;
	uvlong		rxbytes;
	uvlong		txaccepted;
	uvlong		txerrors;
};

struct Udp6Stats {
	int	bound;
	int	closed;
	uvlong	rxmsgs;
	uvlong	rxbytes;
	uvlong	txaccepted;
	uvlong	txerrors;
	int	pending;
	int	convstate;
};

extern int	udp6_open(Ipv6Native*, uchar*, ushort, Udp6Endpoint**);
extern int	udp6_recv(Udp6Endpoint*, Udp6Msg*, ulong);
extern int	udp6_sendto(Udp6Endpoint*, uchar*, ushort, Block*);
extern int	udp6_close(Udp6Endpoint*);
extern void	udp6_stats(Udp6Endpoint*, Udp6Stats*);
extern int	udp6_setlimit(Udp6Endpoint*, int);
extern int	udp6_pending(Udp6Endpoint*);
