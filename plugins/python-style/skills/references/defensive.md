# Prevent stupid mistakes — the defensive-coding checklist

Rule 3's full checklist, plus the regex-group convention it leans on. Every item here exists because the failure mode is silent, late, or hard to spot in review.

Part of the `python-style` skill. Rule numbers are global across the skill — see SKILL.md for the full index and for which file holds which rule.

## Contents

Rule 3 — the checklist:

- **a)** Overwrite the variable holding an iterator at each chaining stage.
- **b)** Always validate user input, and fail early.
- **c)** Split regex work into stages — no clever mega-regex.
- **d)** Multiple files: be explicit about concurrency.
- **e)** Small, simple functions over large complex ones.
- **f)** Check what a function actually returns — look it up, don't assume.
- **g)** Close explicitly — don't trust an `__exit__` you haven't read.
- **h)** A file must be complete before anything else touches it.
- **i)** Use an env-configurable logger.
- **j)** Check whether output aliases input — deep-copy or say so in the name.
- **k)** Re-implementing to avoid a dependency requires test vectors.
- **l)** Use named insertion methods, not overloaded math operators.
- **m)** A file written only to *be written* should be in memory instead.
- **n)** In a Claude Code session: generate test code covering every function written.
- **o)** A result not meant to be edited later gets a frozen type.
- **p)** Be careful with functions that return a pointer to an object.
- **q)** Don't `.strip()` before a regex match.
- **r)** A validating regex is anchored; an extracting regex may not be.
- **s)** State the regex flags explicitly.
- **t)** Make iterator work visible, or give it a name.
- **u)** Compare within the same logical type.
- **v)** A docstring names what the function raises — including what it raises through.
- **w)** An exception you decide not to handle gets a comment on the line.

Then:

- **24.** Named regex groups for data extraction

### 3. Prevent stupid mistakes — the defensive-coding checklist
Each item exists because the failure mode is silent, late, or hard to spot in review.

**a) Overwrite the variable holding an iterator at each chaining stage.**
An exhausted generator doesn't raise when read again — it yields nothing, silently producing an empty result downstream. Reassigning the same name (rule 2) leaves the consumed generator with no reachable name, so it can't be read twice. Fresh names per stage (`_filtered`, `_thresholded`) leave consumed generators sitting around by name — exactly the footgun this avoids.

**b) Always validate user input, and fail early.**
Validate at the boundary — the moment external data enters, not after it has travelled through three functions. Check parameters at the *start* of the function. Reject rather than coerce (rule 16). Bad input should surface where the error message can still say where it came from.

**c) Split regex work into stages — no clever mega-regex.**
One pattern that extracts, validates, and normalizes at once is unreviewable and fails opaquely: a non-match returns `None` with no indication of which part failed.

```python
# Wrong — one pattern doing extraction and full validation; a non-match
# tells you nothing about which part failed.
_pat = re.compile(
    r"^(?P<name>[\w\s]+)\s*<(?P<email>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>$",
    re.U,
)

# Preferred — stage 1 roughly splits the fields, stage 2 validates one
# field. Each stage fails with a specific, reportable reason (rule 16).
# The pattern carries its own whitespace (rule 3q), so it stands alone.
_field_pat = re.compile(r"^\s*(?P<name>[^<]+)<(?P<email>[^>]+)>\s*$", re.U)
_email_pat = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.U)

def parse_contact(raw: str) -> tuple[str, str]:
    _m = _field_pat.match(raw)
    if _m is None:
        raise ValueError(f"not in 'Name <email>' form: {raw!r}")

    name = _m.group("name").strip()
    email = _m.group("email").strip()
    if _email_pat.match(email) is None:
        raise ValueError(f"field extracted but not a valid email: {email!r}")

    return name, email
```
Use named groups throughout (rule 24).

**Email is the standing example, and staging is what makes it tractable.** A full RFC-5322 pattern exists — the one published at <https://emailregex.com> is 426 characters:

```python
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
    """Cheap, readable check first; the 426-char pattern only on survivors."""
    if _email_fast_pat.match(candidate) is None:
        return False
    else:
        return _email_full_pat.fullmatch(candidate) is not None
```

Two things about that pair, both of which have to be said out loud rather than assumed:

