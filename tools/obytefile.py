# Plan2001-O: the first native GE/O byte-object demonstration.
#
# This module is seeded as the normal O-resident "odemo" code.  Its run()
# uses only space.oget/space.oput, which address one published O object by
# numeric OID.  The values below are independent GE/O objects; they are not
# members of the Python graph committed at OID_GRAPH.  The OIDs are PoC
# identifiers, not globally allocated object identities.

import space

HELLO_OID = 42
EMPTY_OID = 44
BINARY_OID = 45
BIG_OID = 46
SAME_A_OID = 47
SAME_B_OID = 48
OVERWRITE_OID = 49
MISSING_OID = 0x1234

HELLO = b"hello\n"
BINARY = b"\x00\xff\x00"
BIG = bytes([(i * 7 + 3) & 0xff for i in range(2048)])
SAME = b"identical bytes\n"
CHANGED = b"changed value\n"
OVER_FIRST = b"first version\n"
OVER_SECOND = b"second version\n"

# p9_space_report looks these up after every automatic run().
class Counter:
    def __init__(self, n=0):
        self.n = n


shared = Counter(0)
alias = shared


def init():
    shared.n = 0


def check(cond, tag):
    if not cond:
        raise AssertionError("Obyte: FAIL " + tag)
    print("Obyte: PASS", tag)


def expect(exc, fn, tag):
    try:
        fn()
    except exc:
        print("Obyte: PASS", tag)
        return
    raise AssertionError("Obyte: FAIL " + tag + " (no exception)")


def check_errors():
    # invalid OID values: no wrapping and no truncation
    expect(TypeError, lambda: space.oget("42"), "reject-string-oid")
    expect(TypeError, lambda: space.oget(1.5), "reject-float-oid")
    expect(OverflowError, lambda: space.oget(-1), "reject-negative-oid")
    expect(OverflowError, lambda: space.oget(1 << 64), "reject-overflow-oid")
    expect(OSError, lambda: space.oget(MISSING_OID), "missing-oid")
    expect(TypeError, lambda: space.oput(42, "not bytes"), "reject-str-data")
    expect(TypeError, lambda: space.oput(42, 7), "reject-int-data")
    expect(OverflowError, lambda: space.oput(-1, b"x"), "reject-negative-put")

    # implementation-reserved OIDs: the Python graph, Environment, code
    # region, native-exec fixtures and low bookkeeping IDs
    for oid, tag in (
        (1, "reserved-roots"),
        (2, "reserved-first"),
        (0xfffffffffffffffd, "reserved-graph"),
        (0xfffffffffffffffc, "reserved-env"),
        (0xffffffff00000000, "reserved-code"),
        (0xfffffffffffffffe, "reserved-upgrade-meta"),
        (0x4f45584543000001, "reserved-exec-test"),
        (0x4f45584543000002, "reserved-badexec-test"),
        (0x4f45584543000003, "reserved-mp-exec"),
    ):
        expect(ValueError, lambda oid=oid: space.oput(oid, b"x"), tag)

    # 1 MiB is the documented conservative PoC whole-object limit
    expect(ValueError,
        lambda: space.oput(50, b"x" * (1024 * 1024 + 1)), "over-limit-put")

    # none of the failed calls above may have changed the live object
    check(space.oget(HELLO_OID) == HELLO, "hello-intact-after-errors")


def first_boot():
    space.oput(HELLO_OID, HELLO)
    check(space.oget(HELLO_OID) == HELLO, "first-put-hello")
    check_errors()
    space.oput(EMPTY_OID, b"")
    check(space.oget(EMPTY_OID) == b"", "empty-bytes")
    space.oput(BINARY_OID, BINARY)
    check(space.oget(BINARY_OID) == BINARY, "binary-nul-and-ff")
    space.oput(BIG_OID, BIG)
    check(space.oget(BIG_OID) == BIG, "larger-than-Objchunk")
    space.oput(SAME_A_OID, SAME)
    space.oput(SAME_B_OID, SAME)
    check(space.oget(SAME_A_OID) == SAME and space.oget(SAME_B_OID) == SAME,
        "two-oids-same-bytes")
    space.oput(SAME_A_OID, CHANGED)
    check(space.oget(SAME_A_OID) == CHANGED, "first-oid-changed")
    check(space.oget(SAME_B_OID) == SAME, "second-oid-unchanged")
    space.oput(OVERWRITE_OID, OVER_FIRST)
    check(space.oget(OVERWRITE_OID) == OVER_FIRST, "overwrite-first")
    print("Obyte: PASS first-boot")
    return 0


def later_boot():
    check(space.oget(HELLO_OID) == HELLO, "reboot-hello")
    check(space.oget(EMPTY_OID) == b"", "reboot-empty")
    check(space.oget(BINARY_OID) == BINARY, "reboot-binary")
    check(space.oget(BIG_OID) == BIG, "reboot-larger-than-Objchunk")
    check(space.oget(SAME_A_OID) == CHANGED, "reboot-first-oid-changed")
    check(space.oget(SAME_B_OID) == SAME, "reboot-second-oid-unchanged")
    check_errors()
    current = space.oget(OVERWRITE_OID)
    if current == OVER_FIRST:
        space.oput(OVERWRITE_OID, OVER_SECOND)
        check(space.oget(OVERWRITE_OID) == OVER_SECOND, "overwrite-second")
    elif current == OVER_SECOND:
        print("Obyte: PASS overwrite-persisted")
    else:
        raise AssertionError("Obyte: FAIL unexpected overwrite value")
    print("Obyte: PASS reboot")
    return 0


def run():
    try:
        value = space.oget(HELLO_OID)
    except OSError:
        value = None
    if value is None:
        return first_boot()
    if value != HELLO:
        raise AssertionError("Obyte: FAIL unexpected OID 42 value")
    return later_boot()
