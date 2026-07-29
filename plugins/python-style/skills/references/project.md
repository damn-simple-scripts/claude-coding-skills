# Project-level conventions

Conventions that apply to the project as a whole rather than to a single line of code.

Part of the `python-style` skill. Rule numbers are global across the skill — see SKILL.md for the full index and for which file holds which rule.

### 17. Minimum interpreter version: Python 3.11+
Don't write code that only works on older Pythons out of habit — use `X | Y` unions, `match` (rule 7), `tomllib` over third-party TOML parsers. Unless a project states an older constraint, target 3.11+.

### 19. Empirical verification before claims — cite exact counts, not impressions
Never state that code works, that a bug is fixed, or that behavior matches expectations without having run it against real data and reported the concrete result. The shape to aim for — what was run, against what, and the counts that came back:

```
scanned 30000 records from the live cache
records with the field present:                30000 / 30000
records with >=2 distinct values across sources: 4863 / 30000  (~16%)
edge cases checked: empty input (ok), single record (ok), malformed (raises)
```

Note what that says and an impression doesn't: the population size, the absolute numbers on both sides of the ratio, and which edge cases were actually exercised. "I tested it and it works" carries none of that, and is the claim most likely to be wrong.

- Prefer the real dataset over synthetic data where one is available.
- Where full-pipeline testing isn't feasible, verify at the unit/function level against real extracted data and *say so* — don't imply full-pipeline testing happened.
- Report edge cases explicitly checked (empty, single-item, malformed), not just the happy path.
- If a claim can't be verified in the current environment, say so plainly.
- Quote the environment for any measurement — a benchmark without its interpreter version is not reproducible.

### 25. One canonical module owns a piece of shared logic
If a capability already has a canonical module, new code calls into it — it does not reimplement a local, slightly-different version. Study an existing function there for the exact signature/convention before writing a new one; don't invent a parallel style. Data-producing code owns the *data*; the canonical module owns its own concern. Don't blur the boundary. Module-level dependencies are imported at the top of the file, not lazily inside functions, where the module already establishes that convention.

### 26. Config files: ship an example, and never use a whitespace-sensitive format
**Always provide an example config file** — and if none is present, write it. A config format with no committed example is a format nobody can adopt without reading the parser.

**Where the format is ours to choose, never pick one whose meaning depends on whitespace** — no YAML. Indentation-significant config breaks on copy-paste, on editors that retab, on a stray space, and it fails in ways that are hard to see in a diff. **Prefer JSON.** (Where the format is imposed by an external tool, that's not a choice to relitigate — this rule is about the cases where it is.)


### 30. Security review at design and finalisation — not per-step
Structured threat analysis happens at **two** points, and neither of them is "continuously, interrupting every incremental step":

**At the design stage.** STRIDE before the code exists, while the architecture is still cheap to change. This is where trust boundaries get decided, where a component's exposure gets chosen rather than discovered, and where a threat found costs a conversation instead of a rewrite. A design-stage STRIDE that finds a missing authentication boundary saves the finalisation-stage review from finding it after everything was built on top of it.

**At the finalisation stage.** STRIDE again against what was actually built — because what shipped is never exactly what was designed. Plus the concrete passes: trust-boundary mapping per file (internal vs. external), authentication/encryption verification on communication paths, injection review, unhandled-outcome check.

**In between — while writing.** Check for vulnerabilities and favor secure options as a matter of course, but don't run the structured analysis per step. Two things do get flagged in the moment rather than deferred: API calls that cross a trust boundary, and anything that contradicts the design-stage threat model — the latter means either the code or the model is wrong, and that is worth knowing immediately rather than at the end.
