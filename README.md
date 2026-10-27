# Memorybook

Memorybook public website frontend.

## Run locally in 5 steps

1. Install PostgreSQL natively (no Docker). Create a `memorybook` role and database using the instructions below.
2. Create the backend virtual environment, install its development dependencies, copy `backend\.env.example` to `backend\.env`, and fill in the local database password and two unique signing keys.
3. Install frontend dependencies with `npm install` in `frontend`.
4. Run `scripts\dev.ps1` on Windows or `bash scripts/dev.sh` on Linux/macOS. The script checks config/database access, upgrades migrations, seeds the repeatable demo catalog, provisions the local administrator, then starts Flask and Vite.
5. Open `http://127.0.0.1:5173`, test `http://127.0.0.1:5000/api/v1/health/live`, and sign in with the administrator provisioned by the script. The verification code is available with `flask --app wsgi dev-mailbox --email you@example.com`.

Create a production bundle with `npm run build` from `frontend`.

## Public website scope

The homepage includes featured catalog filters, book preview dialogs, four
how-it-works steps, an editor preview, digital and print information, book
tiers, featured categories, FAQs, and responsive navigation. The public site
also includes catalog discovery, category browsing and category detail pages,
collection browsing and collection detail pages, pricing information, and an
FAQ page. Discovery filters and pagination are reflected in URL query
parameters; mobile filters use a drawer.

Catalog products, categories, collections, and templates are loaded from the
versioned Flask API when it is configured. Public catalog queries return only
published records. The frontend keeps discovery filters in the URL and uses
backend pagination and filtering. A populated catalog is required for products
to appear.

The design currently uses Google Fonts and Unsplash-hosted photography.

## Flask backend

The backend uses Python 3.11+, Flask, and PostgreSQL installed directly on the
machine. Docker, Redis, and Celery are not required for local development.
PostgreSQL remains the system of record. The default rate limiter uses
in-memory storage, and background PDF, event-email, and daily expired-auth
cleanup work uses a database-tracked `ThreadPoolExecutor` runner.

### Install PostgreSQL natively

- **Windows:** Install PostgreSQL with the official Windows installer. Keep the
  PostgreSQL service running (for example, `postgresql-x64-18`) and use pgAdmin
  or SQL Shell (`psql`) to create a login role and database. In pgAdmin's Query
  Tool, connected as the install-time administrator, run:

  ```sql
  CREATE ROLE memorybook LOGIN PASSWORD 'SET_A_LOCAL_PASSWORD';
  CREATE DATABASE memorybook OWNER memorybook;
  ```

  Or use `psql -U postgres -h 127.0.0.1` and run the same SQL statements.
- **Linux (Debian/Ubuntu):** install the distribution PostgreSQL package, start
  the service, then run `sudo -u postgres createuser --pwprompt memorybook` and
  `sudo -u postgres createdb --owner=memorybook memorybook`.
- **macOS:** install with Homebrew (`brew install postgresql@16`), start the
  service (`brew services start postgresql@16`), then run
  `createuser --pwprompt memorybook` and
  `createdb --owner=memorybook memorybook`.

Use your chosen role password only in the ignored local `.env` file. Do not put
it in shell history, source code, or documentation.

### Backend setup

```powershell
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `backend/.env`: use the PostgreSQL URL format
`postgresql+psycopg://memorybook:CHANGE_ME@127.0.0.1:5432/memorybook`, replace
`CHANGE_ME` with the local role password, and set distinct signing keys. Generate
keys with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The
example already selects file-based development email, PKR, in-memory rate
limiting, the Vite origin, and in-process background jobs. Its signing-key
values are placeholders and must be replaced before using the app.

Install frontend dependencies once:

```powershell
Set-Location ..\frontend
npm install
```

The Vite proxy forwards `/api/*` to `http://127.0.0.1:5000`; the frontend API
base defaults to `/api/v1`, so no CORS override or frontend `.env` is needed.
`GET http://127.0.0.1:5000/api/v1/health/live` is the local API health check.

### Start the complete local stack

From the repository root, run `scripts\dev.ps1` on Windows or
`bash scripts/dev.sh` on Linux/macOS. The scripts verify configuration and the
PostgreSQL connection, run `flask db upgrade`, run the repeatable guarded demo
seed, prompt to create or promote the local administrator, then start Flask on
port 5000 and Vite on port 5173. Stop Vite with Ctrl+C; the scripts stop the API
process as well. The first seed writes demo catalog data to the configured
loopback database, so use only a dedicated local development database.