**The fast pattern is not a cheap superset of the full one — it is a policy.** It rejects `user@[192.168.1.1]` and ``a!#$%&'*+/=?^_`{|}~-b@example.com``, which the full pattern accepts. So `is_email` is stricter than RFC 5322, deliberately. That is usually what a system wants; it is not what rule 3b's cheap-before-expensive ordering implies on its own, so state it where the gate is written.

**The published pattern is not provably complete.** It rejects `"john doe"@example.com`, which RFC 5322 permits — the quoted-string class excludes `\x20`. Treat it as a good pattern, not as the specification.

**A library is a valid option and often the better one.** Building the pattern at runtime is not an option: a regex assembled from fragments cannot be reviewed, cannot be diffed, and cannot be tested against a fixed corpus. And for anything that matters, the only real validator is a confirmation round-trip.

**d) Multiple files: be explicit about concurrency.**
Don't hand-roll a loop that opens N files and hopes each gets closed. Being explicit prevents two classes of stupid mistake: serial bottlenecks where nothing needed to be serial, and leaked FDs from a path that skipped a close. **Any explicit async mechanism is fine** — `asyncio`, a thread plus a work queue, a `ThreadPoolExecutor`, whatever fits. There's no mandated library. What matters:

- The concurrency is *explicit and visible*, not accidental.
- Every opened handle has an unambiguous owner responsible for closing it (`contextlib.ExitStack` / `AsyncExitStack` registers them all in one place — cleanup happens regardless of which branch or exception unwinds).
- Concurrency is bounded. N files means N open FDs at once; a large directory hits the FD limit. Gate with a semaphore, a fixed pool size, or chunking.
- If the per-file work is CPU-bound (parsing, hashing, decompressing), threads/async buy nothing — that's a process-pool question.

**e) Small, simple functions over large complex ones.**
A function should be small enough that its correctness is checkable by reading it once. Prefer several small functions with obvious contracts over one with branching modes, many parameters, or an internal state machine. Small functions are also what makes rule 19 practical — a small function can be verified against real data without standing up the whole pipeline.

**f) Check what a function actually returns — look it up, don't assume.**
Read the documented return type. If it returns multiple elements and the check is cheap, check before using. If accessing by index, verify the index exists.

```python
# Wrong — assumes the split produced at least 3 fields.
_parts = raw.split(":")
host, port = _parts[0], _parts[2]

# Preferred — the check is cheap, so it happens before indexing.
_parts = raw.split(":")
if len(_parts) < 3:
    raise ValueError(f"expected 3+ colon-separated fields, got {len(_parts)}: {raw!r}")
```

**g) Close explicitly — don't trust an `__exit__` you haven't read.**
`with` is fine, but don't rely on the object's `__exit__` doing what you assume. Close explicitly anyway; a second close via `__exit__` is harmless — file objects tolerate double-close. On a write, flush first: that `__exit__` closes is not a promise that it flushed.

Reads are the same rule. There is nothing to flush, but the handle is still a handle, and the reason doesn't change with direction — a reader who sees `open(...)` and no `close()` has to go and read `__exit__` to find out what happened.

Better on a read: don't hold a handle at all. `path.read_text(encoding="utf-8")` and `path.read_bytes()` own theirs and close it, so there is no `__exit__` of yours to trust (rule 5).

**h) A file must be complete before anything else touches it.**
Renaming is the common case, not the whole rule. Any step that hands the file to something outside the code writing it — `os.replace`, an upload, a `subprocess` argument, a hash of the path, another process told to read it — happens after the file is complete. Even where writing to an FD after the inode's name changed happens to work, don't. Different OS, different FS, different buffering, and it becomes a bug.

Complete means: flush **and** close **and** invalidate every variable referencing the file. Then hand it over, outside the `with`.

```python
_tmp_path = path.with_suffix(path.suffix + ".tmp")
logger.debug("writing temp file: %s", _tmp_path)
with open(_tmp_path, "wb") as h:
    h.write(payload)
    h.flush()              # explicit — do not rely on __exit__ flushing
    os.fsync(h.fileno())
    h.close()              # explicit — do not rely on __exit__ closing
del h                      # invalidate the name; nothing can touch it now

logger.debug("renaming %s -> %s", _tmp_path, path)
os.replace(_tmp_path, path)   # rename only once the file is complete

# The same constraint, different consumer. Each of these is "something
# else touches it", and each goes after the close and the del:
#   subprocess.run(["gpg", "--detach-sign", str(path)])
#   upload(path)
#   _digest = hashlib.sha256(path.read_bytes()).hexdigest()
```

