import { ArrowRight, Clock3 } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";

export default function SessionExpired() {
  const location = useLocation();
  const from = location.state?.from;
  return (
    <AuthPageShell eyebrow="For your peace of mind" title="Your session has ended." description="Sign in again to continue. In this preview, sessions are held only in memory and end when the page reloads.">
      <div className="auth-status-illustration"><Clock3 size={25} /><span>No password or token is stored by the demo.</span></div>
      <Link className="button button-dark auth-submit auth-standalone-link" to="/login" state={from ? { from } : undefined}>Sign in again <ArrowRight size={15} /></Link>
      <Link className="auth-switch auth-center-link" to="/">Return to the homepage</Link>
    </AuthPageShell>
  );
}
