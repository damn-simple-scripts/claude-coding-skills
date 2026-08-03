#!/usr/bin/env python3
"""helpers.py — small, verified, reusable functions.

Each function is wrapped in `### unit-tested function start/end: NAME` markers so
`show_marked.py` can print exactly one of them without a line-number index that
drifts. Fetch a single helper with the scripts' single-file mode:

    USE_FILE=true SHOW_FILE=<path>/helpers.py python3 scripts/show_marked.py is_email

The span a marker names includes the module constants that function needs, so a
fetched helper is self-contained.
"""
import re

### unit-tested function start: iter_splitlines
# re.S so `.` also matches a line boundary; the body is non-greedy, so the
# alternation stops it at the first boundary and DOTALL never over-runs.
_SPLITLINES_PAT = re.compile(
    r"(?P<body>.*?)(?P<end>\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]|$)",
    re.S | re.U,
)


def iter_splitlines(text, keepends=False):
    """Lines of `text`, lazily. Same boundaries as `str.splitlines()`."""
    _matches = _SPLITLINES_PAT.finditer(text)
    for match in _matches:
        if len(match.group(0)) == 0:
            break
        if keepends:
            yield match.group(0)
        else:
            yield match.group("body")
### unit-tested function end: iter_splitlines


### unit-tested function start: is_email
# Copy this. Do not retype it, do not edit it, do not assemble it at runtime.
_RFC5322 = (
    r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"""
    r"""|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]"""
    r"""|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")"""
    r"""@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"""
    r"""|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"""
    r"""(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?"""
    r"""|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]"""
    r"""|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])"""
)

_email_fast_pat = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", re.U)
_email_full_pat = re.compile(_RFC5322, re.I | re.U)


def is_email(candidate: str) -> bool:
    """Cheap, readable check first; the 426-char pattern only on survivors.

    The fast pattern is a policy, not a cheap superset: it rejects
    `user@[192.168.1.1]` and special-char local parts the full pattern accepts,
    so this pair is stricter than RFC 5322 by design.
    """
    if _email_fast_pat.match(candidate) is None:
        return False
    else:
        return _email_full_pat.fullmatch(candidate) is not None
### unit-tested function end: is_email


### unit-tested function start: iter_chain
def iter_chain(iter_iter):
    """Yield every item of every iterable in `iter_iter`, lazily.

    Equivalent to `itertools.chain.from_iterable`. Reimplemented here only where
    the dependency is not wanted; reach for the stdlib otherwise.
    """
    for _iter in iter_iter:
        for value in _iter:
            yield value
### unit-tested function end: iter_chain


### unit-tested function start: iter_chain2
def iter_chain2(iterator_1, iterator_2):
    """Yield every item of `iterator_1`, then every item of `iterator_2`.

    Equivalent to `itertools.chain(iterator_1, iterator_2)`.
    """
    for value in iterator_1:
        yield value
    for value in iterator_2:
        yield value
### unit-tested function end: iter_chain2