For manual startup, from `backend/` run `flask --app wsgi config-check`,
`flask --app wsgi db-check`, `flask --app wsgi db upgrade`, then
`python run.py`. In another terminal run `npm run dev -- --host 127.0.0.1`
from `frontend/`. Use `flask --app wsgi retry-failed-jobs` to requeue failed
in-process jobs; PDF jobs can also be requested again from their existing API.

### PostgreSQL troubleshooting

- **Port in use:** confirm PostgreSQL is listening on 5432 and the API on 5000;
  Vite uses 5173. Stop the conflicting local process or configure Vite's port.
- **Wrong password / connection refused:** check that PostgreSQL is running, the
  role and database exist, and the ignored `backend/.env` URL matches them.
  `flask --app wsgi db-check` verifies access without printing credentials.
- **Migration errors:** confirm the connection targets the intended empty or
  development database, then inspect the Alembic error and current revision
  with `flask --app wsgi db current` and `flask --app wsgi db heads`. Do not
  delete or reset an existing database to resolve a migration failure.
- **No books appear:** check that the demo seed completed and query the public
  catalog after the API health endpoint responds.
- **Admin redirects to unauthorized:** create/promote the administrator with
  `flask --app wsgi dev-provision-admin --email you@example.com` for a local
  development account, or `flask --app wsgi grant-admin you@example.com` for
  an existing account. In development, read a new account's verification code
  using `flask --app wsgi dev-mailbox --email you@example.com`, verify the
  email, and sign in again so the frontend receives the admin role.
- **SMTP mail not delivered:** inspect the server log for the SMTP exception.
  For port 587 set `SMTP_USE_TLS=true` and `SMTP_USE_SSL=false`; for port 465
  set `SMTP_USE_TLS=false` and `SMTP_USE_SSL=true`. Confirm the sender address
  is permitted by the provider and outbound SMTP is not blocked by the host or
  network. Never enable both TLS modes.

Celery is an optional alternate job backend only. To use it, install the
`celery` extra, configure `BACKGROUND_JOB_BACKEND=celery` plus a reachable
`CELERY_BROKER_URL`, and run a Celery worker. Redis is only needed if Redis is
chosen for Celery or `RATE_LIMIT_STORAGE_URI`; neither is part of the default
local setup. Authentication verification/reset emails are delivered directly
because their one-time codes and reset tokens are intentionally not persisted
in the background-job queue.

### Backend architecture

`backend/memorybook/` uses the Flask application factory and separates API
blueprints, SQLAlchemy models, schemas, repositories, services, permissions,
integrations, and background tasks (with optional Celery integration). Alembic/Flask-Migrate revisions are stored in
`backend/migrations/`; do not use `db.create_all()` to provision a deployment.

The normalized schema groups account, catalog, project, pricing, PDF/print
order, payment, notification, and support data into relational tables with
foreign keys, indexes, uniqueness and amount constraints. Currency amounts use
`NUMERIC(12, 2)`. Purchased orders retain a price and address snapshot and
reference an immutable project revision. Project images and generated documents
are represented by object-storage keys and metadata; binaries are not stored in
PostgreSQL. PostgreSQL blocks updates and deletes to project revisions.

### Pricing policy

The catalog and pricing endpoints use `PAYMENT_DEFAULT_CURRENCY` (PKR by
default). Admin price records must use that currency. The server computes PDF
prices, print base prices, extra-page charges, discounts, and shipping; browser
totals are never accepted as checkout authority. Print checkout consumes a
short-lived server quote snapshot. The editor uses
`GET /api/v1/projects/<project_id>/pricing-quote?pageCount=<count>` for a
current PDF price and print estimate before shipping.

The current server plan ceilings are Basic 80 pages, Medium 120 pages, and
Premium 200 pages. Products may set lower limits. Print products can also
require even page counts, and product metadata may explicitly restrict cover
finishes by plan.

The catalog APIs expose only active, non-deleted products, categories,
collections, and templates. The project APIs require an authenticated session,
scope every read and write to its owner, and use the current project version in
the `If-Match` header for mutations. A stale project version receives `409
CONFLICT`; clients should reload and reconcile rather than overwrite newer
work. Project documents are validated, normalized into project/page/element
records, and can be saved as immutable revisions and restored later.

