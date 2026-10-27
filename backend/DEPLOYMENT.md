# MemoryBook production deployment

This is an operator runbook, not a claim that this repository is production
ready. No production infrastructure, merchant account, PostgreSQL service,
Redis service, SMTP service, or private asset storage is provisioned or
verified by this project. Complete the release gates below before accepting
traffic or payments.

## Production topology

- Serve the built Vite application from a CDN or static web host over HTTPS.
- Run the Flask API as a Linux service behind an HTTPS reverse proxy or managed
  load balancer. Use Gunicorn; do not use `flask run`.
- Use managed PostgreSQL with TLS, automated backups, point-in-time recovery,
  a separate migration role, and a least-privilege runtime role.
- Use shared Redis with TLS for rate limits when running production processes.
  Redis is not a requirement for the default in-process background job runner.
- Store uploaded assets and generated PDFs in private S3-compatible storage, or
  in an external persistent filesystem directory for a single-host deployment.
  Keep filesystem assets outside the application tree and never expose the
  directory through the reverse proxy. Use S3 for multiple application hosts.
- Use an SMTP provider or transactional-mail service for verification,
  password-reset, order, and admin notifications.
- Centralize JSON stdout/stderr logs, web health, database and Redis metrics,
  database-tracked job failures, storage errors, and payment reconciliation.

The repository does not define a cloud provider, container image, infrastructure
as code, frontend hosting workflow, or monitoring provider. Choose and operate
those services in the target environment; never put credentials in Git or
frontend `VITE_*` variables.

For a complete single-VPS procedure, see
[`docs/DEPLOYMENT_LINUX_VPS.md`](../docs/DEPLOYMENT_LINUX_VPS.md). The
production environment template is
[`backend/.env.production.example`](.env.production.example). The executable
acceptance checklist is [`docs/FINAL_QA_CHECKLIST.md`](../docs/FINAL_QA_CHECKLIST.md).

## Environment configuration

Create environment variables from the names in `../.env.example`; do not copy
live values into that example. Store secrets in the hosting platform's secret
manager and inject them at runtime. Never print resolved connection strings to
build logs.

Required for the Flask production process:

| Variable | Production value / handling |
| --- | --- |
| `FLASK_ENV` | `production`. |
| `SECRET_KEY` | Random secret, at least 32 characters; keep stable across instances and rotations planned. |
| `JWT_SECRET_KEY` | Independent random secret, at least 32 characters. |
| `DATABASE_URL` | `postgresql+psycopg://...` URL for managed PostgreSQL; URL-encode reserved password characters and require TLS per database provider. |
| `RATE_LIMIT_STORAGE_URI` | Shared Redis URL for multi-process production; use `rediss://` when supported/required. The default local backend is in-memory. |
| `BACKGROUND_JOB_BACKEND` | `inprocess` (default) for the database-tracked `ThreadPoolExecutor`; set `celery` only when the optional Celery extra and worker are deliberately deployed. |
| `BACKGROUND_JOB_WORKERS` | Number of in-process background worker threads per Flask process. Use one Gunicorn worker until cross-process job claiming is validated. |
| `CORS_ORIGINS` | Exact HTTPS frontend origins, comma-separated; no wildcard for credentialed requests. |
| `PUBLIC_APP_URL` | Canonical HTTPS frontend origin. |
| `PUBLIC_API_URL` | Canonical HTTPS API origin, used for absolute links/callbacks where configured. |
| `JWT_COOKIE_SECURE` | `true`. |
| `JWT_COOKIE_SAMESITE` | `Lax` for same-site deployments; cross-site cookie deployment requires a deliberate `None` + `Secure` design and CSRF review. |
| `JWT_COOKIE_DOMAIN` | Omit unless the frontend and API are sibling subdomains and the shared domain is explicitly required. |
| `LOG_LEVEL` | `INFO` or an operator-approved level; logs are JSON on stdout. |
| `TRUSTED_PROXY_HOPS` | Number of trusted reverse proxies that overwrite forwarded headers; leave `0` when the API is reached directly. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS` | Provider-issued mail settings and sender authorization. Verify delivery and bounce handling. |
| `AUTH_EMAIL_MODE` | Keep `smtp` in production. The `file` mode is development-only and writes authentication mail to a local CLI mailbox; it is rejected outside development. |
| `ASSET_STORAGE_BACKEND` | `s3` for multi-host deployment, or `filesystem` for one host with an external persistent directory. |
| `ASSET_LOCAL_DIRECTORY` | Absolute persistent path outside the application directory, e.g. `/var/lib/memorybook/assets`; restrict write/read access to the service account and never serve it directly. |
| `ASSET_S3_BUCKET`, `ASSET_S3_REGION` | Private bucket and signing region when `ASSET_STORAGE_BACKEND=s3`. |
| `ASSET_S3_ENDPOINT_URL` | Set only for a non-AWS S3-compatible service. |
| `ASSET_S3_ACCESS_KEY_ID`, `ASSET_S3_SECRET_ACCESS_KEY` | Optional explicit credentials; prefer workload identity/credential provider if available. |
| `ASSET_S3_PRESIGNED_URL_TTL` | Short lifetime suitable for private photo and file access. |
| `PDF_FONT_DIR` | Optional mounted directory of operator-licensed font files. |
| `PDF_MAX_OUTPUT_BYTES`, `PDF_MIN_PRINT_DPI`, `PDF_PRINT_BLEED_INCHES`, `PDF_PRINT_SAFE_MARGIN_INCHES` | Approved rendering thresholds; confirm with the print vendor. |
| `PRINT_ORDER_PAYMENT_EXPIRY_HOURS` | Age after which unpaid print orders are cancelled by the scheduled `flask expire-print-orders` cleanup command; defaults to 24 hours. |
| `PAYMENT_DEFAULT_CURRENCY` | Product/business currency policy, normally `PKR` for the target market. |
| `PAYMENT_PRIMARY_GATEWAY` | Preference only; does not enable or prove a gateway contract. |
| `STRIPE_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Only enable when the account, currency, webhook endpoint, and verified real/sandbox transactions are approved. Secrets stay server-side. |
| `PAYFAST_*`, `JAZZCASH_*`, `EASYPAISA_*` | Keep disabled and credentials empty until the provider-specific merchant contract and code paths are verified. Placeholder variables are not evidence of support. |