**i) Use an env-configurable logger.**
Logging tells you what the tool is actually doing and catches stupid mistakes early — wrong filename generated, input decoded wrong, wrong permissions. Debug-level output should genuinely be enough to debug the application. Level comes from the environment, not a code edit. Expensive log payloads go behind an explicit level check:

```python
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

# From the Python logging HOWTO — guard expensive arguments:
if logger.isEnabledFor(logging.DEBUG):
    logger.debug('Message with %s, %s', expensive_func1(), expensive_func2())
```
Always log the files you access (see rule 2's path example).

**j) Check whether output aliases input — deep-copy or say so in the name.**
If a function takes a dict and returns a new object, a reader assumes nothing in the result is linked back to the input, and will happily mutate the input expecting the result to be unaffected. Where that assumption isn't guaranteed, make it true with a deep copy.

```python
# Wrong — `dict(raw)` is shallow; nested values still alias the caller's
# object. Nothing in the signature warns you.
def to_record(raw: dict) -> dict:
    record = dict(raw)
    record["seen"] = now()
    return record

# Preferred — no shared references, so `to_record` means what a reader
# assumes it means.
def to_record(raw: dict) -> dict:
    record = copy.deepcopy(raw)
    record["seen"] = now()
    return record
```
If deep-copying is genuinely too expensive *in that case* — a hot path, not a final output — the name and docstring must say so in no uncertain terms (`to_record_sharing_nested`, docstring stating that mutating nested values in the result mutates the input). Assess every function for unexpected side effects, and assess "unexpected" from multiple points of view and multiple levels of English fluency/bias — a name that reads as obvious to the author often doesn't to a reader.

**k) Re-implementing to avoid a dependency requires test vectors.**
If you reimplement something rather than take a dependency, provide and *run* test cases — in comments is fine. **For crypto primitives this is non-negotiable. For format parsers (e.g. CBOR) this is non-negotiable.** Something simple — itertools' `take`, chaining iterators — doesn't need them.

```python
def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()

# RFC 5869 Appendix A.1 test vector — run, not assumed:
#   ikm = 0x0b * 22, salt = 000102030405060708090a0b0c, hash = SHA-256
assert hkdf_extract(
    bytes.fromhex("000102030405060708090a0b0c"), bytes([0x0b]) * 22
).hex() == "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5"
```

**l) Use named insertion methods, not overloaded math operators.**
`+=` on a list is an in-place extend; on a tuple it rebinds; the line doesn't say which. Named methods say what happens and where.

```python
# Wrong
results += [node]
results += other_nodes

# Preferred — the method name states how and where data is inserted.
results.append(node)
results.extend(other_nodes)
results.insert(0, first_node)
```
Holds for all data structures. A plain `+` is acceptable in rare cases.

**m) A file written only to *be written* should be in memory instead.**
If the write exists only so the data exists somewhere — a temp result, an intermediate in a conversion, a received request body — use an in-memory buffer (`io.StringIO` / `io.BytesIO`). The filesystem contributes latency and its own failure modes: permissions, full disk, cleanup races, differing FS semantics between platforms. None of that is worth paying for data that never needed to persist.

**Only for small data with a guardrail around it.** Check the size *before* it goes into memory — an unbounded in-memory buffer is just a different stupid mistake (OOM on hostile or unexpectedly large input). No guardrail means the filesystem is the right answer after all.

```python
# Wrong — a disk round-trip purely to hand bytes to the next step.
with open("/tmp/converted.csv", "w") as h:
    csv.writer(h).writerows(rows)
with open("/tmp/converted.csv", "rb") as h:
    upload(h.read())

# Preferred — size is bounded and checked, so it never touches disk.
if len(rows) > _MAX_ROWS:
    raise ValueError(f"{len(rows)} rows exceeds in-memory limit {_MAX_ROWS}")

_buf = io.StringIO()
csv.writer(_buf).writerows(rows)
upload(_buf.getvalue().encode("utf-8"))
```

**n) In a Claude Code session: generate test code covering every function written.**
Every function generated in the session gets exercised against test data. **Any form of testing is acceptable** — no unit-test framework requirement; a plain script full of asserts counts. The point is that rule 19's verification claim is backed by something runnable rather than asserted.

