import { useState } from "react";
import { Bell, BookOpen, ChevronDown, CircleHelp, CreditCard, FileDown, FolderKanban, Home, MapPin, Menu, PackageCheck, Settings, UserRound, X } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { DashboardProvider, useDashboard } from "./DashboardContext.jsx";

const navigation = [
  { title: "Workspace", links: [{ to: "/dashboard", label: "Overview", icon: Home, end: true }, { to: "/dashboard/projects", label: "My projects", icon: FolderKanban }, { to: "/dashboard/recent", label: "Recent projects", icon: BookOpen }, { to: "/dashboard/drafts", label: "Saved drafts", icon: FileDown }, { to: "/dashboard/completed", label: "Completed books", icon: PackageCheck }] },
  { title: "Your account", links: [{ to: "/dashboard/downloads", label: "Downloads", icon: FileDown }, { to: "/dashboard/orders", label: "Orders", icon: PackageCheck }, { to: "/dashboard/notifications", label: "Notifications", icon: Bell }, { to: "/dashboard/profile", label: "Profile", icon: UserRound }, { to: "/dashboard/settings", label: "Settings", icon: Settings }, { to: "/dashboard/billing", label: "Billing history", icon: CreditCard }, { to: "/dashboard/addresses", label: "Saved addresses", icon: MapPin }, { to: "/dashboard/support", label: "Help & support", icon: CircleHelp }] },
];

function DashboardFrame() {
  const { data, storageError } = useDashboard();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const unreadCount = data.notifications.filter((notification) => !notification.read).length;
  return <main className="dashboard-shell">
    <div className="dashboard-shell-head">
      <div><span className="eyebrow">Your creative workspace</span><h1>MemoryBook <span>Studio</span></h1></div>
      <div className="dashboard-head-actions">
        <NavLink to="/dashboard/notifications" className="dashboard-notification-link" aria-label={`Notifications, ${unreadCount} unread`}><Bell size={18} />{unreadCount ? <span>{unreadCount}</span> : null}</NavLink>
        <NavLink className="dashboard-user-menu" to="/dashboard/profile"><span className="dashboard-avatar">{data.profile.name.slice(0, 1).toUpperCase()}</span><span>{data.profile.name.split(" ")[0]}</span><ChevronDown size={14} /></NavLink>
      </div>
    </div>
    <div className="dashboard-mobile-bar"><button className="button button-outline" type="button" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((open) => !open)}>{sidebarOpen ? <X size={16} /> : <Menu size={16} />} Workspace menu</button></div>
    <div className="dashboard-layout">
      <aside className={`dashboard-sidebar${sidebarOpen ? " is-open" : ""}`}>
        <div className="dashboard-sidebar-user"><span className="dashboard-avatar">{data.profile.name.slice(0, 1).toUpperCase()}</span><div><strong>{data.profile.name}</strong><small>MemoryBook member</small></div></div>
        {navigation.map((group) => <div className="dashboard-nav-group" key={group.title}><span className="dashboard-nav-heading">{group.title}</span>{group.links.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={() => setSidebarOpen(false)} className={({ isActive }) => `dashboard-nav-link${isActive ? " active" : ""}`}><Icon size={17} /><span>{label}</span>{label === "Notifications" && unreadCount ? <i>{unreadCount}</i> : null}</NavLink>)}</div>)}
        <div className="dashboard-sidebar-bottom"><p>Made for the moments that matter.</p><button type="button" onClick={() => { logout(); navigate("/session-expired", { replace: true }); }}>Log out</button></div>
      </aside>
      <section className="dashboard-main-content">
        <div className="dashboard-demo-banner"><span>Preview workspace</span><p>Projects and sample workspace activity are demo-only. Paid PDF orders and download access are retrieved from the PDF service.</p></div>
        {storageError ? <div className="dashboard-demo-banner dashboard-storage-error" role="alert"><span>Local storage issue</span><p>{storageError}</p></div> : null}
        <Outlet />
      </section>
    </div>
  </main>;
}

export default function DashboardLayout() {
  return <DashboardProvider><DashboardFrame /></DashboardProvider>;
}
