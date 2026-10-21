# Memorybook

Memorybook public website frontend.

## Run locally

```powershell
cd frontend
npm install
npm run dev
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

Catalog products, categories, tiers, and starting prices are demonstration data
served by `frontend/src/services/catalog.js`; they are not connected to a
production API. Replace them with published backend data during integration.
Category, style, occasion, page-count, book-type, and price filters operate on
this centralized sample catalog.
Account access and project creation are explicitly identified as forthcoming
modules and are not presented as operational features.

The design currently uses Google Fonts and Unsplash-hosted photography.
