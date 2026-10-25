import assert from "node:assert/strict";
import test from "node:test";
import { formatCurrency } from "./money.js";

test("formats catalog prices with their PKR currency", () => {
  assert.equal(formatCurrency(6500, "PKR"), "Rs\u00a06,500");
});

test("preserves the supplied currency and handles invalid amounts safely", () => {
  assert.equal(formatCurrency(42.5, "USD"), "US$42.50");
  assert.equal(formatCurrency(Number.NaN, "PKR"), "Price unavailable");
});
