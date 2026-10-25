# Memorybook

Memorybook public website frontend.

## Run locally

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

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

The backend foundation lives in `backend/` and requires Python 3.11+, PostgreSQL,
and Redis. No database password or signing key is stored in source control.

```powershell
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit the ignored local `.env` file with your PostgreSQL connection string and
unique signing secrets. Keep credentials out of source files and commit history.
Use the password configured for your PostgreSQL role only in that local
environment file or an environment-variable manager. Do not put it in
`.env.example`, Python source, or documentation.
For example, use `postgresql+psycopg://postgres:<URL-ENCODED-PASSWORD>@localhost:5432/memorybook`.
Generate signing secrets with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set different values for `SECRET_KEY` and `JWT_SECRET_KEY`. The Flask CLI loads
`.env` locally through `python-dotenv`; `.env.example` contains placeholders only.
Create the `memorybook` PostgreSQL database and ensure the configured role can
connect before applying migrations:

```powershell
flask --app wsgi config-check
flask --app wsgi db-check
flask --app wsgi db upgrade
flask --app wsgi run --host 127.0.0.1 --port 5000
```

Run the Celery worker in another activated backend terminal:

```powershell
celery -A wsgi:celery worker --loglevel=INFO
```

### Local frontend and API integration

The frontend's centralized `VITE_API_BASE_URL` accepts either a backend origin
(for example `http://127.0.0.1:5000`) or an API base ending in `/api/v1`.
Without it, frontend requests use the Vite `/api` proxy to
`http://127.0.0.1:5000`, avoiding browser CORS during local development. To set
the API prefix explicitly in PowerShell:

```powershell
Set-Location frontend
$env:VITE_API_BASE_URL = "/api/v1"
npm run dev -- --host 127.0.0.1
```

The proxy target can be changed with `VITE_BACKEND_ORIGIN` before starting Vite.
For the directly configured backend URL, set `VITE_API_BASE_URL` to
`http://127.0.0.1:5000/api/v1`; do not add the prefix twice. `VITE_*` values
are public frontend configuration and must never contain credentials.

On Windows, start the installed PostgreSQL service from an elevated PowerShell
when it is stopped:

```powershell
Start-Service postgresql-x64-18
```

Redis is required for Celery-backed PDF jobs and queued notifications. A Redis
server was not available in the inspected local environment; do not start the
Celery worker until Redis is installed and reachable at the configured
`REDIS_URL` (the development default is `redis://localhost:6379/0`). The Flask
API and PostgreSQL-backed catalog/project endpoints can run independently.

### Backend architecture

`backend/memorybook/` uses the Flask application factory and separates API
blueprints, SQLAlchemy models, schemas, repositories, services, permissions,
integrations, and Celery tasks. Alembic/Flask-Migrate revisions are stored in
`backend/migrations/`; do not use `db.create_all()` to provision a deployment.

The normalized schema groups account, catalog, project, pricing, PDF/print
order, payment, notification, and support data into relational tables with
foreign keys, indexes, uniqueness and amount constraints. Currency amounts use
`NUMERIC(12, 2)`. Purchased orders retain a price and address snapshot and
reference an immutable project revision. Project images and generated documents
are represented by object-storage keys and metadata; binaries are not stored in
PostgreSQL. PostgreSQL blocks updates and deletes to project revisions.

The catalog APIs expose only active, non-deleted products, categories,
collections, and templates. The project APIs require an authenticated session,
scope every read and write to its owner, and use the current project version in
the `If-Match` header for mutations. A stale project version receives `409
CONFLICT`; clients should reload and reconcile rather than overwrite newer
work. Project documents are validated, normalized into project/page/element
records, and can be saved as immutable revisions and restored later.

