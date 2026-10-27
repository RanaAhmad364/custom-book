import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Bell, Check, Clock3, Download, FileText, Filter, Heart, Mail, MapPin, PackageCheck, Plus, Search, Settings, Trash2, UserRound } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext.jsx";
import { useDashboard } from "../../features/dashboard/DashboardContext.jsx";
import { DashboardEmptyState, DashboardPageHeading, OrderRow, ProjectCard } from "../../features/dashboard/DashboardUI.jsx";
import { SafeImage } from "../../components/common/SafeImage.jsx";
import { PdfDownloadDetails, PdfDownloadHistory } from "../public/PdfPurchase/PdfPurchase.jsx";
import { apiRequest } from "../../services/apiClient.js";
import { printOrderService } from "../../services/printOrderService.js";
import OrderTimeline from "../../features/orders/OrderTimeline.jsx";

const titles = {
  projects: ["Your library", "My projects", "All your ideas, drafts, and finished books in one place."],
  recent: ["Your workspace", "Recent projects", "Pick up a story you have been shaping lately."],
  drafts: ["Still in progress", "Saved drafts", "Your unfinished stories are safely waiting here."],
  completed: ["Ready to keep", "Completed books", "The stories you have brought to life."],
  favorites: ["Saved for later", "Favorite books", "The designs you love, ready when you are."],
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
  const { data, updateProject, duplicateProject, deleteProject, removeFavorite, setNotifications, updateProfile, updateSettings, addAddress, deleteAddress, reloadDashboard } = useDashboard();
  if (section === "download-detail") return <PdfDownloadDetails />;
  if (section === "order-detail") return <OrderDetails data={data} id={params.orderId} tracking={location.pathname.endsWith("/tracking")} />;
  if (section === "profile") return <Profile data={data} updateProfile={updateProfile} email={user.email} />;
  if (section === "settings") return <SettingsPage data={data} updateSettings={updateSettings} />;
  if (section === "addresses") return <Addresses addresses={data.addresses} addAddress={addAddress} deleteAddress={deleteAddress} />;
  if (section === "support") return <Support />;
  if (section === "notifications") return <Notifications notifications={data.notifications} onChange={setNotifications} />;
  if (section === "billing") return <Billing billing={data.billing} />;
  if (section === "downloads") return <PdfDownloadHistory />;
  if (section === "orders") return <Orders orders={data.orders} pendingOrders={data.pendingOrders || []} reloadDashboard={reloadDashboard} />;
  if (section === "favorites") return <Favorites books={data.favorites} removeFavorite={removeFavorite} />;
  return <Projects section={section} data={data} updateProject={updateProject} duplicateProject={duplicateProject} deleteProject={deleteProject} />;
}

function Favorites({ books, removeFavorite }) {
  const [removingId, setRemovingId] = useState(null);
  return <div className="dashboard-page">
    <DashboardPageHeading eyebrow="Saved for later" title="Favorite books" description="Keep the designs you love close, and start creating whenever you are ready." action={<Link className="button button-outline" to="/books">Explore books <ArrowRight size={14} /></Link>} />
    {books.length ? <div className="dashboard-favorites-grid">{books.map((book) => <article className="dashboard-favorite-card" key={book.id}>
      <Link to={`/books/${book.id}`} aria-label={`View ${book.title}`}><SafeImage src={book.image} alt={book.imageAlt || book.title} /></Link>
      <div><span className="dashboard-card-eyebrow">{book.category} · {book.pages}</span><h2><Link to={`/books/${book.id}`}>{book.title}</Link></h2><p>{book.description}</p>
        <div className="dashboard-favorite-actions"><Link className="button button-dark" to={`/create/${book.id}`} state={{ book }}>Start creating <ArrowRight size={14} /></Link><button className="dashboard-secondary-action" type="button" disabled={removingId === book.id} onClick={async () => { setRemovingId(book.id); try { await removeFavorite(book.id); } finally { setRemovingId(null); } }}><Heart size={14} /> {removingId === book.id ? "Removing…" : "Remove"}</button></div>
      </div>
    </article>)}</div> : <DashboardEmptyState title="Your favorites are waiting." description="Save book designs you love and they will be collected here." action={<Link className="button button-dark" to="/books">Explore book designs <ArrowRight size={14} /></Link>} />}
  </div>;
}