Other variables, defaults, and descriptions are documented in `../.env.example`
and the environment table in the repository README. Review that table and this
one together whenever configuration changes.

For local development without an SMTP provider, set `AUTH_EMAIL_MODE=file`
only in the backend process environment. Read verification/reset messages with
`flask --app wsgi dev-mailbox --email user@example.test`; add `--clear` to
remove the messages displayed by that command. This mailbox is not exposed by
an HTTP endpoint and must never be enabled in production. Reset one of the
dedicated development test-account passwords interactively with
`flask --app wsgi dev-reset-test-password <email>`. The reset command prompts
without echoing the password and revokes that account's existing sessions.

## Release procedure

1. Provision and separately validate PostgreSQL, shared Redis rate-limit
   storage, SMTP, and private asset storage. For filesystem storage, verify the
   persistent directory is outside the release tree and inaccessible to nginx.
   Confirm backups, access policies, TLS, monitoring, and alert routes.
2. Build the frontend in CI using the production API base URL, if configured:

   ```powershell
   Set-Location frontend
   npm ci
   npm test
   npm run build
   ```

   Publish only `frontend/dist/` to the configured HTTPS static host/CDN. Use a
   same-origin `/api` proxy or set `VITE_API_BASE_URL` at build time to the
   canonical API origin. The Vite dev proxy is not a production proxy.
3. Build/install the backend from a reviewed commit on a supported Linux/Python
   runtime. Install the Redis extra when using shared Redis rate-limit storage:

   ```sh
   python -m pip install '.[redis]'
   ```

4. Inject runtime secrets and configuration into a one-off release/migration
   process. Validate without displaying values:

   ```sh
   flask --app wsgi config-check
   flask --app wsgi db-check
   flask --app wsgi db current
   flask --app wsgi db heads
   ```

5. Take and verify a PostgreSQL backup before schema changes. Apply the reviewed
   migration once, from a single release job (not concurrently from every web
   instance):

   ```sh
   flask --app wsgi db upgrade
   ```

6. Start the API with Gunicorn and production environment variables:

   ```sh
   gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 wsgi:app
   ```

   Keep one Gunicorn worker while using the default in-process job runner; its
   job poller is process-local. Set timeouts from measured workload and
   instance limits. The reverse proxy must terminate HTTPS, forward the correct
   host/protocol, apply request-size limits, and preserve the application request ID. Set
   `TRUSTED_PROXY_HOPS` to the exact number of controlled proxies that overwrite
   forwarded headers; do not trust client-supplied forwarding headers.
7. The default database-tracked job runner starts in the Flask process and uses
   a `ThreadPoolExecutor`; inspect failed jobs and retry them using the CLI.
   Celery is an optional alternate and is not required for the default setup.
   Only when deliberately selecting `BACKGROUND_JOB_BACKEND=celery`, install
   the optional extra and start a worker:

   ```sh
   celery -A wsgi:celery worker --loglevel=INFO --concurrency=2
   ```

   Tune concurrency against memory use, PDF size, CPU, and queue latency. This
   optional mode requires a broker; it is separate from Redis rate-limit storage.
