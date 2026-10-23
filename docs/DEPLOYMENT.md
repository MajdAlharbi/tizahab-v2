# Deployment configuration

## Render portfolio demo

`render.yaml` creates a separate Docker web service and PostgreSQL 18 database,
both explicitly on the Free compute plan. Import it as a new Blueprint from
`main`; do not attach the original graduation project's services or database.
Review Render's resource preview before applying it. Supply a private
`DJANGO_SECRET_KEY` of at least 50 securely generated characters when prompted.
Render injects the new database's internal URL and the service's actual public
hostname/origin; no credentials belong in this file or in Git.

The existing container entrypoint runs migrations, collects WhiteNoise static
files and binds Gunicorn to port 8000, matching the Blueprint's `PORT`. A fresh
database receives the bundled catalog through migrations. Additional startup
imports are disabled. The database requires TLS and blocks public connections.
Render terminates HTTPS; Django trusts its forwarded protocol and retains secure
cookies, host validation and HSTS. Automatic service deploys wait for CI checks.

Email delivery is deliberately disabled with Django's dummy backend, so password
reset emails are not sent or logged. OAuth, Redis, monitoring and provider sync
remain unconfigured/disabled. Destination discovery and trip planning use the
local catalog independently of external providers.

Render Free is suitable for a temporary demo, not durable production hosting:
the web service sleeps after 15 minutes idle; its filesystem is ephemeral; the
free database has 1 GB storage, expires after 30 days and has no managed backups.
Record the actual expiration shown in the dashboard. Export any wanted data
before expiration and obtain approval before a paid upgrade. Workspace build
minutes, bandwidth and free service hours are shared; review remaining usage and
potential overages before deploying. See [Render's current Free limits](https://render.com/docs/free).

Verify the public HTTPS URL, registration, authenticated saves, bilingual pages
and static assets after deployment. A successful image build alone is not a
verified deployment. Free services do not provide a shell: provision any future
administrator through a separately authorized secure process, never a hardcoded
account or public setup endpoint.

## Self-hosted Docker Compose

The Compose stack runs Django, Nginx, PostgreSQL and Redis behind an
**HTTPS-terminating reverse proxy on the host**. Provide and validate this trusted
TLS edge before exposing the application publicly.

## Traffic and trust

Browser HTTPS → trusted host TLS proxy → `127.0.0.1:8080` → Nginx → Gunicorn.

- The TLS proxy must preserve the public `Host`, overwrite `X-Forwarded-Proto`
  with `https`, and redirect public HTTP to HTTPS.
- Nginx's HTTP listener is published on loopback only. Do not expose it publicly:
  forwarded-protocol headers are trusted on this private hop.
- Django requires configured allowed hosts, redirects non-secure requests, and
  retains secure session/CSRF cookies and HSTS. Requests arriving from the trusted
  HTTPS proxy do not enter a redirect loop.
- PostgreSQL, Redis and Gunicorn have no published host ports.

## Required private configuration

Set these variables in an untracked environment file or deployment secret store:

- `DJANGO_SECRET_KEY`: a generated strong secret.
- `DB_PASSWORD`: a strong database password; Compose refuses an empty value.
- `DJANGO_ALLOWED_HOSTS`: exact public hostnames, comma separated, without schemes.
- `CSRF_TRUSTED_ORIGINS`: corresponding HTTPS origins, including a nonstandard
  public port if used. Production rejects HTTP origins.

The example file is for local development. Replace its localhost values with the
actual public host/origin when preparing a deployment. Optional SMTP, OAuth and
Sentry settings require their own deliberate configuration.

Compose passes database credentials as separate `DB_*` variables, so punctuation
in passwords is not misinterpreted as a database URL. Its PostgreSQL service is
private to the Docker network and uses `DB_SSL_REQUIRE=False`. Standalone
production PostgreSQL URLs and `DB_*` configurations default to TLS; keep that
requirement for external databases.

Redis uses Django's built-in backend and the declared `redis` client dependency.
The container health check uses Python's standard library against the existing
login page with the same trusted HTTPS header, without depending on `curl`.
Shell entrypoints are kept in LF format for Linux images.

## Startup

The entrypoint runs migrations and `collectstatic`, then starts Gunicorn as a
non-root user. Optional initial importing is controlled by
`DJANGO_LOAD_INITIAL_DATA`, disabled by default in Compose. Data migrations already
seed the bundled places on a fresh database.

The Compose image uses PostgreSQL 15. Before connecting existing data, check its
migration history, rehearse the upgrade with the actual target database version,
and retain a verified recoverable backup. Keep historical migrations in place;
bundled data imports are not backups.

After providing private configuration and the trusted TLS edge, rehearse locally
with `docker compose config` and `docker compose up --build`. Confirm
container health, HTTPS redirects, secure cookies and authenticated POST requests
before a public deployment.

## Before public launch

Before public launch, review the inherited catalog's missing source verification,
prices/hours and event schedules; provide appropriate privacy/contact policies and
working password-reset email delivery. Keep ingestion disabled until provider
credentials, Riyadh coverage, licensing and storage terms are approved. Test
backup restoration, the actual target database version, Docker health and TLS/CSRF
behavior in staging. Test settings and synthetic preview databases must never be
used as production configuration or imported as real content.