Project photos and unpublished admin-design images use private storage;
PostgreSQL stores only object keys, metadata, and checksums. S3-compatible
storage is configured with `ASSET_S3_*`; filesystem storage uses
`ASSET_LOCAL_DIRECTORY`, which must be outside the application tree in
production and must never be exposed directly by nginx. Use S3 for multiple
application hosts. Credentials are read from the environment or the configured
AWS credential provider, never from source control. Uploads accept decoded
JPEG, PNG, and WebP images up to 15 MB and reject images above 40 megapixels.
Private editor URLs are short-lived and require an authorized session when
retrieved. Catalog images use stable API URLs and are publicly readable. Set
`PUBLIC_API_URL` when clients need absolute asset URLs.
User-facing records with history are protected by restrictive foreign keys or
soft deletion rather than destructive cascading deletes.

Authentication routes under `/api/v1/auth/` support registration, email OTP
verification/resend, login/logout, refresh-token rotation, password reset,
current-user/profile updates, and password changes. Access and refresh JWTs
are stored in HttpOnly cookies with CSRF protection; production cookies require
HTTPS. Login requires a verified email. Set `AUTH_EMAIL_MODE=file` in the
development backend process to use the local CLI-only email mailbox when SMTP
is unavailable; use SMTP in production. Password-reset responses are
intentionally identical for existing and unknown email addresses.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `FLASK_ENV` | `development`, `testing`, or `production`. |
| `SECRET_KEY` | Flask signing secret; use a unique secret outside tests. |
| `JWT_SECRET_KEY` | JWT signing secret; use a different unique secret. |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL using the `psycopg` driver. |
| `BACKGROUND_JOB_BACKEND` | `inprocess` (default) or optional `celery`. |
| `BACKGROUND_JOB_WORKERS` | In-process worker thread count (default `2`). |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Optional Celery connection settings; no effect on the default backend. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins. |
| `RATE_LIMIT_STORAGE_URI` | Flask-Limiter storage; defaults to `memory://`; set a Redis URL to opt into Redis. |
| `ASSET_STORAGE_BACKEND` | Private `filesystem` or `s3`; production filesystem storage must live outside the code directory. |
| `ASSET_LOCAL_DIRECTORY` | Persistent filesystem asset root; production default example is `/var/lib/memorybook/assets`. |
| `LOG_LEVEL` | Structured application log threshold. |
| `TRUSTED_PROXY_HOPS` | Number of controlled reverse proxies that overwrite forwarded headers; default `0`. |
| `JWT_ACCESS_TOKEN_MINUTES` | Access-token lifetime. |
| `JWT_REFRESH_TOKEN_DAYS` | Refresh-token lifetime. |
| `JWT_COOKIE_SECURE` | Require HTTPS for auth cookies; always enabled in production. |
| `JWT_COOKIE_SAMESITE` | SameSite policy for auth cookies. |
| `JWT_COOKIE_DOMAIN` | Optional shared cookie domain when the frontend and API use sibling subdomains. |
| `AUTH_OTP_TTL_MINUTES` | Email verification code lifetime. |
| `AUTH_RESET_TTL_MINUTES` | Password-reset link lifetime. |
| `AUTH_EMAIL_MODE` | `smtp` for normal mail delivery; `file` enables the CLI-only mailbox in development. |
| `PUBLIC_APP_URL` | Frontend origin used to compose password-reset links. |
| `PUBLIC_API_URL` | API origin used to create absolute service links. |
| `PAYMENT_DEFAULT_CURRENCY` | Currency policy for payment checkout (default `PKR`). |
| `PAYMENT_PRIMARY_GATEWAY` | Preferred gateway (`manual` by default); manual transfer is always available for PKR. |
| `MANUAL_BANK_NAME`, `MANUAL_BANK_ACCOUNT_TITLE`, `MANUAL_BANK_ACCOUNT_NUMBER`, `MANUAL_JAZZCASH_NUMBER`, `MANUAL_EASYPAISA_NUMBER` | Shop-owned transfer destinations shown during manual checkout. Configure before accepting customer payments. |
| `STRIPE_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Explicit Stripe enablement and server-only API/webhook secrets. Do not expose either secret to Vite. |
| `PAYFAST_ENABLED`, `PAYFAST_MODE`, `PAYFAST_MERCHANT_ID`, `PAYFAST_MERCHANT_SECRET`, `PAYFAST_API_BASE_URL`, `PAYFAST_CONTRACT_VERIFIED`, `PAYFAST_PAYMENT_METHODS` | Illustrative disabled-by-default PayFast settings; no adapter is active until merchant-specific checkout/callback details are verified and implemented. |
| `JAZZCASH_ENABLED`, `JAZZCASH_MODE`, `JAZZCASH_CHECKOUT_CONTRACT_VERIFIED`, `JAZZCASH_CALLBACK_CONTRACT_VERIFIED`, `JAZZCASH_API_URL`, `JAZZCASH_MERCHANT_ID`, `JAZZCASH_PASSWORD`, `JAZZCASH_INTEGRITY_SALT`, `JAZZCASH_PAYMENT_METHODS` | Merchant-specific configuration only; JazzCash is not advertised because server-side status inquiry is not implemented. |
| `EASYPAISA_ENABLED`, `EASYPAISA_MODE`, `EASYPAISA_STORE_ID`, `EASYPAISA_MERCHANT_SECRET` | Reserved configuration examples only; no Easypaisa adapter exists. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`, `SMTP_USE_SSL` | Outbound mail configuration for environments using SMTP. Port 587 normally uses STARTTLS; port 465 uses implicit SSL. Enable one mode only. |

