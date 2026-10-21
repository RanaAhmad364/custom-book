import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight, Expand, Minimize, X } from "lucide-react";
import { CoverArtwork } from "./CoverArtwork.jsx";

function PageArtwork({ page, previewWidth, previewHeight, className = "" }) {
  return <div className={`book-preview-page ${className}`} style={{ backgroundColor: page.background?.color ?? "#fffdf9" }}>
    {(page.elements ?? []).map((element) => {
      const style = {
        left: `${element.x * 100}%`,
        top: `${element.y * 100}%`,
        width: `${element.width * 100}%`,
        height: `${element.height * 100}%`,
        opacity: element.opacity ?? 1,
        transform: `rotate(${element.rotation ?? 0}deg)`,
      };
      if (element.type === "image") {
        return <span key={element.id} className="book-preview-element book-preview-photo-frame" style={{
          ...style,
          transform: `rotate(${element.rotation ?? 0}deg)`,
          border: element.borderWidth ? `${element.borderWidth * previewWidth}px solid ${element.borderColor ?? "#fffdf9"}` : undefined,
          borderRadius: element.borderRadius ? `${element.borderRadius * previewWidth}px` : undefined,
          boxShadow: element.shadow ? "0 8px 18px rgba(28, 40, 34, .18)" : undefined,
        }}><img className="book-preview-photo" style={{
          objectFit: element.fit === "contain" ? "contain" : "cover",
          objectPosition: `${(element.cropX ?? 0.5) * 100}% ${(element.cropY ?? 0.5) * 100}%`,
          transform: `scale(${element.fit === "contain" ? 1 : element.zoom ?? 1})`,
        }} src={element.src} alt={element.name ?? ""} /></span>;
      }
      if (element.type === "text") {
        return <span key={element.id} className="book-preview-element book-preview-text" style={{
          ...style,
          color: element.color,
          fontFamily: element.fontFamily,
          fontSize: `${(element.fontSize ?? 0.025) * previewHeight}px`,
          fontWeight: element.fontWeight,
          fontStyle: element.italic ? "italic" : "normal",
          textDecoration: element.underline ? "underline" : undefined,
          textAlign: element.alignment,
          lineHeight: element.lineHeight,
          letterSpacing: element.letterSpacing ? `${element.letterSpacing}px` : undefined,
          backgroundColor: element.backgroundColor === "transparent" ? undefined : element.backgroundColor,
        }}>{element.text}</span>;
      }
      return <span key={element.id} className="book-preview-element book-preview-shape" style={{
        ...style,
        backgroundColor: element.fill,
        border: `${Math.max(0, (element.strokeWidth ?? 0) * previewWidth)}px solid ${element.stroke}`,
        borderRadius: element.shape === "circle" ? "50%" : `${(element.rx ?? 0) * previewWidth}px`,
      }} />;
    })}
  </div>;
}

