---
name: python-style
description: Clemens's Python coding conventions — one-purpose-per-line readability, a defensive-coding checklist, fail-loud/atomic I/O, lazy-iterator discipline, and empirical verification before claims. Use whenever writing, reviewing, editing, or generating Python (.py) code, or discussing Python I/O, data-processing, or CLI-tooling architecture — even if the user doesn't explicitly ask for "style" or "conventions" to be applied. These conventions deliberately deviate from some idiomatic Python defaults; apply them even when they conflict with what would normally be considered "cleaner" or more Pythonic.
---

# Python Style — Clemens's Conventions

## How to use this skill

**The summaries below are the rules.** Each is complete enough to act on — apply them directly without loading anything else.

**The table below says which reference to read and when.** The references carry the worked examples, the counter-examples, the carve-outs, and the measurements behind rules that would otherwise look arbitrary.

Rule numbers are canonical and global: rule 16 is rule 16 in every file.

**The benchmarks in the references** were run on CPython 3.12.3, x86-64 Linux. They are properties of a CPython version, not language guarantees. Use them to understand why a rule reads the way it does, and re-measure in the target environment before leaning on any of them to justify a hot-path decision.

| File | Rules | Read it when |
|------|-------|--------------|
| `references/readability.md` | 1, 2, 4, 5, 9 | A line fuses stages, a name states a derivation, or a call needs the manual |
| `references/defensive.md` | 3, 24 | Parsing input, writing files, regex, concurrency, or reimplementing a primitive |
| `references/structure.md` | 6, 7, 8, 10, 11, 12, 31 | Choosing a datatype, writing control flow, deciding what to build |
| `references/data-and-io.md` | 13, 14, 15, 16, 18, 20, 21, 22, 23, 27, 28 | Handling data, memory, files, serialization, or failure |
| `references/project.md` | 17, 19, 25, 26, 30 | Setting up a project, verifying work, or wrapping one up |

## Rule summary

### Readability → `references/readability.md`

**1. Code is read left to right.** Front-load meaning; a reader should never reach the end of an argument list to discover something the line's opening implied was open. Bind a fixed choice into a name (`hmac_sha256`, not `hmac.new(..., hashlib.sha256)`). Named lambda, module-level `def`, or nested `def` all work — match the surrounding code.

**2. One purpose per line.** Don't fuse stages of a transformation. Intermediates get a leading-underscore name, overwritten each step. A `return` line only returns — no ternary fused onto it. Path construction and file opening are two purposes. Chained calls each get a line. *Exceptions:* trivial output formatters (`.hex()`, `.lower()`, `math.floor()`) may share the line when all three conditions hold — trivial with no side effect, intermediate neither needed nor reusable, self-describing; and well-known math formulas are one purpose.

**4. Variable names say what the value *is*, not how it was computed.** `_min_length`, not `fixed`. A leading underscore marks a temporary.

**5. Reach for the most descriptive function a type offers.** `mapping.keys()`, not `iter(mapping)`. Where no descriptive name exists, build one (`first = lambda data: next(iter(data))`).

**9. The reader should not need to open documentation.** Common regex operators, `%d`/`%x`, and `strftime` codes are assumed known; `struct` format strings are not. Annotate unfamiliar library surfaces, and cite non-intuitive documented behavior inline where it's crucial to the logic.

### Prevent stupid mistakes → `references/defensive.md`

**3. The defensive-coding checklist.** Every item exists because the failure mode is silent, late, or hard to spot in review:

