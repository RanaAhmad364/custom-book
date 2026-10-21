import { useState } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import PasswordField from "../../features/auth/PasswordField.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function ResetPassword() {
  const { resetEmail, resetPassword } = useAuth();
  const [params] = useSearchParams();
  const email = params.get("email") || resetEmail;
  const [form, setForm] = useState({ password: "", confirmPassword: "" });
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    setStatus("loading");
    try {
      await resetPassword(form);
      setStatus("success");
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "The password could not be updated.");
    }
  }

  return (
    <AuthPageShell eyebrow="Choose a new key" title="Set a new password." description={email ? `Demo reset for ${email}.` : "Enter a new password to complete the demo reset."}>
      {status === "success" ? (
        <div className="auth-success-panel" role="status"><CheckCircle2 size={22} /><div><strong>Password reset preview complete.</strong><p>This mock flow has not changed a real account password.</p></div><Link className="button button-dark auth-submit" to="/login">Back to sign in <ArrowRight size={15} /></Link></div>
      ) : (
        <form className="auth-form" onSubmit={submit}>
          <PasswordField id="reset-password" label="New password" name="password" value={form.password} onChange={update} autoComplete="new-password" />
          <PasswordField id="reset-confirm-password" label="Confirm new password" name="confirmPassword" value={form.confirmPassword} onChange={update} autoComplete="new-password" />
          {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
          <button className="button button-dark auth-submit" type="submit" disabled={status === "loading"}>
            {status === "loading" ? <><span className="loading-spinner" /> Updating…</> : <>Reset password <ArrowRight size={15} /></>}
          </button>
        </form>
      )}
      <p className="auth-switch"><Link to="/login">Return to sign in</Link></p>
    </AuthPageShell>
  );
}
