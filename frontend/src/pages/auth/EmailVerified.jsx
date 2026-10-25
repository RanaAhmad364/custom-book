import { useEffect } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

export default function EmailVerified() {
  const { pendingEmail, clearPendingEmail } = useAuth();
  const [params] = useSearchParams();
  const email = pendingEmail || params.get("email") || "";

  useEffect(() => clearPendingEmail(), [clearPendingEmail]);

  return (
    <AuthPageShell eyebrow="A good start" title="Email verified." description={email ? `Your email address ${email} is verified.` : "Your email address is verified."}>
      <div className="auth-success-panel" role="status">
        <CheckCircle2 size={22} />
        <div><strong>You’re all set.</strong><p>Sign in to continue to your MemoryBook account.</p></div>
      </div>
      <Link className="button button-dark auth-submit auth-standalone-link" to="/login">Continue to sign in <ArrowRight size={15} /></Link>
    </AuthPageShell>
  );
}