export default function BookPreview({ document, initialPageId, onClose, onEditPage, onContinueReview }) {
  const interiorPages = useMemo(() => document.pageOrder.map((id) => document.pages.find((page) => page.id === id)).filter((page) => page && page.type !== "cover"), [document]);
  const slides = useMemo(() => [
    { id: "cover-front", kind: "front", label: "Front cover" },
    ...interiorPages.map((page) => ({ id: page.id, kind: "page", page, label: page.label })),
    { id: "cover-back", kind: "back", label: "Back cover" },
  ], [interiorPages]);
  const initialIndex = Math.max(0, slides.findIndex((slide) => slide.id === initialPageId));
  const [index, setIndex] = useState(initialIndex);
  const [spread, setSpread] = useState(() => globalThis.window?.innerWidth > 600);
  const [zoom, setZoom] = useState(100);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");
  const dialogRef = useRef(null);
  const canvasRef = useRef(null);
  const touchStartRef = useRef(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const bookWidth = Math.max(1, Number(document.book?.size?.width) || 1);
  const bookHeight = Math.max(1, Number(document.book?.size?.height) || 1);
  const pageRatio = bookWidth / bookHeight;

  useEffect(() => {
    const previousOverflow = globalThis.document.body.style.overflow;
    globalThis.document.body.style.overflow = "hidden";
    return () => { globalThis.document.body.style.overflow = previousOverflow; };
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => setFullscreen(Boolean(globalThis.document.fullscreenElement));
    globalThis.document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => globalThis.document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !globalThis.ResizeObserver) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setCanvasSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const mobile = window.matchMedia("(max-width: 600px)");
    const useSinglePageOnMobile = () => {
      if (mobile.matches) setSpread(false);
    };
    useSinglePageOnMobile();
    mobile.addEventListener("change", useSinglePageOnMobile);
    return () => mobile.removeEventListener("change", useSinglePageOnMobile);
  }, []);

  const spreadStart = index > 0 && slides[index]?.kind === "page"
    ? 1 + Math.floor((index - 1) / 2) * 2
    : index;
  const visibleSlides = spread && slides[index]?.kind === "page"
    ? slides.slice(spreadStart, spreadStart + 2)
    : [slides[index]];
  const visibleCount = Math.max(1, visibleSlides.length);
  const fitPageHeight = canvasSize.width && canvasSize.height
    ? Math.min(canvasSize.height - 30, (canvasSize.width - (visibleCount - 1) * 16) / (visibleCount * pageRatio))
    : 0;
  const pageHeight = Math.max(0, fitPageHeight * zoom / 100);
  const pageWidth = pageHeight * pageRatio;
  const pageGap = Math.max(5, Math.min(18, pageWidth * 0.025));

  const navigate = useCallback((nextIndex) => {
    setIndex(Math.min(slides.length - 1, Math.max(0, nextIndex)));
  }, [slides.length]);

  function previous() {
    navigate(spread && slides[index]?.kind === "page" ? Math.max(0, spreadStart - 2) : index - 1);
  }

  function next() {
    navigate(spread && slides[index]?.kind === "page" ? Math.min(slides.length - 1, spreadStart + 2) : index + 1);
  }

  function beginTouch(event) {
    if (event.pointerType !== "touch" || zoom > 100 || event.target.closest("button, select, a")) return;
    if (touchStartRef.current) {
      touchStartRef.current.multiTouch = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    touchStartRef.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function endTouch(event) {
    const start = touchStartRef.current;
    touchStartRef.current = null;
    if (!start || start.multiTouch || zoom > 100) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaX) < 48 || Math.abs(deltaX) < Math.abs(deltaY) * 1.25) return;
    if (deltaX < 0) next();
    else previous();
  }

  async function toggleFullscreen() {
    setFullscreenError("");
    try {
      if (globalThis.document.fullscreenElement) await globalThis.document.exitFullscreen();
      else await dialogRef.current?.requestFullscreen();
    } catch (failure) {
      setFullscreenError(failure instanceof Error ? failure.message : "Fullscreen is unavailable in this browser.");
    }
  }

  function editCurrentPage() {
    const slide = slides[index];
    if (slide?.kind === "page") onEditPage(slide.page.id);
    else onEditPage(document.cover?.pageId);
  }

  return <div className={`editor-modal-backdrop book-preview-backdrop${fullscreen ? " fullscreen" : ""}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="editor-fullbook-preview-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-label="Full book preview">
      <header className="book-preview-header">
        <button className="preview-back-button" type="button" onClick={onClose}><ArrowLeft size={16} /> Back to editor</button>
        <div className="book-preview-title"><span className="eyebrow">A little preview</span><strong>{document.metadata.title}</strong></div>
        <div className="book-preview-header-actions">
          <button className="book-preview-view-toggle" type="button" onClick={() => setSpread((value) => !value)} aria-pressed={spread}>{spread ? "Single page" : "Spread view"}</button>
          <button type="button" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}>{fullscreen ? <Minimize size={16} /> : <Expand size={16} />}</button>
          <button type="button" onClick={onClose} aria-label="Close book preview"><X size={17} /></button>
        </div>
      </header>
      <div className="book-preview-stage">
        <button className="book-preview-nav" type="button" disabled={index === 0} aria-label="Previous page" onClick={previous}><ChevronLeft size={22} /></button>
        <div className="book-preview-canvas" ref={canvasRef} onPointerDown={beginTouch} onPointerUp={endTouch} onPointerCancel={() => { touchStartRef.current = null; }} aria-label={spread && visibleSlides.length > 1 ? "Two-page book spread" : "Book page"}>
          <div className={`book-preview-spread${visibleSlides.length > 1 ? " is-spread" : ""}`} style={{ width: `${visibleCount * pageWidth + (visibleCount - 1) * pageGap}px`, height: `${pageHeight + 22}px`, gap: `${pageGap}px` }}>
            {visibleSlides.map((slide) => <div className="book-preview-sheet" style={{ width: `${pageWidth}px`, height: `${pageHeight + 22}px` }} key={slide.id}>
              {slide.kind === "front" || slide.kind === "back"
                ? <CoverArtwork cover={document.cover} document={document} side={slide.kind} className="book-preview-cover-artwork" />
                : <PageArtwork page={slide.page} previewWidth={pageWidth} previewHeight={pageHeight} />}
              <span>{slide.label}</span>
            </div>)}
          </div>
        </div>
        <button className="book-preview-nav" type="button" disabled={index >= slides.length - 1} aria-label="Next page" onClick={next}><ChevronRight size={22} /></button>
      </div>
      <footer className="book-preview-footer">
        <label>Page<select aria-label="Go to page" value={index} onChange={(event) => navigate(Number(event.target.value))}>{slides.map((slide, slideIndex) => <option key={slide.id} value={slideIndex}>{slide.label}</option>)}</select><small>{index + 1} of {slides.length}</small></label>
        <div className="book-preview-zoom"><button type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(50, value - 10))}>−</button><span>{zoom}%</span><button type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(150, value + 10))}>+</button><button type="button" onClick={() => setZoom(100)}>Fit to screen</button></div>
        <div className="book-preview-footer-actions"><button className="button button-outline" type="button" onClick={editCurrentPage}>Edit this page</button><button className="button button-dark" type="button" onClick={onContinueReview}>Continue to Final Review</button></div>
      </footer>
      {fullscreenError ? <p className="book-preview-error" role="alert">{fullscreenError}</p> : null}
    </section>
  </div>;
}
