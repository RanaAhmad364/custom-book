export function getPageThumbnailSize(pageSize, maxWidth = 48, maxHeight = 42) {
  const pageWidth = Number(pageSize?.width);
  const pageHeight = Number(pageSize?.height);
  if (!Number.isFinite(pageWidth) || !Number.isFinite(pageHeight) || pageWidth <= 0 || pageHeight <= 0) {
    return { width: maxWidth, height: maxHeight };
  }

  const scale = Math.min(maxWidth / pageWidth, maxHeight / pageHeight);
  return { width: pageWidth * scale, height: pageHeight * scale };
}
