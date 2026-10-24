#!/usr/bin/env python3
"""E7.2 real-VirtIO IPv6/NDP/ICMPv6 fixture.

Boots 9pc64e72 through the UEFI loader with a QEMU dgram raw-L2 netdev.  The
host sends a valid ICMPv6 Neighbor Solicitation and Echo Request for the
guest's link-local address and verifies the guest's NA and Echo Reply bytes,
checksums and addresses.  Malformed/protocol-negative frames are checked to
produce no reply.  The guest's serial markers prove the native worker saw the
frames and that the native Chan counters stayed zero.
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
ALLNODES = bytes.fromhex("ff020000000000000000000000000001")
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
    # "fe80::5054:ff:fe12:3456"
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


def echo_request(seq, payload=b"e72-echo"):
    ident = b"\x12\x34"
    body = ident + seq.to_bytes(2, "big") + payload
    return eth(GUEST_MAC, icmp6(HOST_LL, GUEST_LL, 128, 0, body, 64)), ident, seq, payload


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
        tail = "\n".join(self.data.splitlines()[-50:])
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
        f.write("bootfile=/%s\nconsole=0\ne72ipv6=1\n" % os.path.basename(kernel))
    subprocess.run(["mcopy", "-i", esp, kernel, ini, "::/"], check=True)
    return esp


def start_qemu(args, serial_path, net):
    qargs = [
        args.qemu, "-name", "plan2001-e72", "-nodefaults",
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


def wait_reply(link, typ, timeout=10, seq=None, ident=None, payload=None):
    end = time.time() + timeout
    while time.time() < end:
        f = link.recv(0.2)
        if f is None:
            continue
        p = parse_ipv6(f)
        if p is None:
            continue
        ip, icmp = p
        if icmp:
            print("RX-HOST: icmp=%d src=%s dst=%s" % (icmp[0], fmt_ll(ip[8:24]), fmt_ll(ip[24:40])))
        if len(icmp) < 8 or icmp[0] != typ:
            if icmp and icmp[0] == 135:
                # guest solicits our link-layer address; answer it
                pkt = parse_ns(ip, icmp)
                if pkt is not None:
                    link.send(na(pkt))
            continue
        src, dst = ip[8:24], ip[24:40]
        if not icmp_ok(src, dst, icmp):
            continue
        if typ == 136:
            target = icmp[8:24]
            flags = icmp[4]
            tlla = None
            o = 24
            while o + 8 <= len(icmp):
                if icmp[o+1] == 0:
                    break
                if icmp[o] == 2 and icmp[o+1] == 1:
                    tlla = icmp[o+2:o+8]
                o += icmp[o+1] * 8
            if target == GUEST_LL and tlla == GUEST_MAC and src == GUEST_LL:
                return ("na", flags, dst)
        elif typ == 129:
            if ident is not None and icmp[4:6] == ident and icmp[6:8] == seq.to_bytes(2, "big") \
               and icmp[8:] == payload and src == GUEST_LL and dst == HOST_LL:
                return ("echo", None, dst)
    return None


def parse_ns(ip, icmp):
    if len(icmp) < 24:
        return None
    return icmp[8:24]


def drain(link):
    while link.recv(0.05) is not None:
        pass


def run_nic(args):
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
        s.wait(r"^E72IPV6: READY$", 120, "ready")
        m = s.wait(r"^E72IPV6: LLADDR (fe80:[0-9a-f:]+)$", 10, "lladdr")
        global GUEST_LL
        GUEST_LL = parse_ll(m.group(1))
        print("GUEST-LL:", fmt_ll(GUEST_LL))

        link.send(ns(GUEST_LL))
        r = wait_reply(link, 136, 10)
        if r is None:
            die("no valid Neighbor Advertisement from the guest")
        print("NA: flags=0x%02x" % r[1])

        req, ident, seq, payload = echo_request(1)
        link.send(req)
        r = wait_reply(link, 129, 10, seq=seq, ident=ident, payload=payload)
        if r is None:
            die("no valid Echo Reply from the guest")
        print("ECHO: id=0x1234 seq=1 payload=%r" % payload)

        s.wait(r"^E72IPV6: CHAN-NATIVE .* clean=1$", 10, "chan counters")
        s.wait(r"^E72IPV6: NEG-READY$", 10, "neg ready")

        # Protocol/filter negatives.  No replies are allowed.
        drain(link)
        bad = bytearray(ns(GUEST_LL))
        bad[14+40+2] ^= 0xff                     # bad ICMPv6 checksum
        link.send(bytes(bad))
        bad = bytearray(ns(GUEST_LL))
        bad[14+7] = 64                            # invalid NDP hop limit
        link.send(bytes(bad))
        link.send(eth(GUEST_MAC, b"\x45" + b"\0"*59, etype=0x0800))  # IPv4
        link.send(eth(GUEST_MAC, b"\x60" + b"\0"*20, etype=0x86DD))  # truncated
        # bad IPv6 version (0x4) with valid EtherType
        link.send(eth(GUEST_MAC, b"\x40" + b"\0"*59, etype=0x86DD))
        # IPv6 payload length larger than the actual frame
        bad = bytearray(80)
        bad[0] = 0x60
        bad[4:6] = (200).to_bytes(2, "big")
        bad[6] = 58
        bad[7] = 64
        bad[8:24] = HOST_LL
        bad[24:40] = GUEST_LL
        link.send(eth(GUEST_MAC, bytes(bad), etype=0x86DD))
        # valid Echo for a different, non-local address
        other = parse_ll("fe80::dead:beef")
        body = b"\x12\x34\x00\x09e72-wrong"
        link.send(eth(GUEST_MAC, icmp6(HOST_LL, other, 128, 0, body, 64)))

        end = time.time() + 1.2
        while time.time() < end:
            f = link.recv(0.1)
            if f is None:
                continue
            p = parse_ipv6(f)
            if p is not None and p[1] and p[1][0] in (129, 136):
                die("negative frame produced ICMPv6 reply type %d" % p[1][0])

        req, ident, seq, payload = echo_request(2, b"e72-alive")
        link.send(req)
        r = wait_reply(link, 129, 8, seq=seq, ident=ident, payload=payload)
        if r is None:
            die("guest did not answer the post-negative Echo Request")
        print("ALIVE: echo seq=2")

        s.wait(r"^E72IPV6: TXDOWN-READY$", 20, "txdown ready")
        drain(link)
        req, ident, seq, payload = echo_request(3, b"e72-down")
        link.send(req)
        r = wait_reply(link, 129, 1.2, seq=seq, ident=ident, payload=payload)
        if r is not None:
            die("guest replied while link was down")
        s.wait(r"^E72IPV6: TXDOWN n=([1-9][0-9]*)$", 10, "txdown count")

        s.wait(r"^E72IPV6: DONE pass=1 fails=0$", 20, "done")
        for pat, what in [
            (r"^E72IPV6: POSITIVE rx=[1-9][0-9]* tx=[1-9][0-9]*", "positive stats"),
            (r"^E72IPV6: CHECK queue-sat drop=[1-9][0-9]*$", "queue saturation"),
            (r"^E72IPV6: CHECK txq-full rc=-2$", "txq full"),
            (r"^E72IPV6: CHECK txq-closed rc=-1$", "txq closed"),
            (r"^E72IPV6: CHECK repeat-start rc=-7$", "repeat start"),
            (r"^E72IPV6: CHECK repeat-attach rc=0$", "repeat attach"),
            (r"^E72IPV6: STOP rc=0$", "stop"),
            (r"^E72IPV6: CHECK repeat-stop rc=-9$", "repeat stop"),
            (r"^E72IPV6: FINAL worker_exited=1 ", "worker exited"),
        ]:
            if not re.search(pat, s.data, re.M):
                die("missing marker /%s/" % what)
        if re.search(r"panic|fault|suicide", s.data):
            die("guest panic/fault marker")
    finally:
        stop_qemu(q, qlog)
        link.sock.close()
    with open(os.path.join(args.workdir, "boot-virtio.log"), "w") as f:
        f.write(s.data)
    print("PASS: real VirtIO NDP NA + ICMPv6 Echo Reply + negatives")


def run_none(args):
    serial_path = os.path.join(args.workdir, "serial-nonic.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, None)
    s = Serial(serial_path)
    try:
        s.wait(r"^E72IPV6: NODEV n=0$", 120, "no NIC")
        s.wait(r"^E72IPV6: DONE pass=1 fails=0$", 15, "no NIC done")
        if re.search(r"panic|fault|suicide", s.data):
            die("no-NIC guest panic/fault marker")
    finally:
        stop_qemu(q, qlog)
    with open(os.path.join(args.workdir, "boot-nonic.log"), "w") as f:
        f.write(s.data)
    print("PASS: absent controller (NODEV)")


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
    print("PASS: E7.2 IPv6 fixture")


if __name__ == "__main__":
    main()
