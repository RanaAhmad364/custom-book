import test from "node:test";
import assert from "node:assert/strict";
import { getPageThumbnailSize } from "./pageThumbnail.js";

test("page thumbnail dimensions preserve portrait orientation within the preview bounds", () => {
  const size = getPageThumbnailSize({ width: 8.5, height: 11 });

  assert.ok(size.width < size.height);
  assert.ok(size.width <= 48);
  assert.ok(size.height <= 42);
  assert.equal(size.width / size.height, 8.5 / 11);
});

test("page thumbnail dimensions preserve landscape orientation within the preview bounds", () => {
  const size = getPageThumbnailSize({ width: 11, height: 8.5 });

  assert.ok(size.width > size.height);
  assert.ok(size.width <= 48);
  assert.ok(size.height <= 42);
  assert.equal(size.width / size.height, 11 / 8.5);
});

test("page thumbnail dimensions have a safe fallback for invalid book sizes", () => {
  assert.deepEqual(getPageThumbnailSize({ width: 0, height: 11 }), { width: 48, height: 42 });
});
