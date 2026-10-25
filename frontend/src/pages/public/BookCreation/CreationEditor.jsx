import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ActiveSelection } from "fabric";
import {
  AlignCenter, AlignLeft, AlignRight, ArrowLeft, ArrowDown, ArrowUp, BookOpen,
  Check, ChevronDown, ChevronRight, Circle, Cloud, CloudOff, Copy, Eye, FileImage,
  HelpCircle, ImagePlus, LayoutTemplate, LoaderCircle, Menu, Minus, Paintbrush,
  Plus, Redo2, Save, Send, Shapes, Trash2, Type, Undo2, Upload, X,
} from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../features/auth/AuthContext.jsx";
import { projectService } from "../../../services/projectService.js";
import {
  getAdminBookDesign, publishAdminBookDesign, saveAdminBookDesign,
  unpublishAdminBookDesign, uploadAdminDesignAsset,
} from "../../../features/admin/adminService.js";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import EditorCanvas from "../../../features/bookEditor/EditorCanvas.jsx";
import { refreshAssetSources } from "../../../features/bookEditor/assetPreview.js";
import { getPageThumbnailSize } from "../../../features/bookEditor/pageThumbnail.js";
import { createSaveQueue } from "../../../features/bookEditor/saveQueue.js";
import {
  cloneDocument, createPage, createPhotoElement, createShapeElement, createTextElement,
  duplicatePageRecord, formatBytes, pageLayouts, removePage, reorderPageIds,
} from "../../../features/bookEditor/editorDocument.js";
import { getPageLabel, getPagePosition } from "../../../features/bookEditor/pageNavigation.js";
import CoverDesigner from "../../../features/bookEditor/CoverDesigner.jsx";
import BookPreview, { PageArtwork } from "../../../features/bookEditor/BookPreview.jsx";
import BookReview from "../../../features/bookEditor/BookReview.jsx";
import "./BookEditor.css";

const tools = [
  { id: "templates", label: "Templates", Icon: LayoutTemplate },
  { id: "layouts", label: "Layouts", Icon: GridIcon },
  { id: "photos", label: "Photos", Icon: FileImage },
  { id: "upload", label: "Upload", Icon: Upload },
  { id: "text", label: "Text", Icon: Type },
  { id: "elements", label: "Elements", Icon: Shapes },
  { id: "background", label: "Background", Icon: Paintbrush },
  { id: "styles", label: "Styles", Icon: BookOpen },
  { id: "pages", label: "Pages", Icon: Menu },
];

function GridIcon(props) {
  return <LayoutTemplate {...props} />;
}

const colorSwatches = ["#fffdf9", "#f4eee5", "#e8ece5", "#d7e4dc", "#eadccf", "#e8e1ec", "#26352e", "#193f36"];
const editorImageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

function SidebarPanel({
  panel, document, page, activePageId, setActivePageId, setSelectedId, setMobilePanel, inputRef, onAddText, onAddShape, onAddPhoto, onUpload,
  onApplyLayout, onBackground, onReorderPage, onAddPage, onDuplicatePage, onDeletePage, onClose,
}) {
  const readyAssets = document.assets.filter((asset) => asset.src);
  const [dragPage, setDragPage] = useState(null);
  const pageRefs = useRef(new Map());
  useEffect(() => {
    pageRefs.current.get(activePageId)?.scrollIntoView({ block: "nearest" });
  }, [activePageId, document.pageOrder.length]);
  if (!panel) return null;
  return <aside className={`editor-side-panel${panel === "pages" ? " editor-pages-panel" : ""}`}>
    <header className="editor-panel-heading"><div><span className="eyebrow">Studio tools</span><h2>{tools.find((tool) => tool.id === panel)?.label ?? "Pages"}</h2></div><button className="editor-panel-close" type="button" onClick={onClose} aria-label="Close tools panel"><X size={17} /></button></header>
    {panel === "templates" ? <div className="editor-panel-content">
      <p className="editor-panel-note">Keep your original setup. Apply a layout to this page when you’re ready to begin.</p>
      <button className="editor-template-card" type="button" onClick={() => onApplyLayout(pageLayouts[0])}><span className="editor-template-thumb"><BookOpen size={24} /></span><strong>Start with a photo</strong><small>A quiet, full-page moment</small></button>
      {document.book.template ? <div className="editor-template-current"><span className="eyebrow">Selected at setup</span><strong>{document.book.template.title}</strong><small>{document.book.template.category} · ready to customize</small></div> : null}
    </div> : null}
    {panel === "layouts" ? <div className="editor-panel-content">
      <p className="editor-panel-note">Choose a composition for <strong>{getPageLabel(page, document)}</strong>. Existing content is never removed without confirmation.</p>
      <div className="editor-layout-list">{pageLayouts.map((layout, index) => <button className="editor-layout-card" type="button" key={layout.id} onClick={() => onApplyLayout(layout)}>
        <span className={`editor-layout-schematic layout-${layout.id}`}>{layout.slots.map((slot, slotIndex) => <i key={slotIndex} style={{ left: `${slot.x * 100}%`, top: `${slot.y * 100}%`, width: `${slot.width * 100}%`, height: `${slot.height * 100}%` }} />)}</span>
        <span><strong>{layout.name}</strong><small>{layout.description}</small></span>
      </button>)}</div>
    </div> : null}
    {panel === "photos" ? <div className="editor-panel-content">
      <button className="editor-upload-inline" type="button" onClick={() => inputRef.current?.click()}><ImagePlus size={17} /> Add photos</button>
      {!readyAssets.length ? <div className="editor-panel-empty"><FileImage size={25} /><strong>Your photo library is ready</strong><span>Upload a few memories to place them on this page.</span></div> :
        <div className="editor-photo-library">{readyAssets.map((asset) => <button key={asset.id} type="button" className="editor-photo-tile" onClick={() => onAddPhoto(asset)} aria-label={`Place ${asset.name}`}><img src={asset.src} alt="" /><span><Plus size={14} /></span></button>)}</div>}
      {readyAssets.map((asset) => <p className="editor-asset-caption" key={`${asset.id}-caption`}>{asset.name} · {asset.size ? formatBytes(asset.size) : "In this book"}</p>)}
    </div> : null}
    {panel === "upload" ? <div className="editor-panel-content">
      <button className="editor-drop-target" type="button" onClick={() => inputRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onUpload(event.dataTransfer.files); }}><Upload size={23} /><strong>Choose photos</strong><span>JPG, PNG, WebP · up to 15 MB each</span><small>Drop photos here or browse your device.</small></button>
      {readyAssets.length ? <div className="editor-upload-list">{readyAssets.map((asset) => <div key={asset.id}><img src={asset.src} alt="" /><span>{asset.name}<small>{asset.size ? formatBytes(asset.size) : ""}</small></span><Check size={15} /></div>)}</div> : null}
    </div> : null}
    {panel === "text" ? <div className="editor-panel-content">
      <p className="editor-panel-note">Add a heading, a short caption, or a paragraph. Select text on the page to edit its style.</p>
      <div className="editor-text-presets"><button type="button" onClick={() => onAddText("heading")}><strong>Heading</strong><small>Add a title</small></button><button type="button" onClick={() => onAddText("subheading")}><strong className="text-subheading">Subheading</strong><small>Add a section title</small></button><button type="button" onClick={() => onAddText("paragraph")}><span>Paragraph text</span><small>Tell a little more</small></button></div>
    </div> : null}
    {panel === "elements" ? <div className="editor-panel-content">
      <p className="editor-panel-note">Subtle shapes add a little structure to your page.</p>
      <div className="editor-shape-actions"><button type="button" onClick={() => onAddShape("rectangle")}><span className="editor-shape-preview" />Rectangle</button><button type="button" onClick={() => onAddShape("circle")}><Circle size={24} />Circle</button></div>
    </div> : null}
    {panel === "background" || panel === "styles" ? <div className="editor-panel-content">
      <p className="editor-panel-note">{panel === "styles" ? "Set a calm paper tone for this page." : "Choose a paper color for the active page."}</p>
      <div className="editor-background-swatches">{colorSwatches.map((color) => <button key={color} className={page.background?.color === color ? "selected" : ""} type="button" style={{ backgroundColor: color }} onClick={() => onBackground(color)} aria-label={`Set page background to ${color}`} />)}</div>
      <label className="editor-field-label">Custom color<input type="color" value={page.background?.color ?? "#fffdf9"} onChange={(event) => onBackground(event.target.value)} /></label>
      {document.book.template ? <div className="editor-template-current"><span className="eyebrow">Your template</span><strong>{document.book.template.title}</strong><small>Page colors and text remain fully editable.</small></div> : null}
    </div> : null}
    {panel === "pages" ? <div className="editor-panel-content-pages">
        <p className="editor-panel-note">Arrange the pages in your book. Drag a page to change its order.</p>
        <div className="editor-pages-list">{document.pageOrder.map((id, index) => {
        const item = document.pages.find((candidate) => candidate.id === id);
        if (!item) return null;
        const label = getPageLabel(item, document);
        return <div
          className={`editor-page-row${activePageId === id ? " active" : ""}`}
          key={id}
          ref={(element) => {
            if (element) pageRefs.current.set(id, element);
            else pageRefs.current.delete(id);
          }}
          draggable
          onDragStart={() => setDragPage(id)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={() => { if (dragPage && dragPage !== id) onReorderPage(dragPage, id); setDragPage(null); }}
        >
          <button className="editor-page-select" type="button" onClick={() => { setActivePageId(id); setSelectedId(null); setMobilePanel(false); }} aria-current={activePageId === id ? "page" : undefined} aria-label={`Open ${label}`}>
            <span className="editor-page-number">{item.type === "cover" ? "C" : label.replace("Page ", "")}</span><span>{label}</span>
          </button>
          <div><button type="button" aria-label={`Move ${label} earlier`} disabled={index === 0} onClick={() => onReorderPage(id, document.pageOrder[index - 1])}><ArrowUp size={14} /></button><button type="button" aria-label={`Move ${label} later`} disabled={index === document.pageOrder.length - 1} onClick={() => onReorderPage(id, document.pageOrder[index + 2] ?? null)}><ArrowDown size={14} /></button></div>
        </div>;
      })}</div>
        <div className="editor-page-actions">
          <button className="editor-upload-inline" type="button" onClick={onAddPage}><Plus size={16} /> Add a page</button>
          <button className="editor-upload-inline" type="button" onClick={() => onDuplicatePage(page.id)}><Copy size={15} /> Duplicate this page</button>
          {page.type !== "cover" ? <button className="editor-danger-action" type="button" onClick={() => onDeletePage(page.id)}><Trash2 size={15} /> Delete this page</button> : null}
        </div>
      </div> : null}
  </aside>;
}

