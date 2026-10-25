export function getInteriorPages(document) {
  const pagesById = new Map((document?.pages ?? []).map((page) => [page.id, page]));
  return (document?.pageOrder ?? [])
    .map((id) => pagesById.get(id))
    .filter((page) => page && page.type !== "cover");
}

export function getPageLabel(page, document) {
  if (page.type === "cover") return "Cover";
  const pageNumber = getInteriorPages(document).findIndex((item) => item.id === page.id);
  return pageNumber >= 0 ? `Page ${pageNumber + 1}` : page.label;
}

export function getPagePosition(page, document) {
  if (page.type === "cover") return "Cover";
  const interiorPages = getInteriorPages(document);
  const pageNumber = interiorPages.findIndex((item) => item.id === page.id);
  return pageNumber >= 0 ? `Page ${pageNumber + 1} of ${interiorPages.length}` : page.label;
}
