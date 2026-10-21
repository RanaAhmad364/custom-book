import { useState } from "react";
import { ArrowDownToLine, ArrowRight, BookOpen, Check, Copy, Eye, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

export function DashboardPageHeading({ eyebrow, title, description, action }) {
  return (
    <div className="dashboard-page-heading">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>
      {action}
    </div>
  );
}

export function DashboardEmptyState({ icon: Icon = BookOpen, title, description, action }) {
  return <div className="dashboard-empty"><span><Icon size={24} /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function ProjectEditAction({ project, children, className = "button button-dark" }) {
  if (project.document) {
    return <Link className={className} to={`/create/design/${project.id}`}>{children}</Link>;
  }
  return <button className={className} type="button" onClick={() => window.alert("This sample project is for preview only and cannot be edited.")}>{children}</button>;
}

export function ProjectCard({ project, onRename, onDuplicate, onDelete, compact = false }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [title, setTitle] = useState(project.title);
  function saveTitle(event) {
    event.preventDefault();
    const next = title.trim();
    if (next) onRename(project.id, next);
    setEditing(false);
  }

  return (
    <article className={`dashboard-project-card${compact ? " is-compact" : ""}`}>
      <div className="dashboard-project-image"><img src={project.image} alt="" loading="lazy" /><span>{project.status === "completed" ? "Completed" : `${project.progress}% complete`}</span>
        <div className="dashboard-project-menu-wrap">
          <button className="dashboard-icon-button" type="button" aria-label={`More actions for ${project.title}`} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><MoreHorizontal size={19} /></button>
          {menuOpen ? <div className="dashboard-project-menu">
            <button type="button" onClick={() => { setTitle(project.title); setEditing(true); setMenuOpen(false); }}><Pencil size={14} /> Rename</button>
            <button type="button" onClick={() => { onDuplicate(project.id); setMenuOpen(false); }}><Copy size={14} /> Duplicate</button>
            <button type="button" onClick={() => { onDelete(project.id); setMenuOpen(false); }}><Trash2 size={14} /> Delete</button>
          </div> : null}
        </div>
      </div>
      <div className="dashboard-project-content">
        <span className="dashboard-card-eyebrow">{project.category} <span>·</span> {project.pages} pages</span>
        {editing ? <form className="dashboard-rename-form" onSubmit={saveTitle}><input aria-label="Project title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={80} autoFocus /><button className="dashboard-icon-button" type="submit" aria-label="Save project name"><Check size={16} /></button></form> : <h3>{project.title}</h3>}
        <p>Updated {project.updated}</p>
        <div className="dashboard-project-actions">
          <ProjectEditAction project={project}>{project.status === "completed" ? "Open book" : "Continue editing"} <ArrowRight size={14} /></ProjectEditAction>
          <button className="dashboard-secondary-action" type="button" onClick={() => setPreviewOpen(true)}><Eye size={15} /> Preview</button>
        </div>
      </div>
      {previewOpen ? <div className="dashboard-confirm-backdrop" role="presentation" onClick={() => setPreviewOpen(false)}><div className="dashboard-project-preview" role="dialog" aria-modal="true" aria-label={`${project.title} preview`} onClick={(event) => event.stopPropagation()}><button className="dashboard-icon-button" type="button" aria-label="Close preview" onClick={() => setPreviewOpen(false)}>×</button><img src={project.image} alt="" /><div><span className="eyebrow">{project.category} · {project.pages} pages</span><h2>{project.title}</h2><p>{project.status === "completed" ? "Completed book" : `${project.progress}% complete`} · Updated {project.updated}</p><button className="button button-dark" type="button" onClick={() => setPreviewOpen(false)}>Close preview</button></div></div></div> : null}
    </article>
  );
}

export function OrderRow({ order }) {
  return <article className="dashboard-order-row">
    <img src={order.image} alt="" loading="lazy" />
    <div className="dashboard-order-main"><span className="dashboard-card-eyebrow">{order.id}</span><h3>{order.title}</h3><p>Placed {order.date} · {order.total}</p></div>
    <div className="dashboard-order-status"><span className={`dashboard-status status-${order.status.toLowerCase().replace(/\s/g, "-")}`}>{order.status}</span><small>{order.payment}</small></div>
    <div className="dashboard-order-links"><Link to={`/dashboard/orders/${order.id}`}>Details <ArrowRight size={14} /></Link><Link to={`/dashboard/orders/${order.id}/tracking`}>Track order</Link></div>
  </article>;
}

export function DownloadRow({ item, onDownload }) {
  return <article className="dashboard-download-row">
    <img src={item.image} alt="" loading="lazy" />
    <div className="dashboard-order-main"><span className="dashboard-card-eyebrow">{item.id} <span>·</span> {item.date}</span><h3>{item.title}</h3><p>{item.size}</p></div>
    <span className={`dashboard-status status-${item.status.toLowerCase()}`}>{item.status}</span>
    {item.status === "Ready" ? <button className="button button-outline" type="button" onClick={() => onDownload(item)}><ArrowDownToLine size={15} /> Download</button> : <Link className="dashboard-text-link" to={`/dashboard/downloads/${item.id}`}>Details <ArrowRight size={14} /></Link>}
  </article>;
}

export function QuickAction({ icon: Icon, title, to, onClick }) {
  const content = <><span><Icon size={19} /></span><strong>{title}</strong><ArrowRight className="dashboard-quick-arrow" size={15} /></>;
  return to ? <Link className="dashboard-quick-action" to={to}>{content}</Link> : <button className="dashboard-quick-action" type="button" onClick={onClick}>{content}</button>;
}
