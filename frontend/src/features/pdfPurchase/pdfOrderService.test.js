import test from "node:test";
import assert from "node:assert/strict";
import { canDownloadPdf, normalizePdfOrder } from "../../services/pdfOrderService.js";

const baseOrder = {
  id: "pdf-order-1",
  paymentStatus: "successful",
  generationStatus: "ready",
  downloadUrl: "https://downloads.example.test/book.pdf",
};

test("PDF download requires confirmed payment, completed generation, and a server URL", () => {
  assert.equal(canDownloadPdf(normalizePdfOrder(baseOrder)), true);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, paymentStatus: "pending" })), false);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, generationStatus: "generating" })), false);
  assert.equal(canDownloadPdf(normalizePdfOrder({ ...baseOrder, downloadUrl: null })), false);
});

test("non-secure external download URLs are not exposed", () => {
  const order = normalizePdfOrder({ ...baseOrder, downloadUrl: "http://downloads.example.test/book.pdf" });
  assert.equal(order.downloadUrl, null);
  assert.equal(canDownloadPdf(order), false);
});

test("unknown payment and generation states are rejected", () => {
  assert.throws(() => normalizePdfOrder({ ...baseOrder, paymentStatus: "paid-in-browser" }), /unsupported/);
  assert.throws(() => normalizePdfOrder({ ...baseOrder, generationStatus: "almost-ready" }), /unsupported/);
});

test("missing order amount does not become a zero-price order", () => {
  assert.equal(normalizePdfOrder({ ...baseOrder, amount: null }).amount, null);
});