When using the development mailbox, run
`flask --app wsgi dev-mailbox --email user@example.test` to view a test message.
This command is local-only and never creates an HTTP inbox. Reset the dedicated
test-account password interactively, without echoing it, with
`flask --app wsgi dev-reset-test-password user1.test@memorybook.local`.

### API versioning and frontend compatibility

New endpoints use `/api/v1/`. Health endpoints are
`GET /api/v1/health/live` and `GET /api/v1/health/ready`. The backend includes
JWT register/login/refresh/current-user endpoints under `/api/v1/auth/`, public
catalog endpoints under `/api/v1/books`, `/api/v1/categories`,
`/api/v1/collections`, and `/api/v1/templates`, and owner-scoped project,
page, asset, and revision endpoints under `/api/v1/projects`.

The frontend uses cookie credentials with CSRF headers for private requests.
Catalog and project services now consume the versioned APIs; browser local
storage is retained only for editor recovery copies. The existing frontend
`/api/print/*` and `/api/pdf/*` paths remain mounted as compatibility routes.
PDF and print checkout uses server-calculated prices and selected methods from
`GET /api/v1/payments/methods?currency=PKR`. Manual bank transfer, JazzCash, and
Easypaisa instructions are the default; customers submit the transaction
reference at `/api/v1/payments/{paymentId}/manual-confirmation`, and an admin
must approve it in Admin → Payments before the order becomes paid. Configure
the `MANUAL_*` destinations above; blank destinations instruct customers to
contact support. Stripe remains optional (`STRIPE_ENABLED=true`) and requires
server-side secret and webhook credentials. PayFast, JazzCash API checkout,
and Easypaisa API checkout remain unavailable until their merchant contracts
are implemented and verified. Print production advances through
payment-confirmed → processing → printed → shipped (tracking required) →
delivered; every transition is recorded and notifies the customer.

For an existing paid PDF order, the authenticated
owner can request `POST /api/v1/pdf/orders/{id}/generate` with
`{"profile":"digital"}`; print-profile generation is allowed only when the
server-side order price snapshot includes that profile. Generation is queued to the selected background-job backend and reported by `GET /api/v1/pdf/jobs/{jobId}` or the order endpoint.
Only an order with a server-confirmed `paid_at` timestamp can be rendered.
Failed jobs can be retried by requesting generation again. Downloads are
available through owner-scoped entitlements at `GET /api/v1/pdf/downloads` and
`GET /api/v1/pdf/downloads/{downloadId}`; the latter returns a short-lived
signed object-storage URL and records the download.

The PDF renderer reads the immutable project revision referenced by the order,
not the current mutable project. It follows saved page order and normalized
coordinates, renders text, shapes, cropped photos, backgrounds and cover faces,
and parses/validates the produced PDF before storing it. Digital PDFs contain
front cover, interior pages, and back cover. Print PDFs contain a single
back-spine-front spread followed by interior pages, include bleed/trim boxes,
enforce the configured image-DPI threshold, and reject text outside the saved
safe margin. Print spine width uses the saved book/order specification when
available and otherwise uses an estimate from page count. Configured font files
must be licensed for embedding; without those files the renderer uses standard
PDF fonts.

Generated documents are stored in the configured private S3-compatible bucket
under the `generated/pdf/` prefix; the bucket must not allow public access.
The optional Celery backend uses its configured broker. The renderer supports JPEG, PNG,
and WebP image assets; an unsupported/corrupt image or inadequate print
resolution fails the job with a retryable status only when the failure is
transient.

### Admin management

The admin workspace is available at `/admin`. Every `/api/v1/admin/*` endpoint
requires an authenticated account with the `admin` role; a signed-in customer
receives `403`. Grant access to a known account from an authorized backend
operator shell:

