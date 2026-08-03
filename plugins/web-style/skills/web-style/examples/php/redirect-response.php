<?php
declare(strict_types=1);
// Requires PHP >= 8.0 — match (8.0), constructor promotion (n/a here)
//
// Referenced from references/php.md's "Redirects" section.
//
// Redirect::to() emits three redundant layers, in the order they actually
// fire for a real client:
//   1. Location header + explicit status code      (primary)
//   2. <meta http-equiv="refresh"> in the HTML body (no-JS fallback)
//   3. external async JS reading a data-* attribute (last-resort fallback)
//
// Layers 1 and 2 fire before layer 3's script has even finished loading in
// the overwhelming majority of requests — layer 3 exists only for a client
// that honors neither the Location header nor meta-refresh but does still
// execute deferred/async scripts.
//
// $url must be hardcoded/trusted (a literal, or a value from a fixed
// allow-list) — never raw user input. htmlspecialchars() below stops HTML
// injection, not an open redirect or a javascript: scheme. A user-supplied
// redirect target needs its own same-origin/allow-list validation before
// it ever reaches this function; that validation is out of scope here.

final class Redirect
{
    public static function to(string $url, int $status = 302): void
    {
        http_response_code($status);
        header('Location: ' . $url);

        $safeUrl = htmlspecialchars(string: $url, flags: ENT_QUOTES, encoding: 'UTF-8');
        // Target URL travels via data-redirect-url, not interpolated into a
        // <script> body — see references/html-css.md's "Escaping" section
        // and examples/js/redirect.js.
        ?>
<!doctype html>
<html data-redirect-url="<?= $safeUrl ?>">
<head>
    <!-- Head order per references/html-css.md: charset, title, viewport,
         preloads, async script, defer script, other head content, CSS last.
         No preloads, no defer script and no CSS on this page — the
         meta-refresh is "other head content" and sits after the script. -->
    <meta charset="utf-8">
    <title>Redirecting…</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="/assets/js/redirect.js" async
            integrity="sha256-... sha384-... sha512-..."
            crossorigin="anonymous"></script>
    <meta http-equiv="refresh" content="0; url=<?= $safeUrl ?>">
</head>
<body>
    <p>Redirecting to <a href="<?= $safeUrl ?>"><?= $safeUrl ?></a>…</p>
</body>
</html>
        <?php
        exit;
    }
}
