import { useState } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import PasswordField from "../../features/auth/PasswordField.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function ResetPassword() {
  const { resetPassword } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [form, setForm] = useState({ password: "", confirmPassword: "" });
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    if (form.password !== form.confirmPassword) {
      setStatus("error");
      setError("Those passwords don’t match.");
      return;
    }
    setStatus("loading");
    try {
      await resetPassword({ token, password: form.password });
      setStatus("success");
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "The password could not be updated.");
    }
  }

  return (
    <AuthPageShell eyebrow="Choose a new key" title="Set a new password." description="Choose a new password to secure your account.">
      {status === "success" ? (
        <div className="auth-success-panel" role="status"><CheckCircle2 size={22} /><div><strong>Password updated.</strong><p>Sign in with your new password.</p></div><Link className="button button-dark auth-submit" to="/login">Back to sign in <ArrowRight size={15} /></Link></div>
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
