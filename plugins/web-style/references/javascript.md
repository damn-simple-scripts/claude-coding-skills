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

Named handler functions, never anonymous inline closures: they're identifiable in a stack trace and removable via `removeEventListener`.

## Binding style
Bind via `addEventListener` from the `_init` function — never an inline handler attribute. Select elements via `data-*` attributes, not classes or IDs repurposed as JS hooks:

```javascript
document.querySelectorAll('form[data-pow-stage]').forEach(function (form) {
    form.addEventListener('submit', handlePowSubmit);
});
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

## Loading
SRI in multiple hash formats simultaneously (see `references/html-css.md`). `async` for independent libraries with no DOM dependency; `defer` for scripts needing the DOM parsed first.
