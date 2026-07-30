# PHP-Specific Rules

Read this after `SKILL.md`'s cross-cutting rules.

## Contents
- [No framework, no Composer, no autoloader](#no-framework-no-composer-no-autoloader)
- [YAGNI does not apply here](#yagni-does-not-apply-here)
- [DRY, with a require graph as narrow as the request](#dry-with-a-require-graph-as-narrow-as-the-request)
- [Written to be analyzed — by a human and by a static analyzer](#written-to-be-analyzed--by-a-human-and-by-a-static-analyzer)
- [PHP version targeting](#php-version-targeting) — assumed version, version-gate headers, PHP 7 vs 8 pitfalls
- [Request lifecycle](#request-lifecycle) — method-first, processing order, DoS ordering, proxy caching, CSRF, redirects
- [Templating](#templating)
- [Configuration](#configuration)
- [Logging](#logging) — level from config, per-level flush policy, debug-is-not-a-trace, rotation trap
- [Database](#database) — prepared-statement pattern, dual roles, transactions, PDO error mode
- [Security patterns](#security-patterns) — sidecar isolation, HMAC option-integrity, passwords, `exec`, uploads, JSON
- [Access-scoping patterns](#access-scoping-patterns)
- [Extensions and multi-stage builds](#extensions-and-multi-stage-builds)

## No framework, no Composer, no autoloader
Classes load via explicit `require_once __DIR__ . '/../path.php'`. No PSR-4 autoloader at runtime — dynamic class→path resolution driven indirectly by user input is an attack surface an explicit require list doesn't have. Where a project needs third-party functionality (SMTP, TOTP), the default is a custom implementation or a native library rather than pulling in Composer for it. If a project already has Composer-based dependencies, ask before assuming this rule applies retroactively.

## YAGNI does not apply here
YAGNI does not apply to anything that may expose a vulnerability - in php that is everything - all inputs are adversarial, each function that can fail may fail when exposed to the internet, each not handled failure mode may expose a vulnerability.
PHP is the layer sitting directly on adversarial input, and a defense that looks unnecessary at write time is exactly the one that gets found. There is no "we probably won't need that check."

Concretely:
- **Every input is validated** — not only the ones that look reachable, look dangerous, or look like they came from a form the app itself rendered. Protect against DoS here and do check checks before expensive checks such as regex. threat `filter_var` as less expensive than regex. Validate not just the format, also its usecase (e.g. do not relay on `FILTER_VALIDATE_EMAIL` when we directly use it for SMTP - also check for the intended usecase and also check for SMTP injections - also check for storage formats [e.g. if we log in JSON we should check if we log that input and wether it could be used to inject data into our logs]).
- **Every return is checked for errors** — every one, not just the calls that look fallible.
- **An exception never reaches the UI.** A stack trace or an uncaught error in the browser hands an attacker file paths, versions, and query structure, and hands the user a broken page. Every entry point terminates exceptions: catch, log, return a generic error response. This is the constraint that forces logging to exist (`SKILL.md` rule 12).
- **Input timing is validated, not just input content.** Both bounds matter: a form submitted implausibly soon after render is automation, and one submitted after its window closed is stale. Check both. A valid client will obey delays (e.g. enforce that a form can only be submitted after X milliseconds) while a bot will not - checking the timing in a Session is a cheap check that can be done without any database access. Timing checks do not supersede CAPTCHA or PoW challenges - they are complementary (example: a bot may use millions of concurrent connections to submit forms for a bruteforce attack; a PoW would require a significant computational effort for an attacker).
- **Every endpoint is assumed to be a DoS target** and ordered accordingly (see below).
- **Every layer assumes the layer in front of it failed.** Validation at the proxy doesn't excuse validation in PHP; a verified HMAC doesn't excuse an authorization check (`SKILL.md` rule 6).
- **Every calculation can be a DoS target** — before performing expensive calculations such as `password_hash()`, `hash()`, or `bcrypt()`, do other checks first to avoid unnecessary work. If you include a simple PoW challenge can shift the asymmetrical computational costs of an authentication attempt from the server to the client.
- **security in depth** - each form/input/dynamic content shall be protected. Good ides but not limitted to: per request CSRF tokens, whitelist inputs rather than trusting user input, check sizes, validate the hell out of it (validate for valid charset before anything else, validate the fromat itself e.g. email or json, validate the usage like STMP or HTML), use sidecars for format conversions where webapp user controls the input (e.g. file uploaded, we can trust blob in db on this). There is no trust - not even on healthcheck endpoints - at least we shall authenticate them using a shared secret (like a autogenerated UUID).
- <german>**ich glaube an das immerwährende provisorium**</german> (translated: I believe in the ever-present temporary solution). when we write php code it usually survives longer than expected. Therefore the code should be written in a way that it is secure even in multiple years without maintenance. This implies: plan curves for hash stregths (e.g. always uses best available algorithm for password hashing - at the state of writing this is ARGON2ID - with the built in `password_hash()` function -> also ensure that if a timespan [e.g. the current year exeeds 2030] we provid our own constants for minimum hash strength [we always use the maximum of the builtin default constants and our own custom constants]). That is the reason we refrain from using frameworks like laravel. This also implies that the state of the art for web security now may be the absolute baseline in the future - implying to always asses the bestr practices for this paritcular usecase. This also implies that we refrain from using experimental features that are not yet in a standard. This also implies that we never "add security later" always store data securely. **Even if we aint gonna need it now, we may need it in the future**. Never assume that a hash algorithm that we use today will be available in the future - whenever use a list of supported algorithms and have a list of algorithms you prefer to use (selection of the algorithm does not need to happen in a hot-path, this can be done at deployment or in maintenance cron jobs). Long-term code also implies to design a maintenance procedure (e.g. explicit remove stale files, explicit overwrite password hashes of expired users)
- **expect a breach** and ensure the security of the information even if parts of the infrastructure are compromised. Research means to protect what is in the system you will need to protect. prominent examples of this approach are: seperate databases for auth and data, salt and pepper passwords, overwrite passwords of expired users, if we store data for the user we might encrypt it witha user provided key that we do not store, only store the data we actually need, segreagation of duty by splitting reading and writing operations to different database users, pseudonymization in logs, ensure to never store plaintext (not in passwords, nor store the attempts in logs). This also implies that sometimes it may be necessary to detect manipulation of the code base (e.g. run an integrity check over the code base itself) - this has rare usecases but shall be considered.
- **you will need a backup** always design the code so it includes a backup mechanism (e.g. a endpoint only accessible from within the same docker stack with a very stong shared secret that yields encrypted backups)
- **deterministic over just working** if we cannot ensure the right encoding try a more deterministic fallback (e.g. exchange data using base64). If you cannot ensure the right encoding consider using multibyte string functions (e.g. when designing tests always try emojis or chinese characters in fields that are length checked).
- **standard tests on all user provideded input fields** always design a test case where you use standard injection strings for each input field (always try SQL/XML/command/JSON injection strings and simple XSS strings) each field that accept input shall be tested on default patterns (check if this is represented correctly in the database, log, output and any other place where the data is used/may appear). You will need the confidence in this test cases.

YAGNI still applies regarding complexity - we want to avoid bugs like heartbleed that rooted in non-trivial protocol - always keep the communication protocol as simple as it can be (e.g. can we be stateless or do we need to keep track of a state across multiple requests). This also implies that we refrain from JWT-based authentication if we do not have an identity provider AND multiple possible claims.


### password hashing
always use `password_hash()` with the best available algorithm (currently ARGON2ID) and the built-in constants for minimum hash strength.
always use `password_verify()` to verify passwords.
always check if the password hash needs to be updated (e.g. if the algorithm or cost factor has changed).
always use `password_needs_rehash()` to check if a hash needs to be updated.
always benchmark the performance of password hashing algorithms on the target system (this benchmarks could occur in regular system maintenance cron jobs or during deployment).
always model the cossts for each password check - e.g. a user auth should not take longer than 400ms, promoting a active session to admin may take longer - difficulty can only increase, never decrease.

if a password is used to derive a key, use a strong key derivation function. For key derivation: do not use simple hashes or salted hashes or HMACs. For key derivation: deterministic is key - even if the algorithm may be weaker use `hash_pbkdf2` over  `password_hash()`(because we cannot control the salt of `password_hash()`). If used for key derivation prefer `sodium_crypto_pwhash` over `password_hash()` (because password-hash is intended for authentication, not key derivation).
use correct primitives to derive sub keys - at the state of writing this impiles using `hash_hkdf` over `hash_hmac`.
Consider to encapsulate keys instead of deriving them directly from passwords (e.g. we transmit the encryption key encrypted) - this allows more future proof by allowing to rotate key for the encapsulation key.
Always prefer a AEAD cipher over encrypt-then-MAC (at the time of writing this is the state of the art).
Use NIST SP 800-56 series as source:
  NIST SP 800-56C: Recommendation for Key-Derivation Methods in Key-Establishment Schemes
    at time of writing this suggests HKDF
Use NIST Special Publication 800-132 as source: PBKDF
we also honor comments on that like https://csrc.nist.gov/csrc/media/Projects/crypto-publication-review-project/documents/initial-comments/sp800-132-initial-public-comments-2023.pdf 
we also honor https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html (at the time of writing: argon2id as hash, PBKDF2 minimum iterations: HMAC-SHA256=600_000, HMAC-SHA512=220_000, consider SHA1 deprecated after 2030 if used in PBKDF2 use at least HMAC-SHA1 with 1_400_000 iterations).

password hashing is always expensive (per design) - therefore you need to guard it with cheap checks.

## DRY, with a require graph as narrow as the request
Shared logic lives in helper files rather than being duplicated per page. But an explicit `require_once` is a disk read, and disk reads that a request never needed are cost an attacker gets for free — so require what the code path actually uses, where it uses it, rather than a blanket header of every helper at the top of every entry point. A GET render page has no business loading the write-path DB helper, the password-hashing helper, or the challenge verifier.

DRY governs where code lives; it doesn't license loading all of it on every request.

## Written to be analyzed — by a human and by a static analyzer
PHP is written so a reviewer or a static analyzer can follow it without executing it. Constructs that defeat static analysis are out:

- No variable variables (`$$name`); no dynamic property or method access driven by a name from input.
- No `extract()`, no `eval()`, no `create_function()`.
- No `call_user_func()` on a callable assembled at runtime — use a direct call, or an explicit dispatch array with literal keys.
- `require_once` takes a literal path, never a computed one.
- Type declarations on parameters and returns; `declare(strict_types=1)` where the project's PHP version allows.

Several existing rules are downstream of this and reinforce it: no autoloader means the require graph is a greppable fact rather than a runtime behavior; one purpose per line (`SKILL.md` rule 2) means an analyzer and a reviewer see the same thing; small functions keep every return path visible at once.

## PHP version targeting

### Assumed version when unstated
If no PHP version is given, assume the deployment is roughly a year behind: take today's date, subtract twelve months, and target the branch a system patched to that point would carry. Then **sanity-check that against the current Debian stable `php` metapackage**. If the two disagree, Debian stable wins — that's what the target actually ships.

Check both halves at time of writing rather than recalling them: patch levels move monthly, Debian's stable release rolls over every couple of years, and a remembered answer goes stale without announcing itself.

Debian maps one PHP branch per release, so a project pinned to an older Debian is pinned to an older PHP branch regardless of what upstream shipped. Worked example for July 2026: a year back is July 2025 → the 8.4 branch; Debian 13 "trixie" (stable since 2025-08-09) maps `php` → 8.4; the two agree, so target 8.4. For contrast, bookworm maps to 8.2 and bullseye to 7.4 — a bookworm target means 8.2 regardless of the date arithmetic.

### Version-gated features are noted in the file header
Any file using a version-gated feature says so at the top, so a version mismatch surfaces as a readable note rather than a parse error in production:

```php
<?php
declare(strict_types=1);
// Requires PHP >= 8.1 — enums (8.1), readonly properties (8.1)
// Also uses: match (8.0), constructor promotion (8.0)
require_once __DIR__ . '/../lib/log.php';
```

Common gates worth flagging: `match`, constructor promotion, nullsafe operator, named arguments (8.0); enums, readonly properties, `never` return type, first-class callable syntax (8.1); readonly classes, DNF types, standalone `null`/`false`/`true` types (8.2); typed class constants, `json_validate()`, `#[\Override]` (8.3); property hooks, asymmetric visibility (8.4).

### When targeting PHP 7
Don't rely on mechanics whose meaning changes under PHP 8 — code that silently changes behavior on upgrade is a bug with a delayed fuse. The ones that bite:

- **String-to-number comparison.** `0 == "foo"` is `true` in PHP 7 and `false` in PHP 8. Any loose comparison between a number and a string is a behavior change waiting to happen — which is one of the reasons `SKILL.md` rule 4 requires `===` in the first place.
- **PHP 4-style constructors** (a method named after its class) are gone in 8.0. Use `__construct`.
- **Edge-case return values** of several string functions changed between 7 and 8. Check the target version's docs rather than memory.
- **Removed in 8.0:** `each()`, `create_function()`, curly-brace string offsets (`$s{0}`) — all already banned by the static-analyzability rule above, but worth knowing they're hard errors, not deprecations.

### When targeting PHP 8

**Annotate non-obvious semantics at the point of use:**
```php
// Nullsafe: short-circuits to null if $user is null — the rest of the chain
// is not evaluated, so $city is null rather than an error.
$city = $user?->getAddress()?->city;
```

**Named arguments as soon as more than one argument is passed.** Positional arguments past the first are an unlabeled tuple the reader has to resolve against a signature elsewhere in the file — the opposite of `SKILL.md` rule 2. Named arguments make the call self-describing and survive a signature reorder. They also feed the static-analysis rule: an analyzer can flag a wrong argument *name*, but it cannot flag a wrong argument *order*.

```php
// Wrong — what are true and 3?
$stmt = build_query($sql, true, 3);

// Preferred
$stmt = build_query(sql: $sql, readonly: true, retries: 3);
```

## Request lifecycle

### HTTP method is validated first
Every entry point declares its accepted methods explicitly, and the method check runs before session bootstrap, before body decoding, before any other work. Anything not in the declared list gets a 405 immediately.

The declaration is mandatory: there is no implicit "safe" method, and an entry point that omits it is a loud failure rather than one defaulting to permissive (`SKILL.md` rule 4).

### Request processing order
1. Validate HTTP method against the declared allow-list → 405 if not allowed.
2. Send security headers (CSP, `X-Frame-Options`, etc.).
3. Check CSRF, if the page opts in.
4. Validate input — cheap checks before expensive (`SKILL.md` rule 5).
5. Check rate limit, if the endpoint sits under a rate-limited path.
6. Perform the action (DB, business logic).
7. Return the result (JSON or redirect).

### DoS resistance is an ordering property
`SKILL.md` rule 5's cheap-before-expensive ordering is a DoS control first and a performance nicety second. The attack is cost asymmetry: an endpoint that runs an Argon2id verification before checking CSRF lets an unauthenticated attacker spend a few bytes to burn hundreds of milliseconds of CPU and a chunk of memory, repeatedly. Ordering is what removes the asymmetry.

- **CSRF is checked before any expensive crypto.** A request without a valid token never reaches Argon2id.
- **A PoW puzzle is issued and verified before an Argon2id verification is attempted**, so the client pays first — the cost is loaded onto the party who can be made to pay it.
- **Rate limits sit in front of anything touching the DB.**
- **Timing checks are cheap and go early** — an implausibly fast submit is rejected before any hashing happens.

Order by what an attacker can cheaply send versus what it costs to answer. The expensive work happens last, and only for a request that already cleared everything cheaper.

### Cache at the reverse proxy — this is a protection layer, not just performance
The reverse proxy in front is part of the defense stack, not a deployment detail. Serve caching headers wherever content permits, **including dynamic content**: a `Last-Modified` (or `ETag`) with even a one-minute freshness window collapses repeat traffic into 304s and takes the corresponding DB queries off the table entirely. Under load, that is the difference between a slow page and a database that fell over.

- Send `Last-Modified`/`ETag` on dynamic responses whose underlying data has a knowable modification time.
- Handle `If-Modified-Since`/`If-None-Match` and return 304 **before** doing the work — a conditional request that resolves to 304 should never reach the DB. This is the same cheap-before-expensive ordering as above.
- Set `Cache-Control` deliberately per route rather than globally.

**The trap:** anything user-scoped or carrying per-session state — CSRF tokens, HMAC option nonces, anything rendered against `$_SESSION` — is `private`/`no-store`, never a shared cache entry. A cached page carrying another user's CSRF token or option nonce is worse than the load it saved. Cache headers get decided per route, alongside the route's method and CSRF declarations, not bolted on afterward.

### GET renders, POST/PUT/DELETE act — never both in one handler
A page does one thing. If a feature needs both a render and an action, split it: a render-only GET page, and a minimal JSON POST/PUT/DELETE endpoint. Response mode is a property of the route's declared configuration, not something branched on inline.

### CSRF
- Explicit call, never implicit middleware e.g. do not do something like `Csrf::checkOrFail()` we want to see the fail in the endpoint to be assured that it fires and will never be optimized away when changeing the helper function.
- Decoupled from HTTP method — checked only if the page opts in (`csrf => true`), not automatically because the method is POST, an example for a GET endpoint that requires CSRF would be a page that is only to be accessed after login.
- **Rotation:** every safe GET navigation returning HTML issues a fresh token to the session. On failure, rotate the token and return 403 with a machine-readable error (e.g. `error: 'csrf_invalid'`) — never a silent continue.
- **Grace window:** current token and previous token are both valid, so a token rotated between page-load and form-submit (two tabs, a slow submit) doesn't spuriously fail.
- ensure that CSRF is truly random, never derived from content, it shall always include at least 64bit of entropy - ensure that the random source will not block if entropy is exhausted 8this would be a DoS).

### Redirects
Never a bare `header('Location: ...')`. Use a `Redirect::to($url, $status)`-style helper emitting: explicit status code, `Location` header, **and** a non-empty HTML body with a link plus a `<script>` async redirect — so the redirect still works for a client that doesn't follow `Location` automatically or has JS disabled.

## Templating

PHP at the top, then drop into HTML with `<?=` echoes. Never `echo <<<HTML` heredoc blocks:

```php
$title = 'Example';
?>
<!doctype html>
<html>
<head><title><?= htmlspecialchars($title, ENT_QUOTES, 'UTF-8') ?></title></head>
<body><h1><?= htmlspecialchars($title, ENT_QUOTES, 'UTF-8') ?></h1></body>
</html>
```

`htmlspecialchars($var, ENT_QUOTES, 'UTF-8')` on every user-input string in HTML context, no exceptions. If a page renders multiple outcomes (success vs. error), compute the variables once and use a single shared template — not separate branch-local blocks per outcome.

## Configuration
Sourced from a config file, environment variables, or the database — whichever fits the value's lifecycle. Secrets and deployment-specific values come from the environment; structural configuration from a file; per-tenant or user-scoped settings from the DB. A missing required value is a loud failure, not a silent default (`SKILL.md` rule 4). There should never be a case where "default credentials" exist for the application we create.

## Logging
Logging exists because the other rules require it (`SKILL.md` rule 12), not because someone asked for a logging feature. That framing sets its job: capture what can't be handled and can't be shown, and cost as little as possible doing it.

### Level comes from the config file
The active level is read from config, never from a code edit. Logging that can't be turned down is a bottleneck with no off switch, and a level that needs a deploy to change is one nobody changes during an incident. Guard expensive payloads behind the level check rather than building them and discarding them inside the logger.

### Write policy is per level
- **debug / info** — non-blocking write, no flush. The record needs to land *soon*, not *now*. Stalling a request on a disk write to record a routine event buys nothing.
- **warn / critical** — write **and** flush. These are the records that have to survive the process dying immediately afterward, which is usually the exact situation they describe.

"Async" here means non-blocking I/O, not async programming: issue the write and let the request continue; a flush is what forces it out now. Lock the file while writing (`flock()`) so concurrent FPM workers don't interleave partial records into each other's lines.

### Debug is not a trace
Unlike the convention in some other languages, a debug log does **not** cover every branch. Debug exists to make a problem debuggable — not to reconstruct execution. A per-branch trace buries the one line that mattered and re-introduces exactly the I/O cost the write policy above avoids. Log decision points and the values that drove them; don't log that a line ran.

### Rotation, and the open-handle trap
A maintenance script rotates the log. Assume an external `logrotate` may also rotate the file underneath a running process: PHP keeps writing to the now-unlinked inode, the records go nowhere, and nothing errors — a silent failure, which is exactly what `SKILL.md` rule 4 exists to prevent. Handle it explicitly on one side or the other:

- `copytruncate` on the logrotate side — truncates in place so the handle stays valid, at the cost of a small race where writes between copy and truncate are lost; or
- detect and reopen — stat the path and compare inode against the open handle before writing, or reopen on a signal.

Don't assume a long-lived handle stays valid.

## Database

### Prepared statements: per-call-site lazy singletons, no central cache

```php
private static ?PDOStatement $__lazy_stmt_insertUser = null;

private static function buildInsertUserStmt(): PDOStatement {
    $sql = 'INSERT INTO "user" (id, email, created_at) VALUES (?, ?, ?)';
    return self::$__lazy_stmt_insertUser ??= self::getWritePdo()->prepare($sql);
}
```

One `build<Purpose>Stmt()` helper co-located with each query — not a shared, central, SQL-indexed statement cache. Internal helper vars take a `__` prefix. This is one of the few places `??=` is right: it genuinely initializes a cache slot rather than standing in for a missing presence check.

### Dual DB roles: least privilege *and* scaling
Separate read-only and write users (`DB_READ_USER` with SELECT only; `DB_WRITE_USER` with SELECT/INSERT/UPDATE/DELETE on the required tables), lazy-initialized singletons per process (`getReadPdo()` / `getWritePdo()`), reused for the rest of the request.

Two reasons, both load-bearing:
- **Least privilege** — a SQL injection reached through a read path can't write.
- **Scaling** — once reads and writes are already routed through separate connections, pointing the read role at a read-only replica is a configuration change, not a refactor. Code that shares one connection for everything can't be scaled this way without touching every call site.

### Transactions for multi-table writes
Explicit `BEGIN`/`COMMIT`/`ROLLBACK` around any write touching more than one table. Deferrable foreign keys (`DEFERRABLE INITIALLY DEFERRED`) where schema flexibility is needed within a transaction.

### PDO error mode
Set `PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION` explicitly — PDO's silent-error default is exactly what `SKILL.md` rule 4 bans.

## Security patterns

### Isolate high-risk, high-exposure work in a sidecar
Work that is both **high risk** (memory-unsafe native parsers, large complex format-handling codebases) and **high exposure** (runs on attacker-supplied bytes at ingest) does not run inside the PHP-FPM process. It runs in a dedicated, isolated sidecar with no network egress and minimal privileges (`references/deployment.md`).

Image conversion on ingest is the canonical case: the converter parses arbitrary attacker-supplied bytes through a large native codebase with a long CVE history. Running it in a sidecar means a parser exploit lands in a container holding no DB credentials, no session store, and no route out — instead of in the process holding the app's database handles. Once converted, handling the normalized output is comparatively safe and can happen in-process.

Split on the risk × exposure product, not on convenience. High risk with no exposure (a parser only ever fed internally-generated data) and low risk with high exposure (a strlen check on a form field) both stay in-process; it's the combination that gets isolated.

### strong whitelist of valid options
When the user of the webapp can only select from a fixed set of options, use a strong whitelist. This implies that the user cannot enter arbitrary values; only the options listed in the whitelist are valid.
We can do this checks in constant time using `hash_equals()`.
We can also improve this by adding a session fixated nonce - so a user cannot use valid options from a different session (e.g. if some options are only visible to admins).

Suggested solution: HMAC option integrity

#### HMAC option-integrity
For radio/select/checkbox inputs where all valid options are known at render time and there's more than one option:

1. A per-session 64-char hex nonce, generated once, reused for the session.
2. On render, each option gets a hidden MAC: `mac = hmac_sha256(value, "<fieldname>-<nonce>")` — field name and nonce live in the **key** material specifically to block cross-field replay (a MAC computed for one field can't be reused against another).
3. On submit, recompute and verify with `hash_equals()`.
4. **Still regex-validate the value before MAC verification** — per `SKILL.md` rule 6, the MAC proves the value wasn't tampered with client-side; it does not prove the user is authorized to submit it. Separate checks.

Hash-algorithm selection isn't hardcoded: pick the first available from a priority list checked against `hash_hmac_algos()` (HMAC needs an HMAC-capable algorithm, not just any `hash_algos()` entry), and pin the chosen algorithm in the session so a render and a later verify — separate requests — always agree on which algorithm was used.

### Sessions and cookies
Native PHP sessions, short idle TTL. Session storage on a dedicated writable volume — the rest of the app filesystem stays read-only (see `references/deployment.md`). Cookie flags: `HttpOnly`, `Secure`, `SameSite=Strict`.

Sessions are short-lived, never persisted - prevent session fixation and replay attacks.

if a session changes its authentication level (login/logout/elevate) we immediately regenerate the session ID to prevent fixation. Regeneration implies that we first mark the old session as invalid (e.g. setting a session variable) to prevent session handling issues/fixation. Regeneration implies that we always delete the old session (use the parameter of `session_regenerate_id`).
from the man-page (https://www.php.net/manual/en/function.session-regenerate-id.php):
```php
session_start();

// Check destroyed time-stamp
if (isset($_SESSION['destroyed'])) { ... }
$_SESSION['destroyed'] = time(); // session_regenerate_id() saves old session data
session_regenerate_id(true);
unset($_SESSION['destroyed']);
```



### `@`-suppression operator: banned
If a call can fail, check its return value or wrap it and handle the failure — don't suppress the warning and hope.

### `exec`/`shell_exec`/`proc_open`/`system`: a hardening checklist, not a casual call
- **`escapeshellarg()` on every individual argument** — not `escapeshellcmd()` on the whole command line as a substitute; they solve different problems.
- **Prefer a PHP extension/library over shelling out** where one exists — removes the injection surface entirely rather than mitigating it.
- **If shelling out is unavoidable**, use the array-argument form where supported, avoiding shell interpretation of the argument string.
- **Comment the call** with what was considered and why.

### File uploads
Validate by content (`finfo_file()`, magic-byte sniffing), never by client-supplied MIME type or filename extension alone. Store uploads outside the webroot, or with execution disabled for that directory.

### JSON: fail loud on decode

```php
try {
    $data = json_decode($raw, associative: true, flags: JSON_THROW_ON_ERROR);
} catch (JsonException $e) {
    throw new RuntimeException("malformed JSON payload: {$e->getMessage()}", previous: $e);
}
```

The HTTP method check has already run at this point (`SKILL.md` rule 5) — a request that fails it never reaches a decode.
The length sanity check (min-len and max-len) has also already run at this point — we prevent an attack such as the billion-laughs attack.

## Access-scoping patterns
- **Ephemeral, scoped tokens over long-lived credentials** where the access pattern is naturally scoped (one resource, one action) — prefer a token scoped to that pattern over reusing the general session/auth token.
- **Role-based access is checked at the point of use, not just at routing.** Don't rely on a route being "only reachable by admins" as the sole enforcement — check the role/permission again inside the handler performing the sensitive action, so a routing mistake doesn't become an authorization bypass.

## Extensions and multi-stage builds
A PHP extension not present in the base runtime image gets compiled in a build stage and copied into the runtime stage as a compiled artifact — no compiler toolchain, headers, or PECL in the final image. Build against the same PHP version as the runtime so the extension's ABI matches.

The subtlety worth getting right: the runtime still needs the **shared libraries** the extension links against (`libpq`, `imagemagick-libs`), but must not carry the `-dev` header packages or the toolchain that produced the `.so`.

```dockerfile
ARG PHP_BUILD_IMAGE
ARG PHP_RUNTIME_IMAGE

# ---- Build stage: headers + toolchain, compile the extensions ----
FROM ${PHP_BUILD_IMAGE} AS builder

RUN apk add --no-cache $PHPIZE_DEPS postgresql-dev imagemagick-dev \
 && docker-php-ext-install -j"$(nproc)" pdo_pgsql \
 && pecl install imagick-3.7.0 \
 && docker-php-ext-enable imagick

# ---- Runtime stage: compiled .so files + their shared libs only ----
FROM ${PHP_RUNTIME_IMAGE} AS runtime

# Runtime shared libs the extensions link against — no -dev packages.
RUN apk add --no-cache libpq imagemagick-libs

# The compiled extensions, and the ini files that enable them.
COPY --from=builder /usr/local/lib/php/extensions/ /usr/local/lib/php/extensions/
COPY --from=builder /usr/local/etc/php/conf.d/ /usr/local/etc/php/conf.d/

ARG PHP_UID=33
ARG PHP_GID=33
COPY --chown=${PHP_UID}:${PHP_GID} ./app /app
USER ${PHP_UID}:${PHP_GID}
```

PECL packages are version-pinned (`imagick-3.7.0`), never floating. See `references/deployment.md` for the base-image pinning and UID/GID conventions this fits into.
