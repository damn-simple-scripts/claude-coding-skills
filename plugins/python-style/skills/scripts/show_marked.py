#!/usr/bin/env python3
"""show_marked.py — print the code a marker covers.

This script is the definition of "the code between the markers". Anything that
needs that span asks this module for it rather than re-deriving it, so there is
exactly one answer (rule 25).

The span is exclusive of the marker lines. Every line is right-stripped and the
block is stripped, so re-indenting a file or leaving a trailing space does not
change what a marker covers.

Usage:  python3 show_marked.py <marker> [<dir>]
Exit:   0 = printed, 1 = marker not found, 2 = usage error

Single-file mode: set USE_FILE=true and SHOW_FILE=<path.py> to read exactly one
file instead of walking a tree — the fast path for fetching a marked helper.
USE_FILE is the switch (default off) so a stray SHOW_FILE in the environment
cannot silently redirect the default directory scan.
"""
import itertools
import os
import pathlib
import re
import sys
from typing import NamedTuple

_START_PAT = re.compile(r"^### unit-tested function start: (?P<name>\S+)[ \t]*$", re.M | re.U)
_END_PAT = re.compile(r"^### unit-tested function end: (?P<name>\S+)[ \t]*$", re.M | re.U)


class Span(NamedTuple):
    name: str
    path: pathlib.Path
    line: int
    code: str


def _read(path: pathlib.Path) -> str:
    """@throws SystemExit the file cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def canonical(code: str) -> str:
    """The exact text a marker covers. Every consumer of a span goes through here."""
    _stripped = code.strip()
    _lines = _stripped.splitlines()  # one marked span; bounded by the marker block
    _lines = (line.rstrip() for line in _lines)
    return "\n".join(_lines)


def spans_in(path: pathlib.Path) -> list[Span]:
    """Every marked span in one file.

    @throws SystemExit a marker is unpaired, duplicated, or its end precedes its start.
    """
    source = _read(path)
    starts = list(_START_PAT.finditer(source))
    ends = list(_END_PAT.finditer(source))

    _start_names = list(m.group("name") for m in starts)
    _end_names = list(m.group("name") for m in ends)
    for name in _start_names:
        if _start_names.count(name) > 1:
            raise SystemExit(f"{path}: start marker for {name!r} appears more than once")
        if name not in _end_names:
            raise SystemExit(f"{path}: start marker for {name!r} has no end marker")
    for name in _end_names:
        if name not in _start_names:
            raise SystemExit(f"{path}: end marker for {name!r} has no start marker")

    _ends = dict((m.group("name"), m) for m in ends)
    out = []
    for start in starts:
        name = start.group("name")
        end = _ends[name]
        if end.start() < start.end():
            raise SystemExit(f"{path}: end marker for {name!r} precedes its start marker")
        _code = canonical(source[start.end():end.start()])
        _line = source[:start.start()].count("\n") + 1
        out.append(Span(name, path, _line, _code))
    return out


def _file_mode() -> bool:
    """Whether USE_FILE selects single-file mode. Only a truthy token turns it on."""
    return os.environ.get("USE_FILE", "").strip().lower() in ("1", "true", "yes", "on")


def _sources(root: pathlib.Path) -> list[pathlib.Path]:
    """The files a search scans: every `.py` under `root`, or SHOW_FILE alone.

    @throws SystemExit `root` is not a directory in tree mode, or USE_FILE is set
        with no readable SHOW_FILE.
    """
    if not _file_mode():
        if not root.is_dir():
            raise SystemExit(f"{root} is not a directory — rglob would report every marker missing")
        return sorted(root.rglob("*.py"))

    _named = os.environ.get("SHOW_FILE", "").strip()
    if len(_named) == 0:
        raise SystemExit("USE_FILE is set but SHOW_FILE names no file")
    _file = pathlib.Path(_named)
    if not _file.is_file():
        raise SystemExit(f"SHOW_FILE={_named} is not a file")
    return [_file]


def find(name: str, root: pathlib.Path) -> Span:
    """The one span a marker names.

    Scans SHOW_FILE alone when USE_FILE is set, else every `.py` under `root`.

    @throws SystemExit the source set is unusable, no span carries that marker,
        or more than one does.
    """
    _files = _sources(root)
    _per_file = (spans_in(path) for path in _files)          # one span-iterator per file
    _spans = itertools.chain.from_iterable(_per_file)        # flatten as a separate step (rule 3t)
    _matches = list(span for span in _spans if span.name == name)

    if len(_matches) == 0:
        _where = os.environ.get("SHOW_FILE", "").strip() if _file_mode() else root
        raise SystemExit(f"no marked function named {name!r} under {_where}")
    if len(_matches) > 1:
        _where = ", ".join(f"{s.path}:{s.line}" for s in _matches)
        raise SystemExit(f"marker {name!r} is defined more than once: {_where}")
    return _matches[0]


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2

    _root = pathlib.Path(argv[2]) if len(argv) == 3 else pathlib.Path(".")
    span = find(argv[1], _root)   # raises SystemExit if the marker is missing or doubled
    print(span.code)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
