import { useMemo, useState } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, Bell, Camera, Check, Clock3, Download, FileText, Filter, Mail, MapPin, PackageCheck, Plus, Search, Settings, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext.jsx";
import { useDashboard } from "../../features/dashboard/DashboardContext.jsx";
import { DashboardEmptyState, DashboardPageHeading, DownloadRow, OrderRow, ProjectCard } from "../../features/dashboard/DashboardUI.jsx";
import { PdfDownloadDetails, PdfDownloadHistory } from "../public/PdfPurchase/PdfPurchase.jsx";

const titles = {
  projects: ["Your library", "My projects", "All your ideas, drafts, and finished books in one place."],
  recent: ["Your workspace", "Recent projects", "Pick up a story you have been shaping lately."],
  drafts: ["Still in progress", "Saved drafts", "Your unfinished stories are safely waiting here in this demo."],
  completed: ["Ready to keep", "Completed books", "The stories you have brought to life."],
  downloads: ["Your digital library", "Downloads", "Purchased PDFs and your recent download activity."],
  orders: ["Made with care", "Orders", "Follow each printed book from checkout to your doorstep."],
  notifications: ["A little note from us", "Notifications", "Updates about your books, orders, and account."],
  profile: ["Your details", "Profile", "Keep your contact information up to date."],
  settings: ["Make it yours", "Settings", "Choose how MemoryBook keeps you in the loop."],
  billing: ["Your transactions", "Billing history", "A record of charges associated with your books."],
  addresses: ["A place to send them", "Saved addresses", "Manage the delivery details for your future orders."],
  support: ["We are here to help", "Help & support", "Find a helpful answer or reach the MemoryBook support team."],
};

export default function DashboardSection({ section }) {
  const location = useLocation();
  const params = useParams();
  const { user } = useAuth();
  const { data, updateProject, duplicateProject, deleteProject, setNotifications, updateProfile, updateSettings, addAddress, deleteAddress } = useDashboard();
  if (section === "download-detail") return <PdfDownloadDetails />;
  if (section === "order-detail") return <OrderDetails data={data} id={params.orderId} tracking={location.pathname.endsWith("/tracking")} />;
  if (section === "profile") return <Profile data={data} updateProfile={updateProfile} email={user.email} />;
  if (section === "settings") return <SettingsPage data={data} updateSettings={updateSettings} />;
  if (section === "addresses") return <Addresses addresses={data.addresses} addAddress={addAddress} deleteAddress={deleteAddress} />;
  if (section === "support") return <Support />;
  if (section === "notifications") return <Notifications notifications={data.notifications} onChange={setNotifications} />;
  if (section === "billing") return <Billing billing={data.billing} />;
  if (section === "downloads") return <PdfDownloadHistory />;
  if (section === "orders") return <Orders orders={data.orders} />;
  return <Projects section={section} data={data} updateProject={updateProject} duplicateProject={duplicateProject} deleteProject={deleteProject} />;
}

