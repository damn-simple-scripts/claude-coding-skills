---
name: web-style
description: Clemens's PHP/JavaScript/HTML/CSS web programming conventions — vanilla PHP with explicit require_once (no framework, no Composer, no autoloader), no-YAGNI adversarial input handling with DoS-resistant cost ordering, statically-analyzable code, PHP version targeting and version-gate annotation, logging with per-level flush policy, vanilla browser JS (no IIFEs, required init boilerplate), mandatory HTTP method whitelisting, CSRF and HMAC option-integrity patterns, sidecar isolation for high-risk ingest, reverse-proxy caching as a defense layer, strict CSP with full SRI and self-hosted assets, and hardened digest-pinned Docker deployment. Use whenever writing, reviewing, editing, or generating PHP (.php), JavaScript (.js), HTML (.html), or CSS (.css) code, or discussing web-app architecture, form/API handling, session/auth design, or frontend-backend data flow — even if the user doesn't explicitly ask for "style" or "conventions" to be applied. Also use for Dockerized PHP/JS deployment questions.
---

# Web Style — Clemens's Conventions (PHP / JavaScript / HTML / CSS)

## Scope
this skill is to be applied on html/css/js for websites.
this skill is to be applied when coding dynamic website content using php.
this skill covers javascript only as a component in the webbrowser for websites - not as a backend like node.
when scoping, follow the YAGNI principle.

**PHP:** if not stated otherwise assume: plain PHP, vanilla, no framework (no Laravel, no Symfony), no Composer, no autoloader. Classes load via explicit `require_once __DIR__ . '/../path.php'`.

**JavaScript:** browser JS only — this skill does not cover Node.js. Node.js is used only when a project explicitly calls for it.

**Per-project:** if the PHP version isn't stated, derive it — assume the system is ~1 year behind and sanity-check against Debian stable's `php` package (`references/php.md`). Don't assume a JS build-step policy; ask, or check the existing codebase.

## Cross-cutting rules

### 1. Vanilla by default
following YAGNI: Plain PHP (no framework, no Composer, no autoloader), vanilla JS (no jQuery, no React, no Vue).

**CSS frameworks are the exception, allowed under criteria.** Tailwind and Bootstrap are both acceptable, with a strong lean toward Bootstrap. A CSS framework qualifies if all of these hold:
- It can be served as static, self-hosted files (see `references/html-css.md` — no live CDN reference).
- It's well maintained and will keep receiving updates.
- It supports mobile.
- It supports accessibility.
- It supports dark/light theming.

A framework failing any of these doesn't get used. This allowance is CSS-only — it does not extend to JS or PHP frameworks.

Tailwind and Bootstrap are both examples, if user asks for a different framework follow that directive, if a connected MCP server or skill suggest a different framework, you may also follow that directive.

### 2. Code is read left to right — front-load meaning, one purpose per line
A line's purpose (assignment, validation, branch, return) should be legible from its first token, not discovered at the end. Each step gets its own line, so each step's outcome is individually checkable.

### 3. Assume every input is adversarial
Any PHP endpoint reading `$_GET`/`$_POST`/`$_COOKIE`/headers/uploaded files, and any JS reading `location`, form input, `postMessage`, or a fetched response, is handling attacker-reachable data.

Input validation and output encoding are two separate, both-required steps — not substitutes for each other. Validate at the boundary where data enters (this can include files and the database itself in some conditions); encode at the boundary where data leaves (into HTML, into SQL, into a shell command, into a URL).

