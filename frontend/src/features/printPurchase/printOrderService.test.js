import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { normalizePrintOrder, normalizePrintQuote, printOrderService } from "../../services/printOrderService.js";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
const validQuote = {
  id: "quote-1",
  currency: "USD",
  bookPrice: 28,
  printingCharge: 6,
  additionalPages: 2,
  shipping: 8,
  discount: 0,
  taxApplicable: true,
  tax: 3.52,
  total: 47.52,
  productionEstimate: "2026-11-02",
  deliveryEstimate: "2026-11-12",
};

test("print quote uses validated server-calculated line items and dates", () => {
  const quote = normalizePrintQuote({
    ...validQuote,
    usdAmount: "10.36",
    exchangeRate: "0.0037",
  });
  assert.equal(quote.total, 47.52);
  assert.equal(quote.currency, "USD");
  assert.equal(quote.productionEstimate, "2026-11-02");
  assert.equal(quote.taxApplicable, true);
  assert.equal(quote.usdAmount, 10.36);
  assert.equal(quote.exchangeRate, "0.0037");
});

test("print quote rejects missing amounts, invalid tax flags, and missing estimates", () => {
  assert.throws(() => normalizePrintQuote({ ...validQuote, total: undefined }), /omitted total/);
  assert.throws(() => normalizePrintQuote({ ...validQuote, taxApplicable: undefined }), /specify whether tax applies/);
  assert.throws(() => normalizePrintQuote({ ...validQuote, deliveryEstimate: "" }), /omitted production or delivery estimates/);
});

test("print quote represents non-applicable tax without inventing a tax charge", () => {
  const quote = normalizePrintQuote({ ...validQuote, taxApplicable: false, tax: null });
  assert.equal(quote.tax, 0);
  assert.equal(quote.taxApplicable, false);
  assert.throws(() => normalizePrintQuote({ ...validQuote, taxApplicable: false, tax: 1 }), /included tax while marking it as not applicable/);
});

test("print order accepts only backend payment and production states", () => {
  const order = normalizePrintOrder({
    id: "order-1",
    paymentStatus: "successful",
    productionStatus: "In Production",
    quote: validQuote,
  });
  assert.equal(order.productionStatus, "in_production");
  assert.equal(order.checkoutUrl, null);
  assert.throws(() => normalizePrintOrder({ ...order, paymentStatus: "paid" }), /unsupported payment status/);
  assert.equal(normalizePrintOrder({ ...order, productionStatus: "printed" }).productionStatus, "printed");
  assert.equal(normalizePrintOrder({ ...order, productionStatus: "pending_payment" }).productionStatus, "pending_payment");
  assert.throws(() => normalizePrintOrder({ ...order, productionStatus: "forged" }), /unsupported production status/);
  assert.equal(normalizePrintOrder({ ...order, paymentStatus: "refunded" }).paymentStatus, "refunded");
});

test("print order detail preserves customer timeline and shipment data", async () => {
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({
      id: "order-tracking",
      paymentStatus: "successful",
      productionStatus: "shipped",
      quote: validQuote,
      statusHistory: [{ id: "history-1", status: "shipped", createdAt: "2026-03-01T10:00:00Z" }],
      shipment: { trackingNumber: "TRACK-123", shippedAt: "2026-03-01T10:00:00Z" },
      shippingAddress: { fullName: "Book Buyer", city: "Lahore", country: "PK" },
    }),
  });
  const order = await printOrderService.getOrder("order-tracking");
  assert.equal(order.statusHistory[0].status, "shipped");
  assert.equal(order.shipment.trackingNumber, "TRACK-123");
  assert.equal(order.shippingAddress.city, "Lahore");
});

test("unpaid print orders can be cancelled and failed print PDFs can be retried", async () => {
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    const payload = url.endsWith("/cancel")
      ? {
        id: "order-pending",
        paymentStatus: "failed",
        productionStatus: "cancelled",
        quote: validQuote,
      }
      : { job: { id: "print-job", status: "queued" } };
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => payload,
    };
  };
  const cancelled = await printOrderService.cancelUnpaidOrder("order-pending");
  const retried = await printOrderService.retryPrintPdf("order-paid");
  assert.equal(cancelled.productionStatus, "cancelled");
  assert.equal(retried.job.status, "queued");
  assert.match(requests[0].url, /\/print\/orders\/order-pending\/cancel$/);
  assert.match(requests[1].url, /\/print\/orders\/order-paid\/retry-pdf$/);
  assert.equal(requests[0].options.method, "POST");
  assert.equal(requests[1].options.method, "POST");
});

test("checkout links must use HTTPS or the current origin and are only exposed while pending", () => {
  const pending = normalizePrintOrder({
    id: "order-2",
    paymentStatus: "pending",
    productionStatus: "order_placed",
    checkoutUrl: "javascript:alert(1)",
    quote: validQuote,
  });
  const successful = normalizePrintOrder({
    id: "order-3",
    paymentStatus: "successful",
    productionStatus: "payment_confirmed",
    checkoutUrl: "https://payments.example/checkout",
    quote: validQuote,
  });
  assert.equal(pending.checkoutUrl, null);
  assert.equal(successful.checkoutUrl, null);
});

test("print payment retry targets the existing payment and order", async () => {
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
        id: "print-order-existing",
        paymentId: "payment-existing",
        paymentStatus: "pending",
        productionStatus: "order_placed",
        checkoutUrl: "https://www.sandbox.paypal.com/checkoutnow?token=retry",
        quote: validQuote,
      }),
    };
  };
  const retried = await printOrderService.retryPayment("payment-existing", "paypal");
  assert.match(requestUrl, /\/payments\/payment-existing\/retry$/);
  assert.equal(requestBody.provider, "paypal");
  assert.equal(retried.id, "print-order-existing");
  assert.equal(retried.checkoutUrl, "https://www.sandbox.paypal.com/checkoutnow?token=retry");
});