Keep tests **out of the main project directories** — put them in an `_tests` directory. Don't scatter test files through the source tree.

**Mark what is tested, so a tool can find it.** A function under test carries its span:

```python
### unit-tested function start: my_magic
def my_magic(data):
    return sorted(set(data))
### unit-tested function end: my_magic
```

and the test carries what it covered, and when:

```python
### unit-test for: my_magic
# integrity: 2ce5101a1343641ad78b04ed815a5895
# last time passed: 2026-07-18 00:11:27.000Z
# depends on sample: _samples/my_magic_test.csv
# sample generator: __generate_my_magic_sample("_data/full_data.csv")
class TestMyMagic(unittest.TestCase):
    def test_dedupes_and_sorts(self):
        ...
```

- **`### unit-test for:`** is repeatable. One test may cover several markers — stack a header and its lines for each.
- **`# integrity:`** is mandatory. It is the md5 of the code the marker covers, as of the last time the test passed. When it disagrees with the code, the code moved and the test did not.
- **`# last time passed:`** is mandatory. It steers debugging: a failure in code that passed an hour ago is a different search from one that last passed in March.
- **`# depends on sample:`** is mandatory wherever the test reads sample data. It is greppable, so a missing corpus is found before the suite runs rather than as an error inside it.
- **`# sample generator:`** is optional — a call in the test's own module that produces the sample.

**Three scripts define the mechanism, and nothing in it is written by hand:**

- `scripts/show_marked.py <marker>` prints the code the marker covers.
- `scripts/hash_marked.py <marker>` prints the md5 of exactly that. The span needs no prose definition: it is what `show_marked` prints.
- `scripts/verify_marked.py <marker>` generates a missing sample, runs the claiming test, and rewrites `integrity` and `last time passed` **only if it passed**.

`integrity` and `last time passed` are never typed. A stale count looks like a count; a stale md5 looks like proof — so it comes from the tool that watched the test pass, or it lies. A failing test leaves the old hash alone, which is the point: it still names the last code this test is known to have covered.

The md5 is a change detector, not a security control. It answers *did this move*, where nobody is forging a collision. It covers the canonical span — every line right-stripped, the block stripped — so re-indenting a file or leaving a trailing space does not invalidate a test that still covers the code, while `sorted(set(data))` → `sorted(data)` does.

Markers and stamps are comments, so `unittest`, `pytest` and the rest are unaffected.

**o) A result not meant to be edited later gets a frozen type.**
Where a function builds an object the caller isn't supposed to change, the type should enforce that — not a docstring asking nicely. This is rule 3j's problem solved at the type level instead of by copying.

```python
def channel_members(channel: str) -> frozenset[str]:
    return frozenset(_members_of(channel))

@dataclass(frozen=True)
class Node:
    pubkey: str
    first_seen: int

class Observation(NamedTuple):
    node_id: str
    snr: float
```

`frozenset`, `@dataclass(frozen=True)` and `NamedTuple` are all builtin/stdlib, genuinely immutable, hashable, and typed. Reach for them wherever the result is a finished artifact rather than a work in progress.

**p) Be careful with functions that return a pointer to an object.**
Modify a value inside a container explicitly: index it, then mutate it. Don't lean on a function that implicitly hands back the object it just inserted — the reader then needs that function's documented return value just to follow the line.

```python
# Wrong — implicit: setdefault returns the object it inserted, and the
# mutation rides on that return value. It also hides that the insert is
# happening at all.
data.setdefault(pos, set()).add(new_val)

# Preferred — say the two jobs separately. The type states the default,
# so the index is only an index.
data = collections.defaultdict(set)
data[pos].add(new_val)
```

Where a `defaultdict` isn't wanted, the explicit form is still two statements rather than one expression:

```python
if pos not in data:
    data[pos] = set()
data[pos].add(new_val)
```

Only extract a pointer out of a container in restricted cases — a hot path, or where it genuinely improves readability. When you do, **preserve the container's name in the variable's name** and comment the usage so the aliasing is visible (rule 3j):

```python
data_set = data[pos]
data_set.add(new_val)   # < member of data[pos]
```

**q) Don't `.strip()` before a regex match.**
If a value may carry leading/trailing whitespace and you are about to regex it, match the whitespace in the pattern (`\s*`) rather than stripping it away first. Stripping first damages the pattern's reusability: it then only works on pre-stripped input, can't be handed to another tool as-is, and carries an undocumented precondition the caller has to know about.

