# Blissico Admin Reference

Reference checkout: `../Blissico_Dbn` (read-only). This document records the UX and API patterns found in that project to inform MemoryBook's admin implementation. It is a behavioral reference, not code to copy.

## Frontend structure

The frontend is under `blissico_app/src`. `App.jsx` registers admin pages individually and wraps them in `components/AdminRoute.jsx`. The guard waits for authentication, sends logged-out users to login, and sends authenticated non-admins back to the user dashboard.

`components/admin/AdminLayout.jsx` composes a persistent sidebar and topbar around the active page. The sidebar groups links into Main, Management, and System sections, closes on mobile navigation, and includes logout. The topbar contains a menu toggle, greeting, search field, notification menu, and account menu with profile/settings/logout links. Navigation uses React Router `Link`.

The implementation has dedicated page components under `pages/admin`: `AdminDashboard`, `Products`, `Categories`, `DownloadHistory`, `Users`, `EditProfile`, and `AdminCustomizeCard`. The routing also refers to Collections and Occasions pages in `App.jsx`; their source files are not present in the checked-in `pages/admin` listing. Purchases, Notifications, and Contact Messages with reply are not separate admin pages in this checkout. The card design page loads the selected card and saved default customization, then presents a shared card design editor.

Dashboard UI is composed from small pieces under `components/dashboard`: `StatCard`, `QuickStats`, `RevenueChart`, `RecentOrders`, `BestSellingCards`, `TopCategories`, `TopOccasions`, `CategoriesList`, and `QuickActions`. Data loading is split between widgets and the dashboard page. The chart offers time-range controls, while the page combines metric cards, catalog summaries, quick actions, revenue, and recent activity. `TrendChart` and `ActiveDiscounts` were not present in the inspected source tree.

The `Products` and `Categories` pages use explicit forms, list/table views, loading/error messages, refresh-after-save behavior, and `window.confirm` before destructive deletion. `DownloadHistory` has server-fed search/date filters, a paginated table, loading/error/empty states, and customer/product information.

## Backend structure and access control

The backend is under `blissico_backend/app/admin`. Route handlers live in `routes.py` and `analytics_routes.py`; business logic is separated into `service.py`, `catalog_service.py`, and `analytics_service.py`; validation is separated into `validators.py` and `catalog_validator.py`; access control is centralized in `decorators.py`.

Every inspected route in the admin route modules uses `@admin_required`. The decorator verifies the JWT, loads the user, rejects missing/inactive accounts, and returns 403 for users without the Admin role.

Analytics are exposed as separately guarded endpoints: `/analytics/overview`, `/analytics/most-downloaded`, `/analytics/top-selling`, `/analytics/recent-payments`, `/analytics/recent-users`, `/analytics/revenue-chart`, `/analytics/download-chart`, and `/analytics/most-favorited`. Dedicated `/purchases` and `/downloads` route patterns are intended for operational history; this checkout has a dedicated `/downloads` endpoint with search/date filters and pagination, but does not expose `/purchases` in the inspected route module.

## Frontend API access

`src/api/axiosConfig.js` creates the shared Axios instance and attaches the stored access token as a Bearer authorization header. `AuthContext.jsx` stores access and refresh tokens after login. Inspection of the checked-in source did **not** find a response interceptor, silent refresh implementation, or request queue; therefore the requested “silent refresh with a request queue” is not a verified pattern in this checkout and should not be copied as an existing feature.

## Applying the reference to MemoryBook

Keep MemoryBook's existing Flask app factory, `/api/v1/admin` blueprint, `roles_required("admin")` permission guard, SQLAlchemy models, and service layer. Adopt the reference's grouped navigation, page-oriented organization, dashboard composition, mobile sidebar behavior, explicit loading/error/empty states, and server-side filtered history. Extend MemoryBook's own analytics and commerce data rather than importing Blissico models or APIs.
