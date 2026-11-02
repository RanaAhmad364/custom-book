import assert from "node:assert/strict";
import test from "node:test";
import { paypalChargeSummary } from "./paypalChargeSummary.js";

test("USD PayPal orders display only the USD amount", () => {
  assert.equal(paypalChargeSummary({
    orderCurrency: "USD",
    usdAmount: "5.99",
    pkrAmount: "5.99",
    exchangeRate: "1",
  }), "You will be charged $5.99 USD.");
});

test("PKR PayPal orders show the PKR amount only with a conversion snapshot", () => {
  assert.equal(paypalChargeSummary({
    orderCurrency: "PKR",
    usdAmount: "10.08",
    pkrAmount: "2800",
    exchangeRate: "0.0036",
  }), "You will be charged $10.08 USD (PKR 2,800.00).");
  assert.equal(paypalChargeSummary({
    orderCurrency: "PKR",
    usdAmount: "10.08",
    pkrAmount: "2800",
    exchangeRate: null,
  }), "You will be charged $10.08 USD.");
});
