# Plan2001-O: allocator-state corruption fixture.
#
# tools/mkovol REGALLOC=FILE appends FILE to the Space header's existing
# 72-byte user part.  This module is run against an image whose appended
# state is deliberately malformed.  Registration must fail with a clear
# error; it must not reset the counter to zero and start handing out
# OIDs (65 would be the first candidate of a silent reset here).

import space


class Counter:
    def __init__(self, n=0):
        self.n = n


shared = Counter(0)
alias = shared


def init():
    shared.n = 0


def run():
    try:
        space.oregister(b"must not publish")
    except OSError as e:
        if "allocator" not in str(e):
            raise AssertionError("Oreg: FAIL wrong corruption error: %s" % e)
        print("Oreg: PASS corrupt-allocator-rejected")
        print("Oreg: corrupt-allocator-detail", e)
    else:
        raise AssertionError("Oreg: FAIL corrupt allocator accepted")

    try:
        space.oregister()
    except OSError as e:
        print("Oreg: PASS corrupt-allocator-still-rejected")
        print("Oreg: corrupt-allocator-detail", e)
    else:
        raise AssertionError("Oreg: FAIL corrupt allocator later accepted")

    try:
        space.oget(65)
    except OSError:
        print("Oreg: PASS corrupt-allocator-not-reset")
    else:
        raise AssertionError("Oreg: FAIL a reset allocator created OID 65")
    return 0
