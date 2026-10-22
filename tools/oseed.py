# Plan2001 Stage 4: run in the build VM by tools/mkovol.  It compiles the
# demo source with the tree's MicroPython (space.define), then writes the
# seed files the userspace gefs -i reads to make the O objects.  These
# files are host preparation inputs, never runtime program storage.

import space

SRC = "/tmp/odemo.py"
SEED = "/tmp/seed"
CODE_OID = 0xffffffff00000000
NATIVEEXEC = "/tmp/nativeexec"
EXEC_OID = 0x4f45584543000001
BADEXEC_OID = 0x4f45584543000002

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
if x is not None:
    open(SEED + "/exe", "wb").write(x)
    open(SEED + "/exeoid", "w").write("%016x" % EXEC_OID)
    open(SEED + "/bad", "wb").write(x[:72])
    open(SEED + "/badoid", "w").write("%016x" % BADEXEC_OID)
    print("seed: nativeexec", len(x), "%016x" % EXEC_OID)
