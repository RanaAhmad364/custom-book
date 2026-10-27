import { useState } from "react";
import { ArrowRight, CircleAlert, Download, FileDown, LoaderCircle, LockKeyhole, RefreshCw, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { pdfOrderService } from "../../services/pdfOrderService.js";
import { projectService } from "../../services/projectService.js";
import "./ProjectPdfAccessAction.css";

const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function ProjectPdfAccessAction({
  projectId,
  initialAccess,
  className = "button button-outline",
  disabled = false,
}) {
  const { user } = useAuth();
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  async function download(forceRetry = false) {
    if (busy || disabled) return;
    setBusy(true);
    setDialog(null);
    try {
      let access = await projectService.getPdfAccess(user.email, projectId);
      if (access.state === "not_purchased") {
        setDialog({ kind: "not-purchased" });
        return;
      }
      if (access.state === "payment_pending") {
        setDialog({ kind: "payment-pending", orderId: access.orderId });
        return;
      }
      if (access.state === "generating" && access.generationStatus === "failed" && !forceRetry) {
        setDialog({
          kind: "generation-failed",
          message: access.generationError?.message || "Payment is valid, but PDF generation failed.",
        });
        return;
      }
      if (access.state === "generating" && ["queued", "generating"].includes(access.generationStatus)) {
        setDialog({ kind: "generating" });
        return;
      }

      const job = await pdfOrderService.requestGeneration(access.orderId);
      if (job.status !== "ready") {
        setDialog({ kind: "generating" });
        for (let attempt = 0; attempt < 90; attempt += 1) {
          await wait(2000);
          access = await projectService.getPdfAccess(user.email, projectId);
          if (access.state === "ready") break;
          if (access.generationStatus === "failed") {
            setDialog({ kind: "generation-failed", message: access.generationError?.message });
            return;
          }
        }
      } else {
        access = await projectService.getPdfAccess(user.email, projectId);
      }

      if (access.state !== "ready" || !access.downloadId) {
        setDialog({ kind: "generation-failed", message: "PDF generation is taking longer than expected. Please retry." });
        return;
      }
      const file = await pdfOrderService.getDownload(access.downloadId);
      window.location.assign(file.url);
      setDialog(null);
    } catch (failure) {
      const code = failure?.code;
      if (code === "PDF_NOT_PURCHASED") setDialog({ kind: "not-purchased" });
      else if (code === "PDF_PAYMENT_PENDING") setDialog({ kind: "payment-pending", orderId: initialAccess?.orderId });
      else if (code === "PDF_GENERATING") setDialog({ kind: "generating" });
      else setDialog({ kind: "error", message: failure instanceof Error ? failure.message : "The PDF could not be prepared." });
    } finally {
      setBusy(false);
    }
  }

  const message = dialog?.kind === "not-purchased"
    ? "Please purchase this PDF first, then you can download it"
    : dialog?.kind === "payment-pending"
      ? "Your PDF payment is pending. Complete checkout before downloading."
      : dialog?.kind === "generating"
        ? "Your PDF is being generated. You can download it when it’s ready."
        : dialog?.kind === "generation-failed"
          ? dialog.message || "PDF generation failed. Your payment is valid; retry generation without paying again."
          : dialog?.message;

  return <>
    <button className={className} type="button" onClick={download} disabled={busy || disabled}>
      {busy ? <LoaderCircle className="pdf-access-spin" size={16} /> : <Download size={16} />}
      {busy ? "Preparing PDF…" : initialAccess?.generationStatus === "failed" ? "Retry PDF generation" : "Download PDF"}
    </button>
    {dialog ? <div className="pdf-access-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setDialog(null);
    }}>
      <section className="pdf-access-dialog" role="alertdialog" aria-modal="true" aria-labelledby="pdf-access-title">
        <button className="pdf-access-close" type="button" aria-label="Close message" onClick={() => setDialog(null)}><X size={17} /></button>
        <span className="pdf-access-icon">{dialog.kind === "not-purchased" ? <LockKeyhole size={21} /> : dialog.kind === "generating" ? <LoaderCircle className="pdf-access-spin" size={21} /> : <CircleAlert size={21} />}</span>
        <h2 id="pdf-access-title">{dialog.kind === "not-purchased" ? "PDF purchase required" : dialog.kind === "payment-pending" ? "Payment pending" : dialog.kind === "generating" ? "Preparing your PDF" : dialog.kind === "generation-failed" ? "PDF generation failed" : "PDF unavailable"}</h2>
        <p role="status">{message}</p>
        <div className="pdf-access-actions">
          {dialog.kind === "not-purchased" ? <Link className="button button-dark" to={`/create/design/${encodeURIComponent(projectId)}/pdf`} onClick={() => setDialog(null)}>Purchase <ArrowRight size={15} /></Link> : null}
          {dialog.kind === "payment-pending" && dialog.orderId ? <Link className="button button-dark" to={`/pdf/orders/${encodeURIComponent(dialog.orderId)}/processing`} onClick={() => setDialog(null)}>Pay now <ArrowRight size={15} /></Link> : null}
          {dialog.kind === "generation-failed" ? <button className="button button-dark" type="button" onClick={() => { setDialog(null); void download(true); }}><RefreshCw size={15} /> Retry generation</button> : null}
          {dialog.kind === "generating" ? <span className="pdf-access-note"><FileDown size={15} /> Refresh this page or try again shortly.</span> : null}
          <button className="button button-outline" type="button" onClick={() => setDialog(null)}>Close</button>
        </div>
      </section>
    </div> : null}
  </>;
}