function Projects({ section, data, updateProject, duplicateProject, deleteProject }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [view, setView] = useState("grid");
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
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
    {projects.length ? <div className={`dashboard-project-grid${view === "list" ? " is-list" : ""}`}>{projects.map((project) => <ProjectCard key={project.id} project={project} compact={view === "list"} onRename={(id, title) => updateProject(id, { title })} onPrivacyChange={(id, privacyOverride) => updateProject(id, { privacyOverride })} onDuplicate={duplicateProject} onDelete={(id) => setConfirmDelete(id)} />)}</div> : <DashboardEmptyState icon={Search} title={search ? "No matching projects." : section === "drafts" ? "No saved drafts yet." : section === "completed" ? "Your first finished book is waiting." : "Your project library is ready."} description={search ? "Try a different title or clear your filters." : "Explore the designs and make your next story your own."} action={<Link className="button button-outline" to="/books">Explore designs</Link>} />}
    {confirmDelete ? <div className="dashboard-confirm-backdrop" role="presentation" onClick={() => { if (!deleting) setConfirmDelete(null); }}><div className="dashboard-confirm" role="dialog" aria-modal="true" aria-labelledby="delete-project-title" onClick={(event) => event.stopPropagation()}><span className="dashboard-confirm-icon"><Trash2 size={20} /></span><h2 id="delete-project-title">Delete this project?</h2><p>This removes the saved project from your account. Shared designs and copied projects are not removed.</p><div><button className="button button-outline" type="button" disabled={deleting} onClick={() => setConfirmDelete(null)}>Keep project</button><button className="button button-dark" type="button" disabled={deleting} onClick={async () => { setDeleting(true); try { if (await deleteProject(confirmDelete)) setConfirmDelete(null); } finally { setDeleting(false); } }}>{deleting ? "Deleting…" : "Delete project"}</button></div></div></div> : null}
  </div>;
}

function Orders({ orders, pendingOrders, reloadDashboard }) {
  const [filter, setFilter] = useState("All orders");
  const filters = ["All orders", ...new Set(orders.map((order) => order.status))];
  const shown = filter === "All orders" ? orders : orders.filter((order) => order.status === filter);
  const [actionError, setActionError] = useState("");
  const [busyOrderId, setBusyOrderId] = useState(null);
  async function cancelOrder(orderId) {
    if (!window.confirm("Cancel this unpaid print order? It cannot be paid after cancellation.")) return;
    setBusyOrderId(orderId);
    setActionError("");
    try {
      await printOrderService.cancelUnpaidOrder(orderId);
      reloadDashboard();
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : "The print order could not be cancelled.");
    } finally {
      setBusyOrderId(null);
    }
  }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.orders[0]} title={titles.orders[1]} description={titles.orders[2]} action={<Link className="button button-outline" to="/print/orders">Print order history <ArrowRight size={14} /></Link>} />
    {pendingOrders.length ? <section className="dashboard-section-block"><div className="dashboard-section-heading"><div><span className="eyebrow">Checkout needed</span><h2>Pending payment</h2></div></div>
      {actionError ? <p className="dashboard-info-note" role="alert">{actionError}</p> : null}
      <div className="dashboard-order-list">{pendingOrders.map((order) => <article className="dashboard-order-row" key={order.id}><div className="dashboard-order-main"><span className="dashboard-card-eyebrow">{order.reference}</span><h3>{order.title}</h3><p>Placed {order.date} · {order.total}</p><small>{order.paymentExpired ? "Payment window expired. This order can no longer be paid." : "Complete payment to send your book to production."}</small></div><div className="dashboard-order-links">{!order.paymentExpired ? <button className="button button-dark" type="button" disabled={busyOrderId === order.id} onClick={() => order.checkoutUrl ? window.location.assign(order.checkoutUrl) : window.location.assign(`/print/orders/${encodeURIComponent(order.id)}/confirmation`)}>Pay now</button> : null}<button className="button button-outline" type="button" disabled={busyOrderId === order.id} onClick={() => cancelOrder(order.id)}>{busyOrderId === order.id ? "Cancelling…" : "Cancel"}</button></div></article>)}</div>
    </section> : null}
    <div className="dashboard-tab-row">{filters.map((item) => <button className={filter === item ? "active" : ""} key={item} type="button" onClick={() => setFilter(item)}>{item}</button>)}</div>
    <div className="dashboard-order-list">{shown.map((order) => <OrderRow key={order.id} order={order} />)}</div>
    {!shown.length ? <DashboardEmptyState icon={PackageCheck} title="No orders in this view." description="Your printed books and order updates will be collected here." action={<Link className="button button-outline" to="/books">Explore books</Link>} /> : null}
  </div>;
}

