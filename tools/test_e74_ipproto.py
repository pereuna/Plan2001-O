#!/usr/bin/env python3
"""E7.4 real-VirtIO experimental IPv6 Next Header fixture.

Boots 9pc64e74 with a QEMU dgram raw-L2 netdev.  The host verifies, on the
wire, that the guest answers NDP, ICMPv6 Echo, native UDP6 and a direct
Next Header 253 payload.  It also verifies that malformed, unhandled and
extension-header combinations do not produce a 253 reply, and that the
consumer unregisters safely with a callback in flight.

The guest is NORMAL IPv6 only.  Next Header 253 is an experiment selector
(RFC 3692), not WireGuard, encryption or an authenticated tunnel.
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time

GUEST_MAC = bytes.fromhex("525400123456")
HOST_MAC = bytes.fromhex("020000000002")
HOST_LL = bytes.fromhex("fe800000000000000000000000000002")
GUEST_LL = None
IPV4_FROM_GUEST = 0

E74_PROTO = 253


def die(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def cksum(data):
    if len(data) & 1:
        data += b"\0"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i+1]
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff


def parse_ll(s):
    return socket.inet_pton(socket.AF_INET6, s)


def fmt_ll(b):
    return socket.inet_ntop(socket.AF_INET6, b)


def solicited_node(addr):
    return bytes.fromhex("ff0200000000000000000001ff") + addr[-3:]


def solicited_mac(addr):
    return b"\x33\x33\xff" + addr[-3:]


def eth(dst, payload, src=HOST_MAC, etype=0x86DD):
    f = dst + src + etype.to_bytes(2, "big") + payload
    if len(f) < 60:
        f += b"\0" * (60 - len(f))
    return f


def ipv6(src, dst, nexthdr, hop, payload):
    h = bytearray(40)
    h[0] = 0x60
    h[4:6] = len(payload).to_bytes(2, "big")
    h[6] = nexthdr
    h[7] = hop
    h[8:24] = src
    h[24:40] = dst
    return bytes(h) + payload


def icmp6(src, dst, typ, code, body, hop):
    hdr = bytearray(8)
    hdr[0] = typ
    hdr[1] = code
    hdr[4:8] = body[:4]
    rest = bytes(hdr) + body[4:]
    pseudo = src + dst + len(rest).to_bytes(4, "big") + b"\0\0\0" + b"\x3a"
    c = cksum(pseudo + rest)
    rest = rest[:2] + c.to_bytes(2, "big") + rest[4:]
    return ipv6(src, dst, 58, hop, rest)


def ns(target):
    opt = bytes([1, 1]) + HOST_MAC
    body = b"\0\0\0\0" + target + opt
    return eth(solicited_mac(target),
               icmp6(HOST_LL, solicited_node(target), 135, 0, body, 255))


def na(target):
    opt = bytes([2, 1]) + HOST_MAC
    body = bytes([0x60]) + b"\0\0\0" + target + opt
    return eth(GUEST_MAC, icmp6(HOST_LL, GUEST_LL, 136, 0, body, 255))


def echo_request(seq, payload):
    body = b"\x12\x34" + seq.to_bytes(2, "big") + payload
    return eth(GUEST_MAC, icmp6(HOST_LL, GUEST_LL, 128, 0, body, 64))


def udp6_frame(srcport, dstport, payload):
    uh = bytearray(8)
    uh[0:2] = srcport.to_bytes(2, "big")
    uh[2:4] = dstport.to_bytes(2, "big")
    ulen = 8 + len(payload)
    uh[4:6] = ulen.to_bytes(2, "big")
    pseudo = HOST_LL + GUEST_LL + ulen.to_bytes(4, "big") + b"\0\0\0" + b"\x11"
    c = cksum(pseudo + bytes(uh) + payload)
    if c == 0:
        c = 0xffff
    uh[6:8] = c.to_bytes(2, "big")
    return eth(GUEST_MAC, ipv6(HOST_LL, GUEST_LL, 17, 64, bytes(uh) + payload))


def ip253(payload, plen=None, version=0x60):
    ip = bytearray(ipv6(HOST_LL, GUEST_LL, E74_PROTO, 64, payload))
    ip[0] = version
    if plen is not None:
        ip[4:6] = plen.to_bytes(2, "big")
    return eth(GUEST_MAC, bytes(ip))


def hbh253(payload):
    ext = bytes([E74_PROTO, 0]) + b"\0" * 6
    return eth(GUEST_MAC, ipv6(HOST_LL, GUEST_LL, 0, 64, ext + payload))


def parse_ipv6(frame):
    if len(frame) < 14 + 40 or frame[12:14] != b"\x86\xdd":
        return None
    ip = frame[14:]
    if (ip[0] >> 4) != 6:
        return None
    plen = int.from_bytes(ip[4:6], "big")
    if len(ip) < 40 + plen:
        return None
    return ip[:40], ip[40:40+plen]


def icmp_ok(src, dst, payload):
    if len(payload) < 8:
        return False
    h = bytearray(payload)
    got = int.from_bytes(h[2:4], "big")
    h[2:4] = b"\0\0"
    pseudo = src + dst + len(payload).to_bytes(4, "big") + b"\0\0\0" + b"\x3a"
    return cksum(pseudo + bytes(h)) == got


def parse_udp(ip, payload):
    if len(payload) < 8 or ip[6] != 17:
        return None
    ulen = int.from_bytes(payload[4:6], "big")
    if ulen < 8 or len(payload) < ulen:
        return None
    u = bytearray(payload[:ulen])
    got = int.from_bytes(u[6:8], "big")
    u[6:8] = b"\0\0"
    pseudo = ip[8:24] + ip[24:40] + ulen.to_bytes(4, "big") + b"\0\0\0" + b"\x11"
    if cksum(pseudo + bytes(u)) != got:
        return None
    return (int.from_bytes(payload[0:2], "big"),
            int.from_bytes(payload[2:4], "big"),
            payload[8:ulen])


class Serial:
    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.data = ""

    def poll(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                d = f.read()
                self.pos = f.tell()
        except FileNotFoundError:
            return
        if d:
            self.data += d.decode("latin1", "replace").replace("\r", "")

    def wait(self, pattern, timeout, what):
        rx = re.compile(pattern, re.M)
        end = time.time() + timeout
        while time.time() < end:
            self.poll()
            m = rx.search(self.data)
            if m:
                return m
            time.sleep(0.1)
        tail = "\n".join(self.data.splitlines()[-60:])
        die("%s: timeout /%s/; serial tail:\n%s" % (what, pattern, tail))


def make_esp(workdir, loader, kernel, espname):
    esp = os.path.join(workdir, "esp.img")
    if os.path.exists(esp):
        os.unlink(esp)
    subprocess.run(["mformat", "-C", "-i", esp, "-T", "65536", "-h", "64", "-s", "32", "::"], check=True)
    subprocess.run(["mmd", "-i", esp, "::/EFI", "::/EFI/BOOT"], check=True)
    subprocess.run(["mcopy", "-i", esp, loader, "::/EFI/BOOT/" + espname], check=True)
    ini = os.path.join(workdir, "plan9.ini")
    with open(ini, "w") as f:
        f.write("bootfile=/%s\nconsole=0\ne74ip=1\n" % os.path.basename(kernel))
    subprocess.run(["mcopy", "-i", esp, kernel, ini, "::/"], check=True)
    return esp


def start_qemu(args, serial_path, net):
    qargs = [
        args.qemu, "-name", "plan2001-e74", "-nodefaults",
        "-accel", "kvm", "-cpu", "host", "-machine", "q35",
        "-m", "2048", "-smp", "2", "-display", "none",
        "-drive", "if=pflash,format=raw,readonly=on,file=" + args.fwcode,
        "-drive", "if=pflash,format=raw,file=" + args.fwvars,
        "-drive", "file=%s,format=raw,if=none,id=esp" % args.esp,
        "-device", "ide-hd,drive=esp,bootindex=0",
        "-serial", "file:" + serial_path,
    ]
    if net is None:
        qargs += ["-nic", "none"]
    else:
        p1, p2 = net
        qargs += [
            "-netdev", ("dgram,id=n0,local.type=inet,local.host=127.0.0.1,"
                        "local.port=%d,remote.type=inet,remote.host=127.0.0.1,"
                        "remote.port=%d" % (p1, p2)),
            "-device", "virtio-net-pci-non-transitional,netdev=n0,mac=" +
            ":".join("%02x" % b for b in GUEST_MAC),
        ]
    log = open(os.path.join(args.workdir, "qemu-%s.log" % os.path.basename(serial_path)), "wb")
    return subprocess.Popen(qargs, stdout=log, stderr=subprocess.STDOUT), log


def stop_qemu(p, log):
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    log.close()


class Link:
    def __init__(self, p1):
        self.p1 = p1
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def bind(self, p2):
        self.sock.bind(("127.0.0.1", p2))
        self.sock.settimeout(0.2)

    def send(self, frame):
        self.sock.sendto(frame, ("127.0.0.1", self.p1))

    def recv(self, timeout=0.2):
        global IPV4_FROM_GUEST
        self.sock.settimeout(timeout)
        try:
            f, _ = self.sock.recvfrom(65536)
            if len(f) >= 14 and f[12:14] == b"\x08\x00":
                IPV4_FROM_GUEST += 1
            return f
        except socket.timeout:
            return None


def reply_ns(link, ip, payload):
    if len(payload) >= 24:
        link.send(na(payload[8:24]))


def pump(link, timeout, pred):
    """Answer guest NS and return pred(ip, payload) when non-None."""
    end = time.time() + timeout
    while time.time() < end:
        f = link.recv(0.2)
        if f is None:
            continue
        p = parse_ipv6(f)
        if p is None:
            continue
        ip, payload = p
        if payload and ip[6] == 58 and payload[0] == 135:
            reply_ns(link, ip, payload)
            continue
        if payload is None:
            payload = b""
        r = pred(ip, payload)
        if r is not None:
            return r
    return None


def wait_na(link, timeout=10):
    def pred(ip, payload):
        if not payload or payload[0] != 136:
            return None
        if not icmp_ok(ip[8:24], ip[24:40], payload):
            return None
        if payload[8:24] == GUEST_LL and ip[8:24] == GUEST_LL:
            return True
        return None
    return pump(link, timeout, pred) is True


def wait_icmp_echo(link, seq, data, timeout=8):
    def pred(ip, payload):
        if not payload or payload[0] != 129:
            return None
        if not icmp_ok(ip[8:24], ip[24:40], payload):
            return None
        if payload[4:6] == b"\x12\x34" and payload[6:8] == seq.to_bytes(2, "big") \
           and payload[8:] == data and ip[8:24] == GUEST_LL and ip[24:40] == HOST_LL:
            return True
        return None
    return pump(link, timeout, pred) is True


def wait_udp_echo(link, hostport, data, timeout=8):
    def pred(ip, payload):
        u = parse_udp(ip, payload)
        if u is None:
            return None
        sport, dport, got = u
        if sport != 20001 or dport != hostport:
            return None
        if got != data:
            die("UDP6 echo payload mismatch: %r != %r" % (got, data))
        return True
    return pump(link, timeout, pred) is True


def wait_ip253(link, data, timeout=8):
    def pred(ip, payload):
        if ip[6] != E74_PROTO:
            return None
        if ip[8:24] != GUEST_LL or ip[24:40] != HOST_LL:
            return None
        if payload != data:
            return None
        return True
    return pump(link, timeout, pred) is True


def count_ip253(link, data, duration):
    n = 0

    def pred(ip, payload):
        nonlocal n
        if ip[6] == E74_PROTO and payload == data:
            n += 1
        return None
    pump(link, duration, pred)
    return n


def run_nic(args):
    global GUEST_LL
    p1 = free_udp_port()
    p2 = free_udp_port()
    link = Link(p1)
    link.bind(p2)
    serial_path = os.path.join(args.workdir, "serial-virtio.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, (p1, p2))
    s = Serial(serial_path)
    try:
        s.wait(r"^E74IP: READY$", 120, "ready")
        m = s.wait(r"^E74IP: LLADDR (fe80:[0-9a-f:]+)$", 10, "lladdr")
        GUEST_LL = parse_ll(m.group(1))
        print("GUEST-LL:", fmt_ll(GUEST_LL))

        link.send(ns(GUEST_LL))
        if not wait_na(link):
            die("no valid Neighbor Advertisement")
        print("NDP: NA ok")

        req = echo_request(1, b"e74-icmp")
        link.send(req)
        if not wait_icmp_echo(link, 1, b"e74-icmp"):
            die("no ICMPv6 Echo Reply")
        print("ICMPv6: echo ok")

        for port, data in [(41001, b""), (41002, b"A"), (41003, b"B" * 17)]:
            link.send(udp6_frame(port, 20001, data))
            if not wait_udp_echo(link, port, data):
                die("no UDP6 echo for port %d len %d" % (port, len(data)))
        print("UDP6: echoed len 0,1,17")

        hello = b"E74-HELLO-253"
        link.send(ip253(hello))
        if not wait_ip253(link, hello):
            die("no experimental Next Header 253 echo")
        extra = count_ip253(link, hello, 0.8)
        if extra != 0:
            die("duplicate 253 replies for one request: %d" % extra)
        print("IP253: echo ok, no duplicate")

        s.wait(r"^E74IP: POSITIVE .+$", 10, "positive markers")
        s.wait(r"^E74IP: CHAN-NATIVE .* clean=1$", 10, "chan counters")

        s.wait(r"^E74IP: NEG-READY$", 10, "negative ready")
        neg = b"E74-NEG"
        link.send(eth(GUEST_MAC, ipv6(HOST_LL, GUEST_LL, 254, 64, neg)))
        link.send(hbh253(neg))
        link.send(ip253(neg, plen=200))
        link.send(ip253(neg, version=0x40))
        link.send(eth(GUEST_MAC, b"\x60" + b"\0" * 20))
        link.send(eth(GUEST_MAC, b"\x45" + b"\0" * 59, etype=0x0800))

        end = time.time() + 0.9
        bad = 0
        while time.time() < end:
            f = link.recv(0.1)
            if f is None:
                continue
            p = parse_ipv6(f)
            if p is None:
                continue
            ip, payload = p
            if ip[6] == 58 and payload and payload[0] == 135:
                reply_ns(link, ip, payload)
                continue
            if ip[6] == E74_PROTO and payload == neg:
                bad += 1
        if bad:
            die("negative/handled? frames produced %d experimental replies" % bad)

        alive = b"e74-alive"
        link.send(ip253(alive))
        if not wait_ip253(link, alive):
            die("no post-negative ALIVE 253 echo")
        s.wait(r"^E74IP: ALIVE ", 8, "alive marker")
        m = s.wait(r"^E74IP: NEG-RESULT .* unhandled=(\d+) badhdr=(\d+)(?: other=(\d+))?$", 8, "neg result")
        if int(m.group(1)) < 1:
            die("guest did not count an unhandled Next Header")
        if int(m.group(2)) < 1:
            die("guest did not count a malformed IPv6 header")
        print("NEG: no 253 reply for 254/HBH/version/length/truncated/IPv4")

        s.wait(r"^E74IP: UNREG-READY$", 10, "unreg ready")
        link.send(ip253(b"e74-hold"))
        s.wait(r"^E74IP: UNREG-WAIT active=[1-9][0-9]*$", 10, "unreg in-flight")
        s.wait(r"^E74IP: UNREG rc=0 active=0 registered=0$", 10, "unreg result")

        s.wait(r"^E74IP: REARM-READY$", 10, "rearm ready")
        rearm = b"e74-rearm"
        link.send(ip253(rearm))
        if not wait_ip253(link, rearm):
            die("no 253 echo after re-register")
        s.wait(r"^E74IP: REARM-OK ", 10, "rearm result")

        s.wait(r"^E74IP: UNREG-FINAL rc=0$", 10, "unreg final")

        # E7.4.3: admitted callback held past the unregister timeout; Busy
        # must latch DRAINING, reject re-registration, drain, retry and rear.
        s.wait(r"^E743IP: A-READY$", 10, "e743 A ready")
        a_payload = b"E743-A-ORIGINAL"
        c_payload = b"E743-C-STALE"
        link.send(ip253(a_payload))
        s.wait(r"^E743IP: A-ADMITTED active=[1-9][0-9]* registered=1$", 10,
               "e743 A admitted")
        m = s.wait(r"^E743IP: BUSY rc=(-?\d+) registered=(\d+) draining=(\d+) active=(\d+)$",
                   15, "e743 busy")
        if int(m.group(1)) != -3 or int(m.group(2)) != 0 or int(m.group(3)) != 1:
            die("E743 Busy did not latch DRAINING: %s" % m.group(0))
        m = s.wait(r"^E743IP: CONCUR-OWNER rc=(-?\d+) done=(\d+)$", 10,
                   "e743 concurrent unregister")
        if int(m.group(1)) != -3 or int(m.group(2)) != 1:
            die("E743 concurrent unregister was not Busy: %s" % m.group(0))
        m = s.wait(r"^E743IP: REG-B rc=(-?\d+)$", 10, "e743 reg B")
        if int(m.group(1)) != -3:
            die("E743 re-register while draining was not Busy (old bug)")
        if count_ip253(link, a_payload, 0.3) != 0:
            die("E743 original A payload produced a 253 reply")
        s.wait(r"^E743IP: C-READY$", 10, "e743 C ready")
        link.send(ip253(c_payload))
        s.wait(r"^E743IP: A-DONE callsA=1 callsB=0 active=0$", 15,
               "e743 A drained without B")
        if count_ip253(link, c_payload, 0.3) != 0:
            die("E743 stale C payload produced a 253 reply")
        s.wait(r"^E743IP: A-SEND rc=-4$", 10, "e743 callback send rejected")
        s.wait(r"^E743IP: C-DRAINED delivered=[2-9][0-9]*$", 10,
               "e743 stale packet drained")
        s.wait(r"^E743IP: RETRY rc=0$", 10, "e743 unregister retry")
        s.wait(r"^E743IP: NOTREG rc=-4$", 10, "e743 completed unregister")
        for j in range(5):
            s.wait(r"^E743IP: CYCLE %d READY$" % j, 10, "e743 cycle ready %d" % j)
            d = ("E743-D-%d" % j).encode()
            link.send(ip253(d))
            s.wait(r"^E743IP: CYCLE %d GOT callsB=1 len=%d$" % (j, len(d)), 10,
                   "e743 fresh B payload %d" % j)
            s.wait(r"^E743IP: CYCLE %d UNREG rc=0$" % j, 10,
                   "e743 cycle unreg %d" % j)
        s.wait(r"^E743IP: DONE callsA=1 callsB=1$", 10, "e743 done")

        s.wait(r"^E74IP: TXDOWN-READY$", 10, "txdown ready")
        link.send(ip253(b"e74-down"))
        s.wait(r"^E74IP: TXDOWN txdown=[1-9][0-9]*$", 10, "txdown count")
        s.wait(r"^E74IP: STOP rc=0$", 15, "stop")
        s.wait(r"^E74IP: DONE pass=1 fails=0$", 15, "done")

        for pat, what in [
            (r"^E74IP: CHECK dup-reg rc=-3$", "duplicate registration"),
            (r"^E74IP: CHECK reg-nilnet rc=-1$", "nil net registration"),
            (r"^E74IP: CHECK reg-nilcb rc=-1$", "nil callback registration"),
            (r"^E74IP: CHECK send-big rc=-5$", "MTU rejection"),
            (r"^E74IP: CHECK send-v4 rc=-6$", "IPv4 destination rejection"),
            (r"^E74IP: CHECK send-proto rc=-1$", "fixed-protocol restriction"),
            (r"^E74IP: CHECK send-nil rc=-1$", "nil payload rejection"),
            (r"^E74IP: CHECK queue-sat drop=[1-9][0-9]*$", "RX queue saturation"),
            (r"^E74IP: CHECK unreg-twice rc=-4$", "repeat unregister"),
            (r"^E74IP: CHECK repeat-stop rc=-9$", "repeat stop"),
        ]:
            if not re.search(pat, s.data, re.M):
                die("missing marker /%s/" % what)
        if re.search(r"panic|fault|suicide", s.data):
            die("guest panic/fault marker")
        if args.profile == "e77":
            m = s.wait(r"^E74IP: NEG-RESULT .* other=(\d+)$", 8, "e77 IPv4 drop count")
            if int(m.group(1)) < 1:
                die("real IPv4 EtherType frame was not counted as rxother")
            s.wait(r"^E74IP: CHECK ipv4-drop other=1 rxframes=0$", 8, "synthetic IPv4 drop")
            s.wait(r"^E74IP: CHECK udp6-open-v4 rc=-4$", 8, "IPv4-mapped UDP6 open rejection")
            if IPV4_FROM_GUEST != 0:
                die("guest emitted %d IPv4 EtherType frames" % IPV4_FROM_GUEST)
            print("E77: IPv4 EtherType dropped, IPv4-mapped API rejected, no IPv4 TX")
    finally:
        stop_qemu(q, qlog)
        link.sock.close()
    with open(os.path.join(args.workdir, "boot-virtio.log"), "w") as f:
        f.write(s.data)
    print("PASS: real VirtIO NDP/ICMP/UDP6/Next Header 253 and negatives")


def run_none(args):
    serial_path = os.path.join(args.workdir, "serial-nonic.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, None)
    s = Serial(serial_path)
    try:
        s.wait(r"^E74IP: NODEV n=0$", 120, "no NIC")
        s.wait(r"^E74IP: DONE pass=1 fails=0$", 15, "no NIC done")
        if re.search(r"panic|fault|suicide", s.data):
            die("no-NIC guest panic/fault marker")
    finally:
        stop_qemu(q, qlog)
    with open(os.path.join(args.workdir, "boot-nonic.log"), "w") as f:
        f.write(s.data)
    print("PASS: absent controller (no IPv6 consumer)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qemu", required=True)
    ap.add_argument("--fwcode", required=True)
    ap.add_argument("--fwvars", required=True)
    ap.add_argument("--loader", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--espname", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--profile", choices=("e74", "e76", "e77"), default="e74")
    args = ap.parse_args()

    for t in ("mformat", "mmd", "mcopy"):
        if shutil.which(t) is None:
            die("%s not found (mtools)" % t)
    os.makedirs(args.workdir, exist_ok=True)
    fwvars = os.path.join(args.workdir, "vars.fd")
    shutil.copyfile(args.fwvars, fwvars)
    args.fwvars = fwvars
    args.esp = make_esp(args.workdir, args.loader, args.kernel, args.espname)

    run_none(args)
    run_nic(args)
    print("PASS: E7.4 Next Header fixture")


if __name__ == "__main__":
    main()
