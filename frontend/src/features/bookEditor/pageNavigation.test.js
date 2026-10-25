import test from "node:test";
import assert from "node:assert/strict";
import { getInteriorPages, getPageLabel, getPagePosition } from "./pageNavigation.js";

const document = {
  pages: [
    { id: "cover", type: "cover", label: "Cover" },
    { id: "first", type: "page", label: "Page 1" },
    { id: "second", type: "page", label: "Page 2" },
  ],
  pageOrder: ["cover", "second", "first"],
};

test("page labels and positions follow the current order without counting the cover as an interior page", () => {
  assert.deepEqual(getInteriorPages(document).map((page) => page.id), ["second", "first"]);
  assert.equal(getPageLabel(document.pages[0], document), "Cover");
  assert.equal(getPageLabel(document.pages[2], document), "Page 1");
  assert.equal(getPagePosition(document.pages[1], document), "Page 2 of 2");
  assert.equal(getPagePosition(document.pages[0], document), "Cover");
});

test("unknown page labels use the saved label and an empty book has no interior pages", () => {
  assert.equal(getPageLabel({ id: "missing", label: "Recovered page" }, document), "Recovered page");
  assert.deepEqual(getInteriorPages({ pages: [], pageOrder: [] }), []);
});
