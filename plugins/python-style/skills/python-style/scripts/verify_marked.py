#!/usr/bin/env python3
"""verify_marked.py — run the test for a marker, then record that it passed.

Generates missing sample data if the claim records a generator, runs the test
that claims the marker, and — only if it passed — rewrites the `integrity` and
`last time passed` lines.

Nothing writes those two lines by hand. A stale count looks like a count; a stale
md5 looks like proof, so it has to come from the tool that watched the test pass.

Usage:  python3 verify_marked.py <marker> [<dir>]
Exit:   0 = passed and stamped, 1 = failed or unstamped, 2 = usage error
"""
import datetime
import importlib.util
import pathlib
import re
import sys
import unittest
from typing import NamedTuple

import hash_marked

_FOR_PAT = re.compile(r"^### unit-test for: (?P<name>\S+)[ \t]*$", re.M | re.U)
_INTEGRITY_PAT = re.compile(r"^# integrity: (?P<md5>\S+)[ \t]*$", re.M | re.U)
_PASSED_PAT = re.compile(r"^# last time passed: (?P<when>.+?)[ \t]*$", re.M | re.U)
_SAMPLE_PAT = re.compile(r"^# depends on sample: (?P<path>\S+)[ \t]*$", re.M | re.U)
_GENERATOR_PAT = re.compile(r"^# sample generator: (?P<call>.+?)[ \t]*$", re.M | re.U)
# Deliberately not $-anchored (rule 3r): this extracts the name off the front of a
# class/def line, whose tail is a base list or a signature we do not care about.
_TARGET_PAT = re.compile(r"^(?:class (?P<cls>Test\w+)|def (?P<fn>test_\w+))", re.M | re.U)


class Claim(NamedTuple):
    name: str
    path: pathlib.Path
    line: int
    header_index: int
    samples: tuple
    generator: str
    target: str


