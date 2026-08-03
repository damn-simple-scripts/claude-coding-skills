# Data handling and I/O

Iterators, memory, failure handling, serialization, and getting bytes to disk without corrupting them.

Part of the `python-style` skill. Rule numbers are global across the skill — see SKILL.md for the full index and for which file holds which rule.

## Contents

- **13.** Prefer iterators over eager list construction — collect as late as possible
- **14.** Where two forms are equivalent, take the one that builds no intermediate
- **15.** Classify data volume upfront — don't default blindly
- **16.** Fail loud, no silent fallbacks — always with a stated reason; mechanism not prescribed
- **18.** Atomic writes
- **20.** Wrap replaceable operations — small, swappable seams
- **21.** Strict, format-appropriate serialization — JSON is not the default choice
- **22.** Centralized structured-data I/O helper module (`jsonio.py`-style)
- **23.** Explicit memory cleanup with `del` for large intermediates
- **27.** Hex values from external/observed sources: normalize case on ingestion
- **28.** Never assume serialization order is deterministic

### 13. Prefer iterators over eager list construction — collect as late as possible
Default to generator expressions / iterator chains over intermediate lists. Materialize a concrete container only where you actually need one: a final result, something iterated more than once, or something whose length you need.

Independent of rule 2 — a pipeline can be split across lines while still materializing too early. Splitting into lines and collecting early are two different mistakes.

**Don't populate a data structure with a loop — collect into it.**

```python
# Wrong — a loop whose whole job is to fill a set, with error handling
# tangled into the accumulation.
fhs = set()
for raw in rec.variants:
    try:
        fhs.add(full_hash_bytes(decode_packet(raw)))
    except ValueError:
        fhs.add(None)

# Preferred — one small function decides the value for one input; the
# collection is a single expression.
def _hash_or_none(raw):
    try:
        _p = decode_packet(raw)
    except ValueError:
        return None
    if _p is None:
        return None
    return full_hash_bytes(_p)

fhs = set(_hash_or_none(raw) for raw in rec.variants)
```

**The loop form above doesn't just read worse — it *crashes*.** When `decode_packet` returns `None` rather than raising, the loop passes `None` into `full_hash_bytes` and dies with `TypeError`; only `ValueError` was ever caught. Extracting the per-item decision into `_hash_or_none` is what made the missing case visible.

**Name the collection type — don't hide it in brackets.** A `[...]`/`{...}` comprehension materializes a container without naming which; `list(...)`, `set(...)`, `dict(...)` around a generator expression put the target type at the front of the line, where rule 1 wants the meaning. The `set(...)` collection above is already in this form.

