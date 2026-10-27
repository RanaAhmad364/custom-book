import { useEffect, useRef } from "react";
import { Canvas, Circle, FabricImage, IText, Rect, Shadow } from "fabric";
import { normalizeFabricObject } from "./editorDocument.js";

function makeText(element, width, height) {
  return new IText(element.text, {
    left: element.x * width,
    top: element.y * height,
    width: element.width * width,
    fontFamily: element.fontFamily,
    fontSize: element.fontSize * height,
    fontWeight: element.fontWeight,
    fontStyle: element.italic ? "italic" : "normal",
    underline: element.underline,
    scaleY: element.scaleY ?? 1,
    fill: element.color,
    textAlign: element.alignment,
    charSpacing: element.letterSpacing,
    lineHeight: element.lineHeight,
    backgroundColor: element.backgroundColor,
    opacity: element.opacity,
    angle: element.rotation,
    originX: "left",
    originY: "top",
    elementId: element.id,
    kind: element.kind,
    editable: true,
    splitByGrapheme: true,
  });
}

async function makeImage(element, width, height) {
  const image = await FabricImage.fromURL(element.src);
  const frameWidth = element.width * width;
  const frameHeight = element.height * height;
  const scale = element.fit === "cover"
    ? Math.max(frameWidth / image.width, frameHeight / image.height) * (element.zoom ?? 1)
    : Math.min(frameWidth / image.width, frameHeight / image.height);
  const cropWidth = element.fit === "cover" ? Math.min(image.width, frameWidth / scale) : image.width;
  const cropHeight = element.fit === "cover" ? Math.min(image.height, frameHeight / scale) : image.height;
  image.set({
    left: element.x * width,
    top: element.y * height,
    width: cropWidth,
    height: cropHeight,
    scaleX: scale,
    scaleY: scale,
    cropX: element.fit === "cover" ? (image.width - cropWidth) * (element.cropX ?? 0.5) : 0,
    cropY: element.fit === "cover" ? (image.height - cropHeight) * (element.cropY ?? 0.5) : 0,
    opacity: element.opacity,
    angle: element.rotation,
    stroke: element.borderColor,
    strokeWidth: element.borderWidth * width,
    elementId: element.id,
    assetId: element.assetId,
    src: element.src,
    name: element.name,
    fit: element.fit,
    zoom: element.zoom ?? 1,
    cropXNormalized: element.cropX ?? 0.5,
    cropYNormalized: element.cropY ?? 0.5,
    borderRadius: element.borderRadius,
    shadow: element.shadow,
    originX: "left",
    originY: "top",
  });
  if (element.shadow) image.shadow = new Shadow({ color: "rgba(28, 40, 34, 0.18)", blur: 18, offsetX: 0, offsetY: 8 });
  if (element.borderRadius) {
    const radius = (element.borderRadius * width) / scale;
    image.clipPath = new Rect({ width: cropWidth, height: cropHeight, rx: radius, ry: radius, originX: "center", originY: "center" });
  }
  return image;
}

function makeShape(element, width, height) {
  const options = {
    left: element.x * width,
    top: element.y * height,
    width: element.width * width,
    height: element.height * height,
    fill: element.fill,
    stroke: element.stroke,
    strokeDashArray: element.shape === "photo-placeholder" ? [8, 6] : undefined,
    strokeWidth: element.strokeWidth * width,
    opacity: element.opacity,
    angle: element.rotation,
    elementId: element.id,
    shape: element.shape,
    rx: element.rx * width,
    originX: "left",
    originY: "top",
  };
  return element.shape === "circle" ? new Circle({ ...options, radius: Math.min(options.width, options.height) / 2 }) : new Rect(options);
}

function canvasElementToModel(object, dimensions) {
  const element = normalizeFabricObject(object, dimensions);
  if (object.type === "image") {
    element.width = Math.max(0.01, (object.getScaledWidth() ?? object.width) / dimensions.width);
    element.height = Math.max(0.01, (object.getScaledHeight() ?? object.height) / dimensions.height);
  }
  return element;
}