8. Verify `GET /api/v1/health/live` and `/api/v1/health/ready`, static asset
   delivery, CORS/cookie/CSRF behavior over HTTPS, email delivery, private
   upload/download authorization, in-process job execution and retry, and
   log/alert delivery. The readiness endpoint currently verifies PostgreSQL
   only; separately test Redis, SMTP, and asset storage.
9. Keep payments disabled until the provider-specific acceptance criteria below
   pass. Reconcile provider transaction IDs and settlement records before
   opening checkout to customers.

## Database migration and recovery

- Migrations live in `migrations/versions`. Review `flask db history` and
  `flask db heads` in CI/release review; only one migration head is expected.
- Run the upgrade from a single process. Confirm the resulting `flask db
  current` revision and perform an application smoke test before shifting
  traffic.
- Back up before migrations. A generic PostgreSQL backup example (adapt
  credentials and storage destination to the hosting provider) is:

  ```sh
  PGPASSFILE=/etc/memorybook/pgpass pg_dump \
    --host=db.example.com --port=5432 --username=memorybook_backup \
    --dbname=memorybook --format=custom --no-owner \
    --file=memorybook-pre-release.dump
  pg_restore --list memorybook-pre-release.dump
  ```

  `pg_dump` uses libpq connection parameters (or a standard
  `postgresql://` URI), not SQLAlchemy's `postgresql+psycopg://` URL. Keep the
  password in a mode-`0600` passfile or the hosting secret manager, not in the
  command line.

- Test backup restore and point-in-time recovery in a separate environment
  regularly. Encrypt backups, restrict access, and set retention according to
  policy. A dump file is not a verified backup until a restore is tested.
- Prefer a forward corrective migration. Do not automatically run `flask db
  downgrade` in production: schema downgrades may lose data or break a newer
  application. Use downgrade only after reviewing that exact migration,
  testing it against a restored copy, and approving a maintenance window.
- If a release fails after a migration, first roll back application traffic to
  the last compatible release. Keep the expanded schema if backward compatible.
  If data/schema corruption occurred, stop writes, restore the verified
  pre-release backup or point-in-time snapshot, and reconcile any accepted
  orders/payments with the provider before reopening service.
- Preserve immutable project revisions, order price snapshots, payment
  attempts, webhook records, refund records, and audit history during recovery.
  Never delete payment or order history to make a deployment appear healthy.

## Observability and operations

- Collect JSON logs from API processes and any optional Celery worker. Redact authorization,
  cookies, passwords, OTP/reset codes, payment credentials, and full callback
  payloads. Use `X-Request-ID` to correlate requests.
- Alert on API 5xx and readiness failure, database connection exhaustion,
  Redis rate-limit storage unavailability, queued/failed background jobs,
  repeated PDF failures, SMTP errors, storage authorization failures, and
  payment webhook/reconciliation mismatches.
- The included health checks do not validate background jobs, SMTP, Redis,
  asset storage, external payment providers, or backup freshness. Configure external
  checks for those dependencies.
- Establish incident playbooks for provider callback delays, duplicate
  callbacks, failed PDF jobs, leaked/revoked signed URLs, credential rotation,
  database restore, and refund/manual reconciliation.

## Critical acceptance gates

Production readiness is **BLOCKED** until all of these pass in a production-like
environment with synthetic/test accounts:

- Real PostgreSQL migration upgrade, application connectivity, and a verified
  backup restore/rollback drill.
- Auth registration, verification, login, refresh rotation, logout/revocation,
  password reset, CSRF, role enforcement, and owner isolation through the
  deployed HTTPS frontend and API.
- Private asset upload/download/deletion and authorized PDF download against
  production-equivalent object storage.
- Database-tracked job delivery and retry for large multi-page PDF generation,
  with actual output validation, page order, images, fonts, and print constraints.
- Payment initiation, valid/invalid/delayed/duplicate callbacks, server-side
  status verification, failure/retry, amount/currency/reference mismatch,
  refund, and order/entitlement transitions using provider-approved sandbox
  credentials. Do not represent mocks as sandbox verification.
- Print quote-to-order, payment confirmation, production/shipping status
  history, cancellation, and customer tracking through the deployed app.
- Load/performance tests for large projects, upload limits, API/database
  behavior, worker concurrency, and queue backlog; monitoring and rollback
  procedures exercised by the on-call operator.

The current public PayFast information does not provide the merchant-specific
checkout/callback contract needed to run those tests. JazzCash remains blocked
until server-side inquiry is implemented and its merchant contract is tested.
No direct Easypaisa adapter is implemented. Keep all these methods unavailable
until their individual gates pass.
