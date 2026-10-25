import assert from "node:assert/strict";
import test from "node:test";
import { csrfHeaders, hasCsrfToken } from "./csrf.js";

test("does not attempt session refresh without a browser refresh CSRF cookie", () => {
  assert.equal(hasCsrfToken("refresh"), false);
  assert.deepEqual(csrfHeaders("refresh"), {});
});

test("includes the matching CSRF token when a cookie exists", () => {
  const originalDocument = globalThis.document;
  globalThis.document = { cookie: "csrf_access_token=access-value; csrf_refresh_token=refresh-value" };

  try {
    assert.equal(hasCsrfToken("refresh"), true);
    assert.deepEqual(csrfHeaders("refresh"), { "X-CSRF-TOKEN": "refresh-value" });
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});
