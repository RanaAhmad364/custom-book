import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { canDownloadPdf, normalizePdfOrder, pdfOrderService } from "../../services/pdfOrderService.js";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
const baseOrder = {
  id: "pdf-order-1",
  paymentStatus: "successful",
  generationStatus: "ready",
  downloadId: "entitlement-1",
  downloadUrl: "https://downloads.example.test/book.pdf",
};

test("PDF download requires confirmed payment, completed generation, and an entitlement", () => {
  assert.equal(canDownloadPdf(normalizePdfOrder(baseOrder)), true);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, paymentStatus: "pending" })), false);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, generationStatus: "generating" })), false);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, downloadId: null })), false);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, paymentStatus: "refunded" })), false);
});

test("refunded payment states are preserved and accepted", () => {
  const order = normalizePdfOrder({ ...baseOrder, paymentStatus: "partially_refunded" });
  assert.equal(order.paymentStatus, "partially_refunded");
  assert.equal(order.downloadUrl, null);
});

test("non-secure external download URLs are not exposed", () => {
  const order = normalizePdfOrder({ ...baseOrder, downloadUrl: "http://downloads.example.test/book.pdf" });
  assert.equal(order.downloadUrl, null);
  assert.equal(canDownloadPdf(order), true);
});

test("unknown payment and generation states are rejected", () => {
  assert.throws(() => normalizePdfOrder({ ...baseOrder, paymentStatus: "paid-in-browser" }), /unsupported/);
  assert.throws(() => normalizePdfOrder({ ...baseOrder, generationStatus: "almost-ready" }), /unsupported/);
});

test("missing order amount does not become a zero-price order", () => {
  assert.equal(normalizePdfOrder({ ...baseOrder, amount: null }).amount, null);
});

test("payment currency conversion snapshot is preserved for the customer", () => {
  const order = normalizePdfOrder({
    ...baseOrder,
    paymentStatus: "pending",
    generationStatus: "not_started",
    amount: "2800.00",
    currency: "PKR",
    pkrAmount: "2800.00",
    usdAmount: "10.36",
    exchangeRate: "0.00370000",
  });
  assert.equal(order.pkrAmount, "2800.00");
  assert.equal(order.usdAmount, "10.36");
  assert.equal(order.exchangeRate, "0.00370000");
});

test("PDF offer displays the USD equivalent calculated by the backend", async () => {
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({
      amount: "2800.00",
      currency: "PKR",
      usdAmount: "10.36",
      exchangeRate: "0.0037",
    }),
  });
  const offer = await pdfOrderService.getOffer("project-1");
  assert.equal(offer.amount, 2800);
  assert.equal(offer.usdAmount, 10.36);
  assert.equal(offer.exchangeRate, "0.0037");
});

test("retry uses the existing payment instead of creating a second PDF order", async () => {
  let requestUrl = "";
  let requestBody;
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    requestBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        id: "pdf-order-existing",
        paymentId: "payment-existing",
        paymentStatus: "pending",
        generationStatus: "not_started",
        checkoutUrl: "https://www.sandbox.paypal.com/checkoutnow?token=retry",
      }),
    };
  };
  const retried = await pdfOrderService.retryPayment("payment-existing", "paypal");
  assert.match(requestUrl, /\/payments\/payment-existing\/retry$/);
  assert.equal(requestBody.provider, "paypal");
  assert.equal(retried.id, "pdf-order-existing");
  assert.equal(retried.checkoutUrl, "https://www.sandbox.paypal.com/checkoutnow?token=retry");
});

test("generation requests use the existing PDF order", async () => {
  const previousFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ job: { id: "job-1", status: "queued" } }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const job = await pdfOrderService.requestGeneration("pdf-order-1");
    assert.equal(job.id, "job-1");
    assert.match(requests[0].url, /\/pdf\/orders\/pdf-order-1\/generate$/);
    assert.equal(requests[0].options.method, "POST");
    assert.deepEqual(JSON.parse(requests[0].options.body), { profile: "digital" });
  } finally {
    globalThis.fetch = previousFetch;
  }
});
