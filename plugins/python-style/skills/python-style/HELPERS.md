# helpers.py — reusable functions, addressed by marker

`helpers.py` holds small, verified functions. Each is wrapped in
`### unit-tested function start: NAME` / `### unit-tested function end: NAME`
markers, so it is fetched **by name, not by line number** — an index of line
ranges would drift the moment the file is edited; a marker name does not.

## Fetch one helper

Single-file mode on `show_marked.py` prints exactly one marked span, including
the module constants that span needs, so what you get back is self-contained:

```
USE_FILE=true SHOW_FILE=scripts/helpers.py python3 scripts/show_marked.py is_email
```

`USE_FILE` is the switch (default off) — a stray `SHOW_FILE` in the environment
cannot silently redirect a normal directory scan. `hash_marked.py` and
`verify_marked.py` accept the same two variables.

## Contents

Each entry is fetched by its marker name above. `verify` is the marker's md5 as
reported by `hash_marked.py` — cosmetic edits do not move it; a change to the
code does.

| marker | does | equivalent to | verify (md5) |
|---|---|---|---|
| `iter_splitlines` | Lines of a string, lazily, on the full `str.splitlines()` boundary set | `str.splitlines()` — but an iterator, not a materialized list | `c911f58f4db84b89b0d5029698ca555c` |
| `is_email` | Validate an address: cheap policy pre-check, then the 426-char RFC-5322 pattern only on survivors | stricter than RFC 5322 by design | `10ca7ea095a7341cd343ce3b78ee476e` |
| `iter_chain` | Yield every item of every iterable in an iterable of iterables | `itertools.chain.from_iterable` | `8d1e93794d8aeb7e07cc008a2c9a7feb` |
| `iter_chain2` | Yield every item of the first iterable, then the second | `itertools.chain(a, b)` | `ec38ae0501b5ebadf80ff37a7f9f3a9f` |

## Verified

- `iter_splitlines` agrees with `str.splitlines()` on a 17-case boundary corpus
  and 20,000 fuzzed strings, for both `keepends` values.
- `is_email` accepts ordinary addresses and rejects the empty string, a missing
  TLD, spaces, and the documented policy cases `user@[192.168.1.1]`,
  `"john doe"@example.com`, and special-character local parts.
- `iter_chain` matches `itertools.chain.from_iterable` and stays lazy (yields the
  first item without consuming the rest); `iter_chain2` matches
  `itertools.chain(a, b)`.

## Notes

- `is_email`'s full RFC-5322 pattern carries an address-literal branch
  (`user@[…]`) that is never reached. The fast pre-check's character classes
  exclude `[`, so any candidate surviving to the full pattern contains none;
  bracketed-IP addresses are rejected at the pre-check, not by that branch.
- `iter_chain`/`iter_chain2` reimplement stdlib `itertools`; use them only where
  the dependency is unwanted. The two-argument form is `yield from` territory —
  it is spelled out here to sit beside the general `from_iterable` form.
- The markers make each helper a `verify_marked.py` target: a test in an
  adjacent `_tests/` can be stamped against the span's integrity hash, so a
  helper cannot be edited without its test being re-run.
