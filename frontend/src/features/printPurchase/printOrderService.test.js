import test from "node:test";
import assert from "node:assert/strict";
import { normalizePrintOrder, normalizePrintQuote } from "../../services/printOrderService.js";

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
  const quote = normalizePrintQuote(validQuote);
  assert.equal(quote.total, 47.52);
  assert.equal(quote.currency, "USD");
  assert.equal(quote.productionEstimate, "2026-11-02");
  assert.equal(quote.taxApplicable, true);
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
  assert.throws(() => normalizePrintOrder({ ...order, productionStatus: "printed" }), /unsupported production status/);
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
