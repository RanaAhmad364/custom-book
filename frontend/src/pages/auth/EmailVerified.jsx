import { useState } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function EmailVerified() {
  const { pendingEmail, verifyEmail, clearPendingEmail } = useAuth();
  const [params] = useSearchParams();
  const email = pendingEmail || params.get("email") || "";
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  async function confirm() {
    setStatus("loading");
    setError("");
    try {
      await verifyEmail();
      clearPendingEmail();
      setStatus("success");
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "The demo verification could not be completed.");
    }
  }

  return (
    <AuthPageShell eyebrow="A good start" title={status === "success" ? "Email verified." : "Confirm your email."} description={email ? `Email address: ${email}.` : "Confirm this email in the demo flow."}>
      <div className={`auth-success-panel ${status === "error" ? "auth-message-error" : ""}`} role="status">
        <CheckCircle2 size={22} />
        <div><strong>{status === "success" ? "You’re all set for the preview." : status === "error" ? "The demo verification could not be completed." : "Ready to verify this demo email."}</strong><p>{error || "This client-side demonstration does not send or verify a real email."}</p></div>
      </div>
      {status === "idle" ? (
        <button className="button button-dark auth-submit" type="button" onClick={confirm}>Confirm demo verification <ArrowRight size={15} /></button>
      ) : null}
      {status === "loading" ? <p className="auth-message" role="status"><span className="loading-spinner" /> Completing demo…</p> : null}
      <Link className="button button-outline auth-submit auth-standalone-link" to="/login">Continue to sign in <ArrowRight size={15} /></Link>
    </AuthPageShell>
  );
}
