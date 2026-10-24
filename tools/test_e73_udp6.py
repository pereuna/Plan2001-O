#!/usr/bin/env python3
"""E7.3 real-VirtIO native UDP6 datagram fixture.

The host transports raw Ethernet frames over QEMU's dgram netdev (host-side
IPv4 localhost is only the frame transport).  The guest's native IPv6 path
must answer ND, then echo complete UDP6 datagrams from two source ports and
several payload lengths.  Replies are validated byte-for-byte, including the
UDP6 pseudoheader checksum.
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


def udp6_frame(srcport, dstport, payload, src=HOST_LL, dst=None,
               badcksum=False, zerocksum=False, ulen=None, ipv6len=None):
    if dst is None:
        dst = GUEST_LL
    uh = bytearray(8)
    uh[0:2] = srcport.to_bytes(2, "big")
    uh[2:4] = dstport.to_bytes(2, "big")
    u = ulen if ulen is not None else 8 + len(payload)
    uh[4:6] = u.to_bytes(2, "big")
    pseudo = src + dst + u.to_bytes(4, "big") + b"\0\0\0" + b"\x11"
    c = cksum(pseudo + bytes(uh) + payload)
    if c == 0:
        c = 0xffff
    if zerocksum:
        c = 0
    elif badcksum:
        c ^= 0x0100
    uh[6:8] = c.to_bytes(2, "big")
    ip = ipv6(src, dst, 17, 64, bytes(uh) + payload)
    if ipv6len is not None:
        ip = ip[:4] + ipv6len.to_bytes(2, "big") + ip[6:]
    return eth(GUEST_MAC, ip)


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
        f.write("bootfile=/%s\nconsole=0\ne73udp=1\n" % os.path.basename(kernel))
    subprocess.run(["mcopy", "-i", esp, kernel, ini, "::/"], check=True)
    return esp


def start_qemu(args, serial_path, net):
    qargs = [
        args.qemu, "-name", "plan2001-e73", "-nodefaults",
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
        self.sock.settimeout(timeout)
        try:
            f, _ = self.sock.recvfrom(65536)
            return f
        except socket.timeout:
            return None


def reply_ns(link, ip, icmp):
    if len(icmp) >= 24:
        link.send(na(icmp[8:24]))


def wait_na(link, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        f = link.recv(0.2)
        if f is None:
            continue
        p = parse_ipv6(f)
        if p is None:
            continue
        ip, icmp = p
        if len(icmp) < 8:
            continue
        if icmp[0] == 135:
            reply_ns(link, ip, icmp)
            continue
        if icmp[0] != 136:
            continue
        if not icmp_ok(ip[8:24], ip[24:40], icmp):
            continue
        target = icmp[8:24]
        tlla = None
        o = 24
        while o + 8 <= len(icmp):
            if icmp[o+1] == 0:
                break
            if icmp[o] == 2 and icmp[o+1] == 1:
                tlla = icmp[o+2:o+8]
            o += icmp[o+1] * 8
        if target == GUEST_LL and tlla == GUEST_MAC:
            return True
    return False


def wait_echo(link, dport, payload, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        f = link.recv(0.2)
        if f is None:
            continue
        p = parse_ipv6(f)
        if p is None:
            continue
        ip, pl = p
        if pl and pl[0] == 135:
            reply_ns(link, ip, pl)
            continue
        u = parse_udp(ip, pl)
        if u is None:
            continue
        sport, dport_got, data = u
        if sport != 20001:
            continue
        if dport_got != dport:
            die("echo to wrong host port %d (want %d)" % (dport_got, dport))
        if data != payload:
            die("echo payload mismatch for port %d: %r != %r" % (dport, data, payload))
        return True
    return False


def no_echo(link, duration, allow_unreachable=False):
    end = time.time() + duration
    unreachable = False
    while time.time() < end:
        f = link.recv(0.1)
        if f is None:
            continue
        p = parse_ipv6(f)
        if p is None:
            continue
        ip, pl = p
        if pl and pl[0] == 135:
            reply_ns(link, ip, pl)
            continue
        if pl and pl[0] == 1 and len(pl) >= 8 and pl[1] == 4:
            if not icmp_ok(ip[8:24], ip[24:40], pl):
                die("invalid ICMPv6 unreachable checksum")
            unreachable = True
            continue
        u = parse_udp(ip, pl)
        if u is not None and u[0] == 20001:
            die("unexpected UDP echo during negative window")
        if not allow_unreachable:
            # Any other frame is unexpected but harmless for this check.
            pass
    return unreachable


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
        s.wait(r"^E73UDP: READY$", 120, "ready")
        m = s.wait(r"^E73UDP: LLADDR (fe80:[0-9a-f:]+)$", 10, "lladdr")
        GUEST_LL = parse_ll(m.group(1))
        print("GUEST-LL:", fmt_ll(GUEST_LL))

        link.send(ns(GUEST_LL))
        if not wait_na(link):
            die("no valid Neighbor Advertisement")
        print("NDP: NA ok")

        positives = [
            (40001, b""),
            (40002, b"A"),
            (40003, b"B" * 17),
            (40004, b"C" * 1452),
        ]
        for port, payload in positives:
            link.send(udp6_frame(port, 20001, payload))
            if not wait_echo(link, port, payload):
                die("missing echo for port %d len %d" % (port, len(payload)))
        # two quick datagrams in one session: message boundaries and peer ports
        pair = [(40005, b"pair-one"), (40006, b"pair-two")]
        for port, payload in pair:
            link.send(udp6_frame(port, 20001, payload))
        for port, payload in pair:
            if not wait_echo(link, port, payload, 8):
                die("missing paired echo for port %d" % port)
        print("POSITIVE: lengths 0,1,17,1452 and paired messages")

        s.wait(r"^E73UDP: POSITIVE rx=6 tx=6", 10, "positive markers")
        s.wait(r"^E73UDP: CHAN-NATIVE .* clean=1$", 10, "chan counters")

        s.wait(r"^E73UDP: NEG-READY$", 10, "negative ready")
        # bad checksum, zero checksum, short/long UDP length, truncated header
        link.send(udp6_frame(40010, 20001, b"badcsum", badcksum=True))
        link.send(udp6_frame(40011, 20001, b"zerocsum", zerocksum=True))
        link.send(udp6_frame(40012, 20001, b"short", ulen=4))
        link.send(udp6_frame(40013, 20001, b"long", ulen=8 + 5 + 50))
        trunc = bytearray(ipv6(HOST_LL, GUEST_LL, 17, 64, b"\0\0\0\0"))
        trunc[4:6] = (4).to_bytes(2, "big")
        link.send(eth(GUEST_MAC, bytes(trunc)))
        # IPv4 must not reach native UDP6
        link.send(eth(GUEST_MAC, b"\x45" + b"\0" * 59, etype=0x0800))
        # valid datagram to an unbound port
        link.send(udp6_frame(40014, 20009, b"unbound"))
        unreach = no_echo(link, 1.5, allow_unreachable=True)
        print("NEG: no UDP echo; port-unreachable=%s" % unreach)
        link.send(udp6_frame(40015, 20001, b"alive"))
        if not wait_echo(link, 40015, b"alive", 8):
            die("no post-negative ALIVE echo")
        s.wait(r"^E73UDP: NEG-RESULT", 8, "neg result")
        s.wait(r"^E73UDP: ALIVE", 8, "alive marker")

        s.wait(r"^E73UDP: SAT-READY$", 10, "sat ready")
        for i in range(20):
            link.send(udp6_frame(40100 + i, 20002, b"sat%02d" % i))
        s.wait(r"^E73UDP: SAT pending=", 10, "sat pending")
        s.wait(r"^E73UDP: CHECK sat-dropfull=([1-9][0-9]*)$", 10, "sat dropfull")

        s.wait(r"^E73UDP: TXDOWN-READY$", 10, "txdown ready")
        link.send(udp6_frame(40016, 20001, b"down"))
        no_echo(link, 1.2)
        s.wait(r"^E73UDP: TXDOWN txdown=([1-9][0-9]*)$", 10, "txdown count")

        s.wait(r"^E73UDP: CLOSE rc=0$", 15, "close")
        s.wait(r"^E73UDP: ECHO-EXIT exited=1$", 10, "echo exit")
        s.wait(r"^E73UDP: CHECK repeat-close rc=-7$", 10, "repeat close")
        s.wait(r"^E73UDP: CHECK post-close-recv rc=-7$", 10, "post-close recv")
        s.wait(r"^E73UDP: CHECK post-close-send rc=-7$", 10, "post-close send")
        s.wait(r"^E73UDP: STOP rc=0$", 15, "ipv6 stop")
        s.wait(r"^E73UDP: CHECK repeat-stop rc=-9$", 10, "repeat stop")
        s.wait(r"^E73UDP: CHECK restart-after-stop rc=-7$", 10, "restart after stop")

        m = s.wait(r"^E73UDP: COUNTERS in=(\d+) out=(\d+) noports=(\d+) inerrors=(\d+)$", 10, "counters")
        ind, outd, nop, inerr = (int(x) for x in m.groups())
        if ind < 6:
            die("udpInDatagrams too small: %d" % ind)
        if outd < 6:
            die("udpOutDatagrams too small: %d" % outd)
        if nop < 1:
            die("udpNoPorts did not increase: %d" % nop)
        if inerr < 1:
            die("udpInErrors did not increase: %d" % inerr)
        print("COUNTERS: in=%d out=%d noports=%d inerrors=%d" % (ind, outd, nop, inerr))

        s.wait(r"^E73UDP: DONE pass=1 fails=0$", 15, "done")
        if re.search(r"panic|fault|suicide", s.data):
            die("guest panic/fault marker")
    finally:
        stop_qemu(q, qlog)
        link.sock.close()
    with open(os.path.join(args.workdir, "boot-virtio.log"), "w") as f:
        f.write(s.data)
    print("PASS: real VirtIO UDP6 datagrams, checksums and negatives")


def run_none(args):
    serial_path = os.path.join(args.workdir, "serial-nonic.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, None)
    s = Serial(serial_path)
    try:
        s.wait(r"^E73UDP: NODEV n=0$", 120, "no NIC")
        s.wait(r"^E73UDP: DONE pass=1 fails=0$", 15, "no NIC done")
        if re.search(r"panic|fault|suicide", s.data):
            die("no-NIC guest panic/fault marker")
    finally:
        stop_qemu(q, qlog)
    with open(os.path.join(args.workdir, "boot-nonic.log"), "w") as f:
        f.write(s.data)
    print("PASS: absent controller (no UDP service)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qemu", required=True)
    ap.add_argument("--fwcode", required=True)
    ap.add_argument("--fwvars", required=True)
    ap.add_argument("--loader", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--espname", required=True)
    ap.add_argument("--workdir", required=True)
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
    print("PASS: E7.3 UDP6 fixture")


if __name__ == "__main__":
    main()
