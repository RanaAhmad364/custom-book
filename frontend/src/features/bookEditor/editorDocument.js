export const EDITOR_WIDTH = 900;
export const EDITOR_HEIGHT = 900;

export function cloneDocument(document) {
  return structuredClone(document);
}

export function createPage(type = "page", index = 1, background = "#fffdf9") {
  return {
    id: crypto.randomUUID(),
    type,
    label: type === "cover" ? "Cover" : `Page ${index}`,
    background: { color: background },
    layout: "blank",
    elements: [],
  };
}

export function createTextElement(kind = "paragraph", content) {
  const defaults = {
    heading: { text: "Your story begins here", fontSize: 48 / EDITOR_HEIGHT, fontWeight: "600" },
    subheading: { text: "A moment worth remembering", fontSize: 30 / EDITOR_HEIGHT, fontWeight: "500" },
    paragraph: { text: "Add your words, a favorite memory, or a note for later.", fontSize: 22 / EDITOR_HEIGHT, fontWeight: "400" },
  };
  return {
    id: crypto.randomUUID(),
    type: "text",
    kind,
    text: content ?? defaults[kind].text,
    x: 0.1,
    y: kind === "heading" ? 0.16 : kind === "subheading" ? 0.24 : 0.3,
    width: 0.8,
    height: kind === "paragraph" ? 0.28 : 0.12,
    rotation: 0,
    fontFamily: "DM Sans",
    fontSize: defaults[kind].fontSize,
    fontWeight: defaults[kind].fontWeight,
    italic: false,
    underline: false,
    color: "#1d2824",
    alignment: "left",
    letterSpacing: 0,
    lineHeight: 1.2,
    opacity: 1,
    backgroundColor: "transparent",
    scaleY: 1,
  };
}

export function createShapeElement(shape = "rectangle") {
  return {
    id: crypto.randomUUID(),
    type: "shape",
    shape,
    x: 0.36,
    y: 0.36,
    width: 0.28,
    height: 0.28,
    rotation: 0,
    fill: shape === "circle" ? "#dce8e1" : "#eadfce",
    stroke: "#17483e",
    strokeWidth: 2,
    opacity: 1,
    rx: 0.02,
  };
}

export function createPhotoElement(asset, x = 0.1, y = 0.1, width = 0.8, height = 0.8) {
  return {
    id: crypto.randomUUID(),
    type: "image",
    assetId: asset.id,
    src: asset.src,
    name: asset.name,
    x,
    y,
    width,
    height,
    rotation: 0,
    opacity: 1,
    fit: "cover",
    cropX: 0.5,
    cropY: 0.5,
    borderColor: "#fffdf9",
    borderWidth: 0,
    borderRadius: 0,
    shadow: false,
  };
}

export function normalizeFabricObject(object, dimensions = { width: EDITOR_WIDTH, height: EDITOR_HEIGHT }) {
  const scaleX = object.scaleX ?? 1;
  const scaleY = object.scaleY ?? 1;
  const base = {
    id: object.elementId ?? crypto.randomUUID(),
    x: Math.max(0, (object.left ?? 0) / dimensions.width),
    y: Math.max(0, (object.top ?? 0) / dimensions.height),
    width: Math.max(0.01, ((object.width ?? 0) * scaleX) / dimensions.width),
    height: Math.max(0.01, ((object.height ?? 0) * scaleY) / dimensions.height),
    rotation: object.angle ?? 0,
    opacity: object.opacity ?? 1,
  };
  if (object.type === "i-text" || object.type === "textbox" || object.type === "text") {
    return {
      ...base,
      type: "text",
      kind: object.kind ?? "paragraph",
      text: object.text ?? "",
      fontFamily: object.fontFamily ?? "DM Sans",
      fontSize: (object.fontSize ?? 22) / dimensions.height,
      fontWeight: String(object.fontWeight ?? "400"),
      italic: Boolean(object.fontStyle === "italic"),
      underline: Boolean(object.underline),
      scaleY: object.scaleY ?? 1,
      color: object.fill ?? "#1d2824",
      alignment: object.textAlign ?? "left",
      letterSpacing: object.charSpacing ?? 0,
      lineHeight: object.lineHeight ?? 1.2,
      backgroundColor: object.backgroundColor ?? "transparent",
    };
  }
  if (object.type === "image") {
    return {
      ...base,
      type: "image",
      assetId: object.assetId ?? "",
      src: object.src ?? object.getSrc?.(),
      name: object.name ?? "Photo",
      fit: object.fit ?? "cover",
      zoom: object.zoom ?? 1,
      cropX: object.cropXNormalized ?? 0.5,
      cropY: object.cropYNormalized ?? 0.5,
      borderColor: object.stroke ?? "#fffdf9",
      borderWidth: (object.strokeWidth ?? 0) / dimensions.width,
      borderRadius: object.borderRadius ?? 0,
      shadow: Boolean(object.shadow),
    };
  }
  return {
    ...base,
    type: "shape",
    shape: object.shape ?? (object.type === "circle" ? "circle" : "rectangle"),
    fill: object.fill ?? "#dce8e1",
    stroke: object.stroke ?? "#17483e",
    strokeWidth: (object.strokeWidth ?? 0) / dimensions.width,
    rx: (object.rx ?? 0) / dimensions.width,
  };
}