function OrderDetails({ data, id, tracking }) {
  const summaryOrder = [...(data.orders || []), ...(data.pendingOrders || [])].find((item) => item.id === id);
  const [orderDetails, setOrderDetails] = useState(null);
  const [orderDetailsError, setOrderDetailsError] = useState("");
  const [orderDetailsLoading, setOrderDetailsLoading] = useState(false);
  useEffect(() => {
    let active = true;
    if (!id) return undefined;
    setOrderDetails(null);
    setOrderDetailsLoading(true);
    setOrderDetailsError("");
    printOrderService.getOrder(id).then((result) => {
      if (active) setOrderDetails(result);
    }).catch((failure) => {
      if (active) setOrderDetailsError(failure instanceof Error ? failure.message : "Order details could not be loaded.");
    }).finally(() => {
      if (active) setOrderDetailsLoading(false);
    });
    return () => { active = false; };
  }, [id]);
  const order = summaryOrder ? {
    ...summaryOrder,
    ...orderDetails,
    status: summaryOrder.status,
    payment: summaryOrder.payment,
    tracking: orderDetails?.shipment?.trackingNumber || summaryOrder.tracking,
  } : null;
  if (!order) return <div className="dashboard-page"><DashboardEmptyState icon={PackageCheck} title="Order not found." description="This order is not available in your account." action={<Link to="/dashboard/orders">Back to orders</Link>} /></div>;
  return <div className="dashboard-page">
    <DashboardPageHeading eyebrow={tracking ? "A keepsake is on its way" : `Order ${order.id}`} title={tracking ? "Order tracking" : "Order details"} description={order.title} action={<Link className="button button-outline" to="/dashboard/orders"><ArrowLeft size={15} /> All orders</Link>} />
    <div className="dashboard-detail-card"><div className="dashboard-order-hero"><img src={order.image} alt="" /><div><span className="dashboard-card-eyebrow">{order.id}</span><h2>{order.title}</h2><p>Placed {order.date} · {order.total}</p><span className="dashboard-status status-in-production">{order.status}</span></div></div>
      <div className="dashboard-detail-grid"><div><span>Payment</span><strong>{order.payment}</strong></div><div><span>Production status</span><strong>{order.status}</strong></div>{order.deliveryEstimate ? <div><span>Estimated delivery</span><strong>{order.deliveryEstimate}</strong></div> : null}{order.tracking ? <div><span>Tracking reference</span><strong>{order.tracking}</strong></div> : null}</div>
      {!order.tracking && order.status === "Shipped" ? <p className="dashboard-info-note">A tracking reference has not been provided yet.</p> : null}
      {orderDetailsError ? <p className="dashboard-info-note" role="alert">{orderDetailsError}</p> : null}
      <section className="dashboard-order-tracking">
        <div className="dashboard-section-heading"><div><span className="eyebrow">Every step, clearly</span><h2>Order timeline</h2></div></div>
        {orderDetailsLoading ? <p className="dashboard-info-note" role="status">Loading order updates…</p> : null}
        <OrderTimeline items={order.statusHistory} shipment={order.shipment} />
      </section>
      {order.shippingAddress ? <section className="dashboard-order-address">
        <h2><MapPin size={16} /> Delivery address</h2>
        <p>{order.shippingAddress.fullName}</p>
        <p>{order.shippingAddress.line1}{order.shippingAddress.line2 ? `, ${order.shippingAddress.line2}` : ""}</p>
        <p>{[order.shippingAddress.city, order.shippingAddress.region, order.shippingAddress.postalCode].filter(Boolean).join(", ")}</p>
        <p>{order.shippingAddress.country}</p>
      </section> : null}
      {order.printPdf?.print?.status === "failed" ? <div className="dashboard-info-note" role="alert"><strong>Print PDF issue:</strong> {order.printPdf.print.error?.message || "The print-ready PDF could not be generated."} <Link to={`/print/orders/${encodeURIComponent(order.id)}/confirmation`}>View retry options</Link></div> : null}
    </div>
  </div>;
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
  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const success = await updateProfile({
      name: String(form.get("name")).trim(),
      phone: String(form.get("phone")).trim(),
    });
    if (success) {
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    }
  }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.profile[0]} title={titles.profile[1]} description={titles.profile[2]} />
    <form className="dashboard-form-card" onSubmit={submit}><div className="dashboard-profile-photo"><span className="dashboard-avatar dashboard-avatar-large">{profile.name.slice(0, 1).toUpperCase()}</span><div><strong>Account profile</strong><p>Your name and phone number are saved to your account.</p></div></div>
      <div className="dashboard-form-grid"><label>Full name<input name="name" defaultValue={profile.name} required maxLength={80} /></label><label>Email address<input value={email} type="email" disabled /><small>Email changes require account verification.</small></label><label>Phone number<input name="phone" type="tel" defaultValue={profile.phone} placeholder="Add a phone number" /></label></div>
      <div className="dashboard-form-footer"><Link to="/forgot-password">Change password <ArrowRight size={14} /></Link><button className="button button-dark" type="submit">{saved ? <><Check size={15} /> Saved</> : "Save profile"}</button></div>
    </form>
  </div>;
}

