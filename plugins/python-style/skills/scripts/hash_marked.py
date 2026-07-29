#!/usr/bin/env python3
"""hash_marked.py — print the integrity hash of the code a marker covers.

The hash is md5 of exactly what `show_marked.py` prints, encoded UTF-8. That is
the whole definition: this script does not re-derive the span, it asks
`show_marked` for it (rule 25), so the two can never disagree about what a
marker covers.

md5 is a change detector here, not a security control. It answers "did this code
move since the test last passed", where nobody is trying to forge a collision.

Usage:  python3 hash_marked.py <marker> [<dir>]
Exit:   0 = printed, 1 = marker not found, 2 = usage error
"""
import hashlib
import pathlib
import sys

import show_marked


def digest_for(name: str, root: pathlib.Path) -> str:
    """The integrity hash recorded against a marker.

    @throws SystemExit no span carries that marker, or more than one does
        (through `show_marked.find`).
    """
    span = show_marked.find(name, root)   # raises SystemExit if the marker is missing
    _payload = span.code.encode("utf-8")
    return hashlib.md5(_payload).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2

    _root = pathlib.Path(argv[2]) if len(argv) == 3 else pathlib.Path(".")
    print(digest_for(argv[1], _root))   # raises SystemExit if the marker is missing
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
