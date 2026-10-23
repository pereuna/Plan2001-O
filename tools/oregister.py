# Plan2001-O: local native OID registration regression module.
#
# Seeded as the normal O-resident "odemo" code.  It uses only the native
# space.oregister/space.oget/space.oput calls.  OIDs saved in the Python
# graph are test bookkeeping only; the allocator itself lives in the
# native GE/O Space header and does not read this graph.
#
# Fresh image layout (allocator base 64):
#   64, 70  explicitly written native objects (must be skipped)
#   65      empty payload
#   66      hello
#   67      embedded-NUL binary
#   68      2048-byte multi-chunk payload
#   69, 71  two registrations with identical bytes (70 is occupied)
#   72      registration after revising 69 with oput

import space

MANUAL64 = b"manual-64\n"
MANUAL70 = b"manual-70\n"
HELLO = b"hello\n"
BINARY = b"\x00\xff\x00"
BIG = bytes([(i * 7 + 3) & 0xff for i in range(2048)])
SAME = b"identical bytes\n"
CHANGED = b"revised one\n"
MISSING = 0x12345678


class Counter:
    def __init__(self, n=0):
        self.n = n


class State:
    def __init__(self):
        self.boots = 0
        self.max_oid = 0
        self.empty = None
        self.hello = None
        self.binary = None
        self.big = None
        self.same1 = None
        self.same2 = None
        self.rev = None
        self.boot2 = None
        self.boot3 = None
        self.boot4 = None


shared = Counter(0)
alias = shared
state = State()


def init():
    shared.n = 0


def check(cond, tag):
    if not cond:
        raise AssertionError("Oreg: FAIL " + tag)
    print("Oreg: PASS", tag)


def expect(exc, fn, tag):
    try:
        fn()
    except exc:
        print("Oreg: PASS", tag)
        return
    raise AssertionError("Oreg: FAIL " + tag + " (no exception)")


def verify_saved():
    check(space.oget(state.empty) == b"", "saved-empty")
    check(space.oget(state.hello) == HELLO, "saved-hello")
    check(space.oget(state.binary) == BINARY, "saved-binary")
    check(space.oget(state.big) == BIG, "saved-big")
    check(space.oget(state.same1) == CHANGED, "saved-revised")
    check(space.oget(state.same2) == SAME, "saved-original")
    check(space.oget(state.rev) == b"rev\n", "saved-revision-registration")
    check(space.oget(64) == MANUAL64, "saved-manual-64")
    check(space.oget(70) == MANUAL70, "saved-manual-70")
    if state.boot2 is not None:
        check(space.oget(state.boot2) == b"boot2\n", "saved-boot2")
    if state.boot3 is not None:
        check(space.oget(state.boot3) == b"boot3\n", "saved-boot3")


def first_boot():
    expect(TypeError, lambda: space.oregister("not bytes"),
        "reject-str-data")
    expect(TypeError, lambda: space.oregister(7), "reject-int-data")
    expect(ValueError,
        lambda: space.oregister(b"x" * (1024 * 1024 + 1)), "over-limit-data")
    expect(OSError, lambda: space.oget(MISSING), "missing-before-write")

    space.oput(64, MANUAL64)
    space.oput(70, MANUAL70)

    empty = space.oregister()
    check(isinstance(empty, int), "fresh-oid-is-int")
    check(0 < empty < 0xffffffff00000000, "fresh-oid-in-range")
    check(empty == 65 and empty != 64, "skip-explicit-candidate")
    check(space.oget(empty) == b"", "fresh-empty-payload")
    check(space.oget(64) == MANUAL64, "manual-64-intact")

    hello = space.oregister(HELLO)
    check(hello == 66, "fresh-second-oid")
    check(space.oget(hello) == HELLO, "fresh-hello")
    check(space.oget(hello) != b"", "missing-distinct-from-empty")
    expect(OSError, lambda: space.oget(MISSING), "missing-oid")

    binary = space.oregister(BINARY)
    check(binary == 67, "fresh-binary-oid")
    check(space.oget(binary) == BINARY, "fresh-binary-nul-ff")

    big = space.oregister(BIG)
    check(big == 68, "fresh-big-oid")
    check(space.oget(big) == BIG, "fresh-multichunk")

    same1 = space.oregister(SAME)
    check(same1 == 69, "fresh-same-first")
    same2 = space.oregister(SAME)
    check(same1 != same2, "equal-bytes-distinct-oid")
    check(same2 == 71 and space.oget(70) == MANUAL70,
        "skip-manual-future-candidate")
    check(space.oget(same1) == SAME and space.oget(same2) == SAME,
        "equal-bytes-both-readable")

    space.oput(same1, CHANGED)
    check(space.oget(same1) == CHANGED, "revision-changed")
    check(space.oget(same2) == SAME, "revision-other-intact")

    rev = space.oregister(b"rev\n")
    check(rev == 72, "revision-did-not-allocate")
    check(space.oget(rev) == b"rev\n", "revision-registration-payload")

    state.empty = empty
    state.hello = hello
    state.binary = binary
    state.big = big
    state.same1 = same1
    state.same2 = same2
    state.rev = rev
    state.max_oid = rev
    state.boots = 1
    print("Oreg: PASS first-boot")
    return 0


def later_boot():
    verify_saved()
    boot = state.boots + 1
    n = space.oregister(b"boot%d\n" % boot)
    check(n == state.max_oid + 1, "new-oid-strictly-above")
    check(n not in (state.empty, state.hello, state.binary, state.big,
        state.same1, state.same2, state.rev), "new-oid-unused")
    state.max_oid = n

    if boot == 2:
        check(space.oget(n) == b"boot2\n", "reboot-new-payload")
        state.boot2 = n
        state.boots = 2
        print("Oreg: PASS second-boot")
        return 0

    if boot == 3:
        check(space.oget(n) == b"boot3\n", "third-new-payload")
        state.boot3 = n
        state.boots = 3
        print("Oreg: PASS third-boot")
        return 0

    if boot == 4:
        check(space.oget(n) == b"boot4\n", "fourth-new-payload")
        state.boot4 = n
        state.boots = 4
        print("Oreg: PASS fourth-boot")
        return 0

    raise AssertionError("Oreg: FAIL unexpected boot count")


def run():
    if state.boots == 0:
        return first_boot()
    if state.boots == 2:
        # reads and failed reads must not advance the allocator or
        # create an object; the next registration is exactly max+1
        for _ in range(16):
            verify_saved()
            expect(OSError, lambda: space.oget(MISSING), "readonly-missing")
    return later_boot()
