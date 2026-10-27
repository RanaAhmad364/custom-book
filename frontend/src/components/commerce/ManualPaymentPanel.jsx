import { useState } from "react";
import { CircleAlert, Clock3, LoaderCircle, Upload } from "lucide-react";
import { paymentMethodService } from "../../services/paymentMethodService.js";
import "./ManualPaymentPanel.css";

export function ManualPaymentPanel({ order, onSubmitted }) {
  const [reference, setReference] = useState(order?.submittedPaymentReference ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (order?.paymentProvider !== "manual" || order.paymentStatus !== "pending") return null;
  const submitted = order.manualReferenceStatus === "submitted";
  const instructions = order.paymentInstructions ?? {};

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await paymentMethodService.submitManualReference(order.paymentId, reference);
      await onSubmitted();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The transfer reference could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="manual-payment-panel" aria-label="Manual payment instructions">
    <span className="eyebrow">Manual transfer</span>
    <h2>{submitted ? "Transfer details received" : "Pay by bank transfer or mobile wallet"}</h2>
    {submitted
      ? <p><Clock3 size={16} /> Your transfer reference was submitted. We’ll notify you after an administrator verifies the payment.</p>
      : <p>Transfer the exact amount below, then submit the transaction reference from your receipt. Your order stays unpaid until we verify it.</p>}
    <dl>
      {Object.entries(instructions)
        .filter(([key, value]) => value && key !== "note")
        .map(([key, value]) => <div key={key}><dt>{key.replaceAll(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase())}</dt><dd>{value}</dd></div>)}
    </dl>
    {instructions.note ? <small>{instructions.note}</small> : null}
    {!submitted ? <form onSubmit={submit}>
      <label htmlFor="manual-transfer-reference">Transaction reference</label>
      <div><input id="manual-transfer-reference" value={reference} onChange={(event) => setReference(event.target.value)} maxLength={160} required />
        <button className="button button-dark" type="submit" disabled={submitting || !reference.trim()}>
          {submitting ? <LoaderCircle className="manual-payment-spin" size={15} /> : <Upload size={15} />}
          Submit for review
        </button>
      </div>
      {error ? <p className="manual-payment-error" role="alert"><CircleAlert size={15} />{error}</p> : null}
    </form> : null}
  </section>;
}