```python
# Wrong — the line leads with `[`; the reader learns the type only by
# reading to the matching bracket.
_matches = [span for span in _spans if span.name == name]

# Preferred — `list` is the first token: the line names what it collects
# into before it says how.
_matches = list(span for span in _spans if span.name == name)
```

### 14. Where two forms are equivalent, take the one that builds no intermediate
Two forms are equivalent when they produce the same result and imply the same syscalls. Then the tiebreak is memory: prefer the one that doesn't materialize a buffer along the way.

```python
# Wrong — builds an ever-growing intermediate buffer just to hash it.
_buf = b""
for chunk in chunks:
    _buf += chunk
digest = hashlib.sha256(_buf).digest()

# Preferred — same result, no intermediate. Measured on 2000x1KB chunks:
# ~31x faster, and constant memory instead of linear.
_hash = hashlib.sha256()
for chunk in chunks:
    _hash.update(chunk)
digest = _hash.digest()
```

Same for string building — beyond a handful of pieces, one `join` rather than repeated `+=`:

```python
_out = ";".join(fields)   # not: _out = ""; for f in fields: _out += f + ";"
```
**`join` here is not about raw speed.** CPython has an in-place optimization for `str +=` when the target has exactly one reference, so in a simple loop `+=` runs roughly equal to `join` — benchmark it there and it looks fine. The optimization disappears the moment a second reference to the string exists: 6.9x slower at 30k iters, no error, no warning. It is a CPython implementation detail rather than a language guarantee. `join` is predictable; `+=` is fast only by accident. The `bytes`-buffer-then-hash case above has no such rescue and is genuinely ~31x worse.

**Same principle for loops that accumulate into a structure** — a small generator with clean `if`s and `yield`s, collected at the end:

```python
# Wrong — accumulate into a list inside a loop.
def collect_active(nodes):
    out = []
    for n in nodes:
        if n.last_seen is None:
            continue
        if n.last_seen < cutoff:
            continue
        out.append(transform(n))
    return out

# Preferred — a small generator nested in the collecting function, each
# condition on its own line (rule 2), lazy throughout (rule 13); collect
# at the end.
def collect_active(nodes):
    def _active():
        for n in nodes:
            if n.last_seen is None:
                continue
            if n.last_seen < cutoff:
                continue
            yield transform(n)

    return list(_active())
```

**Where the stages are filters and maps rather than control flow, name the source at stage 0 and overwrite it at each stage** (rule 3a). Every line then has one purpose and the same shape:

```python
def collect_active(nodes):
    _nodes = iter(nodes)                                     # stage 0: the source
    _nodes = (n for n in _nodes if n.last_seen is not None)  # drop unseen
    _nodes = (n for n in _nodes if n.last_seen >= cutoff)    # drop stale
    _nodes = (transform(n) for n in _nodes)                  # transform
    _nodes = list(_nodes)                                    # collect
    return _nodes
```

Stage 0 is the line that binds the source into the name every later stage overwrites. For a list, `iter(nodes)` is redundant — a generator expression calls `iter` on its source anyway. Write it regardless: it makes stage 1 look like stage 2 look like stage 3, so a reader scanning the column sees a pipeline instead of one special line followed by a chain. It is also where a source that *isn't* redundant goes — `mapping.items()`, `path.open()`, `cursor.fetchmany()`, `zip(a, b)` — and those lines have to exist somewhere.

The nested-generator form above and this one solve the same problem. Reach for the nested generator where a stage needs control flow — an early `continue`, a `try`, a `yield` of something the input didn't contain. Reach for the overwrite chain where every stage is a filter or a map, because then the chain says so on every line.

**A call that duplicates the data is a volume decision, not a style one.** `str.splitlines()` on a 10 KB config is right, and anything else is noise. On a file whose size you don't know, it builds every line as a new object on top of the string that already holds all of them. 400,000 lines / 18.4 MB, CPython 3.12.3:

| approach | peak allocation | time |
|---|---|---|
| `read_text()` + `.splitlines()` | 56.0 MB | 0.23s |
| `read_text()` + `iter_splitlines()` | 36.7 MB | 1.35s |
| `open(path)`, iterate the handle | **0.0 MB** | **0.17s** |

**Where the file is still on disk, iterate the handle.** It allocates nothing, it is the fastest, and it is three lines.

The scanner below is for text already in hand that cannot be re-read — a payload off a socket, a decompressed blob, a column out of a database. It buys the copy back and pays time for it:

```python
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
```

The boundary set is stated once, in the pattern. Stripping the boundary off the line afterwards spells the same set twice — once in the character class, once in the `rstrip` — and the two drift (rule 10). A named group makes `keepends` a choice of which group to yield, so nothing is stripped and nothing is duplicated.

`str.splitlines()` breaks on more than `\n`: `\r`, `\r\n`, `\v`, `\f`, `\x1c`, `\x1d`, `\x1e`, `\x85`, `\u2028` and `\u2029` are line boundaries to it as well. A replacement is only a replacement if it agrees on every one of them, so a differential test against `splitlines` over a corpus carrying each boundary is part of writing one (rule 3k).

**Run this check on any call whose name does not reveal that it builds the whole thing at once**, not just this one: `.split()`, `.splitlines()`, `.readlines()`, `re.findall` where `finditer` exists, `json.loads` of a large document. The name gives no warning — `.readlines()` would read as easily as a lazy view or a mapping — so the cost stays hidden until the volume is large. `list(...)` and `sorted(...)` are not on this list: their name *is* the materialization, so reaching for one is already the decision. `.read()` is not either — a whole-file read is its own discipline (iterate the handle instead, above; rule 20). `d.items()`/`d.keys()`/`d.values()` return dynamic views, not lists — the materializing form is `list(d.items())`, already implied by choosing `list(...)`. The question is what the call costs at the volume this input can actually reach (rule 15), not at the volume the example had.

Annotate the call with that bound: a `.split`/`.rsplit`/`.splitlines`/`.readlines`/`.findall` carries a comment on its own line or the line above, naming the input's maximum size and why that size is safe.

### 15. Classify data volume upfront — don't default blindly
- **Pre-processing / first pass over raw, unfiltered data:** always iterator/streaming style.
- **Already-filtered dataset:** loading into memory is fine — filtering already bounded the size.
- **Known/bounded size** (a cache of API calls, a small config, a fixed export): lean toward the memory-heavier, simpler option.
- **In doubt:** iterator style, or ask.

Where genuinely ambiguous even after trying to classify, provide both variants labeled explicitly.

### 16. Fail loud, no silent fallbacks — always with a stated reason; mechanism not prescribed
If something required is missing, malformed, or ambiguous, surface it immediately with context — don't substitute a default, swallow the failure, or degrade quietly.

**Not codified: that this must use exceptions.** A Result-style object (same shape as the Rust conventions — an explicit success/failure value the caller must handle) can be equally appropriate. Pick what fits the codebase in front of you.

**What *is* codified: every failure path carries an explicit reason.** Exception, `Result`, or returned error value — it must say *why*. A bare `raise ValueError()` is as much a violation as swallowing the failure.

**Narrow carve-out:** genuinely optional diagnostic/enrichment fields (a nice-to-have summary column) may fail-soft with an empty/placeholder value rather than aborting the pipeline — *only* where that matches the project's existing treatment of similar optional fields. Not a general license. In doubt: fail loud and ask.

### 18. Atomic writes
Any write to a file that could be read by another process, or that must never be left half-written on crash/interrupt, goes to a temp path and is renamed into place (`os.replace`) — not written in-place. See rule 3h for the full sequence.

### 20. Wrap replaceable operations — small, swappable seams
Wrap the operations that are likely to need swapping: decoding structured data, making web requests, reading files. Keep the wrapped methods small so replacing the implementation is a one-file change, not a grep across call sites.

**Adopting an optimized third-party replacement is a judgment call, not a default.** Check that the library is actually, measurably better *and* actually needed for this workload — and weigh the technical debt of the dependency against the benefit:

- **`orjson` over stdlib `json`:** a known win, worth it. But it's not a true drop-in — `dumps` returns `bytes` (not `str`) and takes `orjson.OPT_*` flags instead of `indent=`/`sort_keys=`. The wrapper is exactly where that difference gets absorbed.
- **A third-party CSV writer over `csv`:** not meaningfully better than a good stdlib wrapper. The dependency would introduce more technical debt than it removes. Don't.

The wrapper is what makes this a decision you can revisit cheaply: start on the stdlib behind a seam, measure, and swap only where the evidence says so.

### 21. Strict, format-appropriate serialization — JSON is not the default choice
No permissive/lenient parsing (no trailing commas, no comments, no implicitly-accepted `NaN`/`Infinity`). Malformed input is a fail-loud error (rule 16), never coerced into a best-effort parse.

**Don't default to JSON as the format.** Pick what fits the data: CBOR or Parquet for compact/typed/columnar, CSV/TSV for simple tabular, JSON where it's genuinely right (nested, human-readable, interoperable).

### 22. Centralized structured-data I/O helper module (`jsonio.py`-style)
Route structured-data read/write through one small shared module rather than calling the format library ad hoc at each call site. This is where strict parsing (rule 21), the wrapper seam (rule 20), and atomic writes (rule 18) actually get enforced in one place instead of being re-implemented — or forgotten — per call site.

```python
"""jsonio.py — centralized JSON I/O.

- orjson is the default backend where available (rule 20); the stdlib
  fallback is logged, not silent (rule 16).
- All writes are atomic: temp file in the same directory, then os.replace
  (rule 18).
- Parsing is strict — malformed input is a fail-loud error (rule 21).
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import orjson
    _BACKEND = "orjson"
except ImportError:
    import json as _json
    _BACKEND = "json"
    logger.warning("orjson unavailable — falling back to stdlib json")


class JsonIOError(RuntimeError):
    """Always raised with an explicit reason — never swallowed (rule 16)."""


def _read_bytes(path: Path) -> bytes:
    """Read a file whole; the try wraps one operation and hands the value out (rule 31).

    @throws JsonIOError the file cannot be read.
    """
    try:
        return path.read_bytes()
    except OSError as exc:
        raise JsonIOError(f"cannot read {path}: {exc}") from exc


def _reject_constant(literal: str) -> None:
    """stdlib json accepts NaN/Infinity/-Infinity by default. Rule 21 does not."""
    raise JsonIOError(f"non-RFC-8259 constant in JSON: {literal}")


def load_json(path: Path) -> Any:
    """Read and decode a JSON file.

    @throws JsonIOError the file cannot be read (through `_read_bytes`), its
        content is not valid JSON, or it carries a NaN/Infinity literal
        (through `_reject_constant`).
    """
    logger.debug("reading json: %s", path)
    raw = _read_bytes(path)   # raises JsonIOError if path is unreadable

    if _BACKEND == "orjson":
        try:
            return orjson.loads(raw)
        except orjson.JSONDecodeError as exc:
            raise JsonIOError(f"malformed JSON in {path}: {exc}") from exc
    else:
        try:
            return _json.loads(raw, parse_constant=_reject_constant)
        except _json.JSONDecodeError as exc:
            raise JsonIOError(f"malformed JSON in {path}: {exc}") from exc


def save_json(path: Path, data: Any, *, indent: bool = False) -> None:
    """Atomic write: temp file in the same dir, complete, then os.replace.

    Non-finite floats are not RFC 8259 values and the backends disagree: orjson
    writes null, stdlib raises. Neither routes floats through its `default=`
    hook, so agreeing would cost a recursive walk of `data` on every write.
    Don't hand this function nan or inf.

    @throws JsonIOError `data` cannot be serialized.
    @throws OSError the temp file cannot be created, written, or renamed.
    """
    if _BACKEND == "orjson":
        option = orjson.OPT_INDENT_2 if indent else 0
        try:
            payload = orjson.dumps(data, option=option)
        except orjson.JSONEncodeError as exc:
            raise JsonIOError(f"cannot serialize for {path}: {exc}") from exc
    else:
        try:
            payload = _json.dumps(
                data, indent=2 if indent else None, allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise JsonIOError(f"cannot serialize for {path}: {exc}") from exc

    fd, tmp_path = tempfile.mkstemp(   # raises OSError if path.parent is not writable
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    logger.debug("writing json via temp file: %s -> %s", tmp_path, path)
    try:
        with os.fdopen(fd, "wb") as h:
            h.write(payload)
            h.flush()
            os.fsync(h.fileno())
            h.close()
    except Exception:
        os.unlink(tmp_path)
        raise
    del h                              # invalidate the name before the handover (rule 3h)

    os.replace(tmp_path, path)         # raises OSError if the rename fails
```

The same shape applies to non-JSON formats per rule 21 (`cbor2`/`pyarrow` instead of `orjson`) — `jsonio.py` is the JSON-specific instance of the pattern, not the only one. A Parquet- or CBOR-primary project gets an equivalent sibling module rather than forcing everything through `jsonio.py`.

### 23. Explicit memory cleanup with `del` for large intermediates
Don't rely on a large variable going out of scope naturally. When a large intermediate — a big list/array/DataFrame, or a memory-heavy call result — is done, drop it with `del` before the next heavy step, not at the end of the function.

```python
raw_cache = load_entire_cache(path)   # large — hundreds of MB
index = build_index(raw_cache)
del raw_cache                          # drop before the next heavy step

enriched = enrich_with_context(index)
```
Not for small/short-lived values, where `del` would just be noise.

### 27. Hex values from external/observed sources: normalize case on ingestion
Normalize hex strings from external sources (API responses, packet captures, user input) at the boundary — don't key on or compare hex that might differ only in case later.

The reason it has to happen at the boundary is that the failure is silent, and which way it goes depends on what the code happens to key on:

```python
seen = {"a1b2c3d4"}
"A1B2C3D4" in seen                                        # False — no error
{"a1b2c3d4": "node-1"}.get("A1B2C3D4")                    # None — no error
bytes.fromhex("A1B2C3D4") == bytes.fromhex("a1b2c3d4")    # True
```

The bytes compare equal; the strings do not. A pipeline that decodes to `bytes` early never sees this, and one that keeps the hex as a string sees it as a cache miss, a duplicate row, or a node that appears twice — never as an exception. Normalizing where the string enters is what makes the two paths agree.

### 28. Never assume serialization order is deterministic
A dict preserving insertion order is a hidden mechanic (rule 6), so treat a dict as an unordered type and don't let serialized output depend on it.

Where the serialization has to be deterministic — a fingerprint, a hash input, a dedup key, a signature — sort at the point of serialization, and let the line say so:

```python
# Wrong — deterministic today, and nothing on the line says why.
payload = json.dumps(counts)

# Preferred — the ordering is stated. It survives a reviewer, an encoder
# swap, and a port to a language whose maps genuinely are unordered.
payload = json.dumps(counts, sort_keys=True)
```

Explicit before implicit. A sort that is written down holds across versions, across encoders, and across a rewrite in another language. An order inherited from insertion holds only as long as every future insert lands in the same place, and nothing fails on the day one doesn't.

Where a measurement says the sort is the bottleneck (rule 12), leaning on the 3.7+ insertion-order guarantee is a legitimate optimization — and the line then says that the order is the dict's.

Type-tag values while you are there, so `1` and `"1"` can't collide in the serialized form.

The direct implication: **wherever exact order is crucial — fingerprints, hashes, dedup keys, signatures — sort the keys explicitly** rather than relying on the serializer. Where the values' types could also vary, tag them by type before serializing, so `1` and `"1"` can't collide into the same preimage.
