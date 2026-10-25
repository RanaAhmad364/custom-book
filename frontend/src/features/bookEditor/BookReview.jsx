import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Check, ClipboardCheck, Printer, X } from "lucide-react";
import { Link } from "react-router-dom";
import { analyzeBook } from "./bookReview.js";

function loadAssetDimensions(assets) {
  return Promise.all(assets.map((asset) => new Promise((resolve) => {
    if (!asset.src || !globalThis.Image) {
      resolve([asset.id, { width: asset.width, height: asset.height }]);
      return;
    }
    const image = new Image();
    image.onload = () => resolve([asset.id, { width: image.naturalWidth, height: image.naturalHeight }]);
    image.onerror = () => resolve([asset.id, { width: null, height: null, missing: true }]);
    image.src = asset.src;
  }))).then(Object.fromEntries);
}

export default function BookReview({ document, onClose, onGoToPage, adminMode = false }) {
  const [dimensions, setDimensions] = useState({});
  useEffect(() => {
    let mounted = true;
    loadAssetDimensions(document.assets ?? []).then((loaded) => { if (mounted) setDimensions(loaded); });
    return () => { mounted = false; };
  }, [document.assets]);

  const report = useMemo(() => analyzeBook(document, dimensions), [document, dimensions]);

  return <div className="editor-modal-backdrop book-review-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="book-review-dialog" role="dialog" aria-modal="true" aria-labelledby="book-review-title">
      <header className="book-review-header">
        <div><span className="eyebrow">Before it goes to print</span><h2 id="book-review-title">A final look through</h2><p>We checked your saved pages, images, typography, and print setup.</p></div>
        <button className="editor-panel-close" type="button" onClick={onClose} aria-label="Close final review"><X size={17} /></button>
      </header>
      <div className="book-review-summary">
        <article className={report.pdfReady ? "ready" : "attention"}><ClipboardCheck size={18} /><span><strong>{report.pdfReady ? "Ready for PDF" : "Needs Attention"}</strong><small>{report.pdfReady ? "No blocking page issues found." : "Resolve the blocking items below first."}</small></span>{report.pdfReady ? <Check size={17} /> : <AlertTriangle size={17} />}</article>
        <article className={report.printingReady ? "ready" : "attention"}><Printer size={18} /><span><strong>{report.printingReady ? "Ready for Printing" : "Needs Attention"}</strong><small>{report.printingReady ? "Print checks look good." : "Review print quality and production checks."}</small></span>{report.printingReady ? <Check size={17} /> : <AlertTriangle size={17} />}</article>
      </div>
      <div className="book-review-facts"><span><strong>{report.pageCount}</strong> interior pages</span><span><strong>{report.dimensions}</strong> book dimensions</span><span><strong>{document.book?.coverType || "Not selected"}</strong> cover type</span></div>
      <div className="book-review-issues">
        <h3>{report.issues.length ? `Items to review · ${report.issues.length}` : "Everything looks in order"}</h3>
        {!report.issues.length ? <p className="book-review-clear"><Check size={17} /> No missing photos, empty pages, or detected layout concerns.</p> :
          <ul>{report.issues.map((issue) => <li key={issue.id} className={`severity-${issue.severity}`}>
            <span className="review-issue-icon">{issue.severity === "blocking" ? <AlertTriangle size={16} /> : <Printer size={16} />}</span>
            <span><strong>{issue.message}</strong><small>{issue.pageLabel ?? "Book setup"} · {issue.severity === "blocking" ? "Must fix" : issue.severity === "print" ? "Print check" : "Check page"}</small></span>
            {issue.pageId ? <button type="button" onClick={() => onGoToPage(issue.pageId)}>Go to page <ArrowRight size={14} /></button> : null}
          </li>)}</ul>}
      </div>
      <footer className="book-review-footer"><span>{adminMode ? "Reviewing the admin master design. Publishing is managed from the book catalog." : "Based on the current saved book document. Final production output may vary."}</span><div><button className="button button-outline" type="button" onClick={onClose}>Back to editor</button>{!adminMode && report.pdfReady ? <Link className="button button-outline" to={`/create/design/${document.metadata.id}/print`} onClick={onClose}>Order print <ArrowRight size={15} /></Link> : null}{!adminMode && report.pdfReady ? <Link className="button button-dark" to={`/create/design/${document.metadata.id}/pdf`} onClick={onClose}>Purchase PDF <ArrowRight size={15} /></Link> : null}</div></footer>
    </section>
  </div>;
}
