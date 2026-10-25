import assert from "node:assert/strict";
import test from "node:test";
import { categoryFormPayload, validateCategoryRecord } from "./categoryForm.js";

const validCategory = {
  name: "  Wedding  ",
  slug: " wedding-books ",
  description: "A collection for wedding stories.",
  style: "Editorial",
  heroAssetKey: "catalog/admin/category-cover.webp",
  sortOrder: 3,
  isPublished: true,
};

test("category form validation requires a name, slug, valid format, and whole sort order", () => {
  assert.equal(validateCategoryRecord({ ...validCategory, name: " " }), "Enter a category name.");
  assert.equal(validateCategoryRecord({ ...validCategory, slug: "" }), "Enter a category slug.");
  assert.match(validateCategoryRecord({ ...validCategory, slug: "Wedding Books" }), /lowercase/);
  assert.match(validateCategoryRecord({ ...validCategory, sortOrder: 1.5 }), /whole number/);
  assert.equal(validateCategoryRecord(validCategory), "");
});

test("category form payload preserves edit fields without persisting signed preview URLs or counts", () => {
  const payload = categoryFormPayload({
    ...validCategory,
    id: "category-1",
    image: "https://assets.example.test/temp?signature=temporary",
    heroImage: "https://assets.example.test/temp?signature=temporary",
    bookCount: 4,
    collectionCount: 2,
  });

  assert.deepEqual(payload, {
    id: "category-1",
    name: "Wedding",
    slug: "wedding-books",
    description: "A collection for wedding stories.",
    style: "Editorial",
    heroAssetKey: "catalog/admin/category-cover.webp",
    sortOrder: 3,
    isPublished: true,
  });
});
