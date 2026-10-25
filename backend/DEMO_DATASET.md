# Development demo catalog

The `seed-demo-catalog` Flask command creates an original, repeatable Module 8A
catalog dataset for local development. It reuses the existing catalog, pricing,
design publication, project-copy, image-validation, and filesystem-storage
workflows. It does not reset the database, apply migrations, modify orders, or
delete records.

The command is preview-only by default. From the `backend` directory in
PowerShell:

```powershell
.\.venv\Scripts\flask.exe --app wsgi seed-demo-catalog
```

Only after verifying that `.env` points to a dedicated, non-production,
loopback PostgreSQL database and that filesystem asset storage is enabled,
apply the seed:

```powershell
.\.venv\Scripts\flask.exe --app wsgi seed-demo-catalog --apply --confirm-local-database
```

The command refuses to write unless the app is in development, the database is
PostgreSQL on loopback, filesystem asset storage is selected, and the
confirmation flag is present. It also refuses to seed when the configured
database is behind the repository's migration head. This repository currently
has a pending collection-category relationship migration; review and apply
pending development migrations manually before running the seed command. The
command never applies migrations.

Existing demo records are reused and user edits to existing demo products or
designs are not overwritten. A conflicting,
incomplete, inactive, or incompatible record causes the seed to stop with a
clear error rather than modifying it. Since the normal application services
commit individual operations, a failed run can leave already-created records
in place; rerunning the command is safe and resumes without deleting them.

The dataset uses illustrative PKR prices. The print quote follows the existing
calculation: product starting price + selected variant price + additional-page
charge + shipping. The configured pricing-tier base price is not added to that
quote by the existing order service. The seed creates no orders or payment
confirmations.

The command creates four category and six collection targets, ten products with
four compatible variants each, three demo printing tiers and page-pricing
bands, two sizes, two covers, two paper types, one Pakistan home-delivery rate,
ten validated and published master designs, and three private customer drafts.
New demo customer accounts use reserved `@memorybook.local` addresses and
random, undisclosed password hashes. Set a local password interactively with
`flask dev-reset-test-password demo.customer.1@memorybook.local` (and similarly
for customers 2 and 3); the password is never placed in source code or printed.

After applying, open `http://127.0.0.1:5173/books` to browse the books,
`http://127.0.0.1:5173/categories` for categories, and
`http://127.0.0.1:5173/collections` for collections. Admin catalog and pricing
records are available under `/admin/books`, `/admin/categories`, and
`/admin/pricing` after signing in. To inspect drafts, sign in as one of the
demo customers and open `http://127.0.0.1:5173/dashboard/projects`. Drafts
belong to their respective demo customer accounts and are not public catalog
entries.
