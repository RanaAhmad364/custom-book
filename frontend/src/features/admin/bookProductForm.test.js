import assert from "node:assert/strict";
import test from "node:test";
import { bookFormValues, buildBookPayload, collectionsForCategory, validateBookForm } from "./bookProductForm.js";

test("book form maps existing product and persisted asset keys into editable values", () => {
  const record = {
    id: "book-1",
    title: "A Journey",
    slug: "a-journey",
    startingPrice: 6500,
    categoryId: "category-1",
    collectionId: "collection-1",
    coverAssetKey: "catalog/covers/cover.jpg",
    currency: "PKR",
    adminMetadata: {
      sizeOptions: ["size-1"],
      previewImageKeys: ["catalog/previews/page.jpg"],
      dimensions: { widthMm: "210.00", heightMm: "297.00" },
      customField: "preserved",
    },
  };

  const values = bookFormValues(record);
  const payload = buildBookPayload(values);

  assert.equal(values.currency, "PKR");
  assert.equal(values.startingPrice, "6500");
  assert.equal(payload.startingPrice, "6500");
  assert.equal(payload.categoryId, "category-1");
  assert.equal(payload.collectionId, "collection-1");
  assert.equal(payload.coverAssetKey, "catalog/covers/cover.jpg");
  assert.deepEqual(payload.adminMetadata.sizeOptions, ["size-1"]);
  assert.deepEqual(payload.adminMetadata.previewImageKeys, ["catalog/previews/page.jpg"]);
  assert.equal(payload.adminMetadata.dimensions.heightMm, "297.00");
  assert.equal(payload.adminMetadata.customField, "preserved");
  assert.equal("image" in payload, false);
});

test("new product defaults preserve USD and form metadata defaults", () => {
  const values = bookFormValues({
    title: "New book",
    slug: "new-book",
    description: "A book description",
    categoryId: "category-1",
  });
  const payload = buildBookPayload(values);

  assert.equal(values.currency, "USD");
  assert.equal(payload.bookType, "BASIC");
  assert.equal(payload.pageCountMin, 24);
  assert.deepEqual(payload.adminMetadata.printingTiers, []);
  assert.deepEqual(validateBookForm(values), {});
});

test("book form validation catches missing relations, invalid prices, and page range errors", () => {
  const values = bookFormValues({
    title: "Book",
    slug: "book",
    description: "Description",
    categoryId: "",
    startingPrice: "-1.00",
    currency: "US",
    pageCountMin: 80,
    pageCountMax: 24,
  });
  const errors = validateBookForm(values);

  assert.equal(errors.categoryId, "Choose a category.");
  assert.equal(errors.currency, "Use a three-letter currency code.");
  assert.ok(errors.startingPrice);
  assert.equal(errors.pageCountMax, "Maximum pages must be at least the minimum.");
});

test("book form rejects non-positive dimensions and excessive/invalid page options", () => {
  const values = bookFormValues();
  values.adminMetadata.dimensions.widthMm = "0";
  values.adminMetadata.pageCountOptions = [];

  const errors = validateBookForm(values);
  assert.ok(errors.widthMm);
  assert.ok(errors.pageCountOptions);
});

test("book collection options are limited to the selected category", () => {
  const collections = [
    { id: "travel-collection", categoryId: "travel" },
    { id: "inactive-travel-collection", categoryId: "travel", isPublished: false },
    { id: "family-collection", categoryId: "family" },
    { id: "unresolved-collection", categoryId: null },
  ];

  assert.deepEqual(collectionsForCategory(collections, "travel"), [collections[0]]);
  assert.deepEqual(collectionsForCategory(collections, ""), []);
  assert.deepEqual(collectionsForCategory(collections, "family"), [collections[2]]);
});
