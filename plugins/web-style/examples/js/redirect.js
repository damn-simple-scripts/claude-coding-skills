// Third and last-resort layer of the redirect pattern — see
// references/php.md's "Redirects" section and examples/php/redirect-response.php.
// Loaded via: <script src="/assets/js/redirect.js" async></script>
//
// By the time this fires (if it ever does), the Location header and/or the
// <meta http-equiv="refresh"> tag have almost always already navigated the
// client away — this only runs for a client that honored neither.
//
// Exempt from references/javascript.md's standard _<prefix>_loaded init
// boilerplate: that guard exists to make double dispatch (DOMContentLoaded
// listener + immediate readyState check) safe for scripts that bind
// persistent listeners or set up lasting state. This script does neither —
// it reads a URL once and navigates once. There is no state to protect
// against being entered twice, so the guard has nothing to guard.

const target = document.documentElement.dataset.redirectUrl;
if (target) {
    window.location.href = target;
}
