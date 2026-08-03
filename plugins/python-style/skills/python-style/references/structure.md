# Structure — types, control flow, and what to build

Choosing the right datatype, keeping control flow honest, and not building what isn't needed.

Part of the `python-style` skill. Rule numbers are global across the skill — see SKILL.md for the full index and for which file holds which rule.

### 6. Don't rely on hidden mechanics — treat a datatype as its purpose
Every datatype has a purpose: a mapping maps keys to values, a set holds distinct members, a queue has two ends. Some Python types carry behavior beyond that purpose.

**Assume the reader is a programmer, not specifically a Python programmer.** Someone who also works in other languages arrives with general assumptions about what a mapping or a list is. Language-specific extras are not straightforward to that reader, and code that leans on them is only readable to someone who knows that one implementation.

**A dict does key→value mapping. A dict preserving insertion order is a hidden mechanic** — it does not follow from what a mapping *is*, and most other languages' plain mapping types don't do it. That it is *documented* does not make it *intuitive*: it was a CPython implementation detail in 3.6 and became a language guarantee in 3.7, and a reader still has to know that history to tell whether the order in front of them is intended or incidental.

- **Don't rely on dict iteration order on a general basis.** It isn't more readable. Where order carries meaning, record it in a structure that means order, or sort explicitly (rule 28).
- **You may rely on it in a hot path** where the ordering is genuinely needed and a separate structure would cost real performance. That is a deliberate, local exception — comment it as one so the next reader knows it was a decision, not an accident.
- **If it's a queue, use a queue** — `collections.deque`, `queue.Queue` — not a list playing the part.

**What a `list` actually is.** A general programmer could reasonably assume "list" means something like a linked list — cheap at both ends. Python's `list` is not that: it's a dynamic array. O(1) amortized `append` at the end, O(n) `insert(0, ...)` at the front. Measured at n=50,000: `insert(0)` ran **40x slower than `append`** and **127x slower than `deque.appendleft()`**.

**So when someone says "list", check what they are actually doing** rather than taking the word as a type decision. Inserting at the front → `deque`. A fixed sequence that is never modified → `tuple` (and rule 3o). Membership tests → `set`. The word in the sentence is not the type.

### 7. Clean control flow
**A `break` must be conditional.** An unconditional `break` means the loop isn't a loop — it's unpacking in disguise, and it hides the fact that only one element is handled.

```python
seen = collections.defaultdict(set)
first_or_none = lambda data: next(iter(data), None)

# Wrong — reads as "for each variant", does exactly one.
for raw in rec.variants:
    _packet = decode_packet(raw)
    _digest = full_hash_bytes(_packet)
    seen[_digest].add(day)
    break

# Preferred — say that only the first variant is handled, and handle the
# empty case explicitly (rule 16).
_first = first_or_none(rec.variants)
if _first is None:
    raise ValueError("record has no variants")

_packet = decode_packet(_first)
_digest = full_hash_bytes(_packet)
seen[_digest].add(day)
```

**`if … return` then a bare `return` says "edge case". `if … return` / `else … return` says "two answers to one question".**

A bare trailing `return` reads as the normal path, and the `if` above it reads as the exception to it — a guard. That is the right shape for validation and error paths: `if _p is None: return None` at the top of a function is a guard clause (rule 3b), and nothing about it claims the two returns are peers.

Where they *are* peers, say so:

```python
# Wrong — orjson is not an edge case, it is the expected backend. The bare
# trailing return makes stdlib look like the normal path and orjson like
# the exception to it.
if _BACKEND == "orjson":
    return orjson.loads(raw)
return _json.loads(raw)

# Preferred — two answers to one question, and a third backend now has an
# `elif` to drop into instead of forcing a restructure.
if _BACKEND == "orjson":
    return orjson.loads(raw)
else:
    return _json.loads(raw)
```

**The test: does inverting the condition swap the two returns and change nothing else?** If `if not a: return Y` / `return X` is as true as `if a: return X` / `return Y`, then X and Y answer the same question, neither is the exception, and the pair is an `if`/`else`. If the inversion reads as nonsense, the `if` really is a guard and the guard form is right.

