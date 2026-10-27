import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import PasswordField from "../../features/auth/PasswordField.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function Login() {
  const { user, login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryReturnTo = new URLSearchParams(location.search).get("returnTo");
  const [form, setForm] = useState({ email: "", password: "" });
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const from = location.state?.from;
  const isSafeReturnPath = queryReturnTo?.startsWith("/") && !queryReturnTo.startsWith("//");
  const returnTo = from
    ? `${from.pathname ?? "/dashboard"}${from.search ?? ""}${from.hash ?? ""}`
    : isSafeReturnPath
      ? queryReturnTo
      : "/dashboard";

  if (user) return <Navigate to={returnTo} replace />;

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      await login(form);
      navigate(returnTo, { replace: true });
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "We couldn’t sign you in. Try again.");
    }
  }

  return (
    <AuthPageShell eyebrow="Welcome back" title="Sign in to your account." description="Return to the stories and designs you’re working on.">
      {location.search.includes("expired") ? (
        <p className="auth-message auth-message-info" role="status">Your session has ended. Please sign in again.</p>
      ) : null}
      <form className="auth-form" onSubmit={submit}>
        <label className="auth-field" htmlFor="login-email">
          <span>Email address</span>
          <input id="login-email" name="email" type="email" autoComplete="email" required maxLength={254} value={form.email} onChange={update} />
        </label>
        <PasswordField id="login-password" label="Password" name="password" value={form.password} onChange={update} autoComplete="current-password" />
        {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
        <button className="button button-dark auth-submit" type="submit" disabled={status === "loading"}>
          {status === "loading" ? <><span className="loading-spinner" /> Signing in…</> : <>Sign in <ArrowRight size={15} /></>}
        </button>
      </form>
      <div className="auth-card-links auth-card-links-between">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/session-expired">Session expired?</Link>
      </div>
      <p className="auth-switch">New to MemoryBook? <Link to="/register">Create an account</Link></p>
    </AuthPageShell>
  );
}
