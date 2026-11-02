import assert from "node:assert/strict";
import test from "node:test";
import {
  loadAdminPrintOrderPdf,
  refundAdminReviewCapture,
  retryAdminPrintOrderPdf,
} from "./adminService.js";

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

test("admin print PDF retry targets the paid order retry endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    assert.equal(options.method, "POST");
    return {
      ok: true,
      status: 202,
      headers: { get: () => null },
      json: async () => ({ job: { id: "job-1", status: "queued" } }),
    };
  };
  try {
    const job = await retryAdminPrintOrderPdf("order-1");
    assert.equal(requestUrl, "/api/v1/admin/orders/print/order-1/retry-pdf");
    assert.equal(job.status, "queued");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("admin capture refund sends the recorded capture amount with an idempotency key", async () => {
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      status: 202,
      headers: { get: () => null },
      json: async () => ({ refund: { status: "succeeded" } }),
    };
  };
  try {
    const result = await refundAdminReviewCapture({
      id: "payment-1",
      providerCaptureId: "capture-1",
      providerCaptureAmount: "8.50",
      providerCaptureCurrency: "EUR",
      currency: "USD",
    });
    assert.equal(request.url, "/api/v1/payments/payment-1/refunds");
    assert.equal(JSON.parse(request.options.body).amount, "8.50");
    assert.equal(request.options.headers["Idempotency-Key"], "review-capture-refund:payment-1:capture-1");
    assert.equal(result.status, "succeeded");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
