import test from "node:test";
import assert from "node:assert/strict";
import {
  createPage, createPhotoElement, createPreviewDocument, createTextElement, duplicatePageRecord, pagesWithoutPhotoSlots,
  placePhotoOnPage, removePage, reorderPageIds, resizeBookPageCount,
} from "./editorDocument.js";

function sampleDocument(count = 10) {
  const cover = createPage("cover");
  const pages = Array.from({ length: count }, (_, index) => createPage("page", index + 1));
  pages.forEach((page, index) => {
    page.elements.push({ ...createTextElement("heading", `Page ${index + 1}`), x: index / 100 });
  });
  return {
    schemaVersion: 1,
    metadata: { id: "project", owner: "user@example.test", title: "Test book" },
    book: { pageCount: count, size: { width: 10, height: 10 } },
    pages: [cover, ...pages],
    pageOrder: [cover, ...pages].map((page) => page.id),
    assets: [],
  };
}

test("page ordering moves pages to the requested position without changing identities", () => {
  const order = ["cover", "one", "two", "three", "four"];
  assert.deepEqual(reorderPageIds(order, "one", "three"), ["cover", "two", "one", "three", "four"]);
  assert.deepEqual(reorderPageIds(order, "four", "one"), ["cover", "four", "one", "two", "three"]);
  assert.deepEqual(reorderPageIds(order, "three", null), ["cover", "one", "two", "four", "three"]);
  assert.deepEqual(reorderPageIds(order, "missing", "one"), order);
});

test("duplicating a page clones content with fresh page and element IDs", () => {
  const source = createPage("page", 1);
  source.elements.push(createTextElement("heading", "A memory"));
  const copy = duplicatePageRecord(source, "Page 2");
  assert.notEqual(copy.id, source.id);
  assert.notEqual(copy.elements[0].id, source.elements[0].id);
  assert.equal(copy.elements[0].text, source.elements[0].text);
  copy.elements[0].text = "Changed";
  assert.equal(source.elements[0].text, "A memory");
});

test("removing a page keeps adjacent page content and order intact", () => {
  const document = sampleDocument();
  const removedId = document.pageOrder[4];
  const expectedNextActive = document.pageOrder[3];
  const result = removePage(document, removedId);
  assert.ok(result);
  assert.equal(result.document.pages.some((page) => page.id === removedId), false);
  assert.deepEqual(result.document.pageOrder, document.pageOrder.filter((id) => id !== removedId));
  assert.equal(result.document.book.pageCount, 9);
  assert.equal(result.nextActivePageId, expectedNextActive);
  assert.equal(result.document.pages.find((page) => page.id === expectedNextActive).elements[0].text, "Page 3");
  assert.equal(document.pages.length, 11);
});

test("cover cannot be removed and normalized heading size remains readable", () => {
  const document = sampleDocument(1);
  assert.equal(removePage(document, document.pageOrder[0]), null);
  const heading = createTextElement("heading");
  assert.ok(heading.fontSize > 0.05 && heading.fontSize < 0.06);
});

test("placing an uploaded photo replaces a selected placeholder without changing its frame", () => {
  const placeholder = {
    id: "photo-slot",
    type: "shape",
    shape: "photo-placeholder",
    x: 0.08,
    y: 0.12,
    width: 0.52,
    height: 0.68,
    rotation: 4,
  };
  const heading = createTextElement("heading", "A memory");
  const elements = [heading, placeholder];
  const asset = { id: "asset-1", name: "portrait.jpg", src: "/assets/portrait.jpg" };

  const result = placePhotoOnPage(elements, asset, placeholder.id);

  assert.equal(result.elements.length, 2);
  assert.equal(result.elements[0], heading);
  assert.deepEqual(
    Object.fromEntries(["id", "type", "assetId", "x", "y", "width", "height", "rotation"].map((key) => [key, result.photo[key]])),
    { id: "photo-slot", type: "image", assetId: "asset-1", x: 0.08, y: 0.12, width: 0.52, height: 0.68, rotation: 4 },
  );
  assert.equal(elements[1], placeholder);
});

test("placing a photo on a selected image preserves its existing frame", () => {
  const image = { ...createPhotoElement({ id: "old-asset", src: "/old.jpg" }, 0.2, 0.3, 0.4, 0.5), id: "existing-photo" };
  const replacement = { id: "new-asset", name: "new.jpg", src: "/new.jpg" };

  const result = placePhotoOnPage([image], replacement, image.id);

  assert.equal(result.elements.length, 1);
  assert.equal(result.photo.id, image.id);
  assert.equal(result.photo.assetId, replacement.id);
  assert.deepEqual(
    [result.photo.x, result.photo.y, result.photo.width, result.photo.height],
    [image.x, image.y, image.width, image.height],
  );
});

test("placing a photo without a selected photo slot appends a default-sized image", () => {
  const heading = createTextElement("heading");
  const asset = { id: "asset-1", name: "portrait.jpg", src: "/assets/portrait.jpg" };

  const result = placePhotoOnPage([heading], asset, heading.id);

  assert.equal(result.elements.length, 2);
  assert.equal(result.elements[0], heading);
  assert.deepEqual(
    [result.photo.x, result.photo.y, result.photo.width, result.photo.height],
    [0.1, 0.1, 0.8, 0.8],
  );
});

test("admin page-count changes preserve existing pages and update the base count", () => {
  const document = sampleDocument(3);
  const originalFirstPage = document.pages[1];
  const expanded = resizeBookPageCount(document, 5);
  assert.equal(expanded.book.pageCount, 5);
  assert.equal(expanded.pageOrder.length, 6);
  assert.equal(expanded.pages.find((page) => page.id === originalFirstPage.id).elements[0].text, "Page 1");
  assert.equal(document.book.pageCount, 3);
  assert.equal(resizeBookPageCount(document, 0), null);

  const reduced = resizeBookPageCount(expanded, 2);
  assert.equal(reduced.book.pageCount, 2);
  assert.equal(reduced.pages.length, 3);
});

test("preview fills photo slots with temporary dummy images without changing saved content", () => {
  const document = sampleDocument(1);
  const page = document.pages[1];
  page.elements = [{ id: "slot", type: "shape", shape: "photo-placeholder", x: 0.1, y: 0.2, width: 0.7, height: 0.6 }];

  const preview = createPreviewDocument(document);

  assert.equal(preview.pages[1].elements[0].type, "image");
  assert.match(preview.pages[1].elements[0].src, /^data:image\/svg\+xml,/);
  assert.deepEqual(
    ["x", "y", "width", "height"].map((key) => preview.pages[1].elements[0][key]),
    ["x", "y", "width", "height"].map((key) => page.elements[0][key]),
  );
  assert.equal(document.pages[1].elements[0].type, "shape");
});

test("photo-slot review reports only interior pages without images or placeholders", () => {
  const document = sampleDocument(2);
  document.pages[1].elements = [{ id: "slot", type: "shape", shape: "photo-placeholder" }];
  assert.deepEqual(pagesWithoutPhotoSlots(document), ["Page 2"]);
});
