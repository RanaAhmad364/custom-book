import { ArrowRight, Camera, Compass, PackageCheck, Plus, Sparkles } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useBookCreation } from "../../features/bookCreation/BookCreationContext.jsx";
import { useDashboard } from "../../features/dashboard/DashboardContext.jsx";
import { DashboardEmptyState, DashboardPageHeading, DownloadRow, OrderRow, ProjectCard, ProjectEditAction, QuickAction } from "../../features/dashboard/DashboardUI.jsx";

export default function DashboardHome() {
  const { data, updateProject, duplicateProject, deleteProject } = useDashboard();
  const { begin } = useBookCreation();
  const navigate = useNavigate();
  const drafts = data.projects.filter((project) => project.status === "draft");
  const recent = [...data.projects].sort((a, b) => a.updated === "Today" ? -1 : b.updated === "Today" ? 1 : 0).slice(0, 2);
  const latestOrder = data.orders.slice(0, 1);
  const latestDownload = data.downloads.filter((item) => item.status === "Ready").slice(0, 1);
  const today = new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date());
  function beginPhotoUpload() {
    begin({ startingOption: "quick-start", title: "My MemoryBook" });
    navigate("/create/photos");
  }

  return <div className="dashboard-page">
    <DashboardPageHeading eyebrow={today} title={`Welcome back, ${data.profile.name.split(" ")[0]}.`} description="Your stories are right where you left them." action={<Link className="button button-dark" to="/create"><Plus size={16} /> Create new book</Link>} />
    <section className="dashboard-welcome-card">
      <div className="dashboard-welcome-copy"><span className="eyebrow"><Sparkles size={14} /> Pick up where you left off</span><h2>{drafts[0]?.title ?? "Start a new story"}</h2><p>{drafts[0] ? `${drafts[0].category} · ${drafts[0].pages} pages · ${drafts[0].progress}% complete` : "Choose a design and make something worth keeping."}</p>{drafts[0] ? <ProjectEditAction project={drafts[0]}>Continue designing <ArrowRight size={15} /></ProjectEditAction> : <Link className="button button-dark" to="/books">Explore book designs <ArrowRight size={15} /></Link>}</div>
      <img src={drafts[0]?.image ?? "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=900&q=85"} alt="" />
      <div className="dashboard-progress-ring"><strong>{drafts[0]?.progress ?? 0}%</strong><span>designed</span></div>
    </section>
    <section className="dashboard-quick-actions"><QuickAction icon={Plus} title="Create new book" to="/create" /><QuickAction icon={Compass} title="Explore templates" to="/create/templates" /><QuickAction icon={Camera} title="Upload photos" onClick={beginPhotoUpload} /><QuickAction icon={PackageCheck} title="View orders" to="/dashboard/orders" /></section>
    {data.pendingOrders?.length ? <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">Checkout needed</span><h2>Pending payment</h2></div><Link to="/dashboard/orders">View all <ArrowRight size={14} /></Link></div><div className="dashboard-order-list">{data.pendingOrders.slice(0, 2).map((order) => <article className="dashboard-order-row" key={order.id}><div className="dashboard-order-main"><span className="dashboard-card-eyebrow">{order.reference}</span><h3>{order.title}</h3><p>Placed {order.date} · {order.total}</p></div><div className="dashboard-order-links">{order.paymentExpired ? <span>Payment window expired</span> : order.checkoutUrl ? <button className="button button-dark" type="button" onClick={() => window.location.assign(order.checkoutUrl)}>Pay now <ArrowRight size={14} /></button> : <Link className="button button-dark" to={`/print/orders/${encodeURIComponent(order.id)}/confirmation`}>Pay now <ArrowRight size={14} /></Link>}</div></article>)}</div></section> : null}
    <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">Your projects</span><h2>Recently opened</h2></div><Link to="/dashboard/projects">All projects <ArrowRight size={14} /></Link></div>
      {recent.length ? <div className="dashboard-project-grid dashboard-project-grid-2">{recent.map((project) => <ProjectCard key={project.id} project={project} onRename={(id, title) => updateProject(id, { title })} onDuplicate={duplicateProject} onDelete={(id) => { if (window.confirm("Delete this saved project?")) deleteProject(id); }} />)}</div> : <DashboardEmptyState title="Your project space is ready." description="Choose a template to begin your first book." action={<Link className="button button-outline" to="/books">Explore templates</Link>} />}
    </section>
    <div className="dashboard-two-column">
      <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">In progress</span><h2>Saved drafts</h2></div><Link to="/dashboard/drafts">View drafts <ArrowRight size={14} /></Link></div>
        <div className="dashboard-compact-list">{drafts.slice(0, 3).map((project) => <ProjectEditAction className="dashboard-compact-project" project={project} key={project.id}><img src={project.image} alt="" /><span><strong>{project.title}</strong><small>{project.progress}% complete · Updated {project.updated}</small></span><ArrowRight size={15} /></ProjectEditAction>)}</div>
      </section>
      <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">On its way</span><h2>Recent order</h2></div><Link to="/dashboard/orders">All orders <ArrowRight size={14} /></Link></div>
        {latestOrder.length ? latestOrder.map((order) => <OrderRow key={order.id} order={order} />) : <DashboardEmptyState title="No orders just yet." description="When you order a printed book, its progress will appear here." />}
      </section>
    </div>
    <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">Ready for you</span><h2>Recent downloads</h2></div><Link to="/dashboard/downloads">Download library <ArrowRight size={14} /></Link></div>{latestDownload.length ? latestDownload.map((item) => <DownloadRow key={item.id} item={item} onDownload={() => navigate(`/dashboard/downloads/${encodeURIComponent(item.id)}`)} />) : <DashboardEmptyState title="No PDFs ready yet." description="Purchased and generated PDFs will be available here." />}</section>
  </div>;
}