function ElementInspector({ element, pageHeight, onChange, onDelete, onDuplicate, onShowPhotos, onClose, assets }) {
  if (!element) return <aside className="editor-inspector"><header className="editor-panel-heading"><div><span className="eyebrow">Page settings</span><h2>Make it yours</h2></div><button className="editor-panel-close" type="button" onClick={onClose} aria-label="Close properties panel"><X size={17} /></button></header><p className="editor-panel-note">Select a photo, text, or shape to see its editing controls. Changes are saved to your book document.</p>
    <div className="editor-inspector-tip"><span className="eyebrow">A small tip</span><p>Drag an object to move it. Use its corner handles to resize, or the round handle to rotate.</p></div>
    <div className="editor-inspector-section"><span className="eyebrow">Photos in this book</span>{assets.length ? <button className="editor-inspector-photo-action" type="button" onClick={() => onAddPhoto(assets[0])}><img src={assets[0].src} alt="" /><span>Place {assets[0].name}</span><Plus size={15} /></button> : <p>Upload a photo to start creating.</p>}</div>
  </aside>;
  return <aside className="editor-inspector">
    <header className="editor-panel-heading"><div><span className="eyebrow">Selected {element.type}</span><h2>{element.type === "text" ? "Typography" : element.type === "image" ? "Photo details" : "Shape details"}</h2></div><button className="editor-panel-close" type="button" onClick={onClose} aria-label="Close properties panel"><X size={17} /></button></header>
    {element.type === "text" ? <>
      <label className="editor-field-label">Text<textarea value={element.text} rows={4} onChange={(event) => onChange({ text: event.target.value })} /></label>
      <div className="editor-field-pair"><label className="editor-field-label">Font<select value={element.fontFamily} onChange={(event) => onChange({ fontFamily: event.target.value })}><option>DM Sans</option><option>Georgia</option><option>Arial</option><option>Times New Roman</option></select></label><label className="editor-field-label">Size<input type="number" min="8" max="120" value={Math.round(element.fontSize * pageHeight)} onChange={(event) => onChange({ fontSize: Math.min(120, Math.max(8, Number(event.target.value))) / pageHeight })} /></label></div>
      <div className="editor-field-pair"><label className="editor-field-label">Weight<select value={element.fontWeight} onChange={(event) => onChange({ fontWeight: event.target.value })}><option value="400">Regular</option><option value="500">Medium</option><option value="600">Semibold</option><option value="700">Bold</option></select></label><label className="editor-field-label">Color<input type="color" value={element.color} onChange={(event) => onChange({ color: event.target.value })} /></label></div>
      <div className="editor-field-pair"><label className="editor-check-label"><input type="checkbox" checked={element.italic} onChange={(event) => onChange({ italic: event.target.checked })} /> Italic</label><label className="editor-check-label"><input type="checkbox" checked={element.underline} onChange={(event) => onChange({ underline: event.target.checked })} /> Underline</label></div>
      <div className="editor-inspector-section"><span className="eyebrow">Alignment</span><div className="editor-align-actions"><button type="button" aria-label="Align left" onClick={() => onChange({ alignment: "left" })}><AlignLeft size={16} /></button><button type="button" aria-label="Align center" onClick={() => onChange({ alignment: "center" })}><AlignCenter size={16} /></button><button type="button" aria-label="Align right" onClick={() => onChange({ alignment: "right" })}><AlignRight size={16} /></button></div></div>
      <label className="editor-field-label">Letter spacing<input type="range" min="-2" max="8" step="0.5" value={element.letterSpacing} onChange={(event) => onChange({ letterSpacing: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Line height<input type="range" min="0.8" max="2" step="0.05" value={element.lineHeight} onChange={(event) => onChange({ lineHeight: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Opacity<input type="range" min="0.1" max="1" step="0.05" value={element.opacity} onChange={(event) => onChange({ opacity: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Text background<input type="color" value={element.backgroundColor === "transparent" ? "#fffdf9" : element.backgroundColor} onChange={(event) => onChange({ backgroundColor: event.target.value })} /></label>
    </> : element.type === "image" ? <>
      <div className="editor-inspector-image">{element.src ? <img src={element.src} alt="" /> : <FileImage size={22} />}<span>{element.name ?? "Photo"}</span></div>
      <div className="editor-field-pair"><label className="editor-field-label">Image fit<select value={element.fit} onChange={(event) => onChange({ fit: event.target.value })}><option value="cover">Fill frame</option><option value="contain">Fit image</option></select></label><label className="editor-field-label">Rotation<input type="number" min="-180" max="180" value={Math.round(element.rotation)} onChange={(event) => onChange({ rotation: Number(event.target.value) })} /></label></div>
      <label className="editor-field-label">Opacity<input type="range" min="0.1" max="1" step="0.05" value={element.opacity} onChange={(event) => onChange({ opacity: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Border<input type="color" value={element.borderColor} onChange={(event) => onChange({ borderColor: event.target.value, borderWidth: 0.004 })} /></label>
      <label className="editor-field-label">Border width<input type="range" min="0" max="0.02" step="0.001" value={element.borderWidth} onChange={(event) => onChange({ borderWidth: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Rounded corners<input type="range" min="0" max="0.08" step="0.005" value={element.borderRadius} onChange={(event) => onChange({ borderRadius: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Crop zoom<input type="range" min="1" max="2" step="0.05" value={element.zoom ?? 1} onChange={(event) => onChange({ zoom: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Horizontal crop<input type="range" min="0" max="1" step="0.05" value={element.cropX ?? 0.5} onChange={(event) => onChange({ cropX: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Vertical crop<input type="range" min="0" max="1" step="0.05" value={element.cropY ?? 0.5} onChange={(event) => onChange({ cropY: Number(event.target.value) })} /></label>
      <label className="editor-check-label"><input type="checkbox" checked={element.shadow} onChange={(event) => onChange({ shadow: event.target.checked })} /> Soft shadow</label>
      <button className="editor-upload-inline" type="button" onClick={onShowPhotos}><ImagePlus size={15} /> Replace with another photo</button>
    </> : <>
      <div className="editor-field-pair"><label className="editor-field-label">Fill<input type="color" value={element.fill} onChange={(event) => onChange({ fill: event.target.value })} /></label><label className="editor-field-label">Outline<input type="color" value={element.stroke} onChange={(event) => onChange({ stroke: event.target.value })} /></label></div>
      <label className="editor-field-label">Opacity<input type="range" min="0.1" max="1" step="0.05" value={element.opacity} onChange={(event) => onChange({ opacity: Number(event.target.value) })} /></label>
      <label className="editor-field-label">Rotation<input type="number" min="-180" max="180" value={Math.round(element.rotation)} onChange={(event) => onChange({ rotation: Number(event.target.value) })} /></label>
    </>}
    <div className="editor-inspector-section"><span className="eyebrow">Position & size</span>
      <div className="editor-field-pair"><label className="editor-field-label">X<input type="number" min="0" max="100" value={Math.round(element.x * 100)} onChange={(event) => onChange({ x: Math.min(1, Math.max(0, Number(event.target.value) / 100)) })} /></label><label className="editor-field-label">Y<input type="number" min="0" max="100" value={Math.round(element.y * 100)} onChange={(event) => onChange({ y: Math.min(1, Math.max(0, Number(event.target.value) / 100)) })} /></label></div>
      <div className="editor-field-pair"><label className="editor-field-label">Width<input type="number" min="1" max="100" value={Math.round(element.width * 100)} onChange={(event) => onChange({ width: Math.min(1, Math.max(0.01, Number(event.target.value) / 100)) })} /></label><label className="editor-field-label">Height<input type="number" min="1" max="100" value={Math.round(element.height * 100)} onChange={(event) => onChange({ height: Math.min(1, Math.max(0.01, Number(event.target.value) / 100)) })} /></label></div>
      <label className="editor-field-label">Rotation<input type="number" min="-180" max="180" value={Math.round(element.rotation)} onChange={(event) => onChange({ rotation: Number(event.target.value) })} /></label>
    </div>
    <div className="editor-inspector-actions"><button type="button" onClick={onDuplicate}><Copy size={14} /> Duplicate</button><button className="editor-delete-button" type="button" onClick={onDelete}><Trash2 size={14} /> Delete</button></div>
  </aside>;
}

function mergeRecovery(saved, recovery) {
  if (!recovery || !Array.isArray(recovery.pages) || recovery.schemaVersion !== saved.schemaVersion || recovery.metadata?.id !== saved.metadata.id) return saved;
  const assets = new Map(saved.assets.map((asset) => [asset.id, asset]));
  return {
    ...recovery,
    assets: saved.assets,
    pages: recovery.pages.map((page) => ({
      ...page,
      elements: page.elements.map((element) => element.type === "image"
        ? { ...element, src: assets.get(element.assetId)?.src ?? element.src }
        : element),
    })),
  };
}

export default function CreationEditor({ adminMode = false }) {
  const { projectId, bookId } = useParams();
  const targetId = adminMode ? bookId : projectId;
  return <CreationEditorSession key={`${adminMode ? "admin" : "project"}:${targetId}`} adminMode={adminMode} />;
}

function CreationEditorSession({ adminMode }) {
  const { projectId, bookId } = useParams();
  const [searchParams] = useSearchParams();
  const previewOnly = adminMode && searchParams.get("preview") === "1";
  const targetId = adminMode ? bookId : projectId;
  const { user } = useAuth();
  const query = useQuery({
    queryKey: adminMode ? ["admin-book-design", bookId] : ["created-project", user.email, projectId],
    queryFn: () => adminMode ? getAdminBookDesign(bookId) : projectService.getProject(user.email, projectId),
  });
  const [document, setDocument] = useState(null);
  const documentRef = useRef(null);
  const [activePageId, setActivePageId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [panel, setPanel] = useState("templates");
  const [renderToken, setRenderToken] = useState(0);
  const [zoom, setZoom] = useState(75);
  const [guides, setGuides] = useState(true);
  const [preview, setPreview] = useState(false);
  const [coverDesignerOpen, setCoverDesignerOpen] = useState(false);
  const [bookPreviewOpen, setBookPreviewOpen] = useState(false);
  const [bookReviewOpen, setBookReviewOpen] = useState(false);
  const [mobilePanel, setMobilePanel] = useState(false);
  const [saveStatus, setSaveStatus] = useState("Saved");
  const [saveError, setSaveError] = useState("");
  const [bookPublished, setBookPublished] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [recoveryNotice, setRecoveryNotice] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const fileInputRef = useRef(null);
  const canvasApi = useRef(null);
  const undoStack = useRef([]);
  const redoStack = useRef([]);
  const clipboard = useRef(null);
  const thumbnailRefs = useRef(new Map());
  const assetRefreshRef = useRef(null);
  const dirtyRef = useRef(false);
  const saveQueueRef = useRef(null);
  if (!saveQueueRef.current) saveQueueRef.current = createSaveQueue();

  useEffect(() => {
    if (!query.data?.document) return;
    let active = true;
    const projectDocument = query.data.document;
    if (adminMode) {
      dirtyRef.current = false;
      documentRef.current = projectDocument;
      setDocument(projectDocument);
      setActivePageId(projectDocument.pageOrder[0]);
      setBookPublished(Boolean(query.data.published));
      setPreview(previewOnly);
      return () => { active = false; };
    }
    try {
      const recovery = projectService.getRecovery(user.email, targetId);
      if (recovery && new Date(recovery.metadata.updatedAt) > new Date(projectDocument.metadata.updatedAt)) {
        const recovered = mergeRecovery(projectDocument, recovery);
        if (active) {
          documentRef.current = recovered;
          setDocument(recovered);
          setActivePageId(recovered.pageOrder[0]);
          dirtyRef.current = true;
          setRecoveryNotice(true);
          setSaveStatus("Unsaved changes recovered");
        }
      } else {
        documentRef.current = projectDocument;
        setDocument(projectDocument);
        setActivePageId(projectDocument.pageOrder[0]);
      }
    } catch (failure) {
      setSaveError(failure instanceof Error ? failure.message : "The local recovery copy could not be read.");
      documentRef.current = projectDocument;
      setDocument(projectDocument);
      setActivePageId(projectDocument.pageOrder[0]);
    }
    return () => { active = false; };
  }, [adminMode, previewOnly, query.data, targetId, user.email]);

  const page = useMemo(() => document?.pages.find((item) => item.id === activePageId) ?? document?.pages[0], [document, activePageId]);
  const selectedElement = page?.elements.find((element) => element.id === selectedId) ?? null;

  useEffect(() => {
    thumbnailRefs.current.get(activePageId)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activePageId, document?.pageOrder.length]);

  const commit = useCallback((next, history = true) => {
    if (!next) return;
    const previous = documentRef.current;
    if (history && previous) {
      undoStack.current = [...undoStack.current.slice(-49), cloneDocument(previous)];
      redoStack.current = [];
    }
    documentRef.current = next;
    dirtyRef.current = true;
    setDocument(next);
    setSaveStatus("Unsaved changes");
    setSaveError("");
  }, []);

  const refreshAssetUrls = useCallback((assetId, failedSource) => {
    if (!assetId || assetRefreshRef.current) return assetRefreshRef.current;
    const activeSource = documentRef.current?.assets?.find((asset) => asset.id === assetId)?.src;
    if (activeSource && activeSource !== failedSource) return Promise.resolve();

    const request = (async () => {
      try {
        const refreshed = adminMode
          ? await getAdminBookDesign(targetId)
          : await projectService.getProject(user.email, targetId);
        const latest = documentRef.current;
        const next = refreshAssetSources(latest, refreshed.document);
        if (next !== latest) {
          documentRef.current = next;
          setDocument(next);
          setRenderToken((value) => value + 1);
        } else if (latest?.assets?.find((asset) => asset.id === assetId)?.src === failedSource) {
          setSaveError("A page image could not be loaded. Its secure preview link could not be refreshed; reload the editor or sign in again.");
        }
      } catch {
        setSaveError("A page image could not be loaded. Its secure preview link could not be refreshed; reload the editor or sign in again.");
      } finally {
        assetRefreshRef.current = null;
      }
    })();
    assetRefreshRef.current = request;
    return request;
  }, [adminMode, targetId, user.email]);

  const saveNow = useCallback((providedSnapshot) => {
    const snapshot = providedSnapshot ?? (documentRef.current ? cloneDocument(documentRef.current) : null);
    if (!snapshot) return Promise.resolve(false);
    if (!providedSnapshot && !dirtyRef.current) return Promise.resolve(true);
    const snapshotKey = JSON.stringify(snapshot);
    let recoveryWarning = "";
    if (!adminMode) {
      try {
        projectService.saveRecovery(user.email, targetId, snapshot);
      } catch (failure) {
        recoveryWarning = failure instanceof Error
          ? `Local recovery copy unavailable: ${failure.message}`
          : "Local recovery copy unavailable.";
      }
    }
    const queuedSave = saveQueueRef.current(snapshotKey, async () => {
      setSaveStatus("Saving");
      try {
        if (!adminMode) {
          const savedProject = await projectService.saveDocument(user.email, targetId, snapshot);
          const latest = documentRef.current;
          const refreshed = refreshAssetSources(latest, savedProject.document);
          if (refreshed !== latest) {
            documentRef.current = refreshed;
            setDocument(refreshed);
            setRenderToken((value) => value + 1);
          }
        } else {
          const savedDesign = await saveAdminBookDesign(targetId, snapshot);
          const latest = documentRef.current;
          if (latest?.metadata.updatedAt === snapshot.metadata.updatedAt) {
            documentRef.current = savedDesign.document;
            setDocument(savedDesign.document);
            setRenderToken((value) => value + 1);
          } else {
            const refreshed = refreshAssetSources(latest, savedDesign.document);
            if (refreshed !== latest) {
              documentRef.current = refreshed;
              setDocument(refreshed);
              setRenderToken((value) => value + 1);
            }
          }
        }

        if (documentRef.current?.metadata.updatedAt === snapshot.metadata.updatedAt) {
          if (!adminMode && !recoveryWarning) {
            try {
              projectService.clearRecovery(user.email, targetId);
            } catch (failure) {
              recoveryWarning = failure instanceof Error
                ? `The project is saved, but its recovery copy could not be cleared: ${failure.message}`
                : "The project is saved, but its recovery copy could not be cleared.";
            }
          }
          dirtyRef.current = false;
          setSaveStatus(navigator.onLine ? "Saved" : "Offline");
        }
        setSaveError(recoveryWarning);
        return true;
      } catch (failure) {
        setSaveStatus("Save failed");
        const message = failure instanceof Error ? failure.message : "This change could not be saved.";
        setSaveError(adminMode ? message : `${message} Your recovery copy is kept in this browser.`);
        if (!adminMode) {
          try {
            projectService.saveRecovery(user.email, targetId, snapshot);
          } catch (recoveryFailure) {
            setSaveError(`${message} ${recoveryFailure instanceof Error ? recoveryFailure.message : ""}`.trim());
          }
        }
        return false;
      }
    });
    return queuedSave;
  }, [adminMode, targetId, user.email]);

  useEffect(() => {
    if (!document || !query.data) return undefined;
    if (!dirtyRef.current) return undefined;
    setSaveStatus("Saving");
    const snapshot = cloneDocument(document);
    const timer = window.setTimeout(() => { void saveNow(snapshot); }, 650);
    return () => window.clearTimeout(timer);
  }, [adminMode, document, query.data, saveNow]);

  useEffect(() => () => {
    const latest = documentRef.current;
    if (latest && query.data && (!adminMode || dirtyRef.current)) {
      saveNow(cloneDocument(latest)).catch((saveFailure) => {
        try {
          if (!adminMode) projectService.saveRecovery(user.email, targetId, latest);
          console.warn("Editor document save failed during navigation.", saveFailure);
        } catch (failure) {
          console.error("Could not preserve the editor document while leaving the editor.", { saveFailure, recoveryFailure: failure });
        }
      });
    }
  }, [adminMode, query.data, saveNow, targetId]);

  useEffect(() => {
    const onOnline = () => {
      if (!documentRef.current) return;
      if (dirtyRef.current) {
        setSaveStatus("Unsaved changes");
        void saveNow();
      } else {
        setSaveStatus("Saved");
      }
    };
    const onOffline = () => setSaveStatus("Offline");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [saveNow]);

  const undo = useCallback(() => {
    const previous = undoStack.current.pop();
    if (!previous || !documentRef.current) return;
    redoStack.current.push(cloneDocument(documentRef.current));
    documentRef.current = previous;
    dirtyRef.current = true;
    setDocument(previous);
    setSelectedId(null);
    setRenderToken((value) => value + 1);
    setSaveStatus("Unsaved changes");
  }, []);
  const redo = useCallback(() => {
    const next = redoStack.current.pop();
    if (!next || !documentRef.current) return;
    undoStack.current.push(cloneDocument(documentRef.current));
    documentRef.current = next;
    dirtyRef.current = true;
    setDocument(next);
    setSelectedId(null);
    setRenderToken((value) => value + 1);
    setSaveStatus("Unsaved changes");
  }, []);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (previewOnly) return;
      const target = event.target;
      const typing = target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
      const modifier = event.ctrlKey || event.metaKey;
      if (typing) {
        if (modifier && event.key.toLowerCase() === "s") event.preventDefault();
        return;
      }
      if (canvasApi.current?.canvas?.getActiveObject()?.isEditing) return;
      if (modifier && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
      if (modifier && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); return; }
      if (modifier && event.key.toLowerCase() === "c" && selectedElement) { clipboard.current = structuredClone(selectedElement); return; }
      if (modifier && event.key.toLowerCase() === "v" && clipboard.current) {
        const copy = { ...clipboard.current, id: crypto.randomUUID(), x: Math.min(0.8, clipboard.current.x + 0.025), y: Math.min(0.85, clipboard.current.y + 0.025) };
        const next = cloneDocument(documentRef.current);
        const targetPage = next.pages.find((item) => item.id === activePageId);
        targetPage.elements.push(copy);
        commit(next);
        setSelectedId(copy.id);
        setRenderToken((value) => value + 1);
        return;
      }
      if (modifier && event.key.toLowerCase() === "d" && selectedElement) { event.preventDefault(); duplicateSelected(); return; }
      if (modifier && event.key.toLowerCase() === "a") {
        event.preventDefault();
        const canvas = canvasApi.current?.canvas;
        const objects = canvas?.getObjects() ?? [];
        if (objects.length) canvas.setActiveObject(new ActiveSelection(objects, { canvas }));
        canvas?.requestRenderAll();
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") { if (selectedId) { event.preventDefault(); deleteSelected(); } }
      if (modifier && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveNow();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  useEffect(() => {
    if (!document?.metadata.title) return undefined;
    const onBeforeUnload = (event) => {
      if (dirtyRef.current || saveStatus === "Saving" || saveStatus === "Unsaved changes" || saveStatus === "Save failed") {
        if (!adminMode && documentRef.current) {
          try {
            projectService.saveRecovery(user.email, targetId, cloneDocument(documentRef.current));
          } catch (failure) {
            console.error("Could not preserve the editor document before leaving.", failure);
            setSaveError(failure instanceof Error ? failure.message : "The local recovery copy could not be saved.");
          }
        }
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [adminMode, document?.metadata.title, saveStatus, targetId, user.email]);

  if (query.isPending) return <main className="page-shell"><LoadingState /></main>;
  if (query.isError) return <main className="page-shell"><ErrorState onRetry={query.refetch} /></main>;
  if (!query.data) return <main className="page-shell not-found"><span className="eyebrow">Your workspace</span><h1>We couldn’t find<br /><em>that project.</em></h1><Link className="button button-dark" to="/dashboard/projects">Go to my projects <ChevronRight size={15} /></Link></main>;
  if (!query.data.document) return <main className="page-shell not-found" role="alert"><span className="eyebrow">Your workspace</span><h1>This book isn’t<br /><em>ready to edit.</em></h1><p>This project has no saved book document yet. Return to your projects or try loading it again.</p><button className="button button-outline" type="button" onClick={() => query.refetch()}>Try again</button><Link className="button button-dark" to="/dashboard/projects">Go to my projects <ChevronRight size={15} /></Link></main>;
  if (!document) return <main className="page-shell"><LoadingState /></main>;
  const thumbnailSize = getPageThumbnailSize(document.book.size, 42, 44);

  function updatePage(pageId, updater, history = true) {
    const next = cloneDocument(documentRef.current);
    const target = next.pages.find((item) => item.id === pageId);
    if (!target) return;
    updater(target, next);
    next.metadata.updatedAt = new Date().toISOString();
    commit(next, history);
  }

  function addText(kind) {
    const element = createTextElement(kind);
    updatePage(page.id, (target) => target.elements.push(element));
    setSelectedId(element.id);
    setRenderToken((value) => value + 1);
    canvasApi.current?.selectObject(element.id);
  }

  function addShape(shape) {
    const element = createShapeElement(shape);
    updatePage(page.id, (target) => target.elements.push(element));
    setSelectedId(element.id);
    setRenderToken((value) => value + 1);
  }

  function addPhoto(asset) {
    if (!asset) return;
    const selected = selectedElement;
    if (selected?.type === "shape" && selected.shape === "photo-placeholder") {
      updatePage(page.id, (target) => {
        const index = target.elements.findIndex((item) => item.id === selected.id);
        if (index !== -1) target.elements[index] = { ...createPhotoElement(asset, selected.x, selected.y, selected.width, selected.height), id: selected.id };
      });
      setSelectedId(null);
    } else if (selected?.type === "image") {
      updatePage(page.id, (target) => {
        const index = target.elements.findIndex((item) => item.id === selected.id);
        if (index !== -1) target.elements[index] = { ...createPhotoElement(asset, selected.x, selected.y, selected.width, selected.height), id: selected.id };
      });
    } else {
      const photo = createPhotoElement(asset, 0.1, 0.1, 0.8, 0.8);
      updatePage(page.id, (target) => target.elements.push(photo));
      setSelectedId(photo.id);
    }
    setRenderToken((value) => value + 1);
    setPanel("photos");
  }

  async function addUploadedFiles(fileList) {
    const files = Array.from(fileList ?? []);
    for (const file of files) {
      if (!editorImageTypes.has(file.type.toLowerCase())) { setSaveError(`${file.name} is not a supported image.`); return; }
      if (file.size > 15 * 1024 * 1024) { setSaveError(`${file.name} is larger than 15 MB.`); return; }
      try {
        const asset = adminMode
          ? await uploadAdminDesignAsset(file).then((uploaded) => ({
            id: crypto.randomUUID(),
            assetKey: uploaded.assetKey,
            name: uploaded.filename,
            mimeType: uploaded.mimeType,
            size: uploaded.size,
            checksum: uploaded.checksum,
            width: uploaded.width,
            height: uploaded.height,
            src: uploaded.url,
          }))
          : await projectService.uploadAsset(user.email, targetId, file);
        const next = cloneDocument(documentRef.current);
        next.assets.push(asset);
        next.metadata.updatedAt = new Date().toISOString();
        const photo = createPhotoElement(asset);
        next.pages.find((item) => item.id === activePageId)?.elements.push(photo);
        commit(next);
        setSelectedId(photo.id);
        setRenderToken((value) => value + 1);
        setPanel("photos");
        setSaveError("");
      } catch (failure) {
        setSaveError(failure instanceof Error ? `Could not upload ${file.name}: ${failure.message}` : `Could not upload ${file.name}. Please try again.`);
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function applyLayout(layout) {
    if (page.elements.length && !window.confirm("This layout will replace the content on this page. Your other pages will not be changed. Continue?")) return;
    const assets = documentRef.current.assets.filter((asset) => asset.src);
    updatePage(page.id, (target) => {
      const elements = layout.slots.map((slot, index) => {
        const asset = assets[index];
        return asset
          ? createPhotoElement(asset, slot.x, slot.y, slot.width, slot.height)
          : { ...createShapeElement("rectangle"), shape: "photo-placeholder", x: slot.x, y: slot.y, width: slot.width, height: slot.height, fill: "#edf0eb", stroke: "#d8ded8", strokeWidth: 0.001 };
      });
      if (layout.text) {
        const text = createTextElement(layout.id === "magazine" ? "heading" : "paragraph");
        Object.assign(text, layout.text, { text: layout.id === "magazine" ? "A story to remember" : "Add a caption to your story." });
        elements.push(text);
      }
      target.elements = elements;
      target.layout = layout.id;
    });
    setSelectedId(null);
    setRenderToken((value) => value + 1);
  }

  function changeBackground(color) {
    updatePage(page.id, (target) => { target.background = { color }; });
  }

  function addPage() {
    const newPage = createPage("page", document.pageOrder.length, "#fffdf9");
    const next = cloneDocument(documentRef.current);
    const currentIndex = next.pageOrder.indexOf(activePageId);
    next.pages.push(newPage);
    next.pageOrder.splice(currentIndex + 1, 0, newPage.id);
    next.book.pageCount = next.pageOrder.filter((id) => next.pages.find((item) => item.id === id)?.type !== "cover").length;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
    setActivePageId(newPage.id);
    setRenderToken((value) => value + 1);
  }

  function duplicatePage(pageId) {
    const source = documentRef.current.pages.find((item) => item.id === pageId);
    if (!source) return;
    const copy = duplicatePageRecord(source, `Page ${documentRef.current.pageOrder.length}`);
    copy.type = "page";
    const next = cloneDocument(documentRef.current);
    const currentIndex = next.pageOrder.indexOf(pageId);
    next.pages.splice(next.pages.findIndex((item) => item.id === pageId) + 1, 0, copy);
    next.pageOrder.splice(currentIndex + 1, 0, copy.id);
    next.book.pageCount = next.pageOrder.filter((id) => next.pages.find((item) => item.id === id)?.type !== "cover").length;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
    setActivePageId(copy.id);
    setRenderToken((value) => value + 1);
  }

  function deletePage(pageId) {
    const target = documentRef.current.pages.find((item) => item.id === pageId);
    if (!target || target.type === "cover") return;
    if (!window.confirm(`Delete ${target.label}? This page and its contents will be removed.`)) return;
    const result = removePage(documentRef.current, pageId);
    if (!result) return;
    const next = result.document;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
    if (activePageId === pageId) setActivePageId(result.nextActivePageId);
    setSelectedId(null);
    setRenderToken((value) => value + 1);
  }

  function reorderPage(movedId, beforeId) {
    const next = cloneDocument(documentRef.current);
    const reordered = reorderPageIds(next.pageOrder, movedId, beforeId);
    if (reordered === next.pageOrder) return;
    next.pageOrder = reordered;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
  }

  function duplicateSelected() {
    if (!selectedElement) return;
    const copy = { ...selectedElement, id: crypto.randomUUID(), x: Math.min(0.8, selectedElement.x + 0.025), y: Math.min(0.85, selectedElement.y + 0.025) };
    updatePage(page.id, (target) => target.elements.push(copy));
    setSelectedId(copy.id);
    setRenderToken((value) => value + 1);
  }

  function deleteSelected() {
    if (!selectedId) return;
    const selectedIds = new Set((canvasApi.current?.canvas?.getActiveObjects() ?? []).map((object) => object.elementId).filter(Boolean));
    selectedIds.add(selectedId);
    updatePage(page.id, (target) => { target.elements = target.elements.filter((item) => !selectedIds.has(item.id)); });
    setSelectedId(null);
    setRenderToken((value) => value + 1);
  }

  function updateSelected(changes) {
    if (!selectedId) return;
    updatePage(page.id, (target) => {
      const element = target.elements.find((item) => item.id === selectedId);
      if (element) Object.assign(element, changes);
    });
    const object = canvasApi.current?.findObject(selectedId);
    if (object && !["fit", "zoom", "cropX", "cropY", "borderRadius", "shadow", "width", "height"].some((key) => key in changes)) {
      const fabricChanges = { ...changes };
      if (changes.color) fabricChanges.fill = changes.color;
      if (changes.alignment) fabricChanges.textAlign = changes.alignment;
      if (changes.fontSize) fabricChanges.fontSize = changes.fontSize * Math.round(760 * (document.book.size.height / document.book.size.width));
      if (changes.letterSpacing !== undefined) fabricChanges.charSpacing = changes.letterSpacing;
      if (changes.borderWidth !== undefined) fabricChanges.strokeWidth = changes.borderWidth * 760;
      if (changes.rotation !== undefined) fabricChanges.angle = changes.rotation;
      if (changes.x !== undefined) fabricChanges.left = changes.x * 760;
      if (changes.y !== undefined) fabricChanges.top = changes.y * Math.round(760 * (document.book.size.height / document.book.size.width));
      if (changes.italic !== undefined) fabricChanges.fontStyle = changes.italic ? "italic" : "normal";
      object.set(fabricChanges);
      object.initDimensions?.();
      object.setCoords();
      canvasApi.current?.canvas?.requestRenderAll();
    } else {
      setRenderToken((value) => value + 1);
    }
  }

  function changeTitle(title) {
    const next = cloneDocument(documentRef.current);
    next.metadata.title = title;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
  }

  function changeCover(cover) {
    const next = cloneDocument(documentRef.current);
    next.cover = cover;
    next.metadata.updatedAt = new Date().toISOString();
    commit(next);
  }

  function navigateToReviewedPage(pageId) {
    if (documentRef.current.pages.some((item) => item.id === pageId)) {
      setActivePageId(pageId);
      setSelectedId(null);
      setMobilePanel(false);
    }
    setBookReviewOpen(false);
  }

  function navigateFromPreview(pageId) {
    if (pageId && documentRef.current.pages.some((item) => item.id === pageId)) {
      setActivePageId(pageId);
      setSelectedId(null);
      setMobilePanel(false);
    }
    setBookPreviewOpen(false);
  }

  function fitZoom() { setZoom(75); }

  async function toggleBookPublication() {
    if (!adminMode || dirtyRef.current || saveStatus !== "Saved") return;
    setPublishing(true);
    setSaveError("");
    try {
      if (bookPublished) {
        await unpublishAdminBookDesign(targetId);
        setBookPublished(false);
      } else {
        await publishAdminBookDesign(targetId);
        setBookPublished(true);
      }
    } catch (failure) {
      setSaveError(failure instanceof Error ? failure.message : "Book publication could not be changed.");
    } finally {
      setPublishing(false);
    }
  }

  const statusIcon = saveStatus === "Saving" ? <LoaderCircle className="editor-spin" size={14} /> : saveStatus === "Offline" ? <CloudOff size={14} /> : saveStatus === "Save failed" ? <CloudOff size={14} /> : <Check size={14} />;

  return <main className={`book-editor${recoveryNotice || saveError ? " has-notices" : ""}${mobilePanel ? " mobile-panel-open" : ""}${mobilePanel && panel === "properties" ? " mobile-properties-open" : ""}${preview ? " is-preview" : ""}`}>
    <header className="editor-topbar">
      <Link to={adminMode ? "/admin/books" : "/dashboard/projects"} className="editor-back" aria-label={adminMode ? "Back to books" : "Back to projects"}><ArrowLeft size={17} /><span>{adminMode ? "Books" : "Projects"}</span></Link>
      <div className="editor-project-title"><BookOpen size={17} /><input aria-label="Project name" value={document.metadata.title} readOnly={previewOnly} onChange={(event) => changeTitle(event.target.value)} /><ChevronDown size={13} /></div>
      <span className={`editor-save-status status-${saveStatus.toLowerCase().replaceAll(" ", "-")}`}>{statusIcon}<span>{saveStatus}</span></span>
      <div className="editor-topbar-divider" />
      {!previewOnly ? <div className="editor-history-actions"><button type="button" disabled={!undoStack.current.length} onClick={undo} aria-label="Undo"><Undo2 size={17} /></button><button type="button" disabled={!redoStack.current.length} onClick={redo} aria-label="Redo"><Redo2 size={17} /></button></div> : null}
      <div className="editor-topbar-spacer" />
      {adminMode && !previewOnly ? <>
        <button type="button" className="editor-preview-button" disabled={!dirtyRef.current || saveStatus === "Saving" || publishing}
          onClick={() => { void saveNow(); }}><Save size={15} />Save Draft</button>
        <button type="button" className="editor-preview-button" disabled={dirtyRef.current || saveStatus !== "Saved" || publishing}
          onClick={() => { void toggleBookPublication(); }}>
          {publishing ? <LoaderCircle size={15} className="editor-spin" /> : <Send size={15} />}
          {bookPublished ? "Unpublish design" : "Publish design"}
        </button>
      </> : null}
      {!previewOnly ? <button type="button" className={`editor-top-icon${guides ? " active" : ""}`} onClick={() => setGuides((value) => !value)} aria-label="Toggle safe margin guides"><span className="editor-guide-icon" /></button> : null}
      {!previewOnly ? <button type="button" className="editor-preview-button" onClick={() => setCoverDesignerOpen(true)}><BookOpen size={15} />Cover</button> : null}
      {!previewOnly ? <button type="button" className="editor-preview-button" onClick={() => setBookReviewOpen(true)}><Check size={15} />Final review</button> : null}
      <button type="button" className={`editor-preview-button${preview ? " active" : ""}`} onClick={() => { if (!previewOnly) setPreview(false); setBookPreviewOpen(true); }}><Eye size={15} />Full preview</button>
      <button type="button" className="editor-top-icon" onClick={() => setHelpOpen(true)} aria-label="Editor help"><HelpCircle size={17} /></button>
    </header>
    {recoveryNotice || saveError ? <div className="editor-notices">
      {recoveryNotice ? <div className="editor-recovery-notice" role="status"><Cloud size={15} /> An unsaved local version was recovered. It will be saved with your next changes.<button type="button" onClick={() => setRecoveryNotice(false)} aria-label="Dismiss recovery notice"><X size={14} /></button></div> : null}
      {saveError ? <div className="editor-error-notice" role="alert"><CloudOff size={15} />{saveError}<button type="button" onClick={() => setSaveError("")} aria-label="Dismiss save message"><X size={14} /></button></div> : null}
    </div> : null}
    <div className="editor-workspace">
      {!previewOnly ? <nav className="editor-toolbar" aria-label="Editor tools">{tools.map(({ id, label, Icon }) => <button type="button" key={id} className={panel === id ? "active" : ""} onClick={() => { setPanel(id); setMobilePanel(true); }} aria-label={label}><Icon size={19} /><span>{label}</span></button>)}{selectedElement ? <button type="button" className="editor-mobile-properties-button" onClick={() => { setPanel("properties"); setMobilePanel(true); }} aria-label="Selected item properties"><Paintbrush size={19} /><span>Edit</span></button> : null}</nav> : null}
      {!preview && panel !== "properties" ? <SidebarPanel panel={panel} document={document} page={page} activePageId={activePageId} setActivePageId={setActivePageId} setSelectedId={setSelectedId} setMobilePanel={setMobilePanel} inputRef={fileInputRef} onAddText={addText} onAddShape={addShape} onAddPhoto={addPhoto} onUpload={addUploadedFiles} onApplyLayout={applyLayout} onBackground={changeBackground} onReorderPage={reorderPage} onAddPage={addPage} onDuplicatePage={duplicatePage} onDeletePage={deletePage} onClose={() => setMobilePanel(false)} /> : null}
      <section className="editor-stage">
        <div className="editor-stage-topline"><span>{getPageLabel(page, document)} <small>· {document.book.size.width} × {document.book.size.height} in</small></span><button className="editor-mobile-pages-button" type="button" onClick={() => { setPanel("pages"); setMobilePanel(true); }}>Pages</button><button className="editor-mobile-panel-close" type="button" onClick={() => setMobilePanel(false)}><X size={17} /> Close</button><span className="editor-page-counter">{getPagePosition(page, document)}</span></div>
        <div className="editor-canvas-scroll">
          <div className="editor-canvas-mat" style={{ width: `${zoom}%`, maxWidth: "760px" }}>
            <EditorCanvas document={document} page={page} activePageId={activePageId} pageTitle={getPageLabel(page, document)} onElementsChange={(elements, pageId, history) => updatePage(pageId, (target) => { target.elements = elements; }, history)} onSelectionChange={setSelectedId} onCanvasError={(failure) => setSaveError(`The page preview could not be rendered: ${failure.message}`)} canvasApi={canvasApi} renderToken={renderToken} guides={guides && !preview} zoom={100} selectedId={selectedId} preview={preview} />
          </div>
        </div>
        <div className="editor-zoom-controls"><button type="button" onClick={() => setZoom((value) => Math.max(35, value - 10))} aria-label="Zoom out"><Minus size={14} /></button><span>{zoom}%</span><button type="button" onClick={() => setZoom((value) => Math.min(100, value + 10))} aria-label="Zoom in"><Plus size={14} /></button><i /><button type="button" onClick={fitZoom}>Fit</button><button type="button" onClick={() => setZoom(100)}>100%</button></div>
      </section>
      {!preview ? <ElementInspector element={selectedElement} pageHeight={Math.round(760 * (document.book.size.height / document.book.size.width))} onChange={updateSelected} onDelete={deleteSelected} onDuplicate={duplicateSelected} onShowPhotos={() => { setPanel("photos"); setMobilePanel(true); }} onClose={() => setMobilePanel(false)} assets={document.assets.filter((asset) => asset.src)} /> : null}
    </div>
    <footer className="editor-page-strip">
      <div className="editor-strip-label"><span className="eyebrow">Your book</span><small>{document.pageOrder.filter((id) => document.pages.find((item) => item.id === id)?.type !== "cover").length} interior pages</small></div>
      <div className="editor-timeline">
        <div className="editor-thumbnails" role="group" aria-label="Book page thumbnails">
          {document.pageOrder.map((id) => {
          const item = document.pages.find((candidate) => candidate.id === id);
          if (!item) return null;
          return <button
            type="button"
            key={id}
            ref={(element) => {
              if (element) thumbnailRefs.current.set(id, element);
              else thumbnailRefs.current.delete(id);
            }}
            className={`editor-page-thumb${activePageId === id ? " active" : ""}`}
            onClick={() => { setActivePageId(id); setSelectedId(null); setMobilePanel(false); }}
            aria-label={`Open ${getPageLabel(item, document)}`}
            aria-current={activePageId === id ? "page" : undefined}
            title={getPageLabel(item, document)}
          >
            <span className="editor-thumb-frame">
              <PageArtwork
                page={item}
                previewWidth={thumbnailSize.width}
                previewHeight={thumbnailSize.height}
                className="editor-thumb-preview"
                imageLoading="lazy"
                style={thumbnailSize}
                onAssetError={refreshAssetUrls}
                emptyPlaceholder
              />
            </span>
            <small>{getPageLabel(item, document)}</small>
          </button>;
          })}
        </div>
        {!previewOnly ? <button className="editor-add-page-button" type="button" onClick={addPage}><Plus size={17} /><span>Add page</span></button> : null}
      </div>
    </footer>
    <input ref={fileInputRef} className="editor-visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => addUploadedFiles(event.target.files)} />
    {helpOpen ? <div className="editor-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelpOpen(false); }}><section className="editor-help-dialog" role="dialog" aria-modal="true" aria-labelledby="editor-help-title"><button className="editor-help-close" type="button" onClick={() => setHelpOpen(false)} aria-label="Close help"><X size={17} /></button><span className="eyebrow">A few helpful things</span><h2 id="editor-help-title">Made for your memories.</h2><p>Drag objects to move them, and use the corners to resize. Your work is saved automatically on this device.</p><ul><li><kbd>Delete</kbd> removes the selected item</li><li><kbd>Ctrl</kbd> / <kbd>⌘</kbd> + <kbd>Z</kbd> undo</li><li><kbd>Ctrl</kbd> / <kbd>⌘</kbd> + <kbd>D</kbd> duplicate</li><li><kbd>Ctrl</kbd> / <kbd>⌘</kbd> + <kbd>S</kbd> save now</li></ul><button className="button button-dark" type="button" onClick={() => setHelpOpen(false)}>Back to my book</button></section></div> : null}
    {coverDesignerOpen ? <CoverDesigner document={document} onChange={changeCover} onClose={() => setCoverDesignerOpen(false)} /> : null}
    {bookPreviewOpen ? <BookPreview document={document} initialPageId={activePageId} onClose={() => setBookPreviewOpen(false)} onEditPage={navigateFromPreview} onContinueReview={() => { setBookPreviewOpen(false); setBookReviewOpen(true); }} onAssetError={refreshAssetUrls} /> : null}
    {bookReviewOpen ? <BookReview document={document} onClose={() => setBookReviewOpen(false)} onGoToPage={navigateToReviewedPage} adminMode={adminMode} /> : null}
  </main>;
}
