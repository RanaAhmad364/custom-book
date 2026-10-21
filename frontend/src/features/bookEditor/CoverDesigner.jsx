import { useState } from "react";
import { BookOpen, Check, ImagePlus, X } from "lucide-react";
import { CoverArtwork } from "./CoverArtwork.jsx";

const coverColors = ["#e8ece5", "#f4eee5", "#eadccf", "#e8e1ec", "#26352e", "#193f36"];
const coverSides = [
  { id: "front", label: "Front cover" },
  { id: "spine", label: "Spine" },
  { id: "back", label: "Back cover" },
];

export default function CoverDesigner({ document, onChange, onClose }) {
  const [side, setSide] = useState("front");
  const design = document.cover?.design ?? {};
  const face = design[side] ?? {};
  const assets = document.assets.filter((asset) => asset.src);

  function updateFace(changes) {
    onChange({
      ...document.cover,
      design: {
        ...design,
        [side]: {
          backgroundColor: side === "front" ? "#e8ece5" : "#f4eee5",
          fontFamily: "Georgia",
          textColor: "#20352d",
          layout: "center",
          ...face,
          ...changes,
        },
      },
    });
  }

  return <div className="editor-modal-backdrop cover-designer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="cover-designer-dialog" role="dialog" aria-modal="true" aria-labelledby="cover-designer-title">
      <header className="cover-designer-header">
        <div><span className="eyebrow">The finishing touch</span><h2 id="cover-designer-title">Design your cover</h2></div>
        <button type="button" className="editor-panel-close" onClick={onClose} aria-label="Close cover designer"><X size={17} /></button>
      </header>
      <div className="cover-designer-body">
        <div className="cover-designer-preview">
          <div className={`cover-preview-object side-${side}`}><CoverArtwork cover={document.cover} document={document} side={side} /></div>
          <span><BookOpen size={14} /> {coverSides.find((item) => item.id === side)?.label}</span>
        </div>
        <div className="cover-designer-controls">
          <div className="cover-side-tabs" role="tablist" aria-label="Cover side">
            {coverSides.map((item) => <button type="button" role="tab" aria-selected={side === item.id} className={side === item.id ? "active" : ""} key={item.id} onClick={() => setSide(item.id)}>{item.label}</button>)}
          </div>
          {side === "front" ? <>
            <label className="editor-field-label">Cover title<input value={face.title ?? document.metadata.title} maxLength={100} onChange={(event) => updateFace({ title: event.target.value })} /></label>
            <label className="editor-field-label">Subtitle<input value={face.subtitle ?? ""} maxLength={120} placeholder="A little more of your story" onChange={(event) => updateFace({ subtitle: event.target.value })} /></label>
            <div className="editor-field-pair"><label className="editor-field-label">Typography<select value={face.fontFamily ?? "Georgia"} onChange={(event) => updateFace({ fontFamily: event.target.value })}><option>Georgia</option><option>DM Sans</option><option>Arial</option><option>Times New Roman</option></select></label><label className="editor-field-label">Cover layout<select value={face.layout ?? "center"} onChange={(event) => updateFace({ layout: event.target.value })}><option value="center">Centered</option><option value="lower">Lower third</option><option value="minimal">Minimal</option></select></label></div>
            <label className="editor-field-label">Cover photo</label>
            <div className="cover-photo-choices">
              <button type="button" className={!face.photoAssetId ? "selected" : ""} onClick={() => updateFace({ photoAssetId: null })} aria-label="No cover photo"><X size={16} /></button>
              {assets.map((asset) => <button type="button" key={asset.id} className={face.photoAssetId === asset.id ? "selected" : ""} onClick={() => updateFace({ photoAssetId: asset.id })} aria-label={`Use ${asset.name} as cover photo`}><img src={asset.src} alt="" />{face.photoAssetId === asset.id ? <Check size={14} /> : null}</button>)}
              {!assets.length ? <span><ImagePlus size={14} /> Upload a photo in the editor to use it here.</span> : null}
            </div>
          </> : side === "spine" ? <>
            <label className="editor-field-label">Spine title<input value={face.title ?? document.metadata.title} maxLength={80} onChange={(event) => updateFace({ title: event.target.value })} /></label>
            <label className="editor-field-label">Typography<select value={face.fontFamily ?? "Georgia"} onChange={(event) => updateFace({ fontFamily: event.target.value })}><option>Georgia</option><option>DM Sans</option><option>Arial</option><option>Times New Roman</option></select></label>
          </> : <>
            <label className="editor-field-label">Back cover title<input value={face.title ?? document.metadata.title} maxLength={100} onChange={(event) => updateFace({ title: event.target.value })} /></label>
            <label className="editor-field-label">Back cover note<textarea rows={3} value={face.description ?? ""} placeholder="A short note to close the story" onChange={(event) => updateFace({ description: event.target.value })} /></label>
            <label className="editor-field-label">Typography<select value={face.fontFamily ?? "Georgia"} onChange={(event) => updateFace({ fontFamily: event.target.value })}><option>Georgia</option><option>DM Sans</option><option>Arial</option><option>Times New Roman</option></select></label>
          </>}
          <div className="editor-field-pair">
            <label className="editor-field-label">Background<input type="color" value={face.backgroundColor ?? (side === "front" ? "#e8ece5" : "#f4eee5")} onChange={(event) => updateFace({ backgroundColor: event.target.value })} /></label>
            <label className="editor-field-label">Type color<input type="color" value={face.textColor ?? "#20352d"} onChange={(event) => updateFace({ textColor: event.target.value })} /></label>
          </div>
          <div className="cover-color-swatches" aria-label="Cover colors">{coverColors.map((color) => <button type="button" key={color} aria-label={`Use cover color ${color}`} className={(face.backgroundColor ?? (side === "front" ? "#e8ece5" : "#f4eee5")) === color ? "active" : ""} style={{ backgroundColor: color }} onClick={() => updateFace({ backgroundColor: color })} />)}</div>
          <label className="editor-field-label">Print bleed<input type="number" min="0" max="1" step="0.01" value={document.cover?.design?.bleedInches ?? 0.125} onChange={(event) => onChange({ ...document.cover, design: { ...design, bleedInches: Math.max(0, Number(event.target.value)) } })} /><small>Use at least 0.125 in for standard print bleed.</small></label>
        </div>
      </div>
      <footer className="cover-designer-footer"><span>Cover changes are saved with your project.</span><button className="button button-dark" type="button" onClick={onClose}>Done</button></footer>
    </section>
  </div>;
}
