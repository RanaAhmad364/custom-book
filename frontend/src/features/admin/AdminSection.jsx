import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ArrowUpRight, Check, Eye, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SafeImage } from "../../components/common/SafeImage.jsx";
import {
  loadAdminSection, publishAdminRecord, removeAdminRecord, saveAdminRecord,
  createAdminPricing, createAdminVariant, loadAdminBookReferences, removeAdminPricing,
  adminExportUrl, loadAdminOrderHistory, loadAdminRelatedOrders, sendAdminEmail, updateAdminOrder, updateAdminPricing, updateAdminRefund, reviewAdminPayment, updateAdminSupport, updateAdminUser, uploadAdminAsset,
} from "./adminService.js";
import BookProductForm from "./BookProductForm.jsx";
import AdminRecordEditor from "./AdminRecordEditor.jsx";
import { DashboardPageHeading } from "../dashboard/DashboardUI.jsx";
import { pricingRecordDefaults } from "./pricingForm.js";
import OrderTimeline from "../orders/OrderTimeline.jsx";

const sectionTitles = {
  dashboard: ["Operations overview", "Admin dashboard", "Live platform activity and order health."],
  purchases: ["Orders", "Purchases", "Review PDF and print orders, payments, and fulfillment status."],
  downloads: ["Orders", "Downloads", "Review customer PDF downloads and their associated purchases."],
  profile: ["Platform", "Admin profile", "Update the profile details attached to your administrator account."],
  users: ["Accounts", "Users", "Search accounts and manage access status."],
  books: ["Catalog", "Book products", "Create a product draft, edit specifications, then publish it."],
  categories: ["Catalog", "Categories", "Maintain the public book discovery categories."],
  collections: ["Catalog", "Collections", "Organize books into curated collections."],
  templates: ["Design studio", "Templates", "Build and version page layouts before publication."],
  pricing: ["Commerce", "Pricing", "Manage tiers, per-page pricing, and promotional rules."],
  "pdf-orders": ["Orders", "PDF orders", "Review purchased PDF services and project revisions."],
  "print-orders": ["Orders", "Print orders", "Manage production status, shipping, and tracking."],
  payments: ["Commerce", "Payments", "Review verified payment history, status, and gateway references."],
  refunds: ["Commerce", "Refunds", "Review refunds; gateways without an automated refund contract require manual confirmation."],
  shipping: ["Commerce", "Shipping", "Maintain shipping services and rates."],
  notifications: ["Communications", "Notifications", "Review admin activity notices and send transactional email."],
  reports: ["Insights", "Reports", "Platform performance, revenue, and recent operational activity."],
  support: ["Customer care", "Support", "Respond to tickets and manage support priorities."],
  settings: ["Platform", "Settings", "Manage platform configuration stored by the backend."],
};

const defaults = {
  books: { title: "", slug: "", description: "", categoryId: "", collectionId: "", style: "Editorial", occasion: "", bookType: "BASIC", pageCountMin: 24, pageCountMax: 80, startingPrice: "0.00", currency: "PKR", featured: false, coverAssetKey: "", adminMetadata: { dimensions: { widthMm: "203.00", heightMm: "203.00" }, pageCountOptions: [24, 32, 40], sizeOptions: [], coverOptions: [], paperOptions: [], previewImageKeys: [], printingTiers: [], pdfPrice: "0.00", printingPrice: "0.00", basePageCount: 24, extraPagePrice: "", evenPageCountRequired: false, productionDays: 10 } },
  categories: { name: "", slug: "", description: "", style: "", heroAssetKey: "", sortOrder: 0, isPublished: true },
  collections: { name: "", slug: "", description: "", eyebrow: "", categoryId: "", heroAssetKey: "", recommendedLayouts: [], relatedCategories: [] },
  templates: { name: "", slug: "", description: "", categoryId: "", pages: [{ pageNumber: 1, type: "cover", layout: "cover-photo", background: "#F4F0E8", elements: [{ type: "image", x: 0.08, y: 0.08, width: 0.84, height: 0.84, content: { placeholder: "Cover photo" } }] }] },
  settings: { key: "", value: {}, public: false },
};

function recordLabel(record) {
  return record.title || record.name || record.subject || record.orderNumber || record.ticketNumber || record.email || record.code || record.key || record.id;
}

async function loadAllAdminItems(section) {
  const perPage = 100;
  const first = await loadAdminSection(section, "", { page: 1, perPage });
  if (!Array.isArray(first.items)) throw new Error(`The ${section} service returned an invalid list.`);
  const totalPages = first.pagination?.totalPages;
  if (!Number.isInteger(totalPages) || totalPages < 1) return first.items;
  const pages = await Promise.all(Array.from({ length: totalPages - 1 }, (_, index) =>
    loadAdminSection(section, "", { page: index + 2, perPage })));
  if (pages.some((page) => !Array.isArray(page.items))) throw new Error(`The ${section} service returned an invalid list.`);
  return [...first.items, ...pages.flatMap((page) => page.items)];
}

function adminFailureMessage(failure, fallback) {
  if (!(failure instanceof Error)) return fallback;
  const details = failure.details;
  const fields = details && typeof details === "object"
    ? Object.entries(details).map(([field, reason]) => `${field}: ${String(reason).replaceAll("_", " ")}`)
    : [];
  return fields.length ? `${failure.message} (${fields.join("; ")})` : failure.message;
}

