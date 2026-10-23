# Plan2001 Stage 4: run in the build VM by tools/mkovol.  It compiles the
# demo source with the tree's MicroPython (space.define), then writes the
# seed files the userspace gefs -i reads to make the O objects.  These
# files are host preparation inputs, never runtime program storage.

import space

SRC = "/tmp/odemo.py"
SEED = "/tmp/seed"
CODE_OID = 0xffffffff00000000
NATIVEEXEC = "/tmp/nativeexec"
RAWEXEC = "/tmp/rawexec"
MPEXEC = "/tmp/mpexec"
REGALLOC = "/tmp/regalloc"
EXEC_OID = 0x4f45584543000001
BADEXEC_OID = 0x4f45584543000002
MP_OID = 0x4f45584543000003
RAWEXEC_OID = 0x4f45584543000004

h = space.define(SRC)
mpy = "/usr/glenda/lib/mod/" + h + ".mpy"
b = open(mpy, "rb").read()
env = ("runtime " + space.runtime + "\n"
       "odemo " + h + " " + space.hash(b) + " " + "%016x" % CODE_OID + "\n")
open(SEED + "/env", "w").write(env)
open(SEED + "/envhex", "w").write(space.hash(env))
open(SEED + "/mod/" + h + ".mpy", "wb").write(b)
print("seed: odemo", h, space.hash(b), "%016x" % CODE_OID, len(b))

try:
    x = open(NATIVEEXEC, "rb").read()
except OSError:
    x = None
try:
    r = open(RAWEXEC, "rb").read()
except OSError:
    r = None
try:
    m = open(MPEXEC, "rb").read()
except OSError:
    m = None

# The interpreter must be stored byte for byte: no header patching.  Write
# the copy the seeder reads and read it back before gefs -i stores it.
try:
    a = open(REGALLOC, "rb").read()
except OSError:
    a = None
if a is not None:
    open(SEED + "/alloc", "wb").write(a)
    print("seed: regalloc", len(a), space.hash(a))

if m is not None:
    open(SEED + "/mp", "wb").write(m)
    y = open(SEED + "/mp", "rb").read()
    if y != m:
        raise OSError("seed: mpexec changed while copying")
    open(SEED + "/mpoid", "w").write("%016x" % MP_OID)
    print("seed: mpexec", len(m), "%016x" % MP_OID, space.hash(m), "unchanged")

if r is not None:
    # Experiment C fixture: preserve the target bytes exactly.
    open(SEED + "/rawexec", "wb").write(r)
    y = open(SEED + "/rawexec", "rb").read()
    if y != r:
        raise OSError("seed: rawexec changed while copying")
    open(SEED + "/rawexecoid", "w").write("%016x" % RAWEXEC_OID)
    print("seed: rawexec", len(r), "%016x" % RAWEXEC_OID, space.hash(r), "unchanged")

if x is not None:
    orig = x
    x = x[:12] + b"\xff\xff\xff\xff" + x[16:]
    open(SEED + "/exe", "wb").write(x)
    open(SEED + "/exeoid", "w").write("%016x" % EXEC_OID)
    open(SEED + "/bad", "wb").write(orig[:72])
    open(SEED + "/badoid", "w").write("%016x" % BADEXEC_OID)
    print("seed: nativeexec", len(x), "%016x" % EXEC_OID, "bss 0xffffffff")
elif m is not None:
    # The malformed-object check uses a truncated valid header.  The
    # interpreter bytes above are never modified.
    open(SEED + "/bad", "wb").write(m[:72])
    open(SEED + "/badoid", "w").write("%016x" % BADEXEC_OID)
    print("seed: badexec", 72, "%016x" % BADEXEC_OID)
