#!/usr/bin/env python3
"""E7.1 VirtIO Ethernet fixture.

Boots the opt-in 9pc64e71 kernel through the UEFI loader in disposable QEMU,
using a QEMU dgram netdev as a raw L2 Ethernet peer.  No tap/bridge and no
host privileges are needed.

Evidence is fail-closed and correlated:
  * host -> guest frame appears in the kernel's native RX sink marker;
  * guest -> host frame is read from the host UDP socket and must carry the
    probe's magic/EtherType;
  * the legacy #l attach/read test gets a separate host frame;
  * a second boot with -nic none must report NODEV.

The probe's serial markers are the only guest-side assertion channel.
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time

NIC_MAC = bytes.fromhex("525400123456")
BCAST = b"\xff" * 6


def die(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def make_esp(workdir, loader, kernel, espname):
    esp = os.path.join(workdir, "esp.img")
    if os.path.exists(esp):
        os.unlink(esp)
    subprocess.run(["mformat", "-C", "-i", esp, "-T", "65536", "-h", "64", "-s", "32", "::"],
                   check=True)
    subprocess.run(["mmd", "-i", esp, "::/EFI", "::/EFI/BOOT"], check=True)
    subprocess.run(["mcopy", "-i", esp, loader, "::/EFI/BOOT/" + espname], check=True)
    ini = os.path.join(workdir, "plan9.ini")
    with open(ini, "w") as f:
        f.write("bootfile=/%s\nconsole=0\ne71ether=1\n" % os.path.basename(kernel))
    subprocess.run(["mcopy", "-i", esp, kernel, ini, "::/"], check=True)
    return esp


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
            time.sleep(0.2)
        tail = "\n".join(self.data.splitlines()[-40:])
        die("%s: timeout waiting for /%s/; serial tail:\n%s" % (what, pattern, tail))


def start_qemu(args, serial_path, net=None):
    qargs = [
        args.qemu, "-name", "plan2001-e71", "-nodefaults",
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
            ":".join("%02x" % b for b in NIC_MAC),
        ]
    log = open(os.path.join(args.workdir, "qemu-%s.log" % os.path.basename(serial_path)),
               "wb")
    p = subprocess.Popen(qargs, stdout=log, stderr=subprocess.STDOUT)
    return p, log


def stop_qemu(p, log):
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    log.close()


def ethframe(dst, etype, magic, length=64):
    b = bytearray(length)
    b[0:6] = dst
    b[6:12] = bytes.fromhex("020000000001")
    b[12:14] = etype.to_bytes(2, "big")
    m = magic.encode()
    b[14:14 + len(m)] = m
    return bytes(b)


def check_frame(frame, etype, magic, what):
    if len(frame) < 14 + len(magic):
        die("%s: short frame (%d bytes)" % (what, len(frame)))
    t = int.from_bytes(frame[12:14], "big")
    if t != etype:
        die("%s: EtherType 0x%04x, want 0x%04x" % (what, t, etype))
    off = 14
    if frame[off:off + len(magic)] != magic.encode():
        die("%s: magic mismatch: %r" % (what, frame[off:off + 16]))


def require(serial, pattern, what):
    if not re.search(pattern, serial.data, re.M):
        die("%s: missing /%s/" % (what, pattern))


def run_nic(args):
    p1 = free_udp_port()
    p2 = free_udp_port()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", p2))
    sock.settimeout(0.2)
    serial_path = os.path.join(args.workdir, "serial-virtio.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, net=(p1, p2))
    s = Serial(serial_path)
    try:
        s.wait(r"^E71ETHER: INIT rc=1 ", 120, "boot/init")
        s.wait(r"^E71ETHER: READY$", 30, "attach")
        # Host-generated frame reaches the real VirtIO RX handler.
        host_rx = ethframe(NIC_MAC, 0x88B5, "E71RXRX")
        sock.sendto(host_rx, ("127.0.0.1", p1))

        # Guest -> host frame must be the probe's experimental EtherType.
        got = None
        end = time.time() + 15
        while time.time() < end:
            try:
                got, _ = sock.recvfrom(65536)
                break
            except socket.timeout:
                pass
        if got is None:
            die("no guest Ethernet frame was observed on the host dgram socket")
        check_frame(got, 0x88B6, "E71TXTX", "native TX")
        with open(os.path.join(args.workdir, "host-tx.hex"), "w") as f:
            f.write(got.hex() + "\n")
        with open(os.path.join(args.workdir, "host-rx.hex"), "w") as f:
            f.write(host_rx.hex() + "\n")
        print("HOST-TX: len=%d ethertype=0x88b6 magic=E71TXTX" % len(got))

        s.wait(r"^E71ETHER: TX .*ok=1$", 15, "native TX marker")
        s.wait(r"^E71ETHER: RX len=64 type=0x88b5 match=1$", 20, "native RX marker")

        s.wait(r"^E71ETHER: LEGACY-READY$", 30, "legacy attach")
        host_legacy = ethframe(BCAST, 0x86DD, "E71LEGACY")
        sock.sendto(host_legacy, ("127.0.0.1", p1))
        with open(os.path.join(args.workdir, "host-legacy.hex"), "w") as f:
            f.write(host_legacy.hex() + "\n")
        s.wait(r"^E71ETHER: LEGACY len=64 type=0x86dd match=1$", 20,
               "legacy #l RX")

        s.wait(r"^E71ETHER: DONE pass=1 fails=0$", 30, "done")

        require(s, r"^E71ETHER: CHECK preattach rc=-2$", "preattach negative")
        require(s, r"^E71ETHER: NEG shortlen rc=-4$", "short-length negative")
        require(s, r"^E71ETHER: NEG longlen rc=-4$", "long-length negative")
        require(s, r"^E71ETHER: NEG rxregister-busy rc=-7$", "RX busy negative")
        require(s, r"^E71ETHER: NEG rxunregister-mismatch rc=-9$",
                "RX unregister negative")
        require(s, r"^E71ETHER: NEG rxregister-nil rc=-9$", "RX nil negative")
        require(s, r"^E71ETHER: CHECK down rc=-5$", "down negative")
        require(s, r"^E71ETHER: CHECK queue-full rc=-2$", "full-queue negative")
        require(s, r"^E71ETHER: CHECK queue-closed rc=-1$", "closed-queue negative")
        require(s, r"^E71ETHER: NEG rxunregister-twice rc=-9$",
                "RX unregister-twice negative")
        require(s, r"^E71ETHER: CHAN-NATIVE .* clean=1$",
                "native path touched Chan counters")
        if re.search(r"panic|fault|suicide", s.data):
            die("guest panic/fault marker present")
    finally:
        stop_qemu(q, qlog)
        sock.close()

    with open(os.path.join(args.workdir, "boot-virtio.log"), "w") as f:
        f.write(s.data)
    print("PASS: VirtIO native TX/RX, legacy #l RX, negatives")
    return s


def run_none(args):
    serial_path = os.path.join(args.workdir, "serial-nonic.log")
    if os.path.exists(serial_path):
        os.unlink(serial_path)
    q, qlog = start_qemu(args, serial_path, net=None)
    s = Serial(serial_path)
    try:
        s.wait(r"^E71ETHER: NODEV n=0$", 120, "no-NIC")
        s.wait(r"^E71ETHER: DONE pass=1 fails=0$", 15, "no-NIC done")
        if re.search(r"panic|fault|suicide", s.data):
            die("no-NIC guest panic/fault marker present")
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
    print("PASS: E7.1 Ethernet fixture")


if __name__ == "__main__":
    main()