```python
# Wrong — the pattern now silently requires pre-stripped input.
_pat = re.compile(r"^(?P<name>[^<]+)<(?P<email>[^>]+)>$", re.U)
_m = _pat.match(raw.strip())

# Preferred — the pattern handles its own whitespace and stands alone.
_pat = re.compile(r"^\s*(?P<name>[^<]+)<(?P<email>[^>]+)>\s*$", re.U)
_m = _pat.match(raw)
```

**Stripping *after* extraction is fine.** Don't inflate a pattern's complexity to strip captured data: a low-hanging `\s*` — take it; if making it work needs greedy/lazy switches or precedence tricks, call `.strip()` on the extracted field instead.

**This is not a performance rule.** `raw.strip()` + match and an inline `\s*` match come out **within 2% of each other** (0.0550s vs 0.0541s over 200k iterations). Reusability is the whole reason.

**r) A validating regex is anchored; an extracting regex may not be.**
A regex that validates starts with `^` and ends with `$`. Without both, `re.match` accepts trailing garbage and `re.search` accepts leading garbage too. Only a regex deliberately pulling something out of the *middle* of a larger string omits the anchors — and that is a decision to state, not a default to drift into.

**s) State the regex flags explicitly.**
`^`, `$` and `\w` have no fixed meaning on their own — each hinges on a flag. Pass flags as an argument at compile time, not as an inline `(?m)`/`(?u)` modifier buried in the pattern text, so the pattern's semantics are visible at the call.

**Every regex states `re.U` or `re.A`.** No exceptions. `re.U` *is* the default for `str` patterns, so writing it changes nothing — that's the point: it says the character-class semantics were decided rather than defaulted. `re.A` says the opposite was decided.

```python
# Unicode word characters — the default, stated so it reads as a choice.
_name_pat = re.compile(r"^\w+$", re.U)

# ASCII-only — a real restriction, now visible at the compile call.
_token_pat = re.compile(r"^\w{8,32}$", re.A)

# Flags combine. ^ and $ now anchor each line, not the whole string.
_line_pat = re.compile(r"^\w+$", re.U | re.M)
```

**The rest of the flags:**
- `re.M` / `re.MULTILINE` — use the flag argument, never the inline `(?m)` form. `re.compile(r"^beta$", re.U).search("alpha\nbeta")` finds nothing; add `re.M` and it matches. Same pattern, opposite result.
- `re.I` / `re.IGNORECASE` — well known. No comment needed.
- `re.S` / `re.DOTALL` — **always add a comment saying what it does.** Nobody remembers this one. `_pat = re.compile(r"a.b", re.U); _pat.search("a\nb")` finds nothing; with `re.S`, `.` matches the newline and it does.

```python
# re.S (DOTALL): "." also matches newline, so the body may span lines.
_block_pat = re.compile(r"^BEGIN(?P<body>.*)END$", re.U | re.S)
```

Short and long forms are the same object (`re.M is re.MULTILINE` → `True`) — either spelling is fine, so match the surrounding code.

**t) Make iterator work visible, or give it a name.**
A comprehension is readable exactly as long as one glance says what comes out of it. Past that it is a nested loop wearing comprehension syntax, and the reader is doing the interpreter's job.

```python
# Wrong — what does this produce? The outer name `y` is never used, which
# is the tell: the outer loop is a repeat count in disguise.
list_a = ["a", "b", "c"]
list_b = ["x", "y", "z"]
magic = (x for y in list_b for x in list_a)

# Preferred — a named helper says it in one word at the call site.
def times(n, sequence):
    for _ in range(n):
        for value in sequence:
            yield value

magic = times(len(list_b), list_a)
```

Treat a second `for` clause in one comprehension as the smell (rule 7). Where the nesting is genuinely wanted, produce the inner iterator as its own named thing and flatten it in a separate step, so each line has one job (rule 2):

```python
_rows = (parse(block) for block in blocks)       # step 1: rows per block
_rows = itertools.chain.from_iterable(_rows)   # step 2: flatten
```

`sequence`, not `iterator`: `times` reads its second argument once per repeat, so handing it a generator gives one pass and then silently nothing (rule 3a). The parameter name is the warning.