- **a** Overwrite the variable holding an iterator at each chaining stage — an exhausted generator yields nothing rather than raising.
- **b** Validate user input at the boundary; check parameters at the start of the function; fail early.
- **c** Split regex work into stages — no clever mega-regex that fails opaquely.
- **d** Multiple files: be explicit about concurrency. Any mechanism is fine; every handle needs an owner; bound the concurrency; CPU-bound work isn't an async problem.
- **e** Small, simple functions over large complex ones.
- **f** Check what a function actually returns — look it up. Verify an index exists before using it.
- **g** Flush and close explicitly; don't trust an `__exit__` you haven't read.
- **h** A file must be complete before it is renamed: flush, close, invalidate the name, *then* rename outside the `with`.
- **i** Use an env-configurable logger; guard expensive log payloads behind `isEnabledFor`; always log the files you access.
- **j** Check whether output aliases input — deep-copy, or say so in the name in no uncertain terms.
- **k** Re-implementing to avoid a dependency requires test vectors. Non-negotiable for crypto primitives and format parsers.
- **l** Use named insertion methods (`append`/`extend`/`insert`), not overloaded math operators.
- **m** A file written only to *be written* should be in memory instead — with a size guardrail checked first.
- **n** In a Claude Code session, generate test code covering every function written — any form of testing counts; a script full of asserts is fine. Keep it in `_tests`. Wrap tested functions in `### unit-tested function start/end: <marker>` and stamp the test with `### unit-test for:` plus mandatory `# integrity:` and `# last time passed:` lines, `# depends on sample:` where it reads data, and an optional `# sample generator:`. Never type those by hand — `scripts/verify_marked.py <marker>` runs the test and stamps only on a pass; `scripts/show_marked.py` and `scripts/hash_marked.py` define the span and its hash.
- **o** A result not meant to be edited later gets a frozen type — `frozenset`, `@dataclass(frozen=True)`, `NamedTuple`.
- **p** Be careful with functions that return a pointer to an object. Index then mutate (`data[pos].add(v)`); don't ride `setdefault`'s return value. Extract a pointer only in a hot path or for real readability — preserve the container's name, comment the usage.
- **q** Don't `.strip()` before a regex — match `\s*` in the pattern instead, or the pattern carries an undocumented precondition. Stripping *after* extraction is fine.
- **r** A validating regex is anchored `^`…`$`. Only a deliberately mid-string extracting regex omits the anchors.
- **s** State the regex flags explicitly, as a flag argument rather than an inline `(?m)`. **Every regex states `re.U` or `re.A`** — `re.U` is the default, so writing it says the choice was made. `re.M` over inline; `re.I` needs no comment; `re.S` always gets one.
- **t** Make iterator work visible or name it — a second `for` clause in one comprehension is a nested loop in disguise; hand it to a named helper, or produce the inner iterator and flatten it as a separate step.
- **u** Compare within the same logical type — a string is a representation, not the thing. Convert before comparing (`bytes.fromhex`, `ipaddress.ip_address`); the conversion validates for free where `==` on strings just returns a wrong answer. Where a comparison authenticates — MAC, token, password digest — use `hmac.compare_digest`; elsewhere a digest is a normalized hex string and `==` is right. The line is the environment, not the datatype.
- **v** A docstring names what the function raises, including exceptions that arrive through functions it calls (`@throws X` preferred, then `@exception X`, then `:raises X:`). A function whose only purpose is to raise is exempt — the name in the reject/fail/raise family is the annotation.
- **w** An exception you decide not to handle gets a comment on the line naming the exception that actually arrives and the condition — not the one that was caught on the way, and not a bare `# may raise`.
- **x** `try` is for catching exceptions raised by calls to other code, not for wrapping your own `raise`. A block whose `except` only sees exceptions the same block raises itself has nothing to catch — the raise already does what the `try` was for. Tell: a bare `except (...): raise` with no handling, guarding a block where every exception in flight is self-raised.

**24. Named regex groups for data extraction.** `(?P<name>...)` over positional groups, so extraction stays self-documenting and doesn't break silently on a reordering.

### Structure → `references/structure.md`

**6. Don't rely on hidden mechanics — treat a datatype as its purpose.** Assume the reader is a programmer, not specifically a Python programmer. A dict maps keys to values; its insertion ordering is a hidden mechanic even though guaranteed since 3.7 — don't lean on it generally, though you may in a hot path with a comment. If it's a queue, use a queue. When someone says "list", check what they're actually doing.

**7. Clean control flow.** A `break` must be conditional — an unconditional one means the loop is unpacking in disguise. `if … return` plus a bare `return` says the `if` is a guard on an edge case; where the two returns are peers — inverting the condition would just swap them — use `if`/`else`, so a third case has an `elif` to land in. An iterator is read left to right too — a comprehension with two `for` clauses is a nested loop, so name it (rule 3t). Consecutive `if var == value: return` on one variable is a `match`. `match` vs. dict is decided on readability, not on speed.

**8. Arithmetic is not truthiness.** Never let 0 stand in for False. `if n % 2 != 0`, not `if n % 2`. `if _p is None`, not `if not _p`.

**10. DRY.** A lambda, a small function, a cached result, or a wrapper is almost always available.

**11. YAGNI — including imports.** A dict/`NamedTuple`/plain `@dataclass` before a class; escalate only for real behavior or invariants. Remove unused imports; check after writing.

**12. Optimize at the algorithmic level, not with clever Python.** A data structure that turns O(n²) into O(n) beats any micro-optimization. Clever Python that costs reviewability is a net loss.

**31. Treat a block as a scope, the way every other language does.** A general programmer reads `try`/`if`/`for`/`while`/`with` as scoping; Python leaks every name they bind into the enclosing function. Don't read a name after the block that introduced it — hand the value out of a small function instead. `del` a name that must not outlive its block (rule 3h). Comprehensions *do* scope, which is why the reader can't tell by looking.

### Data handling and I/O → `references/data-and-io.md`

