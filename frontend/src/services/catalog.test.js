import assert from "node:assert/strict";
import test from "node:test";
import { catalogService } from "./catalog.js";

async function withCatalogResponse(book, callback) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({ book }),
  });
  try {
    return await callback();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

test("book details preserve signed gallery URLs from the catalog API", async () => {
  const gallery = [
    { image: "https://assets.example.test/cover?signature=cover", imageAlt: "Cover", label: "Cover" },
    { image: "https://assets.example.test/page?signature=page", imageAlt: "Page", label: "Preview 1" },
  ];
  const result = await withCatalogResponse(
    { id: "book-1", title: "A book", image: gallery[0].image, gallery },
    () => catalogService.getBookDetails("book-1"),
  );

  assert.deepEqual(result.gallery, gallery);
});

test("book details retain the cover-only fallback for older catalog responses", async () => {
  const result = await withCatalogResponse(
    { id: "book-1", title: "A book", image: "https://assets.example.test/cover", imageAlt: "Cover art" },
    () => catalogService.getBookDetails("book-1"),
  );

  assert.deepEqual(result.gallery, [
    { image: "https://assets.example.test/cover", imageAlt: "Cover art", label: "Cover" },
  ]);
});
