#!/usr/bin/env python3
"""Bundled tests for scripts/helpers.py, addressed by `### unit-test for:` markers.

Run and stamp one marker at a time, from inside `scripts/` so `import helpers`
resolves:

    cd scripts && python3 verify_marked.py iter_splitlines .

A pass rewrites that claim's `# integrity:` line to the md5 of the function span
in helpers.py; it therefore tracks the code under test, not this file.
"""
import random
import unittest
from itertools import chain

import helpers


### unit-test for: iter_splitlines
# integrity: c911f58f4db84b89b0d5029698ca555c
# last time passed: 2026-07-20 11:18:13.000Z
class TestIterSplitlines(unittest.TestCase):
    """iter_splitlines must reproduce str.splitlines() on every boundary."""

    _BOUNDARY = [
        "", "a", "a\nb", "a\nb\n", "\n", "\n\n", "a\r\nb", "a\rb",
        "a\vb", "a\fb", "a\x1cb", "a\x1db", "a\x1eb", "a\x85b",
        "a\u2028b", "a\u2029b", "line1\r\nline2\rline3\nline4",
        "trailing\n", "\r\n", "\r", "mix\n\r\n\r", "a\n\n\nb",
    ]

    def test_boundary_corpus(self):
        for keepends in (False, True):
            for text in self._BOUNDARY:
                got = list(helpers.iter_splitlines(text, keepends=keepends))
                expected = text.splitlines(keepends=keepends)  # boundary corpus; short fixed literals
                self.assertEqual(got, expected, (repr(text), keepends))

    def test_fuzz(self):
        alphabet = "ab\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029 "
        rng = random.Random(1234)
        for _ in range(20000):
            length = rng.randint(0, 12)
            text = "".join(rng.choice(alphabet) for _ in range(length))
            for keepends in (False, True):
                got = list(helpers.iter_splitlines(text, keepends=keepends))
                expected = text.splitlines(keepends=keepends)  # fuzz string; <=12 chars by construction
                self.assertEqual(got, expected, (repr(text), keepends))


### unit-test for: is_email
# integrity: 10ca7ea095a7341cd343ce3b78ee476e
# last time passed: 2026-07-20 11:18:13.000Z
class TestIsEmail(unittest.TestCase):
    """is_email accepts policy-valid addresses and rejects the rest."""

    _GOOD = ["a@b.co", "user.name@example.com", "x+y@sub.domain.org", "a_b@c-d.com"]
    _BAD = ["", "a@", "@b.com", "a@@b.com", "a b@c.com", "a@b", "plainaddr"]

    def test_accepts(self):
        for address in self._GOOD:
            self.assertTrue(helpers.is_email(address), address)

    def test_rejects(self):
        for address in self._BAD:
            self.assertFalse(helpers.is_email(address), address)

    def test_ip_literal_rejected_by_fast_gate(self):
        # The full pattern's IP-literal branch is unreachable: the fast gate's
        # character classes exclude '[', so an address literal never reaches it.
        self.assertFalse(helpers.is_email("user@[192.168.1.1]"))


### unit-test for: iter_chain
# integrity: 8d1e93794d8aeb7e07cc008a2c9a7feb
# last time passed: 2026-07-20 11:18:13.000Z
class TestIterChain(unittest.TestCase):
    """iter_chain equals chain.from_iterable and stays lazy."""

    def test_matches_stdlib(self):
        data = [[1, 2], [3], [], [4, 5, 6]]
        got = list(helpers.iter_chain(data))
        expected = list(chain.from_iterable(data))
        self.assertEqual(got, expected)

    def test_lazy(self):
        def endless():
            index = 0
            while True:
                yield [index]
                index += 1
        generator = helpers.iter_chain(endless())
        got = list(next(generator) for _ in range(3))
        self.assertEqual(got, [0, 1, 2])


### unit-test for: iter_chain2
# integrity: ec38ae0501b5ebadf80ff37a7f9f3a9f
# last time passed: 2026-07-20 11:18:13.000Z
class TestIterChain2(unittest.TestCase):
    """iter_chain2 equals chain(a, b) and stays lazy in its second argument."""

    def test_matches_stdlib(self):
        got = list(helpers.iter_chain2([1, 2], [3, 4]))
        expected = list(chain([1, 2], [3, 4]))
        self.assertEqual(got, expected)

    def test_lazy(self):
        def endless():
            index = 0
            while True:
                yield index
                index += 1
        generator = helpers.iter_chain2([-1, -2], endless())
        got = list(next(generator) for _ in range(4))
        self.assertEqual(got, [-1, -2, 0, 1])


if __name__ == "__main__":
    unittest.main()