**13. Prefer iterators over eager list construction; collect as late as possible.** Materialize only for a final result, repeated iteration, or a length. Don't populate a data structure with a loop — collect into it. A single call whose name hides that it copies the data is the same decision: `.split()`, `.splitlines()`, `.readlines()`, `re.findall` — ask what it costs at the volume this input can reach (rule 15), not the example's. Annotate each such call with the input's maximum size and why that size is safe. `list(...)`/`sorted(...)` name their own materialization; `.read()` is a whole-file read (rule 20); `d.items()`/`.keys()`/`.values()` are lazy views.

**14. Where two forms are equivalent, take the one that builds no intermediate.** Same result, same syscalls → prefer the one that doesn't materialize a buffer. Update a hash rather than building a buffer to hash it. `join` rather than repeated `+=`.

**15. Classify data volume upfront.** Raw unfiltered first pass → streaming. Already-filtered → memory is fine. Known/bounded → lean memory-heavy. In doubt → iterator, or ask.

**16. Fail loud, no silent fallbacks — always with a stated reason.** Mechanism not prescribed: an exception or a Result-style object, whichever fits the codebase. Every failure path says *why*. **Load-bearing.**

**18. Atomic writes.** Temp path, then `os.replace` — never in-place. Rule 3h has the full sequence.

**20. Wrap replaceable operations** — structured-data decoding, web requests, file reads — behind small, swappable seams. Adopting a third-party replacement is a judgment call weighed against technical debt, not a default.

**21. Strict, format-appropriate serialization.** No lenient parsing; malformed input is a fail-loud error. **JSON is not the default choice** — pick CBOR/Parquet/CSV/JSON to fit the data.

**22. Centralized structured-data I/O helper module**, `jsonio.py`-style. One place where strict parsing, the wrapper seam, and atomic writes actually get enforced instead of being re-implemented per call site.

**23. Explicit memory cleanup with `del` for large intermediates.** Drop before the next heavy step, not at the end of the function. Not for small values.

**27. Normalize hex case on ingestion**, at the boundary — don't key on or compare hex that might differ only in case later.

**28. Never assume serialization order is deterministic.** Treat a dict as unordered — insertion order is a hidden mechanic (rule 6), and explicit beats implicit. Sort keys explicitly wherever exact order is crucial — fingerprints, hashes, dedup keys, signatures. Type-tag values so `1` and `"1"` can't collide.

### Project-level → `references/project.md`

**17. Minimum interpreter version: Python 3.11+.** `X | Y` unions, `match`, `tomllib`. Unless a project states an older constraint.

**19. Empirical verification before claims** — cite exact counts, not impressions. Real data over synthetic. Say plainly when something couldn't be verified. Report edge cases checked, not just the happy path. **Load-bearing.**

**25. One canonical module owns a piece of shared logic.** Call into it; don't reimplement a local, slightly-different version.

**26. Config files: ship an example**, and write it if none is present. Where the format is ours to choose, never one whose meaning depends on whitespace — no YAML. Prefer JSON.


**30. Security review at design and finalisation — not per-step.** STRIDE twice: at the design stage while the architecture is still cheap to change, and again at finalisation against what was actually built, with trust-boundary mapping, auth/encryption verification, and injection review. While writing, favor secure options but don't run the structured analysis per step — flag only trust-boundary-crossing API calls and anything contradicting the design-stage threat model.

## Applying this skill

1. Apply every rule unless explicitly overridden for a specific case. Where a rule and the task genuinely conflict, say which rule and why rather than dropping it silently — a rule that was wrong for a case is worth knowing about, and a rule that was skipped without a reason looks identical to one that was missed.
2. **Rule 16 (fail-loud) and rule 19 (empirical verification) take precedence** where anything conflicts. Silent failure and unverified claims are the two failure modes that survive review and surface later as production bugs; everything else here is recoverable by reading the code again.
3. If existing project code contradicts these rules, don't silently "fix" it unless asked — but do flag the inconsistency.
4. **Run `scripts/check_style.py [--strict] <file.py>` on Python you generated before reporting it done.** It covers rules 2, 3e, 3g, 3l, 3p, 3q, 3r, 3s, 3t, 3v, 7, 8, 11, 13, 14, 16, 20, 24, 26, 28, 30, and 31, printing rule-numbered findings in three tiers: `error` (no legitimate form), `review` (legitimate only as a stated decision the check can't see), and `info` (a false-positive-prone heuristic — a nudge, not a verdict). The exit code is driven by errors alone; `--strict` makes reviews fatal too, and info never gates. Every other rule here needs a reader: a clean run means the mechanical checks hold, not that the skill was applied.
5. **Reusable functions live in `scripts/helpers.py`, addressed by marker** — `iter_splitlines`, `is_email`, `iter_chain`, `iter_chain2`. Fetch one with `USE_FILE=true SHOW_FILE=scripts/helpers.py python3 scripts/show_marked.py <marker>`. See `HELPERS.md` for what each does and its integrity hash. Copy the verified version rather than rewriting a primitive (rule 3).
