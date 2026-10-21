import { ArrowLeft, BookOpen, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

export default function AuthLayout({ children }) {
  return (
    <main className="auth-page">
      <div className="auth-frame">
        <Link to="/" className="auth-wordmark" aria-label="MemoryBook home">
          <span><BookOpen size={18} /></span>
          <span>MemoryBook</span>
        </Link>
        <div className="auth-demo-warning" role="note">
          <ShieldAlert size={16} />
          <span><strong>Authentication preview.</strong> This client-side demo is not secure production authentication. Never use a real password.</span>
        </div>
        {children}
        <Link className="auth-back-home" to="/"><ArrowLeft size={14} /> Return to MemoryBook</Link>
      </div>
    </main>
  );
}