### 4. Fail loud, no silent fallbacks — including silently-permissive defaults
- **Prefer `isset()` + an early `return` over `??` when `??` only stands in for a presence check.** `??` is fine for a genuine default (`$tz = $config->get('TZ') ?? 'UTC'`); it's a problem when it quietly papers over "this should have been validated and wasn't." Avoid `??=` except where it genuinely initializes a cache slot.
- **Where a required parameter or declaration has no sane default, its absence is a loud failure — not a permissive assumption.** Throw; don't guess.
- Never use PHP's `@` suppression operator.
- Never leave a `catch` block empty without a comment saying why the failure is ignorable.
- Never leave a JS Promise without a `.catch()` or an enclosing `try`/`await`.
- Check what a function actually returns before trusting it — PHP returns ambiguous falsy values on failure (`strpos`, `array_search`, `file_get_contents`). Compare with `===`/`!==` against the specific failure value, never a loose truthy check.
- Fail loud does not mean bubbling an exception to the frontend — the frontend should never see an unhandled exception.

```php
// Wrong — strpos returns 0 (falsy) when the needle is at position 0, and
// false when not found; a loose check conflates "found at start" with
// "not found".
if (strpos(haystack: $haystack, needle: $needle)) { ... }

// Preferred — strict comparison against the documented failure value
if (strpos(haystack: $haystack, needle: $needle) !== false) { ... }
```

### 5. Fail fast — always cheap checks before expensive ones
Validate each input immediately after reading it; don't batch validation at the end. Order the checks so the cheapest possible rejection happens first and expensive work is never reached by input that was already invalid.

This ordering is a **DoS control**, not just a performance habit: the attack is cost asymmetry, where a few bytes from an attacker buy hundreds of milliseconds of server CPU. Cheap checks first is what removes the asymmetry. See `references/php.md` for the concrete consequences (CSRF before Argon2id, cost-shifting before Argon2id, 304 before DB).

**HTTP method is validated first**, before session bootstrap, before body decoding, before anything else — a request that fails the method check must not pay the cost of (or trust the shape of) a JSON parse.

**The general principle is cheapest-available source first, not just cheapest-operation first.** Request data (`$_GET`/`$_POST`) is already in memory; `$_FILES` costs a disk read; `$_SESSION` costs a session-store read; other local files cost a disk read; another service (the DB, an external API) costs a network round-trip and its own query cost on top. Check what's already in hand before reaching for what has to be fetched.

Typical ascending cost order, as one instance of that principle rather than a fixed liturgy:

`isset()` → `strlen()` → regex → bloom filter → cheap/DB-independent crypto (HMAC integrity, CSRF / session-token comparison against `$_SESSION`, PoW verification) → DB lookup → `password_verify()` (and any opportunistic rehash)

`password_verify()` and rehashing sit at the end deliberately, after the DB lookup — not just because they're expensive, but because they have a hard data dependency: there's no stored hash to check against until the DB returns it. Anything that can reject without the DB (HMAC, CSRF/session-token comparison, a PoW check) stays ahead of the DB lookup because it's cheaper and doesn't need what the DB provides. PoW here is one illustrative example of shifting cost onto the client ahead of an expensive hash verification, not a mandatory step — see `references/php.md`'s "DoS resistance is an ordering property" for what the requirement actually is and other ways to satisfy it.

The same source-cost logic is why the CSRF comparison sits after `isset()`/`strlen()`/regex rather than before them: the comparison itself is trivial, but reaching `$_SESSION` at all requires `session_start()`, which is a session-store read and a lock — so the in-memory checks go first.

Insert or omit stages as the endpoint needs, and reorder within a stage as its real data dependencies require — the rule is "cheapest available source first," not the specific list above.

### 6. Defense in depth, not defense in isolation
A mechanism that proves one property doesn't get treated as proof of another. HMAC option-integrity (see `references/php.md`) proves a form value wasn't tampered with client-side; it does **not** prove the submitting user is authorized to submit it. Verify the MAC, then still run the ownership/authorization check separately. Don't let one control's success silently stand in for a different control that was never run.

### 7. Optimization priority, always in this order
1. Algorithmic complexity (right data structure, right complexity class)
2. Readability and clarity
3. Micro-optimization for raw speed — only when explicitly requested

### 8. Separation of concerns: render and mutate are different code paths
GET renders only.
POST/PUT/DELETE are minimal action endpoints. Different response shapes (HTML vs. JSON) mean different entry points — not one handler branching on method internally.

