import assert from "node:assert/strict";
import test from "node:test";
import { formatCurrency } from "./money.js";

test("formats catalog prices according to their currency", () => {
  assert.equal(formatCurrency(6500, "PKR"), "PKR\u00a06,500");
  assert.equal(formatCurrency(3.99, "USD"), "$3.99");
});

test("preserves the supplied currency and handles invalid amounts safely", () => {
  assert.equal(formatCurrency(42.5, "USD"), "$42.50");
  assert.equal(formatCurrency(Number.NaN, "PKR"), "Price unavailable");
});