function rowDetails(record) {
  const fragments = [
    record.email || record.userEmail,
    record.category,
    record.style,
    record.provider,
    record.paymentMethod,
    record.providerPaymentId || record.providerRefundId,
    record.submittedReference ? `Receipt reference ${record.submittedReference}` : undefined,
    record.status,
    record.isPublished === undefined ? undefined : (record.isPublished ? "Published" : "Draft"),
    record.published === undefined ? undefined : (record.published ? "Published" : "Draft"),
    record.masterDesignStatus ? `Master design ${record.masterDesignStatus.replaceAll("_", " ")}` : undefined,
    record.masterDesignVersion ? `v${record.masterDesignVersion}` : undefined,
    record.amount ? `${record.currency || "PKR"} ${record.amount}` : undefined,
    record.startingPrice ? `${record.currency || "PKR"} ${record.startingPrice}` : undefined,
    record.kind === "tier" ? `${record.currency || "PKR"} ${record.basePrice} base` : undefined,
    record.kind === "pagePricing" ? `${record.pricePerPage} per additional page` : undefined,
    record.kind === "shipping" ? `${record.currency || "PKR"} ${record.price}` : undefined,
    record.kind === "variant" ? `${record.currency || "PKR"} ${record.basePrice} printing` : undefined,
    record.widthMm && record.heightMm ? `${record.widthMm} × ${record.heightMm} mm` : undefined,
    record.active === undefined ? undefined : (record.active ? "Active" : "Inactive"),
  ].filter(Boolean);
  return fragments.join(" · ");
}

function MetricCard({ label, value, note }) {
  return <article className="admin-metric-card"><span>{label}</span><strong>{value ?? "—"}</strong>{note ? <small>{note}</small> : null}</article>;
}

function UserTable({ records, selectedId, onSelect, onToggleStatus }) {
  return <div className="admin-table-wrap">
    <table className="admin-management-table">
      <thead><tr><th>User</th><th>Phone</th><th>Roles</th><th>Email</th><th>Account</th><th>Registered</th><th>Actions</th></tr></thead>
      <tbody>{records.map((user) => <tr key={user.id} className={selectedId === user.id ? "is-selected" : ""}>
        <td><strong>{user.name || "Name not provided"}</strong><small>{user.email}</small></td>
        <td>{user.phone || "Not provided"}</td>
        <td><span className="admin-badge-list">{(user.roles ?? []).map((role) => <span className="admin-status" key={role}>{role}</span>)}</span></td>
        <td><span className={`admin-status${user.emailVerified ? "" : " is-muted"}`}>{user.emailVerified ? "Verified" : "Not verified"}</span></td>
        <td><span className={`admin-status${user.isActive ? "" : " is-muted"}`}>{user.isActive ? "Active" : "Inactive"}</span></td>
        <td>{user.createdAt ? new Date(user.createdAt).toLocaleDateString() : "Not provided"}</td>
        <td><div className="admin-table-actions">
          <button className="admin-inline-button" type="button" onClick={() => onSelect(user)}>View</button>
          <button className="admin-inline-button" type="button" onClick={() => onToggleStatus(user)}>{user.isActive ? "Deactivate" : "Activate"}</button>
        </div></td>
      </tr>)}
      {!records.length ? <tr><td colSpan="7" className="admin-table-empty">No users match this search.</td></tr> : null}</tbody>
    </table>
  </div>;
}

function CatalogTable({ section, records, selectedId, onSelect, onDelete, onToggleStatus }) {
  const isCategory = section === "categories";
  return <div className="admin-table-wrap">
    <table className="admin-management-table admin-catalog-table">
      <thead><tr><th>Image</th><th>Name and description</th><th>Slug</th><th>Status</th>
        {isCategory ? <><th>Books</th><th>Collections</th></> : null}
        <th>Sort order</th><th>Actions</th></tr></thead>
      <tbody>{records.map((record) => <tr key={record.id} className={selectedId === record.id ? "is-selected" : ""}>
        <td><SafeImage className="admin-catalog-thumb" src={record.image || record.heroImage} alt={record.imageAlt || record.name || "Catalog image"} /></td>
        <td><strong>{record.name || "Untitled"}</strong><small>{record.description || "No description"}</small></td>
        <td>{record.slug || "—"}</td>
        <td><span className={`admin-status${record.isPublished ? "" : " is-muted"}`}>{isCategory ? record.isPublished ? "Active" : "Inactive" : record.isPublished ? "Published" : "Draft"}</span></td>
        {isCategory ? <>
          <td>{record.bookCount ?? 0} <small>({record.publishedBookCount ?? 0} active · {record.draftBookCount ?? 0} draft)</small></td>
          <td>{record.collectionCount ?? 0}</td>
        </> : null}
        <td>{record.sortOrder ?? 0}</td>
        <td><div className="admin-table-actions">
          <button className="admin-inline-button" type="button" onClick={() => onSelect(record)}>Edit</button>
          {isCategory ? <button className="admin-inline-button" type="button" onClick={() => onToggleStatus(record)}>{record.isPublished ? "Deactivate" : "Activate"}</button> : null}
          <button className="admin-inline-button is-danger" type="button" onClick={() => onDelete(record)}>Delete</button>
        </div></td>
      </tr>)}
      {!records.length ? <tr><td colSpan={isCategory ? "8" : "6"} className="admin-table-empty">No catalog records match this search.</td></tr> : null}</tbody>
    </table>
  </div>;
}