Project photos and unpublished admin-design images use private object storage;
PostgreSQL stores only object keys, metadata, and checksums. S3-compatible
storage is configured with `ASSET_S3_*`; local filesystem storage is available
only in development and testing. Credentials are read from the environment or
the configured AWS credential provider, never from source control. Uploads
accept decoded JPEG, PNG, and WebP images up to 15 MB and reject images above
40 megapixels. Private editor URLs are short-lived and require an
authorized session when retrieved. Catalog images use stable API URLs and are
publicly readable. Set `PUBLIC_API_URL` when clients need absolute asset URLs.
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
| `REDIS_URL` | Redis broker and Celery result backend URL. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins. |
| `RATE_LIMIT_STORAGE_URI` | Flask-Limiter storage, normally Redis in production. |
| `LOG_LEVEL` | Structured application log threshold. |
| `TRUSTED_PROXY_HOPS` | Number of controlled reverse proxies that overwrite forwarded headers; default `0`. |
| `JWT_ACCESS_TOKEN_MINUTES` | Access-token lifetime. |
| `JWT_REFRESH_TOKEN_DAYS` | Refresh-token lifetime. |
| `JWT_COOKIE_SECURE` | Require HTTPS for auth cookies; always enabled in production. |
| `JWT_COOKIE_SAMESITE` | SameSite policy for auth cookies. |
| `JWT_COOKIE_DOMAIN` | Optional shared cookie domain when the frontend and API use sibling subdomains. |
| `AUTH_OTP_TTL_MINUTES` | Email verification code lifetime. |
| `AUTH_RESET_TTL_MINUTES` | Password-reset link lifetime. |
| `AUTH_EMAIL_MODE` | `smtp` for normal mail delivery; `file` enables the CLI-only mailbox in development and is rejected elsewhere. |
| `PUBLIC_APP_URL` | Frontend origin used to compose password-reset links. |
| `PUBLIC_API_URL` | Canonical HTTPS API origin used for absolute service links. |
| `PAYMENT_DEFAULT_CURRENCY` | Currency policy for payment checkout (default `PKR`). |
| `PAYMENT_PRIMARY_GATEWAY` | Preferred gateway identifier only; does not enable a provider. |
| `STRIPE_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Explicit Stripe enablement and server-only API/webhook secrets. Do not expose either secret to Vite. |
| `PAYFAST_ENABLED`, `PAYFAST_MODE`, `PAYFAST_MERCHANT_ID`, `PAYFAST_MERCHANT_SECRET`, `PAYFAST_API_BASE_URL`, `PAYFAST_CONTRACT_VERIFIED`, `PAYFAST_PAYMENT_METHODS` | Illustrative disabled-by-default PayFast settings; no PayFast adapter is active until merchant-specific checkout/callback details are verified and implemented. |
| `JAZZCASH_ENABLED`, `JAZZCASH_MODE`, `JAZZCASH_CHECKOUT_CONTRACT_VERIFIED`, `JAZZCASH_CALLBACK_CONTRACT_VERIFIED`, `JAZZCASH_API_URL`, `JAZZCASH_MERCHANT_ID`, `JAZZCASH_PASSWORD`, `JAZZCASH_INTEGRITY_SALT`, `JAZZCASH_PAYMENT_METHODS` | Merchant-specific configuration only; JazzCash is not advertised because server-side status inquiry is not implemented. |
| `EASYPAISA_ENABLED`, `EASYPAISA_MODE`, `EASYPAISA_STORE_ID`, `EASYPAISA_MERCHANT_SECRET` | Reserved configuration examples only; no Easypaisa adapter exists. |
| `SMTP_HOST`, `SMTP_PORT` | Outbound mail server settings. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Optional SMTP credentials. |
| `SMTP_FROM_EMAIL` | Sender address for verification and reset mail. |
| `SMTP_USE_TLS` | Enable STARTTLS for SMTP. |

When using the development mailbox, run
`flask --app wsgi dev-mailbox --email user@example.test` to view a test message.
This command is local-only and never creates an HTTP inbox. Reset the dedicated
test-account password interactively, without echoing it, with
`flask --app wsgi dev-reset-test-password user1.test@memorybook.local`.
| `ASSET_S3_ENDPOINT_URL` | Optional custom S3-compatible endpoint (for example, MinIO or R2). |
| `ASSET_S3_REGION` | S3 signing region. |
| `ASSET_S3_BUCKET` | Private bucket for project photos. Required for asset uploads. |
| `ASSET_S3_ACCESS_KEY_ID`, `ASSET_S3_SECRET_ACCESS_KEY` | Optional explicit storage credentials; otherwise use the SDK credential provider. |
| `ASSET_S3_PRESIGNED_URL_TTL` | Lifetime in seconds for signed project-photo URLs. |
| `PDF_FONT_DIR` | Optional directory of operator-licensed font files. Supported family file names are listed in `backend/memorybook/services/pdf_renderer.py`; regular, bold, italic, and bold-italic files must all be present to enable a family. |
| `PDF_MAX_OUTPUT_BYTES` | Maximum generated PDF size (default 100 MiB). |
| `PDF_MIN_PRINT_DPI` | Required effective image resolution for print PDFs (default 300 DPI). |
| `PDF_PRINT_BLEED_INCHES` | Default print bleed (default 0.125 in); a larger bleed may be saved with the book or order. |
| `PDF_PRINT_SAFE_MARGIN_INCHES` | Default text safe margin (default 0.25 in). |
| `PDF_DOWNLOAD_MAX_COUNT` | Maximum downloads per generated file (default 5). |
| `PDF_DOWNLOAD_TTL_DAYS` | Download entitlement lifetime (default 30 days). |
| `PAYMENT_WEBHOOK_TOLERANCE_SECONDS` | Maximum accepted Stripe webhook signature age. |

Production startup rejects non-PostgreSQL databases, missing/short secrets, and
non-Redis rate-limit storage. Configure TLS termination and set
`TRUSTED_PROXY_HOPS` only when the configured number of controlled proxies
overwrites forwarded headers.

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
`GET /api/v1/payments/methods?currency=PKR`; method discovery fails closed when
no enabled, implemented, verified provider is available. No Pakistan gateway
is currently activated. For an existing paid PDF order, the authenticated
owner can request `POST /api/v1/pdf/orders/{id}/generate` with
`{"profile":"digital"}`; print-profile generation is allowed only when the
server-side order price snapshot includes that profile. Generation is queued
to Celery and reported by `GET /api/v1/pdf/jobs/{jobId}` or the order endpoint.
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
Celery workers use the existing Redis broker. The renderer supports JPEG, PNG,
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
For the dedicated local administrator (`ra7514770@gmail.com`), use the
development-only provisioning flow from the `backend` directory:

```powershell
$env:AUTH_EMAIL_MODE = "file"
flask --app wsgi db upgrade
flask --app wsgi dev-provision-admin
flask --app wsgi dev-mailbox --email ra7514770@gmail.com
```

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
order views include the immutable project revision attached to each order.
Payment state is read-only in admin and must be verified by the configured
payment provider; the dashboard does not mark payments successful. Customer
refund requests require admin review; refunds without an implemented automated
provider contract require manual processing and verified provider confirmation.

Order, payment, cancellation, and support-ticket model events create admin
notifications and queued email-log entries. The Celery worker sends those
event emails through the configured SMTP service. The admin email form sends
transactional messages immediately and requires SMTP configuration.

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
the real database connection and migration. Current test and release limitations,
production configuration, backups, deployment commands, rollback guidance, and
acceptance gates are documented in [backend/DEPLOYMENT.md](backend/DEPLOYMENT.md).
Provider contract findings are in [backend/PAYMENT_GATEWAYS.md](backend/PAYMENT_GATEWAYS.md).

### Module 20 validation status

Automated local validation: backend **59 passed**, frontend **18 passed**, and
payment-method service **2 passed**; production Vite build succeeds with a
large-main-chunk advisory. These are unit/contract tests, not full deployed
end-to-end tests. Real PostgreSQL, Redis/Celery, object storage, external email,
provider sandbox transactions, large-project load, and backup restore have not
been verified. Production readiness remains **BLOCKED** until the critical
acceptance gates in the deployment runbook pass.
