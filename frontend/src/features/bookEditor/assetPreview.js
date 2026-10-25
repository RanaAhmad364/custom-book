export function refreshAssetSources(document, refreshedDocument) {
  if (!document || !refreshedDocument) return document;
  const sourcesById = new Map(
    (refreshedDocument.assets ?? [])
      .filter((asset) => asset?.id && asset.src)
      .map((asset) => [asset.id, asset.src]),
  );
  let changed = false;
  const assets = (document.assets ?? []).map((asset) => {
    const src = sourcesById.get(asset.id);
    if (!src || src === asset.src) return asset;
    changed = true;
    return { ...asset, src };
  });
  const pages = (document.pages ?? []).map((page) => {
    let pageChanged = false;
    const elements = (page.elements ?? []).map((element) => {
      const src = element.type === "image" ? sourcesById.get(element.assetId) : undefined;
      if (!src || src === element.src) return element;
      pageChanged = true;
      return { ...element, src };
    });
    if (!pageChanged) return page;
    changed = true;
    return { ...page, elements };
  });

  return changed ? { ...document, assets, pages } : document;
}
