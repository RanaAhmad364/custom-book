import { useState } from "react";
import { ArrowRight, MailCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function ForgotPassword() {
  const { requestPasswordReset } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      await requestPasswordReset(email);
      setStatus("success");
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "We couldn’t process that request.");
    }
  }

  return (
    <AuthPageShell eyebrow="A fresh start" title="Reset your password." description="Enter the email address associated with your account.">
      {status === "success" ? (
        <div className="auth-success-panel" role="status">
          <MailCheck size={22} />
          <div><strong>Demo reset link ready.</strong><p>No email was sent. Continue to the demo reset form for {email}.</p></div>
          <button className="button button-dark auth-submit" type="button" onClick={() => navigate(`/reset-password?email=${encodeURIComponent(email)}`)}>Continue to reset <ArrowRight size={15} /></button>
        </div>
      ) : (
        <form className="auth-form" onSubmit={submit}>
          <label className="auth-field" htmlFor="forgot-email"><span>Email address</span><input id="forgot-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
          <button className="button button-dark auth-submit" type="submit" disabled={status === "loading"}>
            {status === "loading" ? <><span className="loading-spinner" /> Preparing…</> : <>Continue <ArrowRight size={15} /></>}
          </button>
        </form>
      )}
      <p className="auth-switch"><Link to="/login">Return to sign in</Link></p>
    </AuthPageShell>
  );
}
