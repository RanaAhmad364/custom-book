import assert from "node:assert/strict";
import test from "node:test";
import { pricingRecordDefaults, validatePricingRecord } from "./pricingForm.js";

test("pricing record defaults cover each supported create form", () => {
  for (const kind of ["tier", "pagePricing", "shipping", "size", "cover", "paper", "variant"]) {
    const record = pricingRecordDefaults(kind);
    assert.equal(record.kind, kind);
    assert.equal(record.__create, true);
  }
});

test("pricing tier validation checks required fields, amount, and currency", () => {
  const tier = pricingRecordDefaults("tier");
  assert.deepEqual(validatePricingRecord("tier", tier), {
    code: "Enter a tier code.",
    name: "Enter a tier name.",
  });
  assert.deepEqual(validatePricingRecord("tier", {
    ...tier,
    code: "BASIC",
    name: "Basic",
  }), {});
  assert.equal(validatePricingRecord("tier", {
    ...tier,
    code: "BASIC",
    name: "Basic",
    basePrice: "-1",
    currency: "US",
  }).basePrice, "Enter a non-negative base price with up to two decimal places.");
});

test("page pricing rejects invalid and inverted ranges", () => {
  const pagePricing = pricingRecordDefaults("pagePricing");
  assert.deepEqual(validatePricingRecord("pagePricing", pagePricing), {
    tierId: "Choose a pricing tier.",
  });
  assert.equal(validatePricingRecord("pagePricing", {
    ...pagePricing,
    tierId: "tier-id",
    minimumPages: 40,
    maximumPages: 24,
  }).maximumPages, "Maximum pages must be at least the minimum.");
  assert.deepEqual(validatePricingRecord("pagePricing", {
    ...pagePricing,
    tierId: "tier-id",
  }), {});
});

test("shipping validation accepts country-level rates and rejects invalid delivery ranges", () => {
  const shipping = {
    ...pricingRecordDefaults("shipping"),
    countryCode: "US",
    serviceCode: "standard",
    serviceName: "Standard delivery",
    price: "5.00",
    currency: "PKR",
    estimatedDaysMin: 8,
    estimatedDaysMax: 3,
  };
  assert.equal(validatePricingRecord("shipping", shipping).estimatedDaysMax,
    "Maximum delivery days must be at least the minimum.");
  assert.deepEqual(validatePricingRecord("shipping", { ...shipping, estimatedDaysMax: 10 }), {});
});

test("variant validation requires a complete, non-negative priced configuration", () => {
  const variant = {
    ...pricingRecordDefaults("variant"),
    sku: "BOOK-8-LINEN",
    productId: "book-id",
    sizeId: "size-id",
    coverTypeId: "cover-id",
    paperTypeId: "paper-id",
    currency: "PKR",
  };
  assert.deepEqual(validatePricingRecord("variant", variant), {});
  assert.equal(validatePricingRecord("variant", { ...variant, basePrice: "-0.01" }).basePrice,
    "Enter a non-negative variant price with up to two decimal places.");
});

test("existing rules and discount records retain client-side edit validation", () => {
  assert.deepEqual(validatePricingRecord("rule", {
    name: "Holiday adjustment",
    type: "percent",
    amount: "10",
  }), {});
  assert.equal(validatePricingRecord("discount", {
    code: "SAVE10",
    type: "percent",
    value: "101",
    maximumUses: 5,
  }).value, "Percentage discounts cannot exceed 100.");
});
