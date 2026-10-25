import test from "node:test";
import assert from "node:assert/strict";
import { canDownloadPdf, normalizePdfOrder } from "../../services/pdfOrderService.js";

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
