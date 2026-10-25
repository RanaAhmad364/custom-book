import { getPageLabel } from "./pageNavigation.js";

export const REQUIRED_BLEED_INCHES = 0.125;
export const SAFE_MARGIN = 0.07;

function estimateTextLines(text, element, pageWidth, pageHeight) {
  const fontSize = Math.max(0.008, element.fontSize ?? 0.025) * pageHeight;
  const charsPerLine = Math.max(1, Math.floor((element.width * pageWidth) / (fontSize * 0.55)));
  return String(text ?? "").split("\n").reduce((total, paragraph) => (
    total + Math.max(1, Math.ceil(paragraph.length / charsPerLine))
  ), 0);
}

export function analyzeBook(document, assetDimensions = {}) {
  const pagesById = new Map((document?.pages ?? []).map((page) => [page.id, page]));
  const pageOrder = document?.pageOrder ?? [];
  const orderedPages = pageOrder.map((id) => pagesById.get(id)).filter(Boolean);
  const coverPage = orderedPages.find((page) => page.type === "cover");
  const interiorPages = orderedPages.filter((page) => page.type !== "cover");
  const assetsById = new Map((document?.assets ?? []).map((asset) => [asset.id, asset]));
  const bookSize = document?.book?.size ?? {};
  const pageWidth = Number(bookSize.width) || 0;
  const pageHeight = Number(bookSize.height) || 0;
  const issues = [];
  const addIssue = (issue) => {
    const page = issue.pageId ? pagesById.get(issue.pageId) : null;
    const pageLabel = page && page.type !== "cover" ? getPageLabel(page, document) : issue.pageLabel;
    issues.push({ ...issue, pageLabel, id: `${issue.code}:${issue.pageId ?? "book"}:${issues.length}` });
  };

  if (!coverPage || document?.cover?.pageId && document.cover.pageId !== coverPage.id) {
    addIssue({ code: "missing-cover", severity: "blocking", message: "The book cover is missing or no longer linked to its cover page." });
  }

  if (pageOrder.length !== (document?.pages ?? []).length || orderedPages.length !== pageOrder.length) {
    addIssue({ code: "page-order", severity: "blocking", message: "The page order does not match the pages in this book." });
  }

  if (Number(document?.book?.pageCount) !== interiorPages.length) {
    addIssue({
      code: "page-count",
      severity: "blocking",
      message: `Book setup says ${document?.book?.pageCount ?? 0} pages, but the document has ${interiorPages.length} interior pages.`,
    });
  }

  if (!pageWidth || !pageHeight) {
    addIssue({ code: "dimensions", severity: "blocking", message: "Book dimensions are missing or invalid." });
  }

  const coverPhotoId = document?.cover?.design?.front?.photoAssetId;
  if (coverPhotoId) {
    const coverAsset = assetsById.get(coverPhotoId);
    if (!coverAsset?.src) {
      addIssue({ code: "missing-cover-photo", severity: "blocking", message: "The selected cover photo is no longer available.", pageId: coverPage?.id, pageLabel: "Front cover" });
    } else {
      const dimensions = assetDimensions[coverPhotoId] ?? coverAsset;
      if (dimensions?.width && dimensions?.height && pageWidth && pageHeight) {
        const effectiveDpi = Math.min(dimensions.width / pageWidth, dimensions.height / pageHeight);
        if (effectiveDpi < 200) {
          addIssue({
            code: "low-resolution",
            severity: "print",
            message: `The cover photo may look soft in print (${Math.round(effectiveDpi)} effective DPI).`,
            pageId: coverPage?.id,
            pageLabel: "Front cover",
          });
        }
      }
    }
  }

  for (const page of orderedPages) {
    if (page.type !== "cover" && page.elements.length === 0) {
      addIssue({ code: "empty-page", severity: "warning", message: `${page.label} is empty.`, pageId: page.id, pageLabel: page.label });
    }

    for (const element of page.elements ?? []) {
      if (element.type === "shape" && element.shape === "photo-placeholder") {
        addIssue({ code: "missing-photo", severity: "blocking", message: "A photo placeholder has not been filled.", pageId: page.id, pageLabel: page.label });
        continue;
      }

      if (element.type === "image") {
        const asset = assetsById.get(element.assetId);
        const dimensions = assetDimensions[element.assetId] ?? asset;
        if (!asset?.src && !element.src || dimensions?.missing) {
          addIssue({ code: "missing-photo", severity: "blocking", message: `${element.name ?? "A photo"} is missing.`, pageId: page.id, pageLabel: page.label });
          continue;
        }

        if (dimensions?.width && dimensions?.height && pageWidth && pageHeight) {
          const dpiX = dimensions.width / Math.max(0.01, element.width * pageWidth);
          const dpiY = dimensions.height / Math.max(0.01, element.height * pageHeight);
          if (Math.min(dpiX, dpiY) < 200) {
            addIssue({
              code: "low-resolution",
              severity: "print",
              message: `${element.name ?? "A photo"} may look soft in print (${Math.round(Math.min(dpiX, dpiY))} effective DPI).`,
              pageId: page.id,
              pageLabel: page.label,
            });
          }
        }
      }

      const right = element.x + element.width;
      const bottom = element.y + element.height;
      if (right > 1.005 || bottom > 1.005 || element.x < -0.005 || element.y < -0.005) {
        addIssue({ code: "overflow", severity: "blocking", message: "An element extends beyond the page edge.", pageId: page.id, pageLabel: page.label });
      }

      if (element.type === "text") {
        const lineCount = estimateTextLines(element.text, element, pageWidth || 1, pageHeight || 1);
        const lineHeight = (element.fontSize ?? 0.025) * (element.lineHeight ?? 1.2) * 1.15;
        if (lineCount * lineHeight > element.height * 1.08) {
          addIssue({ code: "text-overflow", severity: "blocking", message: "Text may not fit inside its text box.", pageId: page.id, pageLabel: page.label });
        }
        if (element.x < SAFE_MARGIN || element.y < SAFE_MARGIN || right > 1 - SAFE_MARGIN || bottom > 1 - SAFE_MARGIN) {
          addIssue({ code: "safe-margin", severity: "print", message: "Text is close to or outside the recommended safe margin.", pageId: page.id, pageLabel: page.label });
        }
      }
    }
  }

  const bleed = Number(document?.cover?.design?.bleedInches ?? document?.cover?.bleedInches) || 0;
  if (bleed < REQUIRED_BLEED_INCHES) {
    addIssue({
      code: "bleed",
      severity: "print",
      message: `Print bleed is ${bleed || "not set"} in; at least ${REQUIRED_BLEED_INCHES} in is recommended.`,
    });
  }

  const blockingIssues = issues.filter((issue) => issue.severity === "blocking");
  const printIssues = issues.filter((issue) => issue.severity === "print" || issue.severity === "warning");
  return {
    issues,
    pageCount: interiorPages.length,
    dimensions: pageWidth && pageHeight ? `${pageWidth} × ${pageHeight} in` : "Not set",
    pdfReady: blockingIssues.length === 0,
    printingReady: blockingIssues.length === 0 && printIssues.length === 0,
    needsAttention: issues.length > 0,
  };
}
