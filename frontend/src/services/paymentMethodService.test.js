import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { paymentMethodService } from "./paymentMethodService.js";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("payment method discovery returns only validated provider options", async () => {
  let requestedUrl = "";
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      json: async () => ({
        currency: "PKR",
        items: [{ provider: "jazzcash", method: "jazzcash_wallet", label: "JazzCash wallet" }],
      }),
    };
  };

  const methods = await paymentMethodService.list("pkr");
  assert.match(requestedUrl, /currency=PKR$/);
  assert.deepEqual(methods, [{
    provider: "jazzcash",
    method: "jazzcash_wallet",
    label: "JazzCash wallet",
    id: "jazzcash:jazzcash_wallet",
  }]);
});

test("payment method discovery rejects malformed contracts and invalid currencies", async () => {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ currency: "USD", items: "not-an-array" }),
  });
  await assert.rejects(paymentMethodService.list("PKR"), /invalid method list/);
  await assert.rejects(paymentMethodService.list("US"), /valid currency is required/);
});
