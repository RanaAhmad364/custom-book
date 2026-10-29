import test from "node:test";
import assert from "node:assert/strict";

import { paypalPaymentService } from "./paypalPaymentService.js";

test("PayPal order service creates an SDK order without client-supplied prices", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url: String(url), options };
    return new Response(JSON.stringify({
      paypalOrderId: "PAYPAL-SDK-ORDER",
      chargedAmountUsd: "10.08",
      rate: "0.00360000",
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  const result = await paypalPaymentService.createOrder("payment-123");
  assert.equal(result.paypalOrderId, "PAYPAL-SDK-ORDER");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.body, undefined);
  assert.match(request.url, /\/payments\/payment-123\/paypal\/create-order$/);
});

test("PayPal capture service sends only the PayPal order ID", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url: String(url), options };
    return new Response(JSON.stringify({ status: "successful" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await paypalPaymentService.captureOrder("payment-123", "PAYPAL-SDK-ORDER");
  assert.equal(result.status, "successful");
  assert.match(request.url, /\/payments\/payment-123\/paypal\/capture-order$/);
  assert.deepEqual(JSON.parse(request.options.body), { paypalOrderId: "PAYPAL-SDK-ORDER" });
});
