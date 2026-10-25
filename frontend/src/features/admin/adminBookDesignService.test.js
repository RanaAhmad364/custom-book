import assert from "node:assert/strict";
import test from "node:test";
import {
  getAdminBookDesign,
  publishAdminBookDesign,
  saveAdminBookDesign,
} from "./adminService.js";

function mockFetch(responses, calls) {
  return async (url, options) => {
    calls.push({ url, options });
    const data = responses.shift();
    return {
      ok: true,
      status: 200,
      headers: { get: () => data.version ? `"${data.version}"` : null },
      json: async () => data,
    };
  };
}

test("admin design service uses version preconditions for saves and publication", async () => {
  const calls = [];
  const template = (version) => ({
    id: "template-1",
    version,
    published: version > 2,
    designDocument: { schemaVersion: 1, metadata: { title: "Master" }, pages: [] },
  });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch([
    { product: { id: "product-1" }, template: template(1) },
    { product: { id: "product-1" }, template: template(2) },
    { product: { id: "product-1" }, template: template(3) },
  ], calls);
  try {
    const initial = await getAdminBookDesign("product-1");
    assert.equal(initial.version, 1);
    await saveAdminBookDesign("product-1", { schemaVersion: 1, metadata: { title: "Saved" } });
    const published = await publishAdminBookDesign("product-1");

    assert.equal(published.published, true);
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].url, "/api/v1/admin/books/product-1/design");
    assert.equal(calls[1].options.headers["If-Match"], '"1"');
    assert.equal(calls[2].options.headers["If-Match"], '"2"');
    assert.equal(calls[2].url, "/api/v1/admin/books/product-1/design/publish");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
