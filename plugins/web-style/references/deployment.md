# Deployment: Docker for PHP/JS Apps

Read this after `SKILL.md`'s cross-cutting rules.

## Base images
Hardened base images, not default/upstream — `dhi.io/*` for PHP, and hardened or `*-alpine` variants for PostgreSQL/nginx/utility containers. **Pin by digest**, not just tag: `image:tag@sha256:...`. Make image references configurable via `.env` (`PHP_BUILD_IMAGE`, `PHP_RUNTIME_IMAGE`, `POSTGRES_IMAGE`, `NGINX_IMAGE`) so a digest bump happens in one place.

## Multi-stage builds
A build stage installs headers and compiles anything native; the runtime stage receives only compiled artifacts and application code — no compiler toolchain, no build dependencies, no PECL. See `references/php.md`'s extensions section for the full worked example, including the shared-library-vs-headers distinction that's easy to get wrong.

## Numeric UID/GID, not names
```dockerfile
ARG PHP_UID=33
ARG PHP_GID=33
RUN groupadd -g ${PHP_GID} app \
 && useradd -u ${PHP_UID} -g ${PHP_GID} -s /sbin/nologin app
COPY --chown=${PHP_UID}:${PHP_GID} ./app /app
USER ${PHP_UID}:${PHP_GID}
```
Numeric IDs are easier to `chown` against from outside the container and more portable across images than named users. Configurable via `.env` (`PHP_UID`, `PHP_GID`).

## Configuration: bind-mount, don't `COPY`
Bind-mount config files/directories from outside the image via Compose volumes rather than `COPY`-ing them in. Keeps the image generic and the config editable without a rebuild.

## No autoloaders in the image
All classes load via explicit `require_once` — no PSR-4 autoloader shipped or enabled at runtime (`references/php.md`).

## Network segmentation
Networks segmented by least-connectivity, not one flat network:
- `edge` — nginx ↔ PHP (published to host; PHP's outbound access lives here if it needs any).
- `db` — PHP ↔ PostgreSQL, `internal: true` (no gateway out).
- `render` (or another per-purpose network) — PHP ↔ an internal-only worker/rendering service, also `internal: true`.

`driver: bridge` is Compose's default — an explicit `driver: bridge` line helps clarify that the default is in use.

## Isolation sidecars for high-risk ingest work
Processing that is both high-risk and high-exposure — image/document conversion on ingest being the canonical case — runs in its own container, not in PHP-FPM (`references/php.md`). The container's job is to make an exploit worthless:

- On an `internal: true` network only — no egress, no route to the DB network.
- No DB credentials, no session store, no secrets in its environment.
- `read_only: true` with a `tmpfs` scratch dir sized for the job.
- Non-root numeric UID/GID, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`.
- Bounded: memory and CPU limits set, so a decompression bomb starves the sidecar rather than the host.

The PHP side hands over bytes and gets bytes back — the sidecar never receives anything that would be worth stealing.

## Read-only filesystems everywhere
Every service — not just PHP-FPM — runs `read_only: true` with `tmpfs` for whatever paths it must write (`/tmp`, `/run`, `/var/run`, `/var/run/postgresql`, session storage):

```yaml
postgres:
  read_only: true
  tmpfs:
    - /tmp
    - /run
    - /var/run/postgresql
```

Immutable image + minimal writable surface = harder to compromise even when a process is exploited.

## Healthchecks
Every service gets one — interval 10s, timeout 2s, retries 3:
- **PHP:** `curl http://localhost/healthz`, or a dedicated `healthcheck.php`.
- **PostgreSQL:** `pg_isready -U <user> -d <db>`.
- **nginx:** `curl http://localhost/healthz` (an internal-only endpoint).
- **A minimal container without a shell or curl:** check whether the image offers a native CLI healthcheck flag; if it doesn't, add an Alpine sidecar that performs the check and exposes a readiness signal other services can depend on (`depends_on` with a `service_healthy` condition).

A high-level healthcheck beats a liveness ping: request an endpoint that exercises the real path and validate the response body (e.g. a known UUID echoed back in JSON), not just a 200 status.

## Pull policy
Explicit `pull_policy: always` on every service that uses a public image — a rebuild then actually picks up fresh images rather than silently reusing a stale local one.
Explicit `pull_policy: build` on every service that uses image build within that docker stack.

## nginx
**Rate limiting**, grouped by path prefix so high-value endpoints (login, register) share one rule.

Example:
```nginx
location ^~ /rate_limitted/ {
    limit_req zone=api burst=10 nodelay;
    fastcgi_pass php:9000;
}
```

**Deny rules** for anything internal — class/bootstrap directories, templates, hidden files:
```nginx
location ^~ /_private/ { deny all; return 403; }
location ~ ^/(lib|templates|_private)/ { deny all; }
location ~ /\.(?!well-known) { deny all; }
```

**Caching** — the proxy is a protection layer, not just a speed-up (`references/php.md`). Honor and serve validators so repeat traffic resolves to 304s instead of DB queries, and keep user-scoped responses out of any shared cache.
Check for edgecases such as dynamic content/auth/cookies.
PHP still decides what's cacheable per route — the proxy enforces it, it doesn't invent it.

**Per-location routing, explicit, not a catch-all**

Example:
```nginx
location /api/ { ... }
location ~ \.php$ { ... }
location / { try_files $uri $uri/ /index.php$is_args$args; }
```

## Makefile
create Makefiles instead of instructing user to do stuff or to run commands manually.
Examples:
- `make secrets` — creates `.env` from `config/env.example` if missing; fills **only placeholder values** (`change-me*`, an all-zero UUID) with random values (hex passwords, real UUIDs). Safe to re-run; never overwrites an already-set value.
- `make deps` — fetches pinned frontend dependencies (`references/html-css.md`).
- `make sri` — computes SRI hashes for vendored assets.
- `make build` / `make up` / `make down` / `make migrate` / `make psql` — lifecycle targets.

## Secrets
Never bake credentials into image layers — `.env` (excluded from the build context, generated via `make secrets`) or Docker secrets.