Two further reasons to prefer the paired form where it applies: a third case drops in as an `elif` in the middle rather than being appended somewhere, and the shape becomes visible as dispatch — which is the cue to reach for a `match` or a dict, below.

*Exception:* where the ask is explicitly to optimize for code length.

**An iterator is read left to right too — a comprehension with two `for` clauses is a nested loop.**
`(finding for check in _CHECKS for finding in check(tree))` names its output before anything that could produce one, and names the inner loop's source (`check`) after the clause that binds it. Left to right, it is out of order twice. Write the loops as loops, or give the nesting a name — rule 3t.

**Consecutive `if var == value: return` on one variable is a `match`.**

```python
# Wrong — a chain of ifs all testing the same variable, which should
# itself be an elif chain: as written, every branch is re-tested after
# one has already matched. And the bare trailing return makes "UNKNOWN"
# look like the normal path (above).
def label(kind):
    if kind == "insert": return "INSERT"
    if kind == "update": return "UPDATE"
    if kind == "delete": return "DELETE"
    return "UNKNOWN"

# Preferred as control flow — the structure says "dispatch on one value".
def label(kind):
    match kind:
        case "insert": return "INSERT"
        case "update": return "UPDATE"
        case "delete": return "DELETE"
        case _:        return "UNKNOWN"

# Preferred where it is data, not control flow — a mapping is a mapping,
# and a lookup table reads as a table.
_LABELS = {
    "insert": "INSERT",
    "update": "UPDATE",
    "delete": "DELETE",
}

def label(kind):
    return _LABELS.get(kind, "UNKNOWN")
```

**`match` vs. dict — decide on readability.**

- **dict when it's a lookup.** A lookup table is data, and a mapping is the type that means "lookup" (rule 6).
- **`match` when comparing just a few options** — or when the branches need guards, destructuring, or type patterns, which a dict cannot express at all.
- **dict when the `match` has grown too long to read.** A forty-case `match` is a wall; a dict is a table.

**One assumption to drop first, because it is wrong here.** In C, a `switch` over dense constants compiles to a jump table and dispatches in O(1) — a programmer arriving with that mindset expects `match` to do the same. CPython does not do this today: literal `match` cases compile to a *sequential comparison chain*, O(n) in the number of cases, with no jump table — `dis` shows it. A dict's lookup cost stays flat, because `str` objects cache their hash. **So in a hot path being optimized (rule 12), use a dict** — and measure it there (rule 19), since this is a current CPython implementation property rather than a language guarantee.

### 8. Arithmetic is not truthiness — never let 0 stand in for False
```python
# Wrong — the reviewer has to stop and work out whether this fires on odd
# or on even. This is math: the result is an integer, not a flag.
if n % 2:
    ...

# Preferred — the comparison states the intent.
if n % 2 != 0:
    ...
```
Applies wherever a numeric result drives a branch: `if len(x)` → `if len(x) != 0`; `if count` → `if count > 0`. Compare the number to the number you mean. The same reasoning is why `if _p is None` beats `if not _p` — `not _p` also swallows `b""` and `0`.

### 10. DRY — don't repeat yourself
Refrain from repeating the same code. A lambda, a small function, a cached result, or a wrapper is almost always available.

```python
# Wrong — the same primitive spelled out at every call site.
node_id = hashlib.sha256(pubkey).digest()
chan_id = hashlib.sha256(channel_name.encode()).digest()

# Preferred — one wrapper, one place to change it. The wrapper body still
# follows rule 2: the chain is split, and the return line only returns.
def sha256_digest(data: bytes) -> bytes:
    _hash = hashlib.sha256(data)
    return _hash.digest()

node_id = sha256_digest(pubkey)
chan_id = sha256_digest(channel_name.encode())
```

### 11. YAGNI — including imports
Before introducing a class, check whether a dict, `NamedTuple`, or plain `@dataclass` (no methods, no invariants) covers the need. Escalate to a full class only when there's actual behavior to encapsulate or an invariant to enforce — not because "this data belongs together".