function AdminPagination({ pagination, page, loading, onChange }) {
  if (!pagination || pagination.totalPages < 2) return null;
  return <nav className="admin-pagination" aria-label="Admin record pages">
    <span>Page {pagination.page ?? page} of {pagination.totalPages} · {pagination.totalItems} total</span>
    <div>
      <button type="button" className="admin-button admin-button-quiet" disabled={loading || page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
      <button type="button" className="admin-button admin-button-quiet" disabled={loading || page >= pagination.totalPages} onClick={() => onChange(page + 1)}>Next</button>
    </div>
  </nav>;
}

function AdminHistoryTable({ records, mode, onSelect }) {
  const downloads = mode === "downloads";
  const showOrderAction = !downloads && typeof onSelect === "function";
  return <div className="admin-table-wrap">
    <table className="admin-management-table">
      <thead><tr>
        <th>User</th><th>Email</th><th>Book</th><th>Type</th><th>Pages</th><th>Amount</th>
        <th>Payment</th><th>{downloads ? "Downloaded" : "Date"}</th>
        {showOrderAction ? <th>Order</th> : null}
      </tr></thead>
      <tbody>{records.map((record) => <tr key={record.id}>
        <td>{record.userName || "Name not provided"}</td>
        <td>{record.userEmail || "—"}</td>
        <td>{record.bookTitle || record.projectTitle || "Untitled project"}</td>
        <td>{record.type === "pdf" ? "PDF" : "Print"}</td>
        <td>{record.pageCount ?? "—"}</td>
        <td>{record.currency || "PKR"} {record.amount ?? "—"}</td>
        <td><span className="admin-status">{(record.paymentStatus || record.status || "unknown").replaceAll("_", " ")}</span></td>
        <td>{record.downloadedAt || record.createdAt ? new Date(record.downloadedAt || record.createdAt).toLocaleString() : "—"}</td>
        {showOrderAction ? <td><button className="admin-inline-button" type="button" onClick={() => onSelect(record)}>View order</button></td> : null}
      </tr>)}
      {!records.length ? <tr><td colSpan={showOrderAction ? 9 : 8} className="admin-table-empty">No {downloads ? "downloads" : "purchases"} match these filters.</td></tr> : null}</tbody>
    </table>
  </div>;
}

function AdminOrderTimeline({ items, loading }) {
  if (loading) return <p className="admin-list-message" role="status">Loading order timeline…</p>;
  if (!items?.length) return <p className="admin-list-message">No status changes have been recorded yet.</p>;
  return <OrderTimeline items={items} />;
}

export default function AdminSection({ sectionOverride }) {
  const { section: routeSection } = useParams();
  const navigate = useNavigate();
  const section = sectionOverride || routeSection || "dashboard";
  const [payload, setPayload] = useState(null);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [categoryOptions, setCategoryOptions] = useState([]);
  const [providerFilter, setProviderFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [bookFilter, setBookFilter] = useState("");
  const [paymentStatusFilter, setPaymentStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [analyticsDays, setAnalyticsDays] = useState("30");
  const [detailHistory, setDetailHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyRequestId = useRef(0);
  const [listPage, setListPage] = useState(1);
  const [bookFormDirty, setBookFormDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pricingCreateKind, setPricingCreateKind] = useState("tier");
  const [emailDraft, setEmailDraft] = useState({ recipient: "", subject: "", body: "" });
  const title = sectionTitles[section] || sectionTitles.dashboard;

  async function refresh(query = search, page = listPage, filterOverrides = {}) {
    setLoading(true);
    setError("");
    try {
      const pagedSections = new Set(["users", "books", "categories", "collections", "templates", "purchases", "downloads", "pdf-orders", "print-orders", "payments", "refunds", "support", "notifications"]);
      const activeStatus = filterOverrides.status ?? statusFilter;
      const activeProvider = filterOverrides.provider ?? providerFilter;
      const activeCategory = filterOverrides.category ?? categoryFilter;
      const result = await loadAdminSection(section, query, {
        ...(section === "payments" || section === "refunds" || section === "pdf-orders" || section === "print-orders" || section === "purchases" || section === "downloads" || section === "support"
          ? { status: activeStatus }
          : {}),
        ...(section === "categories" || section === "collections" || section === "templates"
          ? { published: activeStatus }
          : {}),
        ...(section === "books" ? { published: activeStatus, categoryId: activeCategory } : {}),
        provider: section === "payments" ? activeProvider : "",
        ...(section === "dashboard" ? { days: filterOverrides.days ?? analyticsDays } : {}),
        ...(["purchases", "downloads", "pdf-orders", "print-orders"].includes(section) ? {
          dateFrom: filterOverrides.dateFrom ?? dateFrom,
          dateTo: filterOverrides.dateTo ?? dateTo,
          user: filterOverrides.user ?? userFilter,
          book: filterOverrides.book ?? bookFilter,
          paymentStatus: filterOverrides.paymentStatus ?? paymentStatusFilter,
          ...(["purchases", "downloads"].includes(section) ? { type: filterOverrides.type ?? typeFilter } : {}),
        } : {}),
        ...(pagedSections.has(section) ? { page, perPage: 20 } : {}),
      });
      setPayload(result);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Admin data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    setSelected(null);
    setDraft(null);
    setPayload(null);
    setListPage(1);
    setSearch("");
    setStatusFilter("");
    setCategoryFilter("");
    setCategoryOptions([]);
    setProviderFilter("");
    setDateFrom("");
    setDateTo("");
    setUserFilter("");
    setBookFilter("");
    setPaymentStatusFilter("");
    setTypeFilter("all");
    setDetailHistory(null);
    setBookFormDirty(false);
    setPricingCreateKind(section === "shipping" ? "shipping" : "tier");
    setMessage("");
    setError("");
    refresh("", 1, { status: "", provider: "", dateFrom: "", dateTo: "", user: "", book: "", paymentStatus: "", type: "all" });
  // refresh is intentionally scoped to section changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section]);

  useEffect(() => {
    if (section !== "books") return undefined;
    let active = true;
    loadAllAdminItems("categories").then((items) => {
      if (active) setCategoryOptions(items);
    }).catch((failure) => {
      if (active) setError(failure instanceof Error ? failure.message : "Categories could not be loaded.");
    });
    return () => { active = false; };
  }, [section]);

  const records = useMemo(() => {
    if (section === "shipping") return (payload?.shipping || []).map((item) => ({
      ...item,
      name: `${item.countryCode}${item.regionCode ? ` · ${item.regionCode}` : ""} · ${item.serviceName}`,
      kind: "shipping",
    }));
    if (section === "pricing") return [
      ...(payload?.tiers || []).map((item) => ({ ...item, kind: "tier" })),
      ...(payload?.pagePricing || []).map((item) => ({ ...item, name: `${item.tierCode} · ${item.minimumPages}–${item.maximumPages} pages`, kind: "pagePricing" })),
      ...(payload?.rules || []).map((item) => ({ ...item, kind: "rule" })),
      ...(payload?.discounts || []).map((item) => ({ ...item, kind: "discount" })),
      ...(payload?.variants || []).map((item) => ({ ...item, name: `${item.book} · ${item.size} · ${item.cover} · ${item.paper}`, kind: "variant" })),
    ];
    if (section === "reports" || section === "dashboard") return [];
    return payload?.items || [];
  }, [payload, section]);

  function selectRecord(record) {
    if (section === "books" && draft?.id !== record.id && bookFormDirty &&
        !window.confirm("Discard your unsaved book changes? Uploaded images may remain in storage.")) return;
    setSelected(record);
    setDraft(record);
    setBookFormDirty(false);
    setMessage("");
    const requestId = ++historyRequestId.current;
    const orderType = record.type || (section === "pdf-orders" ? "pdf" : section === "print-orders" ? "print" : null);
    const loadHistory = orderType
      ? loadAdminOrderHistory({ id: record.id, type: orderType })
      : ["users", "books"].includes(section) && record.id
        ? loadAdminRelatedOrders(section, record.id)
        : null;
    setDetailHistory(null);
    if (loadHistory) {
      setDetailHistory({ type: orderType ? "timeline" : "orders", items: [] });
      setHistoryLoading(true);
      loadHistory.then((items) => {
        if (historyRequestId.current === requestId) setDetailHistory({ type: orderType ? "timeline" : "orders", items });
      }).catch((failure) => {
        if (historyRequestId.current === requestId) setError(failure instanceof Error ? failure.message : "Related order history could not be loaded.");
      }).finally(() => {
        if (historyRequestId.current === requestId) setHistoryLoading(false);
      });
    } else {
      setHistoryLoading(false);
    }
  }

  function startCreate() {
    if (section === "books" && draft && bookFormDirty &&
        !window.confirm("Discard your unsaved book changes? Uploaded images may remain in storage.")) return;
    const record = structuredClone(defaults[section] || {});
    setSelected(null);
    setDraft(record);
    setDetailHistory(null);
    setBookFormDirty(false);
    setMessage("");
  }

  function startPricingCreate(kind) {
    setSelected(null);
    setDraft(pricingRecordDefaults(kind, payload?.currency || "PKR"));
    setMessage("");
    setError("");
  }

  async function toggleUserStatus(user) {
    if (user.isActive && !window.confirm(`Deactivate ${user.fullName || user.name || user.email}?`)) return;
    setError("");
    setMessage("");
    try {
      await updateAdminUser({ ...user, isActive: !user.isActive });
      setMessage(user.isActive ? "User account deactivated." : "User account activated.");
      setSelected(null);
      setDraft(null);
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The account status could not be changed.");
    }
  }

  async function saveRecord(record) {
    if (["pdf-orders", "print-orders", "purchases"].includes(section) && selected?.status !== record.status &&
      ["cancelled", "refunded"].includes(record.status) &&
      !window.confirm(`Change this order to ${record.status.replaceAll("_", " ")}?`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (section === "users") await updateAdminUser(record);
      else if (section === "pdf-orders" || section === "print-orders" || section === "purchases") {
        await updateAdminOrder({ ...record, type: section === "pdf-orders" ? "pdf" : section === "print-orders" ? "print" : record.type });
      } else if (section === "support") await updateAdminSupport({ id: record.id, changes: record });
      else if (section === "pricing" || section === "shipping") {
        if (record.__create) {
          const { __create, kind, ...variant } = record;
          if (kind === "variant") await createAdminVariant(variant);
          else await createAdminPricing(kind, variant);
        } else {
          const { id, kind, ...changes } = record;
          await updateAdminPricing({ id, kind, changes });
        }
      } else {
        await saveAdminRecord(section, record);
      }
      setMessage("Changes saved.");
      setSelected(null);
      setDraft(null);
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The change could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleCategoryStatus(record) {
    if (record.isPublished && (record.publishedBookCount ?? 0) > 0) {
      setError(`Cannot deactivate “${record.name}” because ${record.publishedBookCount} published book${record.publishedBookCount === 1 ? " uses" : "s use"} it. Unpublish or reassign those books first.`);
      setMessage("");
      return;
    }
    if (record.isPublished) {
      const draftCount = record.draftBookCount ?? 0;
      const collectionCount = record.collectionCount ?? 0;
      const impact = [
        draftCount ? `${draftCount} draft book${draftCount === 1 ? "" : "s"} will remain assigned` : "",
        collectionCount ? `${collectionCount} collection${collectionCount === 1 ? "" : "s"} reference it` : "",
      ].filter(Boolean).join("; ");
      if (!window.confirm(`Deactivate “${record.name}”?${impact ? ` ${impact}.` : ""} No books will be deleted or reassigned.`)) return;
    }
    await saveRecord({ ...record, isPublished: !record.isPublished });
  }

  async function saveBookProduct(record, { designAfterSave = false } = {}) {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveAdminRecord("books", {
        ...record,
        ...(draft?.id ? { id: draft.id } : {}),
      });
      const book = saved.book || saved;
      const nextPage = draft?.id ? listPage : 1;
      if (!draft?.id) setListPage(1);
      setMessage(designAfterSave ? "Book saved. Continue with the visual design." : "Book changes saved.");
      setSelected(null);
      setDraft(null);
      setBookFormDirty(false);
      await refresh(search, nextPage);
      if (designAfterSave) navigate(`/admin/books/${encodeURIComponent(book.id)}/design`);
    } catch (failure) {
      setError(adminFailureMessage(failure, "The book product could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function deleteRecord(record) {
    const deletingEditedBook = section === "books" && draft?.id === record.id;
    const deletingPagePricing = section === "pricing" && record.kind === "pagePricing";
    const categoryReferences = section === "categories"
      ? [
        record.bookCount ? `${record.bookCount} product${record.bookCount === 1 ? "" : "s"}` : "",
        record.collectionCount ? `${record.collectionCount} collection${record.collectionCount === 1 ? "" : "s"}` : "",
      ].filter(Boolean).join(" and ")
      : "";
    const confirmation = deletingPagePricing
      ? `Delete the ${record.tierCode} ${record.minimumPages}–${record.maximumPages} page-pricing band? New quotes will no longer use this band.`
      : section === "categories"
      ? `Soft-delete ${recordLabel(record)}?${categoryReferences ? ` It is referenced by ${categoryReferences}, so deletion will be rejected until those references are removed.` : ""} Its image will not be removed.`
      : deletingEditedBook && bookFormDirty
      ? `Delete ${recordLabel(record)} and discard your unsaved changes?`
      : `Delete ${recordLabel(record)}? This is a soft delete where supported.`;
    if (!window.confirm(confirmation)) return;
    try {
      if (deletingPagePricing) {
        await removeAdminPricing(record.kind, record.id);
      } else if (section === "collections") {
        const books = await loadAdminBookReferences();
        const references = books.filter((book) => book.collectionId === record.id);
        if (references.length) {
          const examples = references.slice(0, 3).map((book) => book.title || "Untitled book").join(", ");
          throw new Error(`This collection is used by ${references.length} book${references.length === 1 ? "" : "s"}${examples ? ` (${examples})` : ""}. Reassign those books before deleting it.`);
        }
      }
      await removeAdminRecord(section, record.id);
      setMessage("Record deleted.");
      setSelected(null);
      if (deletingEditedBook) {
        setDraft(null);
        setBookFormDirty(false);
      }
      const nextPage = section === "books" && records.length === 1 && listPage > 1 ? listPage - 1 : listPage;
      if (nextPage !== listPage) setListPage(nextPage);
      await refresh(search, nextPage);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The record could not be deleted.");
    }
  }

  async function togglePublication(record) {
    const togglingEditedBook = section === "books" && draft?.id === record.id;
    if (togglingEditedBook && bookFormDirty &&
        !window.confirm("Discard your unsaved book changes before changing publication status?")) return;
    try {
      await publishAdminRecord(section, record.id, !(record.isPublished ?? record.published));
      setMessage(record.isPublished || record.published ? "Record unpublished." : "Record published.");
      setSelected(null);
      if (togglingEditedBook) {
        setDraft(null);
        setBookFormDirty(false);
      }
      await refresh();
    } catch (failure) {
      setError(adminFailureMessage(failure, "Publication could not be changed."));
    }
  }

  async function submitEmail(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const result = await sendAdminEmail(emailDraft);
      setMessage(`Email ${result.email.status}.`);
      setEmailDraft({ recipient: "", subject: "", body: "" });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The email could not be sent.");
    }
  }

  async function processManualRefund(refund, status) {
    setError("");
    setMessage("");
    const providerReference = status === "succeeded"
      ? window.prompt("Enter the verified provider refund transaction reference:")
      : undefined;
    if (status === "succeeded" && !providerReference?.trim()) return;
    if (!window.confirm(`Set this refund to ${status.replaceAll("_", " ")}?`)) return;
    try {
      await updateAdminRefund(refund.id, {
        status,
        ...(status === "succeeded" ? { providerReference: providerReference.trim(), verified: true } : {}),
      });
      setMessage({
        approved: "Refund request approved.",
        rejected: "Refund request rejected.",
        processing: "Refund moved to manual processing.",
        succeeded: "Manual refund confirmation recorded.",
        failed: "Refund marked as failed.",
      }[status]);
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The manual refund update failed.");
    }

  }

  async function reviewManualPayment(payment, status) {
    if (!window.confirm(`${status === "approved" ? "Approve" : "Reject"} this manual payment?`)) return;
    setError("");
    setMessage("");
    try {
      await reviewAdminPayment(payment.id, status);
      setMessage(status === "approved" ? "Manual payment approved and order updated." : "Manual payment rejected; customer can retry.");
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The manual payment could not be reviewed.");
    }
  }

  async function uploadAsset(file) {
    setError("");
    try {
      return await uploadAdminAsset(file);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The image upload failed.");
      return null;
    }
  }

  if (loading && !payload) return <div className="admin-loading"><RefreshCw size={18} className="admin-spin" /> Loading admin workspace…</div>;
  if (error && !payload) return <div className="admin-load-error" role="alert"><AlertCircle size={18} />{error}<button type="button" onClick={() => refresh()}>Try again</button></div>;

  if (section === "dashboard" || section === "reports") {
    const stats = payload || {};
    const downloadTotal = (stats.downloadsSeries || []).reduce((total, item) => total + item.downloads, 0);
    const revenueMax = Math.max(1, ...(stats.revenueSeries || []).map((item) => Number(item.revenue) || 0));
    const downloadsMax = Math.max(1, ...(stats.downloadsSeries || []).map((item) => item.downloads));
    return <div className="admin-page">
      <DashboardPageHeading eyebrow={title[0]} title={title[1]} description={title[2]} action={section === "dashboard" ?
        <div className="admin-table-actions">
          <label className="admin-range-control">Date range
            <select value={analyticsDays} onChange={(event) => { setAnalyticsDays(event.target.value); refresh(search, 1, { days: event.target.value }); }}>
              <option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option>
            </select>
          </label>
          <button className="admin-button admin-button-quiet" type="button" onClick={() => refresh()}><RefreshCw size={15} /> Refresh</button>
        </div> : <button className="admin-button admin-button-quiet" type="button" onClick={() => refresh()}><RefreshCw size={15} /> Refresh</button>} />
      <div className="admin-metric-grid">
        <MetricCard label="Total users" value={stats.totalUsers} />
        <MetricCard label="Active projects" value={stats.activeProjects} />
        <MetricCard label="Orders" value={(stats.pdfPurchases || 0) + (stats.printOrders || 0)} />
        <MetricCard label="Downloads" value={downloadTotal} note={`Last ${analyticsDays} days`} />
        <MetricCard label="Revenue" value={`${stats.currency || "PKR"} ${stats.revenue || "0.00"}`} />
        <MetricCard label="Pending payments" value={stats.needsAttention?.manualPayments ?? 0} />
        <MetricCard label="Orders to ship" value={stats.needsAttention?.ordersToShip ?? 0} />
        <MetricCard label="Favorites" value={stats.favoritesCount} />
      </div>
      {section === "reports" ? <section className="admin-panel"><h2>New users · recent activity</h2><div className="admin-report-grid"><div><h3>Daily registrations</h3>{(stats.userGrowth || []).map((row) => <p key={row.date}><span>{row.date}</span><strong>{row.count}</strong></p>)}</div><div><h3>Admin activity</h3>{(stats.activity || []).map((row, index) => <p key={`${row.action}-${index}`}><span>{row.action} · {row.type}</span><small>{new Date(row.createdAt).toLocaleString()}</small></p>)}</div></div></section>
        : <>
          <div className="admin-analytics-grid">
            <section className="admin-panel"><h2>Revenue trend</h2><div className="admin-series" role="img" aria-label={`Revenue for the last ${analyticsDays} days`}>
              {(stats.revenueSeries || []).map((item) => <div className="admin-series-item" key={item.date} title={`${item.date}: ${stats.currency || "PKR"} ${item.revenue}`}>
                <span style={{ height: `${Math.max(3, Number(item.revenue) / revenueMax * 100)}%` }} />
                <small>{item.date.slice(-2)}</small>
              </div>)}
            </div></section>
            <section className="admin-panel"><h2>Downloads trend</h2><div className="admin-series is-downloads" role="img" aria-label={`Downloads for the last ${analyticsDays} days`}>
              {(stats.downloadsSeries || []).map((item) => <div className="admin-series-item" key={item.date} title={`${item.date}: ${item.downloads} downloads`}>
                <span style={{ height: `${Math.max(3, item.downloads / downloadsMax * 100)}%` }} />
                <small>{item.date.slice(-2)}</small>
              </div>)}
            </div></section>
          </div>
          <section className="admin-analytics-grid admin-rankings">
            {[
              ["Best-selling books", stats.bestSellingBooks, (item) => `${item.orders} orders · ${stats.currency || "PKR"} ${item.revenue}`],
              ["Most-downloaded", stats.mostDownloadedBooks, (item) => `${item.downloads} downloads`],
              ["Most-favorited", stats.mostFavoritedBooks, (item) => `${item.favorites} favorites`],
            ].map(([heading, items, description]) => <section className="admin-panel" key={heading}>
              <h2>{heading}</h2>
              {items?.length ? <ol>{items.map((item) => <li key={item.id}><Link to={`/books/${encodeURIComponent(item.slug || item.id)}`}>{item.title}</Link><span>{description(item)}</span></li>)}</ol>
                : <p className="admin-list-message">No book activity for this period yet.</p>}
            </section>)}
          </section>
          <section className="admin-analytics-grid">
            <div className="admin-panel"><h2>Recent orders</h2><div className="admin-table-wrap"><table><thead><tr><th>Order</th><th>Type</th><th>Placed</th><th>Status</th><th>Total</th></tr></thead><tbody>{(stats.recentOrders || []).map((order) => <tr key={`${order.type}-${order.id}`}><td>{order.orderNumber}</td><td>{order.type === "pdf" ? "PDF" : "Print"}</td><td>{new Date(order.createdAt).toLocaleDateString()}</td><td><span className="admin-status">{order.status}</span></td><td>{stats.currency || "PKR"} {order.amount}</td></tr>)}{!stats.recentOrders?.length ? <tr><td colSpan="5" className="admin-table-empty">No orders have been recorded yet.</td></tr> : null}</tbody></table></div></div>
            <div className="admin-panel"><h2>Recent users</h2><div className="admin-compact-list">{(stats.recentUsers || []).map((user) => <div key={user.id}><strong>{user.name}</strong><span>{user.email}</span><small>{new Date(user.createdAt).toLocaleDateString()}</small></div>)}{!stats.recentUsers?.length ? <p className="admin-list-message">No user accounts yet.</p> : null}</div></div>
          </section>
          <section className="admin-analytics-grid">
            <div className="admin-panel admin-attention"><h2>Needs attention</h2><p><span>Manual payments awaiting approval</span><strong>{stats.needsAttention?.manualPayments ?? 0}</strong></p><Link to="/admin/payments">Review payments</Link><p><span>Orders ready to ship</span><strong>{stats.needsAttention?.ordersToShip ?? 0}</strong></p><Link to="/admin/purchases?status=packed">Review purchases</Link></div>
            <div className="admin-panel"><h2>Quick actions</h2><div className="admin-quick-actions"><Link to="/admin/books">Add a book</Link><Link to="/admin/categories">Manage categories</Link><Link to="/admin/pricing">Update pricing</Link><Link to="/admin/support">View support</Link></div></div>
          </section>
        </>}
    </div>;
  }

  const canCreate = ["books", "categories", "collections", "templates", "settings"].includes(section);
  const canDelete = ["books", "categories", "collections", "templates"].includes(section);
  const canSearch = ["users", "books", "categories", "collections", "templates", "purchases", "downloads", "pdf-orders", "print-orders", "payments", "refunds"].includes(section);
  const pricingKinds = section === "shipping"
    ? [["shipping", "Shipping rate"]]
    : [
      ["tier", "Printing tier"],
      ["pagePricing", "Page pricing"],
      ["size", "Book size"],
      ["cover", "Cover type"],
      ["paper", "Paper type"],
      ["variant", "Book variant"],
    ];
  return <div className="admin-page">
    <DashboardPageHeading eyebrow={title[0]} title={title[1]} description={title[2]}
      action={canCreate ? <button className="admin-button admin-button-primary" type="button" onClick={startCreate}><Plus size={16} /> Create new</button>
        : section === "pricing" || section === "shipping" ? <div className="admin-table-actions">
          <select aria-label="Pricing item type" value={pricingCreateKind} onChange={(event) => setPricingCreateKind(event.target.value)}>
            {pricingKinds.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
          </select>
          <button className="admin-button admin-button-primary" type="button" onClick={() => startPricingCreate(pricingCreateKind)}>
            <Plus size={16} /> Add {pricingKinds.find(([kind]) => kind === pricingCreateKind)?.[1].toLowerCase()}
          </button>
        </div> : null} />
    {message ? <div className="admin-toast admin-toast-success" role="status"><Check size={15} />{message}<button type="button" aria-label="Dismiss notification" onClick={() => setMessage("")}>×</button></div> : null}
    {error ? <div className="admin-toast admin-toast-error" role="alert"><AlertCircle size={15} />{error}<button type="button" aria-label="Dismiss error" onClick={() => setError("")}>×</button></div> : null}
    {section === "notifications" ? <form className="admin-email-panel" onSubmit={submitEmail}>
      <div><span className="admin-kicker">Transactional email</span><h2>Send an important update</h2><p>Delivery is recorded in the email log and requires configured SMTP.</p></div>
      <label>Recipient<input type="email" required value={emailDraft.recipient} onChange={(event) => setEmailDraft({ ...emailDraft, recipient: event.target.value })} /></label>
      <label>Subject<input required maxLength="200" value={emailDraft.subject} onChange={(event) => setEmailDraft({ ...emailDraft, subject: event.target.value })} /></label>
      <label>Message<textarea required value={emailDraft.body} onChange={(event) => setEmailDraft({ ...emailDraft, body: event.target.value })} /></label>
      <button className="admin-button admin-button-primary" type="submit"><Send size={15} /> Send email</button>
    </form> : null}
    {section === "payments" ? <nav className="admin-tabs" aria-label="Payment sections"><Link className="is-active" to="/admin/payments">Payments</Link><Link to="/admin/refunds">Refunds</Link></nav> : null}
    {section === "refunds" ? <nav className="admin-tabs" aria-label="Payment sections"><Link to="/admin/payments">Payments</Link><Link className="is-active" to="/admin/refunds">Refunds</Link></nav> : null}
    <div className={`admin-workspace${draft ? " has-editor" : ""}`}>
      <section className="admin-panel admin-list-panel">
        <div className="admin-list-toolbar">
          <div><h2>{["purchases", "downloads", "pdf-orders", "print-orders"].includes(section) ? "History" : "Records"}</h2><span>{payload?.pagination ? `${payload.pagination.totalItems} total` : `${records.length} shown`}</span></div>
          {["purchases", "downloads"].includes(section) ? <a className="admin-button admin-button-quiet" href={adminExportUrl(section, {
            search, dateFrom, dateTo, user: userFilter, book: bookFilter, paymentStatus: paymentStatusFilter,
            ...(section === "purchases" ? { type: typeFilter, status: statusFilter } : {}),
          })}>Export CSV</a> : null}
          {canSearch ? <div className="admin-search"><input aria-label="Search records" placeholder="Search…" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter") {
              setListPage(1);
              refresh(search, 1);
            }
          }} /><button type="button" aria-label="Search" onClick={() => {
            setListPage(1);
            refresh(search, 1);
          }}><ArrowUpRight size={15} /></button></div>
            : null}
        </div>
        {["payments", "refunds", "purchases", "downloads", "pdf-orders", "print-orders", "support", "categories", "collections", "templates", "books"].includes(section) ? <div className="admin-payment-filters">
          {["purchases", "downloads"].includes(section) ? <>
            <label>Type<select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              {section === "purchases" ? <><option value="all">PDF and print</option><option value="pdf">PDF</option><option value="print">Print</option></>
                : <><option value="all">All download types</option><option value="pdf">PDF</option></>}
            </select></label>
            <label>From<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
            <label>To<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
            <label>User<input value={userFilter} onChange={(event) => setUserFilter(event.target.value)} placeholder="Name or email" /></label>
            <label>Book<input value={bookFilter} onChange={(event) => setBookFilter(event.target.value)} placeholder="Book title" /></label>
            <label>Payment<select value={paymentStatusFilter} onChange={(event) => setPaymentStatusFilter(event.target.value)}><option value="">All payments</option>{["pending", "successful", "failed", "partially_refunded", "refunded"].map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label>
            {section === "purchases" ? <label>Order status<input value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} placeholder="e.g. shipped" /></label> : null}
          </> : null}
          {section === "books" ? <>
            <label>Publication<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All products</option><option value="true">Published</option><option value="false">Draft</option></select></label>
            <label>Category<select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">All categories</option>{categoryOptions.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
          </> : null}
          {["payments", "refunds"].includes(section) ? <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{(section === "payments" ? ["pending", "successful", "failed", "partially_refunded", "refunded"] : ["requested", "pending", "manual_required", "processing", "succeeded", "rejected", "failed"]).map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label> : null}
          {["categories", "collections", "templates"].includes(section) ? <label>{section === "categories" ? "Status" : "Publication"}<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All records</option><option value="true">{section === "categories" ? "Active" : "Published"}</option><option value="false">{section === "categories" ? "Inactive" : "Draft"}</option></select></label> : null}
          {["pdf-orders", "print-orders"].includes(section) ? <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{(section === "pdf-orders" ? ["pending", "paid", "generating", "ready", "failed", "cancellation_requested", "cancelled", "refunded"] : ["order_placed", "payment_confirmed", "processing", "printed", "shipped", "delivered", "design_verified", "in_production", "quality_check", "packed", "out_for_delivery", "cancellation_requested", "cancelled", "refunded"]).map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label> : null}
          {section === "support" ? <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{["open", "in_progress", "waiting_for_customer", "resolved", "closed"].map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label> : null}
          {section === "payments" ? <label>Gateway<select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="">All gateways</option><option value="manual">Manual transfer</option><option value="stripe">Stripe</option><option value="jazzcash">JazzCash</option><option value="payfast">PayFast</option></select></label> : null}
          <button className="admin-button admin-button-quiet" type="button" onClick={() => { setListPage(1); refresh(search, 1); }}>Apply filters</button>
        </div> : null}
        {loading ? <p className="admin-list-message">Loading records…</p> : null}
        {!loading && records.length === 0 ? <p className="admin-list-message">No records yet. New records will appear here when available.</p> : null}
        {["purchases", "downloads"].includes(section) ? <AdminHistoryTable records={records} mode={section} onSelect={selectRecord} /> : null}
        {section === "users" ? <UserTable records={records} selectedId={selected?.id} onSelect={selectRecord} onToggleStatus={toggleUserStatus} /> : null}
        {section === "categories" || section === "collections" ? <CatalogTable section={section} records={records} selectedId={selected?.id} onSelect={selectRecord} onDelete={deleteRecord} onToggleStatus={toggleCategoryStatus} /> : null}
        {!["users", "categories", "collections", "purchases", "downloads"].includes(section) ? <div className="admin-record-list">
          {records.map((record) => <article className={`admin-record${selected?.id === record.id ? " is-selected" : ""}`} key={record.id}>
            <button className="admin-record-main" type="button" onClick={() => selectRecord(record)}>
              <span className="admin-record-mark">{(recordLabel(record) || "?").slice(0, 1).toUpperCase()}</span>
              <span className="admin-record-copy"><strong>{recordLabel(record)}</strong><small>{rowDetails(record) || record.id}</small></span>
              <span className="admin-record-chevron">›</span>
            </button>
            {section === "users" ? <button className={`admin-status-toggle${record.isActive ? " is-enabled" : ""}`} type="button" onClick={() => saveRecord({ ...record, isActive: !record.isActive })}>{record.isActive ? "Active" : "Disabled"}</button> : null}
            {section === "books" && record.id ? <div className="admin-record-actions">
              <button type="button" onClick={() => navigate(`/admin/books/${encodeURIComponent(record.id)}/design`)}>Edit design</button>
              {record.masterDesignStatus !== "not_started"
                ? <button type="button" onClick={() => navigate(`/admin/books/${encodeURIComponent(record.id)}/design?preview=1`)}>Preview design</button> : null}
              <button type="button" onClick={() => togglePublication(record)}>{record.isPublished ? "Unpublish product" : "Publish product"}</button>
              <button type="button" aria-label={`Delete ${recordLabel(record)}`} onClick={() => deleteRecord(record)}><Trash2 size={14} /></button>
            </div> : null}
            {section === "templates" && record.id ? <div className="admin-record-actions">
              <button type="button" onClick={() => togglePublication(record)}>{record.isPublished ?? record.published ? "Unpublish" : section === "books" ? "Design & publish" : "Publish"}</button>
              <button type="button" aria-label={`Delete ${recordLabel(record)}`} onClick={() => deleteRecord(record)}><Trash2 size={14} /></button>
            </div> : null}
            {canDelete && !["books", "templates"].includes(section) && record.id ? <button className="admin-record-delete" type="button" aria-label={`Delete ${recordLabel(record)}`} onClick={() => deleteRecord(record)}><Trash2 size={14} /></button> : null}
            {section === "pricing" && record.kind === "pagePricing" ? <button className="admin-record-delete" type="button"
              aria-label={`Delete ${recordLabel(record)}`} onClick={() => deleteRecord(record)}><Trash2 size={14} /></button> : null}
            {section === "templates" ? <button className="admin-preview-button" type="button" onClick={() => selectRecord(record)}><Eye size={13} /> Design / Preview · v{record.version}</button> : null}
            {section === "books" ? <button className="admin-preview-button" type="button" onClick={() => selectRecord(record)}><Eye size={13} /> Preview book</button> : null}
            {section === "books" && record.id ? <button className="admin-preview-button" type="button"
              onClick={() => navigate(`/admin/books/${encodeURIComponent(record.id)}/design`)}>Design Book</button> : null}
            {section === "refunds" && record.status === "requested" ? <div className="admin-record-actions">
              <button type="button" onClick={() => processManualRefund(record, "approved")}>Approve request</button>
              <button type="button" onClick={() => processManualRefund(record, "rejected")}>Reject request</button>
            </div> : null}
            {section === "refunds" && record.status === "pending" ? <div className="admin-record-actions">
              <button type="button" onClick={() => processManualRefund(record, "approved")}>Retry / confirm provider refund</button>
            </div> : null}
            {section === "refunds" && ["manual_required", "processing"].includes(record.status) ? <div className="admin-record-actions">
              {record.status === "manual_required" ? <button type="button" onClick={() => processManualRefund(record, "processing")}>Approve manual processing</button> : null}
              <button type="button" onClick={() => processManualRefund(record, "succeeded")}>Record verified refund</button>
              <button type="button" onClick={() => processManualRefund(record, "failed")}>Mark refund failed</button>
            </div> : null}
            {section === "payments" && record.provider === "manual" && record.status === "pending" && record.attemptStatus === "submitted" ? <div className="admin-record-actions">
              <button type="button" onClick={() => reviewManualPayment(record, "approved")}>Approve transfer</button>
              <button type="button" onClick={() => reviewManualPayment(record, "rejected")}>Reject transfer</button>
            </div> : null}
          </article>)}
        </div> : null}
        <AdminPagination pagination={payload?.pagination} page={listPage} loading={loading}
          onChange={(page) => { setListPage(page); refresh(search, page); }} />
      </section>
      {draft ? section === "books"
        ? <BookProductForm key={draft.id || "new-book"} record={draft}
          onUpload={uploadAdminAsset} onSave={saveBookProduct} onDirtyChange={setBookFormDirty}
          onCreateVariant={createAdminVariant}
          onDesignBook={() => navigate(`/admin/books/${encodeURIComponent(draft.id)}/design`)}
          saveError={error} saving={saving}
          onClose={() => { setDraft(null); setSelected(null); setBookFormDirty(false); }} />
        : <AdminRecordEditor section={section === "purchases" ? (draft.type === "pdf" ? "pdf-orders" : "print-orders") : section} record={draft} setRecord={setDraft} onUpload={uploadAsset}
          orderHistory={detailHistory?.type === "timeline" ? detailHistory.items : []} orderHistoryLoading={historyLoading}
          onClose={() => { setDraft(null); setSelected(null); }} onSave={saveRecord} saveError={error} saving={saving} /> : null}
    </div>
    {draft && detailHistory?.type === "timeline" && draft.type !== "print" ? <section className="admin-panel admin-history-detail">
      <h2>Order timeline</h2><AdminOrderTimeline items={detailHistory.items} loading={historyLoading} />
    </section> : null}
    {draft && detailHistory?.type === "orders" ? <section className="admin-panel admin-history-detail">
      <h2>Purchase and download history</h2>
      {historyLoading ? <p className="admin-list-message" role="status">Loading related history…</p> : <AdminHistoryTable records={detailHistory.items} mode="purchases" />}
    </section> : null}
    {section === "templates" ? <p className="admin-template-note">Template pages use normalized 0–1 coordinates. Publishing requires at least one page and one editable placeholder. Published edits create an immutable previous-version snapshot; existing project documents remain untouched.</p> : null}
  </div>;
}
