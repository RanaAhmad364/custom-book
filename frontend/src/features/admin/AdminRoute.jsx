import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

export default function AdminRoute() {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <main className="auth-loading" role="status">Checking your admin access…</main>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (!user.roles?.includes("admin")) {
    return <Navigate to="/unauthorized" replace state={{ reason: "admin", from: location }} />;
  }
  return <Outlet />;
}
