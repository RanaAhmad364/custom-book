# MemoryBook end-to-end QA checklist

Use synthetic accounts, non-production payment references, and a dedicated
test database. Do not mark a step complete based only on a unit test or mock.
Record the environment, build/commit, tester, and date when running this list
against a release candidate.

## Storefront and customer journey

| Status | Check | Evidence / notes |
| --- | --- | --- |
| OK locally | Open the home page and confirm the seeded catalog, prices, and local images render. | `http://localhost:5173/`; no broken images observed. |
| OK locally | Open Explore Books, search/filter/sort, and open a book detail page. | `/books` rendered 11 designs; a seeded book detail page rendered successfully. |
| NOT RUN | Register a new synthetic user, read the OTP from the development mailbox, verify it, and log in. | Requires an isolated test account and a fresh development mailbox entry. |
| NOT RUN | Favorite a book, refresh, and confirm the favorite remains; remove it from Favorites. | Verify persistence and logged-out return-to-login behavior. |
| NOT RUN | Start a new book, upload a valid image, add pages, and verify the backend quote changes. | Use a synthetic image; verify rejection of invalid/oversized files. |
| NOT RUN | Place a PDF order using the manual provider, submit a test reference, approve it as admin, and download the generated PDF. | Check ownership, payment status, page count, and output contents. |
| NOT RUN | Place a print order, approve its payment, advance it through production and shipping, add tracking, and confirm customer notifications/history. | Verify every status transition and the delivered state. |
| NOT RUN | Confirm an unpaid or failed payment cannot grant PDF access, and duplicate payment callbacks do not duplicate fulfillment. | Use provider sandbox callbacks or the project's explicit test harness; do not use live payment data. |

## Admin and publication journey

| Status | Check | Evidence / notes |
| --- | --- | --- |
| NOT RUN | Confirm a logged-out user receives a login redirect and a normal user receives 403 from admin APIs. | Exercise browser and API authorization, not only hidden admin navigation. |
| NOT RUN | Create a book, category/collection as needed, design pages and cover, save a draft, then publish. | Use a test catalog record and verify design validation. |
| NOT RUN | Confirm the published book appears in Explore Books and its category/collection, then create a user project from it. | Check public detail and editor rendering match the saved layout. |
| NOT RUN | Review payments awaiting approval, order timeline, tracking, customer history, reports, and admin activity log. | Verify destructive actions require confirmation and are audit logged. |

## Release and operations

| Status | Check | Evidence / notes |
| --- | --- | --- |
| OK locally | Flask liveness endpoint responds directly and through Vite's `/api` proxy. | Both `http://127.0.0.1:5000/api/v1/health/live` and `http://localhost:5173/api/v1/health/live` returned HTTP 200. |
| PASS | Backend automated tests. | `pytest -q`: 126 passed. |
| PASS | Frontend automated tests. | `npm test`: 68 passed. |
| PASS | Production frontend build. | `npm run build` completed successfully. |
| PASS | Production-shaped backend configuration validation. | `flask config-check` passed with HTTPS origins, secure cookies, shared Redis rate-limit storage, SMTP mode, and an external filesystem asset path. |
| PASS | Configured PostgreSQL connection. | `flask db-check` reported successful database connectivity. |
| NOT RUN | Apply and verify all Alembic migrations against a fresh PostgreSQL database. | Do not use a production database for fresh-migration verification. |
| NOT RUN | Verify TLS, CORS, secure cookies, CSRF, SMTP delivery, private object/file storage, logs, and backup restore in a production-like environment. | Use synthetic accounts and provider sandboxes. |
| NOT RUN | Exercise rollback with a verified pre-release backup and confirm payment/order reconciliation. | Keep an approved rollback window and recovery operator. |

## Current execution notes

- The local API health endpoint returned HTTP 200.
- The Vite `/api/v1/health/live` proxy returned HTTP 200.
- Backend tests passed (126); frontend tests passed (68); Vite production
  build succeeded.
- Production-shaped `flask config-check` and local `flask db-check` succeeded.
- Vite responded at `http://localhost:5173`; the browser rendered the home,
  catalog, and a seeded book detail page. The browser reported some 401
  responses during anonymous editor/account initialization; authenticated
  customer and admin journeys have not been completed.
- The production PostgreSQL migration, payment provider, SMTP, private storage,
  backup restore, and deployment checks remain release gates. See
  [DEPLOYMENT_LINUX_VPS.md](./DEPLOYMENT_LINUX_VPS.md) and
  [../backend/DEPLOYMENT.md](../backend/DEPLOYMENT.md).