export default function EditorCanvas({
  document,
  page,
  activePageId,
  pageTitle,
  onElementsChange,
  onSelectionChange,
  onCanvasError,
  canvasApi,
  renderToken,
  guides,
  zoom,
  selectedId,
  preview,
  adminMode = false,
  snapToGrid = false,
}) {
  const elementRef = useRef(null);
  const canvasRef = useRef(null);
  const suppressRef = useRef(false);
  const generationRef = useRef(0);
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const callbacksRef = useRef({ onElementsChange, onSelectionChange, onCanvasError: () => {}, page, document, adminMode, snapToGrid });
  callbacksRef.current = { onElementsChange, onSelectionChange, onCanvasError, page, document, adminMode, snapToGrid };

  const width = 760;
  const ratio = document.book.size.height / document.book.size.width;
  const height = Math.round(width * ratio);

  useEffect(() => {
    const canvas = new Canvas(elementRef.current, {
      width,
      height,
      backgroundColor: page.background?.color ?? "#fffdf9",
      preserveObjectStacking: true,
      selection: true,
      stopContextMenu: true,
      fireRightClick: true,
    });
    canvasRef.current = canvas;
    canvasApi.current = {
      canvas,
      addObject(object) {
        canvas.add(object);
        canvas.setActiveObject(object);
        canvas.requestRenderAll();
      },
      findObject(id) {
        return canvas.getObjects().find((object) => object.elementId === id) ?? null;
      },
      deleteSelected() {
        const selected = canvas.getActiveObjects();
        if (!selected.length) return false;
        selected.forEach((object) => canvas.remove(object));
        canvas.discardActiveObject();
        canvas.requestRenderAll();
        return true;
      },
      selectObject(id) {
        const object = canvas.getObjects().find((item) => item.elementId === id);
        if (object) canvas.setActiveObject(object);
        canvas.requestRenderAll();
      },
    };

    const sync = (history) => {
      if (suppressRef.current) return;
      callbacksRef.current.onElementsChange(
        canvas.getObjects().map((object) => canvasElementToModel(object, { width, height })),
        callbacksRef.current.page.id,
        history,
      );
    };
    const snapObject = (event) => {
      const object = event.target;
      if (!object || !callbacksRef.current.adminMode || !callbacksRef.current.snapToGrid || object.type === "activeSelection") return;
      const grid = width * 0.05;
      const scaledWidth = object.getScaledWidth();
      const scaledHeight = object.getScaledHeight();
      const snappedWidth = Math.min(width, Math.max(grid, Math.round(scaledWidth / grid) * grid));
      const snappedHeight = Math.min(height, Math.max(grid, Math.round(scaledHeight / grid) * grid));
      if (event.transform?.action === "scale") {
        object.set({
          scaleX: snappedWidth / object.width,
          scaleY: snappedHeight / object.height,
        });
      }
      object.set({
        left: Math.min(Math.max(0, Math.round((object.left ?? 0) / grid) * grid), width - object.getScaledWidth()),
        top: Math.min(Math.max(0, Math.round((object.top ?? 0) / grid) * grid), height - object.getScaledHeight()),
      });
      object.setCoords();
    };
    canvas.on("object:moving", snapObject);
    canvas.on("object:scaling", snapObject);
    canvas.on("object:modified", () => sync(true));
    canvas.on("text:changed", () => sync(true));
    canvas.on("selection:created", (event) => { if (!suppressRef.current) callbacksRef.current.onSelectionChange(event.selected?.[0]?.elementId ?? null); });
    canvas.on("selection:updated", (event) => { if (!suppressRef.current) callbacksRef.current.onSelectionChange(event.selected?.[0]?.elementId ?? null); });
    canvas.on("selection:cleared", () => { if (!suppressRef.current) callbacksRef.current.onSelectionChange(null); });

    return () => {
      generationRef.current += 1;
      canvasApi.current = null;
      canvas.dispose();
      canvasRef.current = null;
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !page) return undefined;
    const generation = ++generationRef.current;
    suppressRef.current = true;
    canvas.clear();
    canvas.backgroundColor = page.background?.color ?? "#fffdf9";
    canvas.setDimensions({ width, height });
    canvas.setZoom(zoom / 100);
    canvas.setViewportTransform([zoom / 100, 0, 0, zoom / 100, 0, 0]);
    let cancelled = false;

    (async () => {
      for (const element of page.elements) {
        let object;
        if (element.type === "text") object = makeText(element, width, height);
        else if (element.type === "image") object = await makeImage(element, width, height);
        else object = makeShape(element, width, height);
        if (preview) object.selectable = false;
        if (cancelled || generation !== generationRef.current) return;
        canvas.add(object);
      }
      const selectedObject = canvas.getObjects().find((object) => object.elementId === selectedRef.current);
      if (selectedObject && !preview) canvas.setActiveObject(selectedObject);
      suppressRef.current = false;
      canvas.requestRenderAll();
    })().catch((failure) => {
      suppressRef.current = false;
      callbacksRef.current.onCanvasError(failure instanceof Error ? failure : new Error("Could not render this page."));
    });

    return () => {
      cancelled = true;
    };
  }, [activePageId, renderToken, width, height, zoom, page?.background?.color, preview]);

  return (
    <div className={`editor-artboard${guides ? " show-guides" : ""}`} style={{ aspectRatio: `${width} / ${height}` }}>
      <canvas ref={elementRef} aria-label={`Editable ${pageTitle ?? page?.label ?? "book page"}`} />
      {page.background?.borderColor && page.background?.borderStyle !== "none" ? <div
        className="editor-page-border"
        style={{ borderColor: page.background.borderColor, borderStyle: page.background.borderStyle ?? "solid" }}
        aria-hidden="true"
      /> : null}
      {guides ? <div className="editor-safe-guide" aria-hidden="true" /> : null}
    </div>
  );
}
