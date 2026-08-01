# JavaScript-Specific Rules (Browser Only)

Read this after `SKILL.md`'s cross-cutting rules. **Scope: browser JS only** — nothing here concerns Node.js. Node.js is used only when a project explicitly calls for it.

## No inline anything
External `.js` files only. No inline `<script>` blocks, no `onclick="..."`-style HTML attributes, no `eval()`, no `new Function()`, no `innerHTML` with untrusted content.

## No IIFEs — anywhere, for anything
Not `(function () { ... })()`, not `(() => { ... })()`, not as a module wrapper, not as a scoping trick, not as a one-off "just to keep this out of global scope." Named, top-level functions instead. An IIFE buries the function's identity, keeps it out of stack traces, makes it unremovable as a listener, and hides its purpose behind punctuation — the opposite of `SKILL.md` rule 2 (front-load meaning, purpose legible from the first token).

## Required file boilerplate

Every JS file that needs to run setup code uses this exact shape:

```javascript
var _<prefix>_loaded = false;

function <prefix>_init() {
    if (_<prefix>_loaded) { return; }
    _<prefix>_loaded = true;
    // ... bind events, set up state ...
}

document.addEventListener("DOMContentLoaded", <prefix>_init);

// Mandatory fallback — never omit. Covers the case where this script
// executed after DOMContentLoaded already fired, so the event will never
// fire again: check every readyState that indicates the DOM is already up.
if (document.readyState === "complete" ||
    document.readyState === "loaded" ||
    document.readyState === "interactive") {
    <prefix>_init();
}
```

`<prefix>` is the page name. The `_<prefix>_loaded` guard makes the double dispatch (listener + immediate check) safe when both paths fire.

Concrete example, from a forgot-password page:

```javascript
var _forgot_loaded = false;

function forgot_init() {
  if (_forgot_loaded) { return; }
  _forgot_loaded = true;
  if (window.bmPow && window.bmHttp && window.bmUi) { bmForgotBind(); return; }
  window.addEventListener("load", bmForgotLoadRetry, { once: true });
}

document.addEventListener("DOMContentLoaded", forgot_init);
if (document.readyState === "complete" || document.readyState === "loaded" || document.readyState === "interactive") { forgot_init(); }
```

This variant also waits on cross-file dependencies (`window.bmPow`, `window.bmHttp`, `window.bmUi`) before binding, falling back to the `load` event once if they aren't ready — an optional extension on top of the mandatory guard/dispatch shape, for pages whose script depends on globals from another `<script>` tag with no guaranteed load order.

## Namespacing
Global namespaces are project-prefixed: `bmHttp`, `bmPow`, `bmPwStrength`, `bmUi` (project prefix + purpose). `window.bm*` globals are defined **at script-load time**, not deferred into `_init` — other scripts must be able to rely on them before `DOMContentLoaded` fires.

Named handler functions, never anonymous inline closures — for callbacks **registered as a listener or a continuation**: `addEventListener` handlers and `.then()`/`.catch()` chains. A named function is identifiable in a stack trace and removable via `removeEventListener`; an anonymous closure registered this way is neither.

This does **not** cover one-off iteration callbacks (`forEach`, `map`, `filter`, and similar) — they're never registered anywhere, aren't removed independently, and don't need a stack-trace identity beyond their caller's. An anonymous callback there is fine, and the skill's own examples use them (see "Binding style" below).

For Promise continuations specifically, prefer `async`/`await` over a `.then()`/`.catch()` chain — it sidesteps the naming question entirely, since there's no continuation callback left to name:

```javascript
// Fine — anonymous callback, but it's a one-off iteration, not something registered.
items.forEach(function (item) { ... });

// Avoid — anonymous continuation callbacks.
fetchThing().then(function (result) { ... }).catch(function (err) { ... });

// Preferred — async/await removes the continuation callback altogether.
async function loadThing() {
    try {
        const result = await fetchThing();
        // ...
    } catch (err) {
        // ...
    }
}
```

## Binding style
Bind via `addEventListener` from the `_init` function — never an inline handler attribute. Element selection has a preference order, not a hard ban on any of them: **`data-*` attributes first, class-based selection second, ID-based selection allowed as a fallback.**

```javascript
document.querySelectorAll('form[data-pow-stage]').forEach(function (form) {
    form.addEventListener('submit', handlePowSubmit);
});
```