function Projects({ section, data, updateProject, duplicateProject, deleteProject }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [view, setView] = useState("grid");
  const [confirmDelete, setConfirmDelete] = useState(null);
  const base = section === "drafts" ? data.projects.filter((item) => item.status === "draft") : section === "completed" ? data.projects.filter((item) => item.status === "completed") : section === "recent" ? [...data.projects].sort((a, b) => (a.updated === "Today" ? -1 : b.updated === "Today" ? 1 : 0)).slice(0, 3) : data.projects;
  const projects = useMemo(() => {
    const filtered = base.filter((project) => project.title.toLowerCase().includes(search.toLowerCase()) && (statusFilter === "all" || project.status === statusFilter));
    if (sort === "title") return filtered.sort((a, b) => a.title.localeCompare(b.title));
    return filtered;
  }, [base, search, statusFilter, sort]);
  const heading = titles[section];
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={heading[0]} title={heading[1]} description={heading[2]} action={<Link className="button button-dark" to="/books"><Plus size={16} /> New project</Link>} />
    <div className="dashboard-project-toolbar">
      <label className="dashboard-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search your projects" aria-label="Search projects" /></label>
      <label className="dashboard-select-label"><Filter size={15} /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter projects"><option value="all">All statuses</option><option value="draft">Drafts</option><option value="completed">Completed</option></select></label>
      <label className="dashboard-select-label"><select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort projects"><option value="recent">Recently updated</option><option value="title">Title A–Z</option></select></label>
      <div className="dashboard-view-switch" role="group" aria-label="Project display"><button type="button" className={view === "grid" ? "active" : ""} onClick={() => setView("grid")}>Grid</button><button type="button" className={view === "list" ? "active" : ""} onClick={() => setView("list")}>List</button></div>
    </div>
    {projects.length ? <div className={`dashboard-project-grid${view === "list" ? " is-list" : ""}`}>{projects.map((project) => <ProjectCard key={project.id} project={project} compact={view === "list"} onRename={(id, title) => updateProject(id, { title })} onDuplicate={duplicateProject} onDelete={(id) => setConfirmDelete(id)} />)}</div> : <DashboardEmptyState icon={Search} title={search ? "No matching projects." : section === "drafts" ? "No saved drafts yet." : section === "completed" ? "Your first finished book is waiting." : "Your project library is ready."} description={search ? "Try a different title or clear your filters." : "Explore the designs and make your next story your own."} action={<Link className="button button-outline" to="/books">Explore designs</Link>} />}
    {confirmDelete ? <div className="dashboard-confirm-backdrop" role="presentation" onClick={() => setConfirmDelete(null)}><div className="dashboard-confirm" role="dialog" aria-modal="true" aria-labelledby="delete-project-title" onClick={(event) => event.stopPropagation()}><span className="dashboard-confirm-icon"><Trash2 size={20} /></span><h2 id="delete-project-title">Delete this project?</h2><p>This removes the project from the current in-memory demo workspace.</p><div><button className="button button-outline" type="button" onClick={() => setConfirmDelete(null)}>Keep project</button><button className="button button-dark" type="button" onClick={() => { deleteProject(confirmDelete); setConfirmDelete(null); }}>Delete project</button></div></div></div> : null}
  </div>;
}

function Orders({ orders }) {
  const [filter, setFilter] = useState("All orders");
  const shown = filter === "All orders" ? orders : orders.filter((order) => order.status === filter);
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.orders[0]} title={titles.orders[1]} description={titles.orders[2]} action={<Link className="button button-outline" to="/print/orders">Print order history <ArrowRight size={14} /></Link>} />
    <div className="dashboard-tab-row">{["All orders", "In production", "Delivered"].map((item) => <button className={filter === item ? "active" : ""} key={item} type="button" onClick={() => setFilter(item)}>{item}</button>)}</div>
    <div className="dashboard-order-list">{shown.map((order) => <OrderRow key={order.id} order={order} />)}</div>
    {!shown.length ? <DashboardEmptyState icon={PackageCheck} title="No orders in this view." description="Your printed books and order updates will be collected here." action={<Link className="button button-outline" to="/books">Explore books</Link>} /> : null}
  </div>;
}

