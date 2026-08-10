---
name: rust-style
description: The user's Rust coding conventions, including dependency and release practices, architecture patterns for web-exposed services, and Docker build practices. Use whenever writing, reviewing, editing, or generating Rust (.rs) code; when touching Cargo.toml, Cargo.lock, build.rs, rust-toolchain or a Dockerfile in a Rust project; when choosing, adding, upgrading, downgrading, replacing or version-pinning a Rust dependency, or weighing a crate's maturity and maintenance; when setting or changing the Rust edition or toolchain version; when preparing a release, production build, container image or healthcheck; or when discussing Rust error-handling/logging/IO/concurrency/process-isolation approach — even if the user doesn't explicitly ask for "style" or "conventions" to be applied. These conventions deliberately deviate from some idiomatic Rust defaults; apply them even when they conflict with what would normally be considered "cleaner" or more idiomatic code.
---

# Rust Style — Conventions

## Confirmed rules

### 1. Foundational principle: one purpose per line, stated as early as possible
This is the root rule — several rules below are *implications* of this principle, not independent style choices.

- **One purpose per line.** A single line should do one thing. Don't chain a function call and its error-handling/unwrapping into the same statement.
- **Code is read left to right**, so the *purpose* of a line (e.g. that it's a `return`, or that it's assigning a value) should be signaled as early as possible in the line — ideally by the first token. A reader should know what a line is *for* before reaching its end.
- **Flatten, don't nest.** Splitting a statement is only an improvement if the result is *flatter*. If pulling a fallible call out of a line pushes its real outcome one level deeper into a nested `match`, you've moved the cost, not removed it. Apply rule 5's fix — a named intermediate, matched at the *same* level, or an early return — instead of nesting a second `match` inside a match arm.

**Why this matters:** if the purpose of a line is only revealed at the end (e.g. a trailing `?` that silently turns an ordinary-looking expression into a possible early-return), the reader has to hold the line in suspension and re-interpret it retroactively once they hit the end. Putting the purpose first means the reader's left-to-right pass is never invalidated by something they find later in the same line.

**The test is the reader, not the line count.** These rules are a proxy for "a reader understands this on one left-to-right pass, without holding anything in suspension." When applying them mechanically makes a passage harder to follow than what was there before, the rules lost that round — leave the clearer version and say why. Rewriting compliant-and-clear code into compliant-and-worse code is a violation of this rule, not an application of it.

### 2. No `?` operator
Do not use `?` for error propagation, even where it's the idiomatic choice.

**Why this deviates from idiomatic Rust — and how it follows from rule 1:** `?` fails rule 1 twice over. First, it bubbles an error *and* calls a function in the same line — one line, two purposes. Second, the fact that a line can early-return is only visible at the very end of the line, which violates "purpose stated as early as possible." `?` is normally preferred in idiomatic Rust because it's the checked, compiler-enforced way to propagate errors — the deviation here isn't about safety, it's that the resulting control flow is invisible until the reader hits the last character. Do not "fix" this back to `?` — it is intentional, not an oversight.

### 3. No unchecked `.unwrap()`
Never call `.unwrap()` (or `.expect()` without deliberate justification) where an error path exists. Errors must be handled explicitly.

### 4. Explicit `match` / `if ... .is_err()` for error handling
Given rules 2 and 3, error handling is done via explicit `match` on the `Result`/`Option`, or `if ...is_err() { ... }` / `if let Err(e) = ...` style branching. This is the replacement pattern for `?`.

**Combined rationale for 2–4:** the goal is that every fallible operation has a visible, reviewable handling block at the call site, rather than propagation happening implicitly.

### 5. Never match on (or unwrap) a function call inline — assign first, then handle
Directly consistent with rule 1: don't write `match DO_SOMETHING_THAT_RETURNS_RESULT() { ... }` or unwrap a call inline. Split into two lines:

```rust
// Wrong — call and match fused into one statement/expression
match do_something_that_returns_result() {
    Ok(v) => ...,
    Err(e) => ...,
}

// Preferred — two lines, two purposes
let _res = do_something_that_returns_result();
match _res {
    Ok(v) => ...,
    Err(e) => ...,
}
```
Line 1's sole purpose is the call/assignment; line 2's sole purpose is the branching. Never collapse them.

**Naming convention — leading underscore for intermediate results:** variables holding a `Result`/`Option` that exists only to be unwrapped/matched a line or two later are prefixed with `_` — e.g. `_res`. This is a *prefix pattern*, not a single hardcoded name: use a descriptive stem (`_conn`, `_parsed`, `_lookup`) when a function has multiple short-lived intermediates, so they don't collide.

