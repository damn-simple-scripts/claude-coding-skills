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

final class Redirect
{
    public static function to(string $url, int $status = 302): void
    {
        http_response_code($status);
        header('Location: ' . $url);

        $safeUrl = htmlspecialchars($url, ENT_QUOTES, 'UTF-8');
        // Target URL travels via data-redirect-url, not interpolated into a
        // <script> body — see references/html-css.md's "Escaping" section
        // and examples/js/redirect.js.
        ?>
<!doctype html>
<html data-redirect-url="<?= $safeUrl ?>">
<head>
    <meta charset="utf-8">
    <title>Redirecting…</title>
    <meta http-equiv="refresh" content="0; url=<?= $safeUrl ?>">
    <script src="/assets/js/redirect.js" async
            integrity="sha256-... sha384-... sha512-..."
            crossorigin="anonymous"></script>
</head>
<body>
    <p>Redirecting to <a href="<?= $safeUrl ?>"><?= $safeUrl ?></a>…</p>
</body>
</html>
        <?php
        exit;
    }
}
