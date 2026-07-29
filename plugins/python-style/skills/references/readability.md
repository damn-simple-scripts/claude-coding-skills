# Readability — how code reads

How a line, a name, and an unfamiliar library call should present themselves to a reader.

Part of the `python-style` skill. Rule numbers are global across the skill — see SKILL.md for the full index and for which file holds which rule.

### 1. Code is read left to right — front-load meaning
The reader should learn what a line does as early in the line as possible, and should never have to read to the end of an argument list to discover something the line's opening implied was open.

```python
# Wrong — reading left to right, `hmac.new(...)` suggests the hash function
# is a runtime choice. You only learn it is fixed to sha256 at the end of
# the argument list.
prk = hmac.new(salt, ikm, hashlib.sha256).digest()

# Preferred — the *name* carries sha256, so the reader never has to consider
# that the algorithm might be selected dynamically. Either binding does that
# equally; the syntax is not the point. Match the surrounding code.
hmac_sha256 = lambda key, msg: hmac.new(key, msg, hashlib.sha256)
# ...or:
def hmac_sha256(key, msg):
    return hmac.new(key, msg, hashlib.sha256)

_mac = hmac_sha256(salt, ikm)
prk = _mac.digest()   # chain split — rule 2
```

**A named lambda, a module-level `def`, and a `def` nested inside the calling function all satisfy this equally.** What matters is that the *name* carries the fixed choice, not the syntax that binds it. Pick whichever reflects the style of the surrounding code — PEP 8 / ruff flag the named-lambda form as `E731`, so a project with that lint enabled is already using `def`.

### 2. One purpose per line
A single line does one thing. Don't fuse stages of a transformation into one line just because the syntax allows it.

**Intermediate stages: leading-underscore name, overwritten each step** — not a fresh descriptive name per stage.

```python
# Wrong — filter, threshold check, and transform all fused into one line
result = [transform(x) for x in items if is_valid(x) and x.score > threshold]

# Preferred — each stage on its own line, each stage still a lazy
# generator, not a list (rule 13). `_items` is intentionally overwritten:
_items = (x for x in items if is_valid(x))           # filter valid
_items = (x for x in _items if x.score > threshold)  # filter thresh
_items = (transform(x) for x in _items)              # transform output
result = list(x for x in _items)                     # collect
```

Why overwrite rather than name each stage distinctly: see rule 3a — it's a defensive measure, not naming taste.

#### Exception: trivial output formatters may share the line
`.hex()`, `.lower()`, `.upper()`, `math.floor()` and friends only shape the output. They may sit on the same line as the calculation — but **all three conditions must hold**:

1. **Trivial, no side effect.**
2. **The intermediate is not needed *and* cannot usefully be reused.**
3. **Self-describing** — any programmer reads it without opening the manual.

```python
# OK — nothing to reuse, nothing to look up.
node_id = full_hash_bytes(packet).hex()
channel = raw_name.strip().lower()
bucket_index = math.floor(score / _BUCKET_WIDTH)
```

Condition 2 is the one that needs actual thought. `.hex()` on a throwaway `bytes` is fine. But where the intermediate object *is* reusable, discarding it costs memory efficiency (rule 14) — reuse the object and reset its content rather than destroying it:

```python
# Wrong in a hot loop — a buffer allocated and thrown away every iteration.
for row in rows:
    _buf = io.StringIO()
    csv.writer(_buf).writerow(row)
    send(_buf.getvalue().strip())

# Preferred — one buffer, reset per iteration. Measured on 20k rows: 1.54x
# faster, identical output.
_buf = io.StringIO()
_writer = csv.writer(_buf)
for row in rows:
    _buf.seek(0)
    _buf.truncate(0)
    _writer.writerow(row)
    send(_buf.getvalue().strip())
```

The same three conditions apply to output-formatting lambdas and functions, not just builtins.

**Prefer to carry the formatting in the variable name:**

```python
elements = len(rec.variants)        # wrong — does not say it is a count
element_count = len(rec.variants)   # preferred
```

#### Exception: well-known math formulas are one purpose
```python
# OK — the modified-Z-score / MAD outlier test is a recognized formula.
# Splitting it into five lines helps neither the reader who knows it nor
# the reader who doesn't.
if abs(c - median) / (1.4826 * mad) > sigma:
    ...
```

#### A `return` line only returns
```python
# Wrong — the return line evaluates a ternary. A `bla if blub else foo` is
# itself something the reader must stop and reason about.
return "active" if node.last_seen > cutoff else "stale"

# Preferred — decide, then return. "active" and "stale" are peers, not a
# case and its exception, so they pair (rule 7).
if node.last_seen > cutoff:
    return "active"
else:
    return "stale"

# Also OK — the ternary on its own line, then return. A ternary is handled
# just like a function call: fine as a line's single purpose, not fine
# fused onto the return. If this ternary also contained a function call it
# would become too complex for one line and would need splitting further.
_res = "active" if node.last_seen > cutoff else "stale"
return _res

# OK — return + a simple function/lambda call, when the return type
# matches. The reader already read and understood the call as a unit, so
# nothing new is being evaluated on the return line.
return status_label(node)

# OK — return + literal object, when building that object *is* the
# function's whole purpose. Not OK if the function's main point is
# something else and the object is incidental.
def as_record(node):
    return {"pubkey": node.pubkey, "seen": node.last_seen}
```

