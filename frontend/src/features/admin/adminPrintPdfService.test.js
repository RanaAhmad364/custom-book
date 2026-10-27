import assert from "node:assert/strict";
import test from "node:test";
import { loadAdminPrintOrderPdf } from "./adminService.js";

test("admin print PDF service requests an encoded order path and returns the signed URL", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ url: "/admin/orders/print/order-1/pdf/signed-token", expiresInSeconds: 3600 }),
    };
  };
  try {
    const result = await loadAdminPrintOrderPdf("order/1");
    assert.equal(calls[0].url, "/api/v1/admin/orders/print/order%2F1/pdf");
    assert.equal(calls[0].options.credentials, "include");
    assert.equal(result.expiresInSeconds, 3600);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("admin print PDF service rejects a response without a signed URL", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({ fileName: "order.pdf" }),
  });
  try {
    await assert.rejects(loadAdminPrintOrderPdf("order-1"), /invalid response/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