function OrderDetails({ data, id, tracking }) {
  const order = data.orders.find((item) => item.id === id);
  if (!order) return <div className="dashboard-page"><DashboardEmptyState icon={PackageCheck} title="Order not found." description="This order is not available in this demo workspace." action={<Link to="/dashboard/orders">Back to orders</Link>} /></div>;
  return <div className="dashboard-page">
    <DashboardPageHeading eyebrow={tracking ? "A keepsake is on its way" : `Order ${order.id}`} title={tracking ? "Order tracking" : "Order details"} description={order.title} action={<Link className="button button-outline" to="/dashboard/orders"><ArrowLeft size={15} /> All orders</Link>} />
    <div className="dashboard-detail-card"><div className="dashboard-order-hero"><img src={order.image} alt="" /><div><span className="dashboard-card-eyebrow">{order.id}</span><h2>{order.title}</h2><p>Placed {order.date} · {order.total}</p><span className="dashboard-status status-in-production">{order.status}</span></div></div>
      <div className="dashboard-detail-grid"><div><span>Payment</span><strong>{order.payment}</strong></div><div><span>Production</span><strong>{order.status}</strong></div><div><span>Delivery</span><strong>{order.status === "Delivered" ? "Delivered" : "Estimated after production"}</strong></div></div>
      <div className="dashboard-order-timeline"><div className="is-complete"><span><Check size={14} /></span><div><strong>Order placed</strong><small>{order.date}</small></div></div><div className="is-current"><span><Clock3 size={14} /></span><div><strong>{order.status === "Delivered" ? "Delivered to your home" : "Carefully in production"}</strong><small>{order.tracking}</small></div></div><div><span><MapPin size={14} /></span><div><strong>On its way home</strong><small>Tracking information appears when your order ships.</small></div></div></div>
    </div>
  </div>;
}

function Downloads({ downloads }) {
  const [history, setHistory] = useState([]);
  function download(item) { setHistory((current) => [item.id, ...current]); window.alert("This is a demo download. Real PDF files will be provided when a backend is connected."); }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.downloads[0]} title={titles.downloads[1]} description={titles.downloads[2]} />
    {downloads.length ? <><div className="dashboard-download-list">{downloads.map((item) => <DownloadRow key={item.id} item={item} onDownload={download} />)}</div><section className="dashboard-section-block dashboard-download-history"><div className="dashboard-section-heading"><div><span className="eyebrow">Your activity</span><h2>Download history</h2></div></div>{history.length ? history.map((id) => <p key={id} className="dashboard-history-line"><Check size={14} /> Download requested for {id} · just now</p>) : <p>Your download activity will appear here.</p>}</section></> : <DashboardEmptyState icon={Download} title="Your library is waiting." description="Purchased PDFs and their generation status will show here." action={<Link className="button button-outline" to="/books">Explore books</Link>} />}
  </div>;
}

function DownloadDetails({ data, id }) {
  const item = data.downloads.find((entry) => entry.id === id);
  if (!item) return <div className="dashboard-page"><DashboardEmptyState icon={Download} title="Download not found." description="This file is not available in this demo workspace." action={<Link to="/dashboard/downloads">Back to downloads</Link>} /></div>;
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={`PDF ${item.id}`} title="Download details" description={item.title} action={<Link className="button button-outline" to="/dashboard/downloads"><ArrowLeft size={15} /> Downloads</Link>} /><div className="dashboard-detail-card dashboard-download-detail"><img src={item.image} alt="" /><div><span className={`dashboard-status status-${item.status.toLowerCase()}`}>{item.status}</span><h2>{item.title}</h2><p>Requested {item.date}</p><p>File size · {item.size}</p>{item.status === "Ready" ? <button className="button button-dark" type="button" onClick={() => window.alert("This demo PDF is not an actual downloadable file.")}><ArrowDownToLine size={15} /> Download PDF</button> : <p className="dashboard-info-note"><Clock3 size={15} /> Your PDF is being prepared in this demo.</p>}</div></div></div>;
}