**u) Compare within the same logical type.**
A string that represents something — a hash, an address, a version, a UUID — is a representation, not the thing. Comparing representations compares the transport encoding and silently answers a question nobody asked: `"A1B2" == "a1b2"` is `False` while the bytes are identical, and `"::1" == "0:0:0:0:0:0:0:1"` is `False` while the address is the same one.

Convert when you *work* with the value. Working means comparing it, ordering it, or deciding on it. Storing it, logging it, passing it through, or extracting it out of a larger blob is not working — a hash pulled from a packet stays hex until something asks a question about it.

```python
# Wrong — three different questions, all answered by string equality.
if observed_pubkey_hex == known_pubkey_hex:
    ...
if client_ip == allowed_ip:
    ...
if computed_mac_hex == expected_mac_hex:
    ...

# Preferred — convert, then ask.
_observed = bytes.fromhex(observed_pubkey_hex)
_known = bytes.fromhex(known_pubkey_hex)
if _observed == _known:
    ...

_client = ipaddress.ip_address(client_ip)
_allowed = ipaddress.ip_address(allowed_ip)
if _client == _allowed:
    ...

if hmac.compare_digest(computed_mac, expected_mac):
    ...
```

The conversion is also where the input gets validated, for free: `bytes.fromhex("zz")` raises, and `ipaddress.ip_address("300.1.1.1")` raises. String comparison accepts both and returns `False` — a wrong answer where the typed form gives an error (rule 16). Rule 27 is the narrow case of this rule for the times the hex has to stay a string.

**Constant-time comparison is for authentication, not for hashes in general.**
`hmac.compare_digest` where the comparison *authenticates* — a MAC check, a session or API token, a password digest, anything inside an auth backend. There the comparison's timing is an output an attacker can measure, so it has to carry no information about how much of the guess was right. Hand it `bytes`; `compare_digest` rejects a `str` containing any non-ASCII character.

Everywhere else it is not a security control and doesn't earn the ceremony. Checking a download against a published checksum, deduplicating artifacts by digest, spotting a changed build output — nobody is measuring and there is nothing to leak. Compare those as what they are: hex strings, normalized where they entered (rule 27), with `==`.

Two normalized hex strings are the same logical type, so this rule is satisfied. What it forbids is comparing across the boundary — a normalized digest against an unnormalized one, or a hex string against `bytes`. The line is the environment, not the datatype: the same `sha256` output is a secret in an auth backend and a filename in a build cache.

**v) A docstring names what the function raises — including what it raises through.**
A caller decides how to handle a failure by reading the signature, and the signature does not carry the failure. Annotate it. Three syntaxes do the job; prefer them in this order — Javadoc's `@throws X`, then Doxygen's `@exception X`, then Sphinx's `:raises X:`. Where the surrounding code already picked one, match it (rule 9).

Transitive raises count. An exception that reaches the caller through a function this one calls is part of this function's contract whether or not this function's own body contains a `raise`. The caller cannot see the call chain from the signature, and an exception that is only documented three frames down is not documented.

```python
def load_json(path: Path) -> Any:
    """Read and decode a JSON file.

    @throws JsonIOError the file cannot be read (through `_read_bytes`), or
        its content is not valid strict JSON.
    """
```

**A function whose only purpose is to raise is exempt** — the name is the annotation. `_reject_constant`, `_raise_for_status`, `_fail_unknown_field`: a name in the reject/refuse/fail/raise family already states the contract, and `@throws` on it says the same thing twice (rule 10).

**w) An exception you decide not to handle gets a comment on the line.**
Not handling an exception is a decision. Unwritten, it is indistinguishable from not having noticed it, and a reviewer cannot tell which — so they either re-derive the call chain or wave it through.

```python
def load_json(path: Path) -> Any:
    logger.debug("reading json: %s", path)
    raw = _read_bytes(path)   # raises JsonIOError if path is unreadable
```

Name the exception that actually arrives, not the one that was caught on the way. `_read_bytes` catches `OSError` and raises `JsonIOError` from it, so `# throws OSError` at this call site documents an exception the caller will never see — a comment that is wrong is worse than no comment, because it is trusted. And name the condition: `# may raise` tells the reader nothing they had not already suspected.

### 24. Named regex groups for data extraction
Use named groups (`(?P<name>...)`) over positional groups so extraction and downstream field access stay self-documenting and don't break silently on a reordering. Pairs with rule 3c — split the work across staged patterns, each using named groups.
