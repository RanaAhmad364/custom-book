# Linux VPS deployment

This is a deployment procedure for a single Linux VPS running PostgreSQL,
Redis-backed rate limiting, Flask/Gunicorn, and nginx. The backend's default
job runner is in-process; this guide uses one Gunicorn worker to avoid multiple
independent job pollers competing for work. Scale-out is not supported by this
topology without a shared job backend and additional deployment validation.

For managed PostgreSQL, provision the database and roles with the provider,
enable and verify TLS, and follow the same migration/runtime-role separation.
Use private S3-compatible storage instead of the local asset directory when
running more than one application host.

## 1. Provision users, services, and directories

Install a supported Python (3.11+), PostgreSQL, Redis, nginx, and Node.js only
if the frontend is built on the host. Create a non-login service account and a
separate writable data directory:

```sh
sudo useradd --system --home /opt/memorybook --shell /usr/sbin/nologin memorybook
sudo install -d -o memorybook -g memorybook -m 0750 /var/lib/memorybook/assets
sudo install -d -o root -g memorybook -m 0750 /etc/memorybook
```

The application files belong under `/opt/memorybook/releases/<release-id>`;
uploads stay under `/var/lib/memorybook/assets`, outside the release/code
directory, and must not be exposed as an nginx static alias.

Create separate PostgreSQL roles for schema migrations and runtime access. Set
strong unique passwords through a protected administrative session:

```sql
CREATE ROLE memorybook_owner LOGIN PASSWORD 'SET_A_MIGRATION_PASSWORD';
CREATE ROLE memorybook_app LOGIN PASSWORD 'SET_A_RUNTIME_PASSWORD';
CREATE DATABASE memorybook OWNER memorybook_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE memorybook TO memorybook_app;
```

Migrations run as `memorybook_owner`. After each successful migration, grant
the runtime role only application DML access and set default privileges for
objects created by the owner:

```sql
\connect memorybook
GRANT USAGE ON SCHEMA public TO memorybook_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO memorybook_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO memorybook_app;
ALTER DEFAULT PRIVILEGES FOR ROLE memorybook_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO memorybook_app;
ALTER DEFAULT PRIVILEGES FOR ROLE memorybook_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO memorybook_app;
```

Use TLS for database connections, especially to managed PostgreSQL; validate
the provider CA rather than disabling certificate checks. URL-encode reserved
characters in passwords.

## 2. Install a release and configure secrets

Check out a reviewed release into a versioned directory, create a virtual
environment, install runtime packages plus Redis storage support, and build
the frontend:

```sh
cd /opt/memorybook/releases/<release-id>/backend
python3.11 -m venv /opt/memorybook/venvs/<release-id>
/opt/memorybook/venvs/<release-id>/bin/pip install --upgrade pip
/opt/memorybook/venvs/<release-id>/bin/pip install '.[redis]'
cd ../frontend
npm ci
npm test
npm run build
```

Maintain `/opt/memorybook/current` as a symlink to the active release and
publish that release's `frontend/dist/` under `/opt/memorybook/frontend/`.
Switch these symlinks only after the migration and smoke-check gates pass.

Create `/etc/memorybook/memorybook.env` from
[`backend/.env.production.example`](../backend/.env.production.example), then
replace every placeholder. Protect the file (`root:memorybook`, mode `0640`).
At minimum configure independent random `SECRET_KEY` and `JWT_SECRET_KEY`,
PostgreSQL runtime/migration URLs, exact HTTPS `CORS_ORIGINS`, canonical app/API
URLs, secure cookies, trusted proxy hops, shared Redis
`RATE_LIMIT_STORAGE_URI`, SMTP, the private asset path, and PayPal's mode,
client ID, client secret, and webhook ID. Use sandbox credentials and the
PayPal webhook endpoint `/api/v1/payments/webhooks/paypal` to verify the full
checkout/capture flow before switching `PAYPAL_MODE=live`. Set
`PAYMENT_PRIMARY_GATEWAY=paypal`; manual transfer is disabled by default and
should only be enabled deliberately with `MANUAL_PAYMENTS_ENABLED=true`.
Set an initial USD-per-PKR value in `PAYPAL_PKR_TO_USD_RATE` and maintain the
admin-editable `paypal_pkr_to_usd_rate` setting under Admin → Settings.
Never place secrets in `VITE_*` variables or the built frontend.

For an external database, set the database URL's TLS and CA options according
to the provider. For local PostgreSQL on the VPS, configure PostgreSQL SSL and
use a verified certificate for TCP connections. For multiple web hosts, set
`ASSET_STORAGE_BACKEND=s3` with a private bucket and workload identity or
restricted server-side credentials.

## 3. Migrate, seed, and create the first administrator

Back up before every migration. Keep the database URL in a protected
`pgpass` file, not in shell history (mode `0600`), and verify that the dump can
be read:

```sh
export PGPASSFILE=/etc/memorybook/pgpass
BACKUP_FILE="/var/backups/memorybook-pre-release-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --host=127.0.0.1 --port=5432 --username=memorybook_backup \
  --dbname=memorybook --format=custom --no-owner \
  --file="$BACKUP_FILE"
pg_restore --list "$BACKUP_FILE"
```

Regularly test restore to a separate, empty database; never restore over
production as a test:

```sh
createdb --host=127.0.0.1 --username=memorybook_owner \
  --owner=memorybook_owner memorybook_restore_check
pg_restore --host=127.0.0.1 --username=memorybook_owner \
  --dbname=memorybook_restore_check --no-owner --role=memorybook_owner \
  "$BACKUP_FILE"
```