function Notifications({ notifications, onChange }) {
  const [category, setCategory] = useState("All");
  const categories = ["All", ...new Set(notifications.map((notification) => notification.category))];
  const filtered = notifications.filter((notification) => category === "All" || notification.category === category);
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.notifications[0]} title={titles.notifications[1]} description={titles.notifications[2]} action={<button className="button button-outline" type="button" onClick={() => onChange(notifications.map((notification) => ({ ...notification, read: true })))}><Check size={15} /> Mark all read</button>} />
    <div className="dashboard-tab-row">{categories.map((item) => <button className={category === item ? "active" : ""} key={item} type="button" onClick={() => setCategory(item)}>{item}</button>)}</div>
    <div className="dashboard-notification-list">{filtered.map((notification) => <article className={`dashboard-notification-card${notification.read ? "" : " is-unread"}`} key={notification.id}><span className="dashboard-notification-icon">{notification.category === "Order" ? <PackageCheck size={18} /> : notification.category === "Download" ? <Download size={18} /> : <Bell size={18} />}</span><div><span className="dashboard-card-eyebrow">{notification.category} · {notification.date}</span><h3>{notification.title}</h3><p>{notification.message}</p></div>{notification.read ? <span className="dashboard-read-label">Read</span> : <button className="dashboard-text-link" type="button" onClick={() => onChange(notifications.map((item) => item.id === notification.id ? { ...item, read: true } : item))}>Mark read</button>}</article>)}</div>
    {!filtered.length ? <DashboardEmptyState icon={Bell} title="All caught up." description="New account, design, and order updates will arrive here." /> : null}
  </div>;
}

function Profile({ data, updateProfile, email }) {
  const [saved, setSaved] = useState(false);
  const profile = data.profile;
  function submit(event) { event.preventDefault(); const form = new FormData(event.currentTarget); updateProfile({ name: String(form.get("name")).trim(), phone: String(form.get("phone")).trim() }); setSaved(true); window.setTimeout(() => setSaved(false), 2500); }
  function uploadPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 5 * 1024 * 1024) {
      window.alert("Choose an image smaller than 5 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") updateProfile({ photo: reader.result });
    };
    reader.onerror = () => window.alert("We couldn’t read that image. Please choose another file.");
    reader.readAsDataURL(file);
  }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.profile[0]} title={titles.profile[1]} description={titles.profile[2]} />
    <form className="dashboard-form-card" onSubmit={submit}><div className="dashboard-profile-photo"><span className="dashboard-avatar dashboard-avatar-large">{profile.photo ? <img src={profile.photo} alt="" /> : profile.name.slice(0, 1).toUpperCase()}</span><div><strong>Profile photo</strong><p>Images are held in this browser session only.</p><label className="button button-outline dashboard-photo-upload"><Camera size={14} /> Upload photo<input className="dashboard-visually-hidden" type="file" accept="image/*" onChange={uploadPhoto} /></label></div></div>
      <div className="dashboard-form-grid"><label>Full name<input name="name" defaultValue={profile.name} required maxLength={80} /></label><label>Email address<input value={email} type="email" disabled /><small>Email changes require account verification.</small></label><label>Phone number<input name="phone" type="tel" defaultValue={profile.phone} placeholder="Add a phone number" /></label></div>
      <div className="dashboard-form-footer"><Link to="/forgot-password">Change password <ArrowRight size={14} /></Link><button className="button button-dark" type="submit">{saved ? <><Check size={15} /> Saved in this preview</> : "Save profile"}</button></div>
    </form>
    <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">Preferences</span><h2>Notification preferences</h2></div></div>{[["emailUpdates", "Design inspiration", "Occasional notes and ideas for your next book."], ["orderUpdates", "Order updates", "Important updates about your purchases."]].map(([key, label, note]) => <label className="dashboard-setting-row" key={key}><span><strong>{label}</strong><small>{note}</small></span><input type="checkbox" checked={profile[key]} onChange={(event) => updateProfile({ [key]: event.target.checked })} /></label>)}</section>
  </div>;
}

function SettingsPage({ data, updateSettings }) {
  const items = [["orderEmails", "Order updates", "Receive email when your book moves through production."], ["productNews", "News & inspiration", "Occasional updates about new designs and ideas."], ["twoStep", "Two-step verification", "Add another layer after real authentication is connected."]];
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.settings[0]} title={titles.settings[1]} description={titles.settings[2]} />
    <section className="dashboard-form-card"><div className="dashboard-section-heading"><div><span className="eyebrow">Your preferences</span><h2>Privacy & notifications</h2></div><Settings size={20} /></div>{items.map(([key, title, description]) => <label className="dashboard-setting-row" key={key}><span><strong>{title}</strong><small>{description}</small></span><input type="checkbox" checked={data.settings[key]} onChange={(event) => updateSettings({ [key]: event.target.checked })} /></label>)}</section>
    <div className="dashboard-info-note"><ShieldCheck size={17} /> These preview settings are only held in memory. Account security features need backend authentication.</div>
  </div>;
}

