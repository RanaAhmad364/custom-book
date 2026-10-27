import { useState } from "react";
import {
  Bell, BookOpen, Boxes, ChartNoAxesCombined, ChevronLeft, CircleDollarSign, Download, FileText,
  LayoutDashboard, LogOut, Menu, PackageCheck, Settings, ShoppingBag,
  Truck, Users, Wallet, X, UserRound, MessageSquareText,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

const groups = [
  { title: "Overview", items: [{ path: "/admin", label: "Dashboard", icon: LayoutDashboard, end: true }] },
  { title: "Commerce", items: [
    { path: "/admin/purchases", label: "Purchases", icon: ShoppingBag },
    { path: "/admin/downloads", label: "Downloads", icon: Download },
  ] },
  { title: "Catalog", items: [
    { path: "/admin/books", label: "Book Products", icon: BookOpen },
    { path: "/admin/categories", label: "Categories", icon: Boxes },
    { path: "/admin/collections", label: "Collections", icon: PackageCheck },
    { path: "/admin/templates", label: "Templates", icon: FileText },
    { path: "/admin/pricing", label: "Pricing", icon: CircleDollarSign },
  ] },
  { title: "Operations", items: [
    { path: "/admin/users", label: "Users", icon: Users },
    { path: "/admin/payments", label: "Payments", icon: Wallet },
    { path: "/admin/refunds", label: "Refunds", icon: CircleDollarSign },
    { path: "/admin/shipping", label: "Shipping", icon: Truck },
    { path: "/admin/notifications", label: "Notifications", icon: Bell },
    { path: "/admin/support", label: "Contact / Support", icon: MessageSquareText },
  ] },
  { title: "Platform", items: [
    { path: "/admin/reports", label: "Reports", icon: ChartNoAxesCombined },
    { path: "/admin/settings", label: "Settings", icon: Settings },
    { path: "/admin/profile", label: "Admin profile", icon: UserRound },
  ] },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const currentGroup = groups.flatMap((group) => group.items).find((item) =>
    item.end ? location.pathname === item.path : location.pathname.startsWith(item.path),
  );
  return (
    <main className={`admin-shell${collapsed ? " is-collapsed" : ""}`}>
      <header className="admin-topbar">
        <button className="admin-mobile-toggle" type="button" aria-label="Toggle admin navigation" onClick={() => setMobileOpen((value) => !value)}>
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <div className="admin-brand"><span className="admin-brand-mark"><BookOpen size={18} /></span><span>MemoryBook <em>Admin</em></span></div>
        <div className="admin-topbar-context">
          <strong>{currentGroup?.label || (location.pathname.includes("/design") ? "Book designer" : "Admin workspace")}</strong>
          <span>Welcome back, {user?.name || user?.email}</span>
        </div>
        <div className="admin-topbar-user">
          <Link to="/admin/notifications" aria-label="View notifications"><Bell size={17} /></Link>
          <Link to="/admin/profile" aria-label="Admin profile"><UserRound size={17} /></Link>
          <button type="button" aria-label="Log out" onClick={async () => { await logout(); navigate("/login", { replace: true }); }}><LogOut size={16} /></button>
        </div>
      </header>
      <div className="admin-frame">
        <aside className={`admin-sidebar${mobileOpen ? " is-open" : ""}`}>
          <button className="admin-collapse" type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
            <ChevronLeft size={16} />
          </button>
          {groups.map((group) => (
            <div className="admin-nav-group" key={group.title}>
              <span className="admin-nav-heading">{group.title}</span>
              {group.items.map(({ path, label, icon: Icon, end }) => (
                <NavLink key={path} to={path} end={end} title={collapsed ? label : undefined}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) => `admin-nav-link${isActive ? " is-active" : ""}`}>
                  <Icon size={17} /><span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
          <div className="admin-sidebar-bottom"><span>Restricted administrator workspace</span></div>
        </aside>
        {mobileOpen ? <button className="admin-sidebar-scrim" type="button" aria-label="Close admin navigation" onClick={() => setMobileOpen(false)} /> : null}
        <section className="admin-content"><Outlet /></section>
      </div>
    </main>
  );
}