**Chained fallible steps: flatten with early returns, don't nest a second match inside a match arm.**
A fallible operation *inside* a match arm is the case that actually breaks this rule in practice —
the "obvious" fix nests a second match instead of flattening, which is worse than the original:
```rust
// Wrong — the ORIGINAL code already violates this rule (matches a live call):
match std::env::var(key) {
    Ok(raw) => raw.parse::<usize>().unwrap_or(default),
    Err(_) => default,
}

// Wrong again, differently — "fixing" the inline unwrap_or by nesting a second
// match inside the Ok arm still violates this rule, and now the real outcome
// (value vs. default vs. logged-and-default) is two levels deep instead of one:
match std::env::var(key) {
    Ok(raw) => match raw.parse::<usize>() {
        Ok(value) => value,
        Err(error) => {
            warn!(key, %raw, %error, "env var not a valid usize; using default");
            default
        }
    },
    Err(_) => default,
}

// Preferred — flatten instead of nesting: each fallible step gets its own
// `_`-prefixed intermediate and its own match at the top level, closing the
// first one out with an early return rather than nesting into it.
let _raw = std::env::var(key);
let raw = match _raw {
    Ok(v) => v,
    Err(_) => return default,
};
let _parsed = raw.parse::<usize>();
match _parsed {
    Ok(value) => value,
    Err(error) => {
        warn!(key, %raw, %error, "env var not a valid usize; using default");
        default
    }
}
```
Both "wrong" versions above match a live call — the second one just hides that violation one level
deeper instead of fixing it. Nesting a match inside a match arm doesn't add a purpose per line, it
hides one match inside another; expanding a one-liner into more tokens is not the same thing as
flattening it (rule 1's new "flatten, don't nest" bullet). The flattened version keeps every
outcome — parsed value, missing-var default, unparseable-and-logged default — reachable at the
same level of indentation, so a reader finds any of them by scanning one `match`, not two.

**The other shape: alternatives, not a chain — "if A fails, try B instead."**
The example above is a *linear chain*: step 2 runs because step 1 SUCCEEDED. The other common
shape is a fallback, where step 2 exists only because step 1 FAILED, there is no default to
return, and both causes have to survive into the final error. The linear recipe doesn't
transplant onto it — so flatten it the mirror-image way: **early-return the SUCCESS and let the
failure fall through**, keeping each attempt at the top level.
```rust
// Wrong — the fallback attempt is nested inside the first attempt's Err arm, so the
// three outcomes (primary, fallback, neither) sit at three different depths:
let _primary = File::open(primary_path);
match _primary {
    Ok(file) => read_entries(file),
    Err(cause_primary) => {
        let _fallback = File::open(fallback_path);
        match _fallback {
            Ok(file) => read_entries(file),
            Err(cause_fallback) => Err(format!(
                "no wordlist: {primary_path}: {cause_primary}; {fallback_path}: {cause_fallback}"
            )),
        }
    }
}

// Preferred — each attempt is its own top-level match that either returns the success
// or yields the cause and falls through. The error path reads as a straight list of
// attempts, and both causes are still in hand at the end.
let _primary = File::open(primary_path);
let cause_primary = match _primary {
    Ok(file) => return read_entries(file),
    Err(error) => error,
};
let _fallback = File::open(fallback_path);
let cause_fallback = match _fallback {
    Ok(file) => return read_entries(file),
    Err(error) => error,
};
Err(format!(
    "no wordlist: {primary_path}: {cause_primary}; {fallback_path}: {cause_fallback}"
))
```
Adding a third source later appends one more block instead of adding one more level of
indentation — that's the test for whether this shape has actually been flattened.
**This is an addition, not a replacement:** a step that runs because the previous one *succeeded*
is still the linear case, and still flattens the way the first example shows.

### 6. Buffered I/O
Use buffered readers/writers (e.g. `BufReader`, `BufWriter`) for file or stream I/O rather than raw/unbuffered reads.

### 7. Timing via `std::time::Instant`
Performance/rate metrics are measured using `std::time::Instant`, not wall-clock alternatives like `SystemTime` (which is subject to clock adjustments).

### 8. Structured, level-based logging through a facade — configurable level, backend by project fit
**The requirement:** significant runtime events are emitted as `info`-level log events through a
logging facade. `println!`/`eprintln!` are for throwaway debugging only, never for anything that
ships. **The log level must be configurable via an environment variable, regardless of backend —
non-negotiable.** `env_logger`'s `RUST_LOG` is the reference pattern; `tracing-subscriber`'s
`EnvFilter` is the equivalent for `tracing`.

**Backend is a deliberate per-project choice — pick one of two, ask if unstated:**
- **`log` + `env_logger`** — small, simple scripts and CLIs; plain text-line output is enough.
- **`tracing` (+ `tracing-subscriber`)** — complex, multi-component, or async/concurrent projects
  (spans carry causality across `.await`/thread boundaries that plain `log` events can't), or
  whenever output needs to be structured/specific-format (JSON logs, span-based tracing for
  observability tooling).

Pick one per binary and stay consistent — a project mixing both is the actual defect. Existing
code already consistently using one of them is not a violation; don't rewrite it to match a
default (see "Applying this skill" item 3).

### 9. Dependency management via `cargo add`
Add dependencies with `cargo add <crate>` rather than hand-editing `Cargo.toml` version entries.

### 10. `.ok()` (Result→Option conversion) is a code smell — check for a `Result`-native equivalent first
Treat `.ok()` used to convert a `Result<T, E>` into an `Option<T>` as a default red flag.

**Why:** the conversion discards the `E` value — contradicting rules 2–4. This pattern shows up because training data and common tutorials skew toward `Option`-shaped idioms even where `Result` already has the needed method. Concretely: `as_deref()` exists on both `Option<T>` and `Result<T, E>` — reaching for `.ok()` first is an unnecessary detour that throws away the error for no reason.

**When reviewing or writing code:** check whether `Result` already exposes the method being chased (`as_deref`, `as_ref`, `map`, `and_then`, `unwrap_or*` all exist on both types) before calling `.ok()`.

### 11. Prefer `&str` over `String` in hot paths — avoid unnecessary allocation
Use `&str` (borrowed) instead of `String` (owned, heap-allocated) wherever a borrow suffices, specifically to avoid generating new heap objects in hot paths.

- **Hot paths** (loops, per-item processing, high-frequency calls): refrain from allocating new `String`s. Prefer `&str`, slices, or reusing buffers.
- **Output boundaries** (final results, log/error messages): allocating a `String` here is fine — paid once, not per-iteration.

Don't apply this as a blanket "never use `String`" rule — it's about allocation churn in frequently-executed code.

### 12. Collect as late as possible — chain iterators, don't materialize early
Prefer chaining iterator adapters (`.map()`, `.filter()`, `.fold()`, `.take()`, etc.) and only calling `.collect()` at the very end of the pipeline.

**Why:** the iterator-level expression of rule 11. Each intermediate `.collect()` forces a full allocation before the next stage even starts. `.fold()` is a good example of staying lazy — it accumulates without ever collecting an intermediate collection.

**When reviewing or writing code:** flag a `.collect()` immediately followed by further chaining on the result. A `.collect()` at the true end of a pipeline is fine.

**Tension with rules 1/5 worth naming, not resolving by default:** a long lazy chain is itself one line doing several things — in tension with "one purpose per line." No default resolution is set; if a chain's purpose isn't clear left-to-right, consider breaking it into named steps and flag the tradeoff rather than silently picking a side.

### 13. Explicit iterators over implicit ones — align with `rayon`/`tokio` parallelization
Prefer explicit iterator-producing methods (e.g. `.lines()`) over implicit/manual loops achieving the same thing (e.g. repeated `.read_line()` calls).

**Why:** keeps the codebase parallelization-ready. `.lines()` returns a real `Iterator`, so a `rayon`-parallel equivalent (`.par_lines()`) is a drop-in swap if that path ever needs to scale. A hand-rolled `read_line()` loop has no such parallel counterpart.

**When reviewing or writing code:** prefer iterator methods over manual loops doing the same thing, especially ones with known `rayon` (`par_*`) or async equivalents — even if parallelism isn't used yet, it keeps the door open without a rewrite.

### 14. Production builds use `cargo-auditable` for SBOM generation, plus ship `Cargo.toml` in the final image
For production code, build with `cargo auditable build --release` (from `rust-secure-code/cargo-auditable`) rather than plain `cargo build --release`.

**Why:** compiled Rust binaries strip away `Cargo.toml`/`Cargo.lock` — container scanners (Trivy, Syft, Anchore) normally can't see which crates went into the binary. `cargo-auditable` embeds the dependency list directly into the binary at build time, so scanners can extract an accurate SBOM with no source/lockfile needed. Drop-in replacement for `cargo`; typically paired with `cargo audit bin <path>`.

**Also copy `Cargo.toml` into the final image** (e.g. `COPY --from=builder /app/Cargo.toml /Cargo.toml`) so file-based scanners that look for a manifest directly (not just binary introspection) also have something to find. Redundant with the embedded SBOM by design — two independent detection paths, not a replacement for one another.

**Scope:** production/release builds specifically — not necessarily every local dev build.

### 15. Forking/spawning worker processes: evaluate a hardening checklist, don't apply all of it blindly
When forking or spawning a worker/child process that operates on user-supplied data, evaluate (don't necessarily apply) each hardening step below. Which ones apply depends on deployment context — e.g. a container already running with `--cap-drop=ALL` and a read-only filesystem has handled some of this at the infrastructure layer already; re-implementing it in-process would be redundant, but should be a conscious decision, not an oversight.

**Checklist to evaluate per fork/spawn:**
- **Clear the environment** before exec.
- **Drop privileges** as early as possible, and permanently.
- **Switch user** to an unprivileged account for the actual work.
- **Landlock** (or equivalent LSM sandbox) to restrict filesystem access.
- **chroot** to constrain the visible filesystem root.
- **seccomp** to restrict the syscall surface.
- **rlimits** (`setrlimit`) to bound memory/CPU/fd/process-count consumption.
- **Close unneeded file descriptors** in the child.

**Ordering trap:** `setgid()` must be called *before* `setuid()`. Dropping user privileges first silently leaves the process with its original group privileges — compiles and runs with no visible error.

**Before building a custom sandbox, evaluate `minijail0` (ChromeOS) first** — a reference implementation of this exact checklist.

**Mandatory: comment every fork/spawn using the template below, within 10 lines of the call site.**

Every checklist item gets its own line, always all 8, in a fixed grepable format:
`// HARDENING: <item>=<STATE> — <citation/reason>`. `<STATE>` is one of five closed vocabulary
words — `APPLIED` (enforced by code in this repo — cite the file:line), `DELEGATED` (enforced by
an external tool this project invokes — cite the tool, flag, and the condition under which that
flag fires), `CONTAINER` (already provided by the deployment environment — cite the infra
artifact), `SKIPPED` (deliberately not applicable — one clause why), or `UNVERIFIED` (genuinely
not known — state what would settle it; use this instead of guessing, never round a guess up to
`APPLIED`).

**Template:**
```rust
// HARDENING: environment=<STATE> — <citation/reason>
// HARDENING: privilege-drop=<STATE> — <citation/reason>
// HARDENING: user-switch=<STATE> — <citation/reason>
// HARDENING: landlock=<STATE> — <citation/reason>
// HARDENING: chroot=<STATE> — <citation/reason>
// HARDENING: seccomp=<STATE> — <citation/reason>
// HARDENING: rlimits=<STATE> — <citation/reason>
// HARDENING: fd-close=<STATE> — <citation/reason>
```

**Worked example:**
```rust
// HARDENING: environment=APPLIED — env::remove_vars() at sandbox.rs:41, cleared before spawn
// HARDENING: privilege-drop=CONTAINER — Dockerfile `USER 65532`; container never runs as root
// HARDENING: user-switch=CONTAINER — same as privilege-drop, no in-process setuid() needed
// HARDENING: landlock=SKIPPED — Landlock unavailable on the deploy kernel; chroot covers this
// HARDENING: chroot=DELEGATED — minijail0 `-C <path>`, emitted unconditionally by build_argv()
// HARDENING: seccomp=DELEGATED — minijail0 `-S <policy>`, emitted unconditionally by build_argv()
// HARDENING: rlimits=APPLIED — setrlimit(RLIMIT_AS) at sandbox.rs:88; untrusted input size unbounded
// HARDENING: fd-close=UNVERIFIED — minijail0's fd-closing behavior not confirmed; needs a test
let child = spawn_worker(&args); // <-- call site the block above documents
```

**Never replace an existing hardening block with a less-verified one.** If the comment already
there cites something you can't re-verify, leave it and add what you actually checked — don't
downgrade a citation to a guess just to make an edit look complete.

**Reference:** Gopi Krishnan S, ["Principles of Secure C and C++ Programming"](https://medium.com/@gopikrishnans_46095/principles-of-secure-c-and-c-programming-bb97e60a692c) — least-privilege / drop-privileges-early and the `setgid()`/`setuid()` ordering trap.

### 16. Rust is chosen for performance or safety — when it's safety, assume the code is exposed
Every use of Rust should have a clear reason: performance, or safety. When it's safety (e.g. Rust as a memory-safe parser for untrusted input — images, uploads, network data), **assume that code is exposed to an adversary** — treat it as an attack surface, not just "well-typed code that happens to be memory safe." Connects directly to rules 15 and 17.

### 17. Web-exposed Rust services: split server from worker, choose a hardening level deliberately
Don't put request-handling and exposed data-processing (parsing multimedia, rendering untrusted documents, decoding attacker-supplied formats) in one undifferentiated blob. A typical production web service splits into up to four binaries:

1. **Main program** — parses CLI args, dispatches to server or healthcheck.
2. **Server binary** — runs the webserver (`tokio`-based), handles routing/HTTP, invokes worker(s) for exposed/risky work.
3. **Healthcheck binary** — always a separate compiled binary, never a flag or subcommand on the server binary (mandatory — rule 18). Kept separate so the server process doesn't carry healthcheck-only attack surface.
4. **Worker binary/binaries** — one minimal task each, likely communicating with the server via a pipe.

**Security level is a deliberate choice — pick one of three, ask if unstated:**
- **Hardened:** server (`tokio`) forks/`execve`s to a separate worker binary, hardened per rule 15 before `execve`. Multiple forks/execve per request are acceptable here — when Rust's whole point in a component is security, isolation wins over raw throughput; scale via a reverse proxy/more replicas instead of skipping isolation.
- **Medium:** worker runs in its own OS process (still process-level isolation) but without a full `execve` re-exec — skip the fork+exec hardening dance when full hardening isn't warranted, while keeping the process boundary.
- **Fast/internal:** `tokio` and `rayon` share the same process — only appropriate for internal, trusted, or already-established-safe/performance-focused code, not for components whose entire justification is safety against untrusted input (rule 16).

**When in doubt, ask which level applies (hardened/medium/fast)** rather than defaulting silently — a real security-vs-throughput tradeoff, not a style choice.

**On mixing `tokio` and `rayon` in the "fast" tier:** don't call `.par_iter()` directly inside a `tokio` request handler — blocks an I/O worker thread on CPU-bound work, which can freeze the whole async runtime under load. Established pattern: `rayon::spawn` to dispatch to Rayon's pool, `tokio::sync::oneshot::channel` to receive the result asynchronously. Budget the two pools deliberately (both default to "use all cores," causing oversubscription under a capped container CPU limit), and skip parallel dispatch for trivially small workloads.

**Reference:** PostHog Engineering, ["Untangling Tokio and Rayon in production"](https://posthog.com/blog/untangling-rayon-and-tokio) — a production incident (2.5s p99 spikes) from exactly this anti-pattern, and the `rayon::spawn` + `tokio::sync::oneshot` fix.

### 18. Webserver projects must ship a self-contained healthcheck as a separate binary
A webserver project must ship a dedicated healthcheck binary — a distinct compiled artifact (a `[[bin]]` entry or `src/bin/*.rs`) with its own `main`. **A CLI flag or subcommand on the server binary is not an accepted form of this — do not implement the healthcheck as `argv` dispatch inside the server binary.** The healthcheck logic must be fully self-contained — no shelling out to `curl`/`wget`/`nc`/system tools. Matters especially for `FROM scratch` images (see Docker section), which have no shell to invoke anything with anyway.

**Why a separate binary is mandatory, not a style preference:** a CLI flag means the healthcheck code is compiled into, and reachable within, the same process that serves untrusted requests — exactly the attack surface rule 17 splits server from worker to avoid. A separate binary removes that code from the serving process's binary and address space entirely; it isn't just a different default entry point, it's a different artifact the serving process never loads.

### 19. Every line needs a justifiable reason — don't write what you can't justify
If you can't state why a line exists, it shouldn't be written — especially for choices that add complexity without a stated payoff. Before writing a line, be able to answer:
- Do we need `.collect()` here, or can this stay a lazy iterator (rule 12)?
- Do we need to normalize/fix string case, or do we already know enough about the input to skip it?
- Do we need complex iterator/`Result` chaining, or would a plain `if` be simpler and equally correct?

Every piece of complexity should be traceable to a concrete reason, or it's a smell.

### 20. Branch-level debug logging, without wasting CPU on formatting
Include debug-level logging on branches (not necessarily in loops, and especially not hot paths — rule 11) so logs explain *why* a branch was taken. When a debug print requires nontrivial computation to produce, guard it behind `log_enabled!` so the expensive part never runs when the log level wouldn't emit it:

```rust
if log_enabled!(Level::Info) {
    let x = 3 * 4; // expensive computation
    info!("the answer was: {}", x);
}
```
(Example from the [`env_logger` documentation](https://docs.rs/env_logger/latest/env_logger/).) Without the guard, expensive computation runs unconditionally even when the log level would discard the message.

**The guard buys nothing when the expensive part is already an argument to the log macro.** Both
`log` and `tracing` check the level *before* evaluating their arguments, so
`debug!("{}", build_summary(names))` already skips the work — wrapping that single expression in
`log_enabled!` is a no-op. Reach for the guard when the expensive part needs statements of its own
before the call, which is also the shape that goes wrong most often:
```rust
// Wrong — the summary is built unconditionally; the guard arrived one line too late to matter
let summary = build_summary(names);
debug!("{summary}");
```
**ANDing a business condition into the guard is fine.** `if log_enabled!(Level::Debug) && rate < 1000.0`
emits only when both hold, and `&&` short-circuits either way — put whichever test is cheaper
first (`log_enabled!` is an atomic load; a computed business condition usually isn't).

### 21. Fail early and verbose
Detect and report a problem as early as possible, with enough context (rule 8/20 logging) to understand what went wrong — rather than letting bad state propagate further before it surfaces. Operational counterpart to rule 3.

### 22. Handle errors early — validate at the boundary, not downstream
- Check function parameters at the *start* of each function.
- Validate as soon as user-provided data is parsed — don't let it travel further before being checked.
- Whenever a function returns `Option`/`Result`, always check explicitly before any unwrap-equivalent access (rules 2–4), and make sure every propagated error *does* get logged somewhere, so the failure is traceable. **Somewhere, not necessarily here** — see "Who logs" immediately below for where that log line belongs.

**Who logs, when the error is returned rather than handled:** a small pure function that hands its
error back to a caller inside the same program does **not** have to log it itself. **Log once, at
the place that decides what to do about the failure** — and make the returned error carry enough
context (the path, the line, the offending value) for that place to say something useful. A
library function whose errors are all logged by its one caller is compliant; two log lines for one
failure is a defect the same way zero is.

Log at the point of detection instead whenever nobody upstream will: when the error is about to be
swallowed, ignored or converted into a default; when it crosses a thread, process or trust
boundary; or when the caller is a third party you don't control. If a returned error is logged
nowhere, the function that produced it owns the miss.

Rule 21's "as early as possible" governs **detection** — check at the boundary, return
immediately, don't let bad state travel. It does not govern where the log line lives. Detecting
late is the defect rule 21 exists to stop; logging one frame up, at the place that knows what the
failure *means*, is not.

### 23. Default to readability over performance, and clean code over manual optimization — unless stated otherwise
- **Readability over performance** absent a stated performance requirement.
- **Trust the compiler; don't do its job by hand.** Write the clean/obvious version and let the compiler handle inlining/simple loop transforms rather than hand-rolling "clever" code to pre-empt an optimization it would likely already perform. Not a license for algorithmic laziness (rule 26) — specifically about not micro-optimizing at the code-shape level.

### 24. Thread/process communication: default to a fixed-size, array-based queue — but always analyze the actual use case
Absent a stated alternative, prefer a fixed-size array-based queue (ring buffer: two pointers looping through a fixed array), lock-free where possible, with predictable/contiguous memory addresses (NUMA-awareness where it matters). **Always pull this from `std` or an established dependency — never hand-roll a lock-free ring buffer.** Lock-free concurrent code is exactly where a subtle bug (missed memory-ordering, an ABA edge case) is invisible in testing and only surfaces under real load (rule 25 territory).

**Don't skip the use-case analysis — the default is a starting point:**
- **Producer/consumer cardinality**: SPSC, SPMC, or MPMC? Changes which structure is actually correct.
- **Fixed vs. unbounded**: can the workload actually be bounded?
- **Where the real bottleneck is**: if I/O-bound rather than queue-throughput-bound, plain `std::sync::mpsc` may be right specifically because it reduces complexity for free.
- **Is `rayon` already in play?** — check `.par_bridge()` before a hand-managed queue.
- **Are `tokio` and `rayon` being tangled?** (rule 17) — if communication is between an async task and a `rayon` worker, `tokio::sync::oneshot::channel` (single result) or `tokio::sync::mpsc` (stream) is likely right, not a raw ring buffer.

**Concrete crate options to evaluate (not a ranked default — pick based on the analysis above):**
- `crossbeam` (`ArrayQueue`) — well-established, MPMC, good default starting point.
- `ringbuf` ([`agerasev/ringbuf`](https://github.com/agerasev/ringbuf)) — SPSC-focused lock-free ring buffer.
- `turbo-mpmc` — lock-free MPMC, benchmarked faster than `crossbeam-channel` per its own docs; newer/less established, weigh against rule 25.
- `nexus-queue` — lock-free ring buffer (basis for `nexus-channel`, a bounded SPSC channel); also newer/less established.

**Always add a comment at the point of use explaining the reasoning** for the specific queue/channel chosen — cardinality, why fixed-size or not, why this crate over alternatives.

### 25. Prefer well-established, actively maintained crates over experimental ones
Maintenance matters more than marginal performance or novelty. Default to the established crate unless there's a concrete, stated reason a newer/experimental one's advantage matters for this specific use case.

### 26. Optimize at the algorithmic level before the code level *(general — not Rust-specific)*
If a better data structure/algorithm changes the complexity class, fix that first. E.g.: a hash table gives O(1) lookup — don't performance-tune a tree instead; a Bloom filter gives an O(1) existence check — don't optimize a full search instead of switching. Code-level tuning only makes sense once the algorithmic approach is already right.

### 27. Decouple blocking stages — buffer, don't chain blocking I/O directly *(general — not Rust-specific)*
Don't wire a blocking read directly into a blocking write (read a chunk, block writing it, repeat) — decouple with buffering (reader side, writer side, or both) or async I/O, so one slow stage doesn't force the other to stall in lockstep. Memory constraints can override this (don't buffer the entire input just to avoid blocking chains if that blows the memory budget) — but a bounded buffer or async I/O is cheap enough to be the default, not something reached for only when convenient.

### 28. Always target the most recent stable Rust edition
Unless a project has a stated compatibility constraint, use the newest stable edition available — don't default to an older one out of habit.

### 29. Comments and reports speak the project's language — never the skill's
This skill is a private instruction set. It must be invisible in everything that ships.

- **Never write a rule number, or this skill's name or author, into anything that ships** — source
  code, comments, commit messages, PR or issue text. `// rule 22: validate at the boundary` is
  meaningless to any reader who doesn't have this document. Write the *reason* instead: `// reject
  before the value reaches the renderer`. This half is unconditional and has no exceptions:
  shipped artifacts outlive the conversation that produced them, and their readers will never
  have this document.
- **A report back to the user is the one surface where this is conditional.** If the user raised
  these conventions themselves — invoked this skill by name, named the convention set, or asked
  for a compliance review against it — then citing rule numbers back to them is useful and
  allowed, because they are holding the document. In every other case report in the project's own
  vocabulary: state the problem and the reason, never the authority. The deciding question is
  whether the *user* put these conventions on the table, not whether the review found anything.
- **Comments describe the code as it is now, not how it changed.** No "the old version did X", no
  "changed from `HASH_NAMES` because…", no narrating your own diff. Change history belongs in the
  commit message, not in a file that outlives it — a comment describing a previous state is wrong
  the moment someone reads it without that diff in front of them.
- **A comment's job is the *why* that rule 19 says every line needs** — the constraint, the trap,
  the thing the code can't say about itself. If a comment just restates what the code already
  plainly does, delete it.
- **Exception:** the mandatory hardening comment (rule 15) and the queue-choice comment (rule 24)
  are required content, and they *are* rationale, not narration — write them in project vocabulary
  too, citing the enforcing flag/call/tool, never "rule 15" or "rule 24".

### 30. Verify before asserting — or mark it unverified
Don't hand over code, or a claim about code, that you haven't actually checked.

- **Code you propose gets compiled, not imagined.** A snippet offered in a review or a report is
  still code — run `cargo check` on it in the real crate before emitting it. Type errors in a
  one-line "fix" are the common case, not an exotic one.
- **Claims about the codebase get looked up.** "There is no other caller", "this is already
  handled elsewhere", "nothing else uses this field" — go read it, then say it.
- **When verification genuinely isn't possible, say so in the same breath**, using rule 15's
  `UNVERIFIED` vocabulary: name what you did not check and what would settle it. No toolchain, a
  platform-only dependency, no access to the file — all fine reasons; silently rounding an
  unchecked assumption up to an assertion is not.

**Why this is a rule and not a nicety:** a confident wrong answer costs the reader more than "I
didn't check" does — they act on it, and the correction arrives after the damage. Every other rule
here assumes what you report is true.

## Docker: two-stage minimal-image builds for Rust binaries

Rust binaries destined for production run in Docker, built as a **two-stage build**: a `builder` stage with the full Rust toolchain, and a minimal runtime stage receiving only the compiled binary. The strongest form, when the binary has no C-library dependencies (SQLite, OpenSSL, etc. need special static-linking handling if present), is `musl` libc + `FROM scratch`.

### Why `musl` + `FROM scratch`
By default, Rust statically links pure-Rust dependencies but *dynamically* links C libraries like `libc` — a binary built with the default `x86_64-unknown-linux-gnu` target still needs `glibc` present, which a `scratch` (empty) image doesn't have; it fails with `no such file or directory` because the dynamic linker itself is missing. Building against `x86_64-unknown-linux-musl` instead statically links libc too, producing a genuinely standalone binary (verify with `ldd <binary>` → `statically linked`). That binary can run in `FROM scratch` containing nothing but itself.

**Security payoff, not just size:** a `FROM scratch` container has no shell, no package manager, no OS utilities — if the process is compromised, the attacker lands in an empty container with nothing further to exploit. (This is also why rule 18's healthcheck must be self-contained — there's no shell here to invoke a script even if you wanted one.)

### Worked example

```dockerfile
# ---- Stage 1: builder ----
FROM rust:1.75-bookworm AS builder
WORKDIR /app

# Cache dependency compilation separately from source changes
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs \
    && rustup target add x86_64-unknown-linux-musl \
    && cargo build --release --target x86_64-unknown-linux-musl \
    && rm -rf src

# Now copy real source and build the actual binary
COPY src ./src
RUN cargo auditable build --release --target x86_64-unknown-linux-musl
# ^ cargo-auditable (rule 14) — embeds the dependency list into the binary
#   itself so container scanners (Trivy etc.) can read it with no source/lockfile.

# ---- Stage 2: runtime ----
FROM scratch AS runtime
COPY --from=builder /app/target/x86_64-unknown-linux-musl/release/<binary-name> /<binary-name>
COPY --from=builder /app/Cargo.toml /Cargo.toml
# ^ rule 14 — plain-manifest copy alongside the embedded SBOM, for scanners
#   that look for a manifest file directly rather than introspecting the binary.
CMD ["/<binary-name>"]
```

Notes:
- **Dependency-layer caching**: building against a dummy `src/main.rs` first means Docker caches the (usually slow) dependency layer across rebuilds where only app code changed.
- **`FROM scratch` has no shell** — certs for outbound TLS must be copied in explicitly (`COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt`).
- **If C dependencies are unavoidable**, they need explicit static linking before `FROM scratch` is viable — otherwise `distroless` (e.g. `gcr.io/distroless/cc-debian12`) is the fallback.

### What was actually tested vs. not, for this skill draft
No Docker available in the sandbox this skill was drafted in, so the full `docker build`/`FROM scratch` step was **not** tested end-to-end. What *was* verified directly: `cargo build --release --target x86_64-unknown-linux-musl` on a fresh `cargo new` project produces a binary confirmed via `ldd` (`statically linked`) and `file` (`static-pie linked`) with zero dynamic dependencies, and it runs correctly. The Docker-specific parts are drawn from the reference articles below but not independently re-verified by building the image.

**Ready-to-run prompt for Claude Code to test the full build (needs local Docker):**

> Using the Dockerfile in `<path>`, run `docker build -t rust-scratch-test .` then `docker run --rm rust-scratch-test` and confirm it prints the expected output. Also run `docker images | grep rust-scratch-test` to report the final image size. If the build fails, diagnose whether it's a missing static-link dependency vs. a Dockerfile syntax issue, and report which.

### References
- Brenden Hyde, ["Building a Standalone Rust Binary for a Scratch Docker Container"](https://bxbrenden.github.io/)
- 21 Analytics, ["Docker 'FROM scratch' Containers for Rust"](https://www.21analytics.co/blog/docker-from-scratch-for-rust-applications/)
- Leapcell, ["Building Minimal and Secure Rust Web Applications with Docker"](https://leapcell.io/blog/building-minimal-and-secure-rust-web-applications-with-docker)

## Applying this skill

When writing or reviewing Rust code:
1. Apply rules 1–30 without exception unless the user explicitly overrides for a specific case.
2. For web-exposed services, apply the architecture split (rule 17) and ask which security tier (hardened/medium/fast) applies if it isn't already stated.
3. If existing project code contradicts these rules, don't silently "fix" it unless asked — but do flag the inconsistency.
4. Every piece of nontrivial code should be traceable to a stated reason (rule 19).
5. Report findings in the project's own vocabulary (rule 29) — the problem and the reason, not the
   authority. Rule numbers may be cited back to a user who raised these conventions themselves
   (invoked this skill, or asked for a review against it), and never anywhere else: not in code,
   comments, commit messages, or PR text.
6. **Check every site of a rule, not just the first.** Finding one instance makes the search *feel*
   finished; it isn't. After reporting a violation, sweep the same file again for that same rule
   before moving on — repeat instances of one rule are the most commonly missed findings.
7. **Give the structural rules their own deliberate pass.** The rules a grep can find (`?`,
   `.unwrap()`, `.ok()`, `println!`) are cheap, and they crowd out the ones that need a whole-file
   or whole-architecture read: the flatten-don't-nest half of rule 5, and rules 15–18, 22, 24, 27,
   30.
   A review that reports only cheap findings usually hasn't looked at the expensive ones at all —
   so name which structural rules you actually checked, so that "not mentioned" can't be misread
   as "not violated".
8. **These rules govern shipped code.** Inside `#[cfg(test)]`, `.unwrap()`/`.expect()` on test
   setup and assertions is fine — a panic *is* the failure report there. Everything else still
   applies to test code.
