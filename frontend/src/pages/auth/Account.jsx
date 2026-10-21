import { ArrowRight, LogOut, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext.jsx";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";

export default function Account() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function endSession() {
    logout();
    navigate("/session-expired", { replace: true });
  }

  return (
    <AuthPageShell eyebrow="Your MemoryBook" title="Welcome in." description="This protected account page demonstrates the client-side auth flow.">
      <div className="auth-status-illustration"><UserRound size={25} /><span>Signed in as <strong>{user?.email}</strong></span></div>
      <p className="auth-message auth-message-info">No real account, password, or session token is created or persisted. Account projects are not connected.</p>
      <button className="button button-outline auth-submit" type="button" onClick={endSession}>Log out <LogOut size={15} /></button>
      <Link className="auth-switch auth-center-link" to="/books">Explore books <ArrowRight size={14} /></Link>
    </AuthPageShell>
  );
}