export function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function reorderPageIds(pageOrder, movedId, beforeId) {
  const from = pageOrder.indexOf(movedId);
  if (from < 0 || !beforeId || movedId === beforeId) return pageOrder;
  const reordered = [...pageOrder];
  reordered.splice(from, 1);
  const target = reordered.indexOf(beforeId);
  if (target < 0) return pageOrder;
  reordered.splice(target, 0, movedId);
  return reordered;
}

export function duplicatePageRecord(source, label) {
  const copy = structuredClone(source);
  copy.id = crypto.randomUUID();
  copy.label = label;
  copy.elements = copy.elements.map((element) => ({ ...element, id: crypto.randomUUID() }));
  return copy;
}

export function removePage(document, pageId) {
  const targetIndex = document.pageOrder.indexOf(pageId);
  const target = document.pages.find((page) => page.id === pageId);
  if (!target || target.type === "cover") return null;
  const next = cloneDocument(document);
  next.pages = next.pages.filter((page) => page.id !== pageId);
  next.pageOrder = next.pageOrder.filter((id) => id !== pageId);
  next.book.pageCount = next.pageOrder.filter((id) => next.pages.find((page) => page.id === id)?.type !== "cover").length;
  return { document: next, nextActivePageId: next.pageOrder[Math.max(0, targetIndex - 1)] };
}

export const pageLayouts = [
  { id: "single", name: "Full-page photo", description: "One image, edge to edge.", slots: [{ x: 0.04, y: 0.04, width: 0.92, height: 0.92 }] },
  { id: "two", name: "Two photos", description: "A pair of moments, side by side.", slots: [{ x: 0.04, y: 0.05, width: 0.44, height: 0.9 }, { x: 0.52, y: 0.05, width: 0.44, height: 0.9 }] },
  { id: "three", name: "Three photos", description: "One hero with two companions.", slots: [{ x: 0.04, y: 0.05, width: 0.55, height: 0.9 }, { x: 0.63, y: 0.05, width: 0.33, height: 0.43 }, { x: 0.63, y: 0.52, width: 0.33, height: 0.43 }] },
  { id: "four", name: "Four photos", description: "A balanced little collage.", slots: [{ x: 0.04, y: 0.05, width: 0.44, height: 0.43 }, { x: 0.52, y: 0.05, width: 0.44, height: 0.43 }, { x: 0.04, y: 0.52, width: 0.44, height: 0.43 }, { x: 0.52, y: 0.52, width: 0.44, height: 0.43 }] },
  { id: "photo-text", name: "Photo + text", description: "A photograph with a personal note.", slots: [{ x: 0.04, y: 0.05, width: 0.53, height: 0.9 }], text: { x: 0.63, y: 0.3, width: 0.31, height: 0.42 } },
  { id: "editorial", name: "Editorial", description: "A quiet image and a clear caption.", slots: [{ x: 0.08, y: 0.08, width: 0.84, height: 0.62 }], text: { x: 0.08, y: 0.75, width: 0.8, height: 0.14 } },
  { id: "collage", name: "Collage", description: "Loose, playful photo groupings.", slots: [{ x: 0.08, y: 0.08, width: 0.5, height: 0.48 }, { x: 0.54, y: 0.17, width: 0.38, height: 0.34 }, { x: 0.25, y: 0.6, width: 0.55, height: 0.32 }] },
  { id: "minimal", name: "Minimal", description: "Space to let one moment breathe.", slots: [{ x: 0.14, y: 0.1, width: 0.72, height: 0.7 }], text: { x: 0.14, y: 0.84, width: 0.72, height: 0.08 } },
  { id: "magazine", name: "Magazine", description: "A bold image and headline.", slots: [{ x: 0.04, y: 0.19, width: 0.92, height: 0.72 }], text: { x: 0.05, y: 0.04, width: 0.88, height: 0.11 } },
];