function Billing({ billing }) {
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.billing[0]} title={titles.billing[1]} description={titles.billing[2]} />
    {billing.length ? <div className="dashboard-billing-table-wrap"><table className="dashboard-billing-table"><thead><tr><th>Invoice</th><th>Date</th><th>Description</th><th>Amount</th><th>Status</th><th></th></tr></thead><tbody>{billing.map((item) => <tr key={item.id}><td><strong>{item.id}</strong></td><td>{item.date}</td><td>{item.description}</td><td>{item.amount}</td><td><span className="dashboard-status status-ready">{item.status}</span></td><td><button className="dashboard-text-link" type="button" onClick={() => window.alert("Invoice download will be available with billing integration.")}><FileText size={14} /> Invoice</button></td></tr>)}</tbody></table></div> : <DashboardEmptyState icon={FileText} title="No billing history yet." description="Receipts for your orders will appear here." />}
  </div>;
}

function Addresses({ addresses, addAddress, deleteAddress }) {
  const [adding, setAdding] = useState(false);
  function submit(event) { event.preventDefault(); const form = new FormData(event.currentTarget); addAddress({ name: String(form.get("name")), line: String(form.get("line")), city: String(form.get("city")), postal: String(form.get("postal")) }); setAdding(false); }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.addresses[0]} title={titles.addresses[1]} description={titles.addresses[2]} action={!adding ? <button className="button button-dark" type="button" onClick={() => setAdding(true)}><Plus size={15} /> Add address</button> : null} />
    {adding ? <form className="dashboard-form-card dashboard-address-form" onSubmit={submit}><h2>New delivery address</h2><div className="dashboard-form-grid"><label>Recipient<input name="name" required /></label><label>Street address<input name="line" required /></label><label>City<input name="city" required /></label><label>Postal code<input name="postal" required /></label></div><div className="dashboard-form-footer"><button className="button button-outline" type="button" onClick={() => setAdding(false)}>Cancel</button><button className="button button-dark" type="submit">Save address</button></div></form> : null}
    {addresses.length ? <div className="dashboard-address-list">{addresses.map((address) => <article className="dashboard-address-card" key={address.id}><MapPin size={18} /><div><strong>{address.name}</strong><p>{address.line}<br />{address.city} {address.postal}</p></div><button className="dashboard-icon-button" type="button" aria-label={`Delete address for ${address.name}`} onClick={() => deleteAddress(address.id)}><Trash2 size={16} /></button></article>)}</div> : !adding ? <DashboardEmptyState icon={MapPin} title="No saved addresses yet." description="Save a delivery address for a future printed book." action={<button className="button button-outline" type="button" onClick={() => setAdding(true)}><Plus size={15} /> Add your first address</button>} /> : null}
  </div>;
}

function Support() {
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.support[0]} title={titles.support[1]} description={titles.support[2]} />
    <div className="dashboard-support-grid"><article><span><CircleHelpIcon /></span><h2>Browse the help center</h2><p>Find answers about choosing a design, making your book, payments, and delivery.</p><Link className="button button-outline" to="/help">Visit help center <ArrowRight size={14} /></Link></article><article><span><Mail size={20} /></span><h2>Talk to our team</h2><p>Send a note about an order or a question about creating your book.</p><Link className="button button-dark" to="/contact">Contact support <ArrowRight size={14} /></Link></article></div>
  </div>;
}

function CircleHelpIcon() {
  return <UserRound size={20} />;
}