Use the migration-owner URL for schema changes. The example below assumes
`/etc/memorybook/migrations.env` contains that owner URL and
`/etc/memorybook/memorybook.env` contains the remaining production settings:

```sh
cd /opt/memorybook/releases/<release-id>/backend
set -a
. /etc/memorybook/memorybook.env
. /etc/memorybook/migrations.env
set +a
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi config-check
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi db-check
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi db current
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi db heads
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi db upgrade
```

Back up before upgrading and test the result before enabling traffic. The demo
catalog seed is guarded for local development databases; do not disable its
guard to populate production:

```sh
/opt/memorybook/venvs/<release-id>/bin/flask --app wsgi seed-demo-catalog --apply --confirm-local-database
```

Run that seed command only against a dedicated local/staging database. Add
approved production products using the protected admin tools. Create/promote
the initial administrator only after the account has been registered and
verified:

```sh
/opt/memorybook/venvs/current/bin/flask --app wsgi grant-admin admin@example.com
```

Do not use the development mailbox or development provisioning command in
production.

## 4. Run Flask with systemd

Create `/etc/systemd/system/memorybook.service`:

```ini
[Unit]
Description=MemoryBook Flask API
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=memorybook
Group=memorybook
WorkingDirectory=/opt/memorybook/current/backend
EnvironmentFile=/etc/memorybook/memorybook.env
ExecStart=/opt/memorybook/venvs/current/bin/gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120 wsgi:app
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/memorybook/assets

[Install]
WantedBy=multi-user.target
```

Keep one Gunicorn worker while using the in-process runner. Its database job
records expose status and failure details; use
`flask --app wsgi retry-failed-jobs` for operator-approved retries. Schedule
unpaid print-order expiry and delivered-upload cleanup separately with a
systemd timer or cron. The print-payment window defaults to 24 hours and can
be changed with `PRINT_ORDER_PAYMENT_EXPIRY_HOURS`:

```sh
/opt/memorybook/venvs/current/bin/flask --app wsgi expire-print-orders
/opt/memorybook/venvs/current/bin/flask --app wsgi cleanup-delivered-uploads
```

For systemd, create `/etc/systemd/system/memorybook-cleanup.service`:

```ini
[Unit]
Description=MemoryBook delivered-upload retention cleanup
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=memorybook
Group=memorybook
WorkingDirectory=/opt/memorybook/current/backend
EnvironmentFile=/etc/memorybook/memorybook.env
ExecStart=/opt/memorybook/venvs/current/bin/flask --app wsgi cleanup-delivered-uploads
```

Create `/etc/systemd/system/memorybook-cleanup.timer`:

```ini
[Unit]
Description=Daily MemoryBook delivered-upload cleanup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer with `sudo systemctl daemon-reload` and
`sudo systemctl enable --now memorybook-cleanup.timer`; inspect runs with
`sudo journalctl -u memorybook-cleanup.service`.

Use an hourly systemd unit for unpaid print-order expiration. Create
`/etc/systemd/system/memorybook-expire-print-orders.service`:

```ini
[Unit]
Description=Expire unpaid MemoryBook print orders
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=memorybook
Group=memorybook
WorkingDirectory=/opt/memorybook/current/backend
EnvironmentFile=/etc/memorybook/memorybook.env
ExecStart=/opt/memorybook/venvs/current/bin/flask --app wsgi expire-print-orders
```

Create `/etc/systemd/system/memorybook-expire-print-orders.timer`:

```ini
[Unit]
Description=Hourly unpaid print-order expiry

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer with `sudo systemctl enable --now
memorybook-expire-print-orders.timer` and inspect its run log with
`sudo journalctl -u memorybook-expire-print-orders.service`.

Then enable and inspect the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now memorybook
sudo systemctl status memorybook
sudo journalctl -u memorybook -f
```

## 5. Serve the frontend and API through nginx

Publish `frontend/dist/` to a versioned static directory and configure nginx to
serve the SPA and reverse-proxy `/api/` to loopback port 8000. Configure TLS
certificates, request/body size limits appropriate to image uploads, HTTP to
HTTPS redirects, and the exact forwarded headers. The app must only trust
forwarded headers from the known proxy; set `TRUSTED_PROXY_HOPS=1` for this
single nginx proxy.

```nginx
server {
    listen 443 ssl http2;
    server_name www.example.com;
    root /opt/memorybook/frontend/current;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID $request_id;
        client_max_body_size 16m;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

If frontend and API are on different hostnames, configure `CORS_ORIGINS` to
the exact frontend origin and review cookie SameSite/CSRF behavior. Do not add
wildcard CORS origins.

## 6. Verify, monitor, and update safely

Before accepting traffic, verify HTTPS, `/api/v1/health/live`,
`/api/v1/health/ready`, login/CSRF, registration email, private asset access,
manual-payment review, generated PDF access, nginx upload limits, Redis rate
limits, log redaction, and PostgreSQL backup/restore. Follow the
[end-to-end QA checklist](./FINAL_QA_CHECKLIST.md) and the release gates in
[`backend/DEPLOYMENT.md`](../backend/DEPLOYMENT.md).

For each update, build into a new release directory, run automated tests,
create and verify a database backup, apply migrations once using the migration
role, switch the `current` symlink, restart systemd, then run smoke checks. Keep
the previous release and backup until acceptance passes. Roll back application
code first only when the old code is schema-compatible. For destructive or
incompatible schema changes, stop writes and restore the verified backup or
point-in-time snapshot; reconcile all accepted payments and orders before
reopening checkout. Never run an unreviewed production downgrade.