def _read(path: pathlib.Path) -> str:
    """@throws SystemExit the file cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def block_bounds(source: str, header_index: int) -> tuple[int, int]:
    """Where the comment block under one header starts and ends, in `source` as it is now.

    Stamping rewrites the file, so an offset taken from an earlier read is only
    valid until the first write. Every consumer re-derives bounds through here
    (rule 25); the ordinal survives a rewrite because stamping never adds or
    removes a header.
    """
    _headers = list(_FOR_PAT.finditer(source))
    header = _headers[header_index]
    _next = _FOR_PAT.search(source, header.end())
    _end = _next.start() if _next else len(source)
    return (header.end(), _end)


def _claim_in(source: str, header: re.Match, header_index: int, path: pathlib.Path) -> Claim:
    """One `### unit-test for:` header and the comment block beneath it.

    @throws SystemExit no Test class or test_ function follows the header.
    """
    _start, _end = block_bounds(source, header_index)
    block = source[_start:_end]

    _generator = _GENERATOR_PAT.search(block)
    _target = _TARGET_PAT.search(source, header.end())
    if _target is None:
        raise SystemExit(f"{path}: claim for {header.group('name')!r} has no Test class or test_ function after it")

    return Claim(
        name=header.group("name"),
        path=path,
        line=source[:header.start()].count("\n") + 1,
        header_index=header_index,
        samples=tuple(m.group("path") for m in _SAMPLE_PAT.finditer(block)),
        generator=_generator.group("call") if _generator else "",
        target=_target.group("cls") or _target.group("fn"),
    )


def claims_for(name: str, root: pathlib.Path) -> list[Claim]:
    """Every claim naming this marker.

    @throws SystemExit no test claims it.
    """
    out = []
    for path in sorted(root.rglob("*.py")):
        source = _read(path)
        for _index, header in enumerate(_FOR_PAT.finditer(source)):
            if header.group("name") != name:
                continue
            out.append(_claim_in(source, header, _index, path))
    if len(out) == 0:
        raise SystemExit(f"no test claims marker {name!r} under {root}")
    return out


def _import_test_module(claim: Claim, root: pathlib.Path):
    """Load the claim's test module from its own file.

    A test is addressed by where it is, not by its stem: rule 3n puts tests under
    `_tests`, which is not importable from `root`, and two packages may each hold a
    `test_mod.py`. `root` stays on `sys.path` so the test can import what it covers.

    @throws SystemExit the test module cannot be loaded.
    """
    if str(root.resolve()) not in sys.path:
        sys.path.insert(0, str(root.resolve()))

    _spec = importlib.util.spec_from_file_location(claim.path.stem, claim.path)
    if _spec is None:
        raise SystemExit(f"cannot import {claim.path}: no loader for it")

    module = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(module)   # raises whatever the test module raises at import time
    except ImportError as exc:
        raise SystemExit(f"cannot import {claim.path}: {exc}")
    return module


def ensure_samples(claim: Claim, root: pathlib.Path) -> None:
    """Generate any sample the claim depends on and does not have.

    The generator is a call written in the claim's own test module and is
    evaluated there.

    @throws SystemExit a sample is missing and no generator is recorded, or the
        generator ran and the sample still is not there.
    """
    for sample in claim.samples:
        _path = root / sample
        if _path.exists():
            continue
        if claim.generator == "":
            raise SystemExit(f"{claim.path}:{claim.line} {claim.name}: sample missing: {sample}, no generator recorded")

        print(f"  sample missing: {sample} — generating with {claim.generator}")
        module = _import_test_module(claim, root)
        eval(compile(claim.generator, str(claim.path), "eval"), vars(module))

        if not _path.exists():
            raise SystemExit(f"{claim.name}: generator ran and {sample} still does not exist")
        print(f"  generated: {sample}")


def run_test(claim: Claim, root: pathlib.Path) -> bool:
    """True where the claimed test passed."""
    module = _import_test_module(claim, root)
    _loader = unittest.TestLoader()
    _suite = _loader.loadTestsFromName(claim.target, module)
    _runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    _result = _runner.run(_suite)
    return _result.wasSuccessful()


def stamp(claim: Claim, root: pathlib.Path) -> None:
    """Rewrite the claim's integrity and timestamp. Called only after a pass.

    @throws SystemExit a mandatory integrity or 'last time passed' line is missing.
    """
    digest = hash_marked.digest_for(claim.name, root)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000Z")

    source = _read(claim.path)
    _start, _end = block_bounds(source, claim.header_index)   # re-derived: an earlier stamp moved the old offsets
    block = source[_start:_end]
    if _INTEGRITY_PAT.search(block) is None:
        raise SystemExit(f"{claim.path}:{claim.line} {claim.name}: no integrity line to stamp (it is mandatory)")
    if _PASSED_PAT.search(block) is None:
        raise SystemExit(f"{claim.path}:{claim.line} {claim.name}: no 'last time passed' line to stamp (it is mandatory)")

    block = _INTEGRITY_PAT.sub(f"# integrity: {digest}", block)
    block = _PASSED_PAT.sub(f"# last time passed: {now}", block)
    _out = source[:_start] + block + source[_end:]
    claim.path.write_text(_out, encoding="utf-8")
    print(f"  stamped {claim.path}:{claim.line}  integrity {digest[:8]}  passed {now}")


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2

    root = pathlib.Path(argv[2]) if len(argv) == 3 else pathlib.Path(".")
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 2

    name = argv[1]
    hash_marked.digest_for(name, root)      # raises SystemExit if the marker is missing or doubled
    claims = claims_for(name, root)         # raises SystemExit if no test claims it

    passed = True
    for claim in claims:
        print(f"\n{claim.path}:{claim.line}  {claim.name} -> {claim.target}")
        ensure_samples(claim, root)         # raises SystemExit if a sample cannot be produced
        if run_test(claim, root):
            stamp(claim, root)
        else:
            passed = False
            print(f"  FAILED — not stamped; the recorded integrity still points at the last passing code")

    if passed:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
