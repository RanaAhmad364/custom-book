import { useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import PasswordField from "../../features/auth/PasswordField.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

function getStrength(password) {
  if (!password) return 0;
  return [
    password.length >= 8,
    /[a-z]/.test(password) && /[A-Z]/.test(password),
    /\d/.test(password),
    /[^a-zA-Z0-9]/.test(password),
  ].filter(Boolean).length;
}

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirmPassword: "" });
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const strength = useMemo(() => getStrength(form.password), [form.password]);

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
    setError("");
    try {
      const result = await register(form);
      navigate(`/verify-otp?email=${encodeURIComponent(result.user.email)}`);
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "We couldn’t create your account.");
    }
  }

  return (
    <AuthPageShell eyebrow="A place for your stories" title="Create your account." description="Your account will bring your MemoryBook projects together.">
      <form className="auth-form" onSubmit={submit}>
        <label className="auth-field" htmlFor="register-name"><span>Your name</span><input id="register-name" name="name" autoComplete="name" required maxLength={100} value={form.name} onChange={update} /></label>
        <label className="auth-field" htmlFor="register-email"><span>Email address</span><input id="register-email" name="email" type="email" autoComplete="email" required maxLength={254} value={form.email} onChange={update} /></label>
        <PasswordField id="register-password" label="Create password" name="password" value={form.password} onChange={update} autoComplete="new-password" />
        <div className="password-strength" aria-live="polite">
          <div className="password-strength-track" aria-label={`Password strength ${strength} of 4`}>
            {[1, 2, 3, 4].map((level) => <span className={strength >= level ? `strength-${strength}` : ""} key={level} />)}
          </div>
          <span>{form.password ? ["", "Needs work", "Fair", "Good", "Strong"][strength] : "Use 8+ characters; add mixed case, a number, or a symbol."}</span>
        </div>
        <PasswordField id="register-confirm-password" label="Confirm password" name="confirmPassword" value={form.confirmPassword} onChange={update} autoComplete="new-password" />
        <label className="auth-consent"><input type="checkbox" required /><span>I agree to the <Link to="/terms">Terms</Link> and acknowledge the <Link to="/privacy">Privacy Policy</Link> draft.</span></label>
        {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
        <button className="button button-dark auth-submit" type="submit" disabled={status === "loading"}>
          {status === "loading" ? <><span className="loading-spinner" /> Creating…</> : <>Create account <ArrowRight size={15} /></>}
        </button>
      </form>
      <p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p>
    </AuthPageShell>
  );
}
