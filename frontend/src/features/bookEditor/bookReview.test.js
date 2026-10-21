import test from "node:test";
import assert from "node:assert/strict";
import { analyzeBook, REQUIRED_BLEED_INCHES } from "./bookReview.js";

function sampleDocument() {
  return {
    book: { pageCount: 1, size: { width: 8, height: 8 } },
    cover: { pageId: "cover", design: { bleedInches: REQUIRED_BLEED_INCHES } },
    pageOrder: ["cover", "page-1"],
    pages: [
      { id: "cover", type: "cover", label: "Cover", elements: [] },
      { id: "page-1", type: "page", label: "Page 1", elements: [] },
    ],
    assets: [],
  };
}

test("review reads page count, empty pages, dimensions, and print bleed from the document", () => {
  const report = analyzeBook(sampleDocument());
  assert.equal(report.pageCount, 1);
  assert.equal(report.dimensions, "8 × 8 in");
  assert.equal(report.pdfReady, true);
  assert.equal(report.printingReady, false);
  assert.ok(report.issues.some((issue) => issue.code === "empty-page" && issue.pageId === "page-1"));
});

test("review detects missing photos and offers the source page id", () => {
  const document = sampleDocument();
  document.pages[1].elements.push({ type: "image", id: "photo", assetId: "missing", name: "portrait.jpg", x: 0.1, y: 0.1, width: 0.8, height: 0.8 });
  const report = analyzeBook(document);
  assert.equal(report.pdfReady, false);
  assert.ok(report.issues.some((issue) => issue.code === "missing-photo" && issue.pageId === "page-1"));
});

test("review flags low-resolution images using effective print density", () => {
  const document = sampleDocument();
  document.pages[1].elements.push({ type: "image", id: "photo", assetId: "asset", x: 0.1, y: 0.1, width: 0.8, height: 0.8 });
  document.assets.push({ id: "asset", src: "data:image/png;base64,AA==" });
  const report = analyzeBook(document, { asset: { width: 800, height: 800 } });
  assert.ok(report.issues.some((issue) => issue.code === "low-resolution" && issue.pageId === "page-1"));
});

test("review detects text overflow, unsafe margins, missing covers, and page-count mismatch", () => {
  const document = sampleDocument();
  document.pages[0].type = "page";
  document.cover.pageId = "missing";
  document.book.pageCount = 3;
  document.pages[1].elements.push({ type: "text", id: "text", text: "A long title that will wrap across too many lines", x: 0.01, y: 0.01, width: 0.1, height: 0.02, fontSize: 0.08, lineHeight: 1.2 });
  const report = analyzeBook(document);
  assert.ok(report.issues.some((issue) => issue.code === "missing-cover"));
  assert.ok(report.issues.some((issue) => issue.code === "page-count"));
  assert.ok(report.issues.some((issue) => issue.code === "text-overflow" && issue.pageId === "page-1"));
  assert.ok(report.issues.some((issue) => issue.code === "safe-margin" && issue.pageId === "page-1"));
});
