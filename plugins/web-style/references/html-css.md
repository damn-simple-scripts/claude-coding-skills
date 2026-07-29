# HTML/CSS-Specific Rules

Read this after `SKILL.md`'s cross-cutting rules.

## Content Security Policy
Strict baseline: `default-src 'self'; script-src 'self'; style-src 'self'` — no inline JS or CSS anywhere, unconditionally. All scripts and styles are external files. If a page needs to call an external API, that specific URL is added to `connect-src` for that page — not a static catch-all `connect-src` covering things most pages don't need.

## Self-host, don't live-link a CDN
Default posture is self-hosting. If a third-party JS/CSS library is needed and nothing states otherwise, download it once and vendor it as a pinned, static file served from the project's own origin — not a live `<script src="https://cdn.example.com/...">`. A `make deps`-style target fetches pinned frontend dependencies; a `make sri` target computes their SRI hashes. Reach for an actual live CDN reference only when a project explicitly states that's the intended setup.

## CSS frameworks — allowed under criteria
Tailwind and Bootstrap are both acceptable, with a strong lean toward Bootstrap. A framework qualifies only if all of these hold:

- **Servable as static, self-hosted files** — per the rule above.
- **Well maintained**, with a real track record of continuing updates.
- **Mobile support.**
- **Accessibility support.**
- **Dark/light theme support.**

A framework failing any of these doesn't get used. This is a CSS-only allowance — it doesn't extend to JS or PHP frameworks (`SKILL.md` rule 1).
Tailwind and Bootstrap are safe examples, users or skills or MCP may suggest alternatives.

## Subresource Integrity — on every external script and stylesheet
Every `<script>` and `<link rel="stylesheet">` carries an `integrity` attribute computed in multiple hash formats simultaneously (sha256, sha384, sha512), plus `crossorigin="anonymous"`.

Algorithm selection isn't hardcoded to "always emit all three": it's the intersection of `{sha256, sha384, sha512}` (SRI's spec-supported set) and whatever `hash_algos()` actually offers at generation time. If none of the three are available, omit integrity rather than emitting a useless one. If SRI is calculated statically, aim for all three of them so we are future-proof (in case sha256 may become deprecated).

`integrity`/`crossorigin` only make sense on single-file resources — an `imagesrcset` preload covering multiple format variants has no single file to hash, so it omits integrity.

```html
<link rel="stylesheet" href="/assets/css/app.css"
      integrity="sha256-... sha384-... sha512-...">
<script src="/assets/js/app.js"
        integrity="sha256-... sha384-... sha512-..."
        crossorigin="anonymous"></script>
```

## No inline event handlers — bind from an external script
No `onclick`, `onload`, or any `on*` attribute in markup. Behavior is bound in the page's external `.js` file, via `addEventListener` registered from that file's guarded `_init` function, with elements selected via `data-*` attributes rather than repurposed classes/IDs. See `references/javascript.md` for the required boilerplate and binding style.

this is a direct implication from the STRIDE principle - we protect our users by securing our page using CSP and other security headers.

```html
<!-- Wrong -->
<button onclick="deleteBox(42)">Delete</button>

<!-- Preferred -->
<button data-action="delete-box" data-box-id="42">Delete</button>
```

```javascript
// bound in the page's JS file, from <prefix>_init():
document.querySelectorAll('[data-action="delete-box"]').forEach(function (button) {
    button.addEventListener('click', handleDeleteBox);
});
```

## `<head>` element order (fixed)
1. `<meta charset>`
2. `<title>`
3. `<meta viewport>`
4. Preloads (resource hints)
5. `async` `<script>`
6. `defer` `<script>`
7. Other head content
8. CSS `<link rel="stylesheet">` — **last**, since it's render-blocking

Scripts precede CSS so the parser doesn't wait on blocking CSS before it can start fetching scripts; preloads sit earlier still, so CSS-referenced resources aren't discovered only after CSS itself loads.

## Preload strategy by asset type
- **Fonts** → HTTP `Link:` header (not a tag — needs discovery before HTML parsing starts).
- **JS/CSS** → `<link rel="preload">` in `<head>`.
- **Images** → one `<link rel="preload" as="image" imagesrcset="..." imagesizes="..." type="...">` **per offered format**, so the browser preloads only the format it supports. There's no privileged "main" image — every displayed image is responsive (`<img srcset>`/`<picture>`) and preloaded the same way.
- **Always set `fetchpriority`** on every preload, header or tag: async JS = `high`, defer JS = `low`, CSS = `low` (the blocking stylesheet link already promotes it), fonts = `high`, images = `auto` (overridable per image).

## Fonts
System fonts preferred (`-apple-system`, `BlinkMacSystemFont`, `'Segoe UI'`, …) — avoid a web-font fetch entirely where possible. If one is unavoidable, preload it via an HTTP header:

```
Link: </assets/fonts/x.woff2>; rel=preload; as=font; type=font/woff2; crossorigin; fetchpriority=high; integrity="sha384-..."
```

## Escaping
`htmlspecialchars($var, ENT_QUOTES, 'UTF-8')` on every user-input string rendered into HTML — no exceptions. This is the output-encoding half of `SKILL.md` rule 3; see `references/php.md`'s templating section for the full pattern.

A value safe as element *content* is not automatically safe inside a `<script>` block or an unquoted attribute — those have different escaping requirements. To get a server-side value into client-side JS, pass it via a `data-*` attribute and read it with `dataset`:

```php
<!-- Wrong — htmlspecialchars alone doesn't protect a script context against
     a value like `</script><script>evil()</script>` -->
<script>const boxId = "<?= $boxId ?>";</script>

<!-- Preferred -->
<div id="box" data-box-id="<?= htmlspecialchars($boxId, ENT_QUOTES, 'UTF-8') ?>"></div>
```

## `rel="noopener noreferrer"` on `target="_blank"` links
Prevents the opened page from getting a reference back to `window.opener`. This may be obsolete on modern browsers, but we still include it for compatibility.

## Semantic HTML over generic `<div>`/`<span>` where an equivalent exists
`<nav>`, `<button>`, `<label for="...">`, `<table>` for tabular data. Not a hard rule where no semantic element fits — don't force one.

## Forms: server-side validation is the boundary; client-side is UX only
A `required`/`pattern` attribute or a client-side JS check improves the experience but is not a security control — it's trivially bypassed by sending the request directly. Every submission gets the same server-side fail-fast validation (`SKILL.md` rule 5) regardless of what client-side checks exist.

## Attribution is honored, not engineered around
A CC-BY (or other attribution-required) asset is never redrawn or recreated purely to sidestep the attribution requirement. The license is honored in-page — e.g. a footer credit.
