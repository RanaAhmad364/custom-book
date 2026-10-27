import { ArrowRight, LockKeyhole } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";

export default function Unauthorized() {
  const location = useLocation();
  const from = location.state?.from;
  const adminDenied = location.state?.reason === "admin";
  if (adminDenied) {
    return (
      <AuthPageShell eyebrow="Admin area" title="You don’t have access to this page." description="Your account is signed in, but it does not have the administrator role.">
        <div className="auth-status-illustration"><LockKeyhole size={25} /><span>Contact an administrator if you believe you should have access.</span></div>
        <Link className="button button-dark auth-submit auth-standalone-link" to="/dashboard">Return to your dashboard <ArrowRight size={15} /></Link>
        <Link className="auth-switch auth-center-link" to="/">Return to the homepage</Link>
      </AuthPageShell>
    );
  }
  return (
    <AuthPageShell eyebrow="Members area" title="Sign in to continue." description="This page is reserved for signed-in visitors. Your destination will be kept for after sign-in.">
      <div className="auth-status-illustration"><LockKeyhole size={25} /><span>Sign in to access this protected page.</span></div>
      <Link className="button button-dark auth-submit auth-standalone-link" to="/login" state={from ? { from } : undefined}>Go to sign in <ArrowRight size={15} /></Link>
      <Link className="auth-switch auth-center-link" to="/register">Create an account</Link>
    </AuthPageShell>
  );
}
