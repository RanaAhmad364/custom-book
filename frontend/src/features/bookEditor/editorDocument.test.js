import test from "node:test";
import assert from "node:assert/strict";
import {
  createPage, createTextElement, duplicatePageRecord, removePage, reorderPageIds,
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