function SettingsPage({ data, updateSettings }) {
  const items = [["orderEmails", "Order updates", "Receive email when your book moves through production."], ["productNews", "News & inspiration", "Occasional updates about new designs and ideas."]];
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.settings[0]} title={titles.settings[1]} description={titles.settings[2]} />
    <section className="dashboard-form-card"><div className="dashboard-section-heading"><div><span className="eyebrow">Your preferences</span><h2>Privacy & notifications</h2></div><Settings size={20} /></div>
      <label className="dashboard-setting-row"><span><strong>Full privacy</strong><small>Keep your uploaded photos and project pages private. Admins may view photos only for a paid print order in production. Original uploads are removed after the configured retention period once an order is delivered.</small></span><input type="checkbox" checked={Boolean(data.settings.privacyMode)} onChange={(event) => updateSettings({ privacyMode: event.target.checked })} /></label>
      {items.map(([key, title, description]) => <label className="dashboard-setting-row" key={key}><span><strong>{title}</strong><small>{description}</small></span><input type="checkbox" checked={data.settings[key]} onChange={(event) => updateSettings({ [key]: event.target.checked })} /></label>)}</section>
    <div className="dashboard-info-note"><Settings size={17} /> These preferences are saved to your account.</div>
  </div>;
}

function Billing() {
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    apiRequest("/payments/history").then(({ data }) => {
      if (!Array.isArray(data?.items)) throw new Error("Payment history returned an invalid response.");
      if (active) setPayments(data.items);
    }).catch((failure) => {
      if (active) setError(failure instanceof Error ? failure.message : "Payment history could not be loaded.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [reloadKey]);

  async function requestRefund(payment) {
    const amount = window.prompt(`Enter the refund amount in ${payment.currency}:`, payment.amount);
    if (amount === null) return;
    const reason = window.prompt("Why are you requesting a refund?");
    if (reason === null) return;
    setError("");
    setMessage("");
    try {
      await apiRequest(`/payments/${encodeURIComponent(payment.id)}/refund-requests`, {
        method: "POST",
        body: { amount, reason },
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      setMessage("Your refund request was submitted for review.");
      setReloadKey((key) => key + 1);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The refund request could not be submitted.");
    }
  }

  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.billing[0]} title={titles.billing[1]} description={titles.billing[2]} />
    {message ? <p className="dashboard-info-note" role="status">{message}</p> : null}
    {error ? <p className="dashboard-info-note" role="alert">{error}</p> : null}
    {loading ? <p className="dashboard-info-note">Loading your payment history…</p> : payments.length ? <div className="dashboard-billing-table-wrap"><table className="dashboard-billing-table"><thead><tr><th>Transaction</th><th>Date</th><th>Gateway / method</th><th>Amount</th><th>Status</th><th>Refund</th></tr></thead><tbody>{payments.map((payment) => {
      const refunds = payment.refunds ?? [];
      const refundPending = refunds.some((refund) => ["requested", "pending", "manual_required", "processing"].includes(refund.status));
      return <tr key={payment.id}><td><strong>{payment.providerPaymentId || payment.id}</strong></td><td>{new Date(payment.createdAt).toLocaleDateString()}</td><td>{payment.provider}{payment.paymentMethod ? ` · ${payment.paymentMethod}` : ""}</td><td>{new Intl.NumberFormat(undefined, { style: "currency", currency: payment.currency }).format(Number(payment.amount))}</td><td><span className="dashboard-status status-ready">{payment.status.replaceAll("_", " ")}</span></td><td>{refundPending ? refunds.map((refund) => refund.status.replaceAll("_", " ")).join(", ") : ["successful", "partially_refunded"].includes(payment.status) ? <button className="dashboard-text-link" type="button" onClick={() => requestRefund(payment)}>Request refund</button> : refunds.length ? refunds.map((refund) => refund.status.replaceAll("_", " ")).join(", ") : "—"}</td></tr>;
    })}</tbody></table></div> : !loading ? <DashboardEmptyState icon={FileText} title="No billing history yet." description="Verified payments and refund status will appear here." /> : null}
  </div>;
}

function Addresses({ addresses, addAddress, deleteAddress }) {
  const [adding, setAdding] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const saved = await addAddress({
      name: String(form.get("name")),
      line: String(form.get("line")),
      city: String(form.get("city")),
      postal: String(form.get("postal")),
      countryCode: String(form.get("countryCode")),
    });
    if (saved) setAdding(false);
  }
  return <div className="dashboard-page"><DashboardPageHeading eyebrow={titles.addresses[0]} title={titles.addresses[1]} description={titles.addresses[2]} action={!adding ? <button className="button button-dark" type="button" onClick={() => setAdding(true)}><Plus size={15} /> Add address</button> : null} />
    {adding ? <form className="dashboard-form-card dashboard-address-form" onSubmit={submit}><h2>New delivery address</h2><div className="dashboard-form-grid"><label>Recipient<input name="name" required maxLength={160} /></label><label>Street address<input name="line" required maxLength={200} /></label><label>City<input name="city" required maxLength={120} /></label><label>Postal code<input name="postal" required maxLength={30} /></label><label>Country code<input name="countryCode" defaultValue="PK" required minLength={2} maxLength={2} /></label></div><div className="dashboard-form-footer"><button className="button button-outline" type="button" onClick={() => setAdding(false)}>Cancel</button><button className="button button-dark" type="submit">Save address</button></div></form> : null}
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
