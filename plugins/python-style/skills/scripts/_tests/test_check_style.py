#!/usr/bin/env python3
"""Behavior corpus for check_style.py — one snippet per row, asserted findings.

Each case states the source, then the (rule, kind) findings it must produce and
the ones it must NOT. Run to tune: a surprising PASS/FAIL localizes a false
positive or a blind spot to exactly one check. Import path assumes this file
runs from scripts/ (sibling to check_style.py):

    cd scripts && python3 -m unittest _tests.test_check_style -v

@throws AssertionError a check drifted from the documented behavior.
"""
import ast
import unittest
from typing import NamedTuple

import check_style


class Case(NamedTuple):
    name: str
    source: str
    must: frozenset       # (rule, kind) pairs that must appear
    must_not: frozenset   # (rule, kind) pairs that must NOT appear


def _findings(source: str) -> set:
    """Every (rule, kind) a full check_style pass yields on `source`."""
    tree = ast.parse(source)
    _annotated = check_style._annotated_lines(source)
    out = set()
    for finding in check_style._run_checks(tree, _annotated):
        out.add((finding.rule, finding.kind))
    return out


# --- true positives: the shape each check exists to catch ---------------------
_POSITIVE = [
    Case("ret_ternary", "def f(x):\n    return 1 if x else 2\n",
         frozenset({("2", "error")}), frozenset()),
    Case("arith_truthiness", "def f(n):\n    if n % 2:\n        return 1\n",
         frozenset({("8", "error")}), frozenset()),
    Case("len_truthiness", "def f(x):\n    if len(x):\n        return 1\n",
         frozenset({("8", "error")}), frozenset()),
    Case("list_augassign", "def f():\n    xs = []\n    xs += [1]\n    return xs\n",
         frozenset({("3l", "error")}), frozenset()),
    Case("unused_import", "import os\n",
         frozenset({("11", "error")}), frozenset()),
    Case("nested_comprehension", "def f(m):\n    return list(a for r in m for a in r)\n",
         frozenset({("3t", "error")}), frozenset()),
    Case("bracket_listcomp", "def f(m):\n    return [x for x in m]\n",
         frozenset({("13", "error")}), frozenset()),
    Case("positional_group", "import re\np = re.compile(r'(\\d+)', re.U)\n",
         frozenset({("24", "error")}), frozenset()),
    Case("no_re_flags", "import re\np = re.compile(r'^x$')\n",
         frozenset({("3s", "error")}), frozenset()),
    Case("inline_flag", "import re\np = re.compile(r'(?i)^x$', re.U)\n",
         frozenset({("3s", "error")}), frozenset()),
    Case("silent_except", "def f():\n    try:\n        g()\n    except Exception:\n        pass\n",
         frozenset({("16", "error")}), frozenset()),
    Case("materialize_unbounded", "def f(s):\n    return s.split(',')\n",
         frozenset({("13", "error")}), frozenset()),
]

# --- legitimate forms that must stay quiet (false-positive guards) ------------
_NEGATIVE = [
    Case("gen_in_list_ok", "def f(m):\n    return list(x for x in m)\n",
         frozenset(), frozenset({("13", "error")})),
    Case("os_path_split_ok", "import os\ndef f(p):\n    return os.path.split(p)\n",
         frozenset(), frozenset({("13", "error")})),
    Case("materialize_bounded_ok",
         "def f(s):\n    return s.split(',')  # <=3 fields, header line\n",
         frozenset(), frozenset({("13", "error")})),
    Case("except_with_reason_ok",
         "def f():\n    try:\n        g()\n    except Exception:\n        pass  # best-effort cleanup, safe to skip\n",
         frozenset(), frozenset({("16", "error")})),
    Case("named_group_ok", "import re\np = re.compile(r'(?P<n>\\d+)', re.U)\n",
         frozenset(), frozenset({("24", "error")})),
    Case("emptiness_not_arith_ok", "def f(x):\n    if not x:\n        return 1\n",
         frozenset(), frozenset({("8", "error")})),
    Case("import_used_via_attr_ok", "import os.path\ndef f(p):\n    return os.path.join(p, 'a')\n",
         frozenset(), frozenset({("11", "error")})),
]

# --- known weak spots: document current behavior so a fix is a visible diff ---
# Each row asserts what check_style does TODAY, flagged in the report as a
# candidate to tune. If a future edit changes the behavior, the assert fails and
# forces an intentional update here.
_KNOWN_WEAKNESS = [
    # False positive: 'token' is a substring of 'token_count' (rule 30 word match).
    Case("secret_substring_fp", "def f(token_count, n):\n    return token_count == n\n",
         frozenset({("30", "info")}), frozenset()),
    # False positive: a re-export module; 'helpers' is only named in __all__.
    Case("reexport_all_fp", "import helpers\n__all__ = ['helpers']\n",
         frozenset({("11", "error")}), frozenset()),
    # Blind spot: handle stored on an attribute (self.f) is not tracked at all,
    # so an unclosed open() on an attribute target yields nothing.
    Case("attr_open_blind", "def f(self):\n    self.f = open('x')\n",
         frozenset(), frozenset({("3g", "review")})),
    # Blind spot: json.dumps via `from json import dumps` is not matched
    # (check keys on json.dumps attribute form only).
    Case("json_from_import_blind", "from json import dumps\ndef f(d):\n    return dumps(d)\n",
         frozenset(), frozenset({("28", "info")})),
]


class TestCheckStyle(unittest.TestCase):
    def _run(self, cases):
        for case in cases:
            got = _findings(case.source)
            self.assertTrue(case.must <= got,
                            f"{case.name}: missing {case.must - got}; got {got}")
            self.assertFalse(case.must_not & got,
                             f"{case.name}: unexpected {case.must_not & got}")

    def test_positive(self):
        self._run(_POSITIVE)

    def test_negative(self):
        self._run(_NEGATIVE)

    def test_known_weakness(self):
        self._run(_KNOWN_WEAKNESS)


if __name__ == "__main__":
    unittest.main()