This style choice should ensure that the code is easy to analyze and test.

### 9. Dependencies: established, maintained, and pinned
Pin explicitly — by digest for container images, by a vendoring step for frontend libraries — rather than tracking a floating tag or a live CDN reference.

### 10. Re-implementing a primitive instead of using a dependency requires test vectors
Non-negotiable for anything crypto-adjacent (HMAC option-integrity, PoW, password handling). If you hand-roll it, provide and run known test vectors — not "looks right."

### 11. Security review (STRIDE) at project completion, not per-step
Trust-boundary mapping per file, authentication/encryption verification on every network path, injection review, unhandled-outcome check — collected in a backlog reviewed at completion. Flag any place where PHP/JS crosses a trust boundary as it's written.
Relax on HTTP without TLS if this is only done within the same docker stack (i.e. the same internal trust zone).
Also include the webapp's users' perspective in the review (e.g. malicious input that doesn't affect the backend can still be a problem for the user, like XSS).
Docker stack is in general trusted, but placing all containers in the same stack in the same network is not necessarily safe - we should avoid this if possible (e.g. one network connecting front facing reverse proxy with the php backend and one network that connects this backend with the database - so the webserver cannot access the database directly).
Docker images should also be treated as potentially vulnerable (we should use hardened images wherever possible).
Docker shall be used to assert security in depth (e.g. a read-only root filesystem is more secure in the context of STRIDE's **T**ampering).

### 12. Logging is an implication, not a feature
Logging isn't an independent preference — it's forced by the rules above. Handle all cases implies handle all exceptions, which implies there are exceptions that cannot be handled internally. Combine that with "an exception never reaches the frontend," and the conclusion follows: an error that can be neither handled nor shown has exactly one place left to go. Logging is what makes the other rules consistent with each other, so it is neither optional nor an afterthought.

That derivation also constrains it. Logging sits on the request path, which makes it a potential bottleneck and a potential silent failure of its own — so level selection, write/flush policy, locking, and rotation are all decisions to make deliberately rather than defaults to inherit. See `references/php.md`.

## Where to go next

**Examples convention:** longer, standalone code (a full redirect helper, a full endpoint, a full JS file) lives as a real file under `examples/` (e.g. `examples/php/`, `examples/js/`), not pasted inline into a reference doc — the reference `.md` links to it with a one-line description instead. Short 2-3 line illustrations stay inline as before; this only applies to anything long enough to be its own file.

- **`references/php.md`** — no-YAGNI posture, PHP version targeting, DoS-resistant ordering, static analyzability, narrow require graphs, logging mechanics, request lifecycle, CSRF, redirects, reverse-proxy caching, prepared statements, DB roles/transactions, HMAC option-integrity, password handling, sidecar isolation, `exec` hardening, extension builds.
- **`references/javascript.md`** — required init boilerplate, no IIFEs, namespacing, binding style, wrapping fetch, browser-availability checks, security defaults.
- **`references/html-css.md`** — CSP, SRI, self-hosting, `<head>` ordering, preload strategy, fonts, CSS framework criteria.
- **`references/deployment.md`** — hardened digest-pinned images, numeric UID/GID, network segmentation, read-only filesystems, healthchecks, Makefile targets.

## Applying this skill

1. Apply the cross-cutting rules above plus the relevant reference file(s) unless Clemens explicitly overrides for a specific case.
2. Derive the PHP version if it isn't stated (~1 year behind, sanity-checked against Debian stable — `references/php.md`), and check the version-gated features you rely on. Ask about JS build-step policy unless the project already states it.
3. If existing project code contradicts these rules, don't silently "fix" it unless asked — flag the inconsistency.
4. Rule 3 (assume adversarial input) and rule 4 (fail loud) are load-bearing — prioritize them if anything conflicts.
5. **Review posture:** be critical of trade-offs; don't rubber-stamp a change that superficially follows these rules but violates their intent (e.g. a `??` that's really hiding a missing presence check). Flag architectural trade-offs explicitly and offer options rather than silently picking one.