IDs earn their keep for **cross-element references** — element A's hook needs to point at element B, and a self-contained `data-*` attribute on A alone can't express that (e.g. a password-visibility-toggle button that needs to find "its" input). Two patterns, in order of preference:

```javascript
// Preferred where A and B share a container — a shared data-* wrapper,
// traversed with closest(). No id involved anywhere.
// <div data-field-group>
//   <button data-action="toggle-visibility">Show</button>
//   <input data-role="password-input" type="password">
// </div>
function handleToggleVisibility(event) {
    const group = event.currentTarget.closest('[data-field-group]');
    const target = group.querySelector('[data-role="password-input"]');
    target.type = target.type === 'password' ? 'text' : 'password';
}

// Fallback where A and B aren't in a shared container — target's id stored
// in the trigger's data-* attribute, resolved via getElementById.
// <button data-toggle-target="password-field">Show</button>
// <input id="password-field" type="password">
function handleToggleVisibility(event) {
    const target = document.getElementById(event.currentTarget.dataset.toggleTarget);
    target.type = target.type === 'password' ? 'text' : 'password';
}
```

## Wrapping repeated operations

Wrap an operation whose boilerplate repeats across call sites, or that might need to change in one place later. A JSON POST is the standard case: the method, headers, and `JSON.stringify` are identical everywhere, so they live in one wrapper (DRY), and every call site keeps one purpose per line (`SKILL.md` rule 2) — send, check, parse, act, each individually visible and individually checkable.

```javascript
// Wrong — the fetch boilerplate is duplicated at every call site, and the
// request, status check, parse, and use are fused into one expression:
// nothing between "fetch" and "name" can be inspected or fail loudly.
const name = (await (await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
})).json()).name;

// Preferred — boilerplate lives in one wrapper, one seam to change.
function postJson(url, payload) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
}

// Call site: one purpose per line, each step's outcome checkable.
const response = await postJson(url, payload);
if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
}
const result = await response.json();
renderName(result.name);
```

The status check is not optional: `fetch()` does **not** reject on HTTP error statuses (404, 500) — only on network failure. A 500 whose body is an HTML error page will otherwise surface as a confusing JSON parse error three lines later, instead of as the status failure it actually is.

This is also a great opportunity to follow the DRY principle and include handling of CSRF tokens in a reusable way.

## Browser availability
`fetch()` can be assumed available.

For anything else, **check current browser support at the time of writing** rather than assuming from memory — availability moves, and a function that was safe to use last year may still be unsupported in a browser the project has to serve (or vice versa). Verify against current support data before relying on a method.

If the person states that the site, or a specific sub-page, must run on **all browsers**, consider a polyfill: raise it explicitly and decide together, rather than silently either dropping the feature or shipping something that breaks on older engines.

## Security defaults

### `===`/`!==` always, never `==`/`!=`
JS's loose-equality coercion rules are a well-known footgun (`'' == 0`, `null == undefined`, `[] == false`).

### `textContent`, not `innerHTML`, for anything that isn't a fixed literal
If rendering user-supplied rich text as HTML is genuinely required, that's a sanitization-library decision (e.g. DOMPurify) — not something to hand-roll, per `SKILL.md` rule 10.

### Every Promise chain has explicit error handling
An `async` function called without `await` needs an explicit `.catch()`. An unhandled rejection is the JS equivalent of a PHP `@`-suppressed failure.

### `postMessage`: always check `event.origin`
Never act on a message without validating `event.origin` against an explicit allowlist.

## Client-side validation is UX only — the backend check is mandatory
A `required`/`pattern` attribute or a pre-submit JS check improves the experience — it saves the user a round trip — but it is not a security control: it runs in a browser the attacker fully controls and is trivially bypassed by sending the request directly. Client-side validation is **negotiable** — simplify or skip it under time pressure and it's not a real defect. The server-side validation of the same data is **not negotiable** — skipping it is a real defect regardless of what the client already checked.

See `references/html-css.md`'s "Forms" section for the HTML-side statement of this rule, and `references/php.md`'s "YAGNI does not apply here" and "JSON: fail loud on decode" sections for what the mandatory backend half looks like — not duplicated here.

## Loading
SRI in multiple hash formats simultaneously (see `references/html-css.md`). `async` for independent libraries with no DOM dependency; `defer` for scripts needing the DOM parsed first.