```python
# Just data, no behavior — a dict is enough.
node = {"pubkey": pubkey, "confidence": confidence, "first_seen": first_seen}

# Escalate only when there is real behavior/invariants to protect:
class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._events: list[float] = []

    def allow(self) -> bool:
        ...
```

**This applies to imports.** If a file doesn't need an import, remove it. After writing code, check that every import is actually used.

### 12. Optimize at the algorithmic level, not with clever Python
If a different data structure or algorithm changes the complexity class, fix that first. A dict/set gives O(1) membership — don't tune a linear scan instead of switching. A Bloom filter gives an O(1) probabilistic existence check. `bisect` on a sorted list beats re-sorting per query. `collections.Counter`/`defaultdict` beat hand-rolled accumulation.

Only once the algorithm is right does code-level tuning make sense — and even then prefer the clear version over "fancy" Python (nested comprehension tricks, `functools.reduce` chains, walrus density, metaclass cleverness). Clever Python that saves microseconds while costing reviewability is a net loss; a data structure that turns O(n²) into O(n) is not.

### 31. Treat a block as a scope, the way every other language does
A general programmer reads `try`, `if`, `for`, `while` and `with` as scoping constructs: a name introduced inside the block belongs to the block and is gone when the block closes. Python does not work that way. Only modules, functions, classes and comprehensions scope; every other block leaks every name it binds into the enclosing function, where it stays readable afterwards.

That leak is a hidden mechanic (rule 6), so don't build on it. Python itself concedes the point in one place: `except OSError as exc` **deletes** `exc` when the clause ends. That deletion is the behavior the reader already expects everywhere else.

**Don't read a name after the block that introduced it.** Where a value has to cross the boundary, hand it across explicitly. The block's job becomes producing one value, and the thing that produces a value is a small function (rule 3e).

```python
# Wrong — `raw` is introduced inside the try and read after it. It runs,
# and to a C, Rust or Java reader it reads as a use-after-scope bug.
def load_bytes(path):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IOError(f"cannot read {path}: {exc}") from exc
    return decode(raw)

# Preferred — the try wraps one operation and returns its value. `raw` is
# introduced in the scope that uses it.
def _read_bytes(path):
    try:
        return path.read_bytes()
    except OSError as exc:
        raise IOError(f"cannot read {path}: {exc}") from exc

def load_bytes(path):
    raw = _read_bytes(path)
    return decode(raw)
```

**Where extracting a function isn't wanted, declare the name before the block.** The extraction above is the better fix — the block gets one job and the value leaves through a `return`. This one needs no new function and always works:

```python
# Generalized fix — declare outside the scope, before use. The name now
# visibly belongs to the function, and the try only assigns to it.
def load_bytes(path):
    raw = None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IOError(f"cannot read {path}: {exc}") from exc
    return decode(raw)
```

`raw = None` is not a value anyone reads — the `except` re-raises, so `decode` never sees it. It is a declaration, and it is the line a C or Java reader went looking for and didn't find.

**A module-level `try` around an import is a necessary exception.** An optional dependency has no other spelling:

```python
try:
    import orjson
    _BACKEND = "orjson"
except ImportError:
    import json as _json
    _BACKEND = "json"
    logger.warning("orjson unavailable — falling back to stdlib json")
```

The names bound here are module globals by construction. There is no enclosing function to hand them out of, and no small function that could return an import — an import binds into the namespace that executed it. This is where rule 20's seam lives.

**A loop variable is the same case.** `for node in nodes:` leaves `node` bound to the last item after the loop. Reading it there is reading a name every other language calls dead. If the last item is what you want, produce it deliberately and name it (`_last`), so the line says so.

**Where a name must not outlive its block, `del` it.** That is what rule 3h's `del h` is doing: `with open(...) as h` leaves `h` bound to a closed file, and the `del` restores the scoping the reader assumed was there.

**A comprehension does scope** — `[x for x in items]` does not leak `x` — which makes the asymmetry the real argument. A reader cannot tell by looking which Python blocks scope and which don't, so don't ask them to.