#### Path construction and file opening are two purposes
You almost always want the path logged (rule 3i), which is a second, independent reason to split.

```python
# Wrong — join + open on one line, and no record of which file was touched.
with open(os.path.join(cache_dir, meta_filename(day)), "r", encoding="utf-8") as h:
    ...

# Preferred — build the path, log it, then open it. The log line is what
# tells you the path was wrong or the permissions were wrong.
_meta_path = os.path.join(cache_dir, meta_filename(day))
logger.debug("reading meta file: %s", _meta_path)
with open(_meta_path, "r", encoding="utf-8") as h:
    ...
```

#### Chained calls each get a line
```python
# Wrong — preimage construction, hashing, digest extraction, truncation,
# and return all fused into one line.
return hashlib.sha256(_canonical_preimage(packet)).digest()[:CANONICAL_HASH_BYTES]

# Preferred — one step per line.
_preimage = _canonical_preimage(packet)
_hash = hashlib.sha256(_preimage)
_digest = _hash.digest()
_truncated = _digest[:CANONICAL_HASH_BYTES]
return _truncated
```

#### Splitting is a review technique, not just formatting
```python
# Wrong — setdefault does two jobs at once: it inserts a default AND
# returns the inserted object, which is then mutated on the same line.
seen.setdefault(digest, set()).add(day)
```

Following that line requires `setdefault`'s exact documented return value. Split, it is two operations — get-or-create the set, then add to it:

```python
if digest not in seen:
    seen[digest] = set()
seen[digest].add(day)             # explicit: index the dict, then mutate

# Or say it with the type — a defaultdict means "missing key gets a default".
seen = collections.defaultdict(set)
seen[digest].add(day)
```

Note `{day}`, not `set(day)`: where `day` is a string, `set("2026-07-01")` yields a set of *characters* — no error, wrong set.

`seen[digest] = {day}` is not the split: it clobbers an existing set on a second insert for the same key, where `setdefault(...).add(...)` adds to it. The one-liner saves one line and costs a manual lookup — it reads as clever and reviews as opaque, a rule 3 problem rather than a formatting one. If splitting a line reveals the line was doing something other than what it looked like, that is the rule working.

### 4. Variable names say what the value *is*, not how it was computed
```python
# Wrong — `fixed` describes how the value was derived, not what it means.
fixed = _PUBKEY_LEN + _TIMESTAMP_LEN + _SIGNATURE_LEN
if len(payload) < fixed + 1:
    raise ValueError("payload too short")

# Preferred — the name states what the value is. The leading underscore
# marks it a temporary not needed outside this function.
_min_length = _PUBKEY_LEN + _TIMESTAMP_LEN + _SIGNATURE_LEN + 1
if len(payload) < _min_length:
    raise ValueError(f"payload {len(payload)}B < minimum {_min_length}B")
```

### 5. Reach for the most descriptive function a type offers
When working with a datatype, check whether a more descriptive function exists than the generic one. A reader should not need the manual to learn what a call projects.

```python
# Wrong — `iter(mapping)` yields the keys, but nothing on the line says so.
# The reader has to check the manual to notice. That makes review harder.
for k in iter(mapping):
    ...

# Preferred — the method name states which projection is taken.
for key in mapping.keys():
    ...
for key, value in mapping.items():
    ...
for value in mapping.values():
    ...
```

Where genuinely no descriptive name exists, build one (rules 1 and 10):

```python
first = lambda data: next(iter(data))
```

`next(iter(data))` doesn't say "first" to a reader, and Python offers no builtin that does. That is what this rule means by *no descriptive name exists* — and it is rarer than it looks.

`iter(mapping)` is not such a case. `.keys()` already exists, already says what it projects, and costs nothing to prefer — there is no memory axis and no speed axis to trade against readability.

The belief that `.keys()` materializes is a Python 2 memory — there it returned a list. In Python 3 it returns a lazy view, so both spellings are lazy and neither allocates. What costs memory is `list(...)` wrapped around either spelling — that is rule 13, not a choice between these two.

The rule generalizes past mappings — every type has its own vocabulary, and the descriptive call is the one that names the operation:

```python
# Wrong — a membership loop the reader has to decode into "subset".
if all(x in allowed for x in requested):
    ...

# Preferred — the method names the operation.
if requested.issubset(allowed):
    ...
```

### 9. The reader should not need to open documentation
After writing code, assess whether the reader is plausibly familiar with the library surface being used. If not — annotate.

**Assumed known, no annotation needed:** common regex operators, `%`-style format specifiers (`%d`, `%x`), time format strings (`strftime` codes), and comparable everyday formats.

**Not assumed known** — e.g. `struct` format strings. Annotate what the non-obvious parameters mean:

```python
# struct format: "<" = little-endian, "I" = unsigned int (4 bytes).
_ts = struct.unpack_from("<I", payload, off)
# docs: "The result is a tuple even if it contains exactly one item."
timestamp = _ts[0]
```
Two things happening there, both required by this rule: the format string is decoded for the reader, and the call is split from the indexing so the documented tuple-even-for-one-item behavior can be cited on the line it matters. **Where a specific, non-intuitive, documented behavior is crucial to the logic, cite the documentation inline** — don't make the reader go find it.