```powershell
flask --app wsgi grant-admin admin@example.com
```

The command is idempotent and grants a role to an existing account only. Ask
the administrator to sign out and back in to refresh the frontend role data.
Use the development-only provision command to create or promote an account and
send its email-verification code through the local mailbox:

```powershell
flask --app wsgi dev-provision-admin
flask --app wsgi dev-mailbox --email you@example.com
```

The provision command prompts for the administrator email and, for a new
account, an initial password. `--email you@example.com` may be supplied to skip
the email prompt.

The auth pages cover registration, OTP verification/resend, login, and
password reset. The API client sends cookie credentials and CSRF headers,
attempts one refresh after an expired access token, retries the original
request once, and returns to login if refresh fails. Password-reset requests
use the same response for existing and unknown addresses to avoid exposing
which email addresses have accounts.

On first creation, enter and confirm the initial password at the hidden prompt;
it is hashed with the normal registration password utility and is never printed.
The command uses normal account registration and sends a verification code to
the development mailbox. Complete email verification at `/verify-otp` in the
frontend, then sign in at `/login` and open `/admin`. If the account already
exists, the command only ensures its `admin` role; it does not change its
password or bypass email verification. Re-running the command is safe.

The admin APIs provide dashboard/report metrics, user status management,
product/category/collection/template management, pricing and shipping
configuration, order/payment/refund views, support responses, platform
settings, audit history, and transactional email.

New book products and templates are drafts until published. Public catalog
queries continue to filter on active/published state. Template publication
requires at least one page with an editable placeholder. Updating a published
template saves its prior document as an immutable version; projects record the
template version used at creation and keep their own project document. Admin
order lists redact project revision documents for private projects; non-private
order behavior is preserved. Private photos are available through a separately
audited flow only for paid print orders in production.
Payment state is read-only in admin and must be verified by the configured
payment provider; the dashboard does not mark payments successful. Customer
refund requests require admin review; refunds without an implemented automated
provider contract require manual processing and verified provider confirmation.

Order, payment, cancellation, and support-ticket model events create admin
notifications and queued email-log entries. The background-job runner sends those event emails through the configured SMTP service. The admin email form sends
transactional messages immediately and requires SMTP configuration.

### Customer photo privacy and retention

Customers can enable **Full privacy** in Dashboard Settings. It is off by
default to preserve existing account behavior. A project can inherit the account
setting or explicitly choose Private or Standard in the project list. Project
pages and uploaded photos remain owner-authenticated; they are not exposed in
public catalog or shared listings.

Opening the private photo list and each individual photo is recorded in
`admin_activity_logs`. Administrators can view those photos only when the print
order is paid and `in_production`.

The cleanup command removes original project uploads for delivered print orders
after 30 days by default. Set `PROJECT_UPLOAD_RETENTION_DAYS` to change the
retention period, then schedule this command with Windows Task Scheduler or cron:

```powershell
flask --app wsgi cleanup-delivered-uploads
```

Use `--days N` to override the configured period for a one-time run. Cleanup
does not delete project records or shared catalog assets. Removed photos remain
as unavailable references in the saved project and cannot be downloaded again.

### Tests

```powershell
Set-Location backend
pytest

Set-Location ..\frontend
npm test
node --test src\services\paymentMethodService.test.js
npm run build
```

Tests use isolated SQLite databases; run `flask --app wsgi db-check` and
`flask --app wsgi db upgrade` with your configured PostgreSQL service to validate
the real database connection and migration. Production configuration,
backups, deployment commands, rollback guidance, and acceptance gates are in
[backend/DEPLOYMENT.md](backend/DEPLOYMENT.md). For a single Linux VPS, use
[docs/DEPLOYMENT_LINUX_VPS.md](docs/DEPLOYMENT_LINUX_VPS.md); the production
environment template is [backend/.env.production.example](backend/.env.production.example).
Run the end-to-end checks in [docs/FINAL_QA_CHECKLIST.md](docs/FINAL_QA_CHECKLIST.md)
before accepting traffic or payments.
Provider contract findings are in [backend/PAYMENT_GATEWAYS.md](backend/PAYMENT_GATEWAYS.md).

### Deployment readiness

The deployment checklist tracks which local browser steps have been exercised
and which release gates still require production-like services. Unit and
contract tests do not substitute for real PostgreSQL migration/restore,
authenticated browser journeys, SMTP delivery, private storage, payment
provider sandbox transactions, or operational rollback drills. Production
readiness remains **BLOCKED** until the acceptance gates in the deployment
runbook pass.
