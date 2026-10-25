import test from "node:test";
import assert from "node:assert/strict";
import { refreshAssetSources } from "./assetPreview.js";

test("refreshes expired image URLs from the latest authorized project response", () => {
  const document = {
    assets: [{ id: "asset-1", assetKey: "projects/book/photo.jpg", src: "/expired" }],
    pages: [{
      id: "page-1",
      elements: [{ id: "image-1", type: "image", assetId: "asset-1", src: "/expired" }],
    }],
  };
  const refreshed = {
    assets: [{ id: "asset-1", src: "/fresh-signed-url" }],
  };

  const result = refreshAssetSources(document, refreshed);

  assert.equal(result.assets[0].src, "/fresh-signed-url");
  assert.equal(result.pages[0].elements[0].src, "/fresh-signed-url");
  assert.equal(document.assets[0].src, "/expired");
});

test("does not alter content or asset URLs absent from the refresh response", () => {
  const document = {
    assets: [{ id: "asset-1", src: "/existing" }],
    pages: [{ id: "page-1", elements: [{ id: "image-1", type: "image", assetId: "missing", src: "/keep" }] }],
  };

  assert.equal(refreshAssetSources(document, { assets: [] }), document);
});
