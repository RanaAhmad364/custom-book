import { ArrowRight, LockKeyhole } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";

export default function Unauthorized() {
  const location = useLocation();
  const from = location.state?.from;
  return (
    <AuthPageShell eyebrow="Members area" title="Sign in to continue." description="This page is reserved for signed-in visitors. Your destination will be kept for after sign-in.">
      <div className="auth-status-illustration"><LockKeyhole size={25} /><span>Sign in to access this protected page.</span></div>
      <Link className="button button-dark auth-submit auth-standalone-link" to="/login" state={from ? { from } : undefined}>Go to sign in <ArrowRight size={15} /></Link>
      <Link className="auth-switch auth-center-link" to="/register">Create an account</Link>
    </AuthPageShell>
  );
}
