import { useEffect, useState } from "react";
import { AlertCircle, FilePlus2, Plus, Save } from "lucide-react";
import { SafeImage } from "../../components/common/SafeImage.jsx";
import { loadAdminBookReferences, loadAdminPrintOrderPdf, loadAdminSection, loadPrivatePrintOrderPhotos } from "./adminService.js";
import { categoryFormPayload, validateCategoryRecord } from "./categoryForm.js";
import { validatePricingRecord } from "./pricingForm.js";
import { apiUrl } from "../../services/apiClient.js";
import OrderTimeline from "../orders/OrderTimeline.jsx";

const PRINT_ORDER_STATUSES = [
  "order_placed", "payment_confirmed", "processing", "printed", "shipped", "delivered",
  "design_verified", "in_production", "quality_check", "packed", "out_for_delivery",
  "cancellation_requested", "cancelled", "refunded",
];
const SUPPORT_STATUSES = ["open", "in_progress", "waiting_for_customer", "resolved", "closed"];
const SUPPORT_PRIORITIES = ["low", "normal", "high", "urgent"];

function labelFor(key) {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
}

function Input({ label, value, onChange, type = "text", required = false, ...props }) {
  return <label className="admin-form-field">
    <span>{label}{required ? " *" : ""}</span>
    <input type={type} required={required} value={value ?? ""} onChange={(event) => onChange(event.target.value)} {...props} />
  </label>;
}

function Select({ label, value, options, onChange, required = false, multiple = false }) {
  return <label className="admin-form-field">
    <span>{label}</span>
    <select required={required} multiple={multiple} value={multiple ? (value ?? []) : (value ?? "")} onChange={(event) => onChange(multiple
      ? Array.from(event.target.selectedOptions, (option) => option.value)
      : event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}

function Textarea({ label, value, onChange, rows = 3, ...props }) {
  return <label className="admin-form-field">
    <span>{label}</span>
    <textarea rows={rows} value={value ?? ""} onChange={(event) => onChange(event.target.value)} {...props} />
  </label>;
}

function Toggle({ label, checked, onChange }) {
  return <label className="admin-form-toggle">
    <input type="checkbox" checked={Boolean(checked)} onChange={(event) => onChange(event.target.checked)} />
    <span>{label}</span>
  </label>;
}

function ReadOnlyValue({ label, value }) {
  const display = value === null || value === undefined || value === ""
    ? "Not provided"
    : typeof value === "boolean" ? (value ? "Yes" : "No")
      : Array.isArray(value) ? value.join(", ") || "None"
        : typeof value === "object" ? Object.entries(value).map(([key, item]) => `${labelFor(key)}: ${String(item)}`).join(" · ")
          : String(value);
  return <div className="admin-detail-field"><span>{label}</span><strong>{display}</strong></div>;
}

function formatDeliveryAddress(address) {
  if (!address || typeof address !== "object") return address;
  return [
    address.fullName,
    [address.line1, address.line2].filter(Boolean).join(", "),
    [address.city, address.region, address.postalCode].filter(Boolean).join(", "),
    address.country,
    address.phone,
  ].filter(Boolean).join(" · ");
}

async function loadAllAdminCategories() {
  const perPage = 100;
  const firstPage = await loadAdminSection("categories", "", { page: 1, perPage });
  if (!Array.isArray(firstPage.items)) throw new Error("The category service returned an invalid list.");
  const totalPages = firstPage.pagination?.totalPages;
  if (!Number.isInteger(totalPages) || totalPages < 2) return firstPage.items;

  const remainingPages = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) =>
      loadAdminSection("categories", "", { page: index + 2, perPage })),
  );
  if (remainingPages.some((page) => !Array.isArray(page.items))) {
    throw new Error("The category service returned an invalid list.");
  }
  return [...firstPage.items, ...remainingPages.flatMap((page) => page.items)];
}

function FormFields({ section, record, update, categories = [], books = [], pricingOptions, settingValueText, setSettingValueText }) {
  if (section === "users") {
    return <div className="admin-detail-grid">
      <ReadOnlyValue label="Name" value={record.name} />
      <ReadOnlyValue label="Email" value={record.email} />
      <ReadOnlyValue label="Phone" value={record.phone} />
      <ReadOnlyValue label="Roles" value={record.roles} />
      <ReadOnlyValue label="Email verification" value={record.emailVerified ? "Verified" : "Not verified"} />
      <ReadOnlyValue label="Account status" value={record.isActive ? "Active" : "Inactive"} />
      <ReadOnlyValue label="Registration date" value={record.createdAt ? new Date(record.createdAt).toLocaleString() : null} />
    </div>;
  }

  if (section === "categories" || section === "collections") {
    const isCategory = section === "categories";
    const activeCategories = categories.filter((category) => category.isPublished !== false);
    const currentCategory = categories.find((category) => category.id === record.categoryId);
    const selectedCategoryMissing = record.categoryId
      && !activeCategories.some((category) => category.id === record.categoryId);
    return <>
      <div className="admin-form-grid">
        <Input label={isCategory ? "Category name" : "Collection name"} required value={record.name} onChange={(value) => update("name", value)} maxLength={isCategory ? 120 : 160} />
        <Input label="Slug" required value={record.slug} onChange={(value) => update("slug", value)} maxLength={isCategory ? 140 : 180}
          {...(isCategory ? { pattern: "[a-z0-9]+(?:-[a-z0-9]+)*", title: "Use lowercase letters, numbers, and single hyphens." } : {})} />
        <Textarea label="Description" value={record.description} onChange={(value) => update("description", value)} maxLength={5000} />
        {isCategory
          ? <Input label="Style" value={record.style} onChange={(value) => update("style", value)} maxLength={60} />
          : <Input label="Eyebrow" value={record.eyebrow} onChange={(value) => update("eyebrow", value)} maxLength={120} />}
        {isCategory ? null : <Select label="Category" value={record.categoryId ?? ""} options={[
          { value: "", label: "Choose a category" },
          ...(selectedCategoryMissing
            ? [{
              value: record.categoryId,
              label: currentCategory?.name || record.categoryName || "Current category (inactive or unavailable)",
            }]
            : []),
          ...activeCategories.map((category) => ({ value: category.id, label: category.name })),
        ]} onChange={(value) => update("categoryId", value)} required />}
        <Input label="Sort order" type="number" min="0" step="1" value={record.sortOrder} onChange={(value) => update("sortOrder", value === "" ? "" : Number(value))} />
        {isCategory ? null : <>
          <Textarea label="Recommended layouts (one per line)" value={(record.recommendedLayouts ?? []).join("\n")} onChange={(value) => update("recommendedLayouts", value.split("\n").map((item) => item.trim()).filter(Boolean))} />
          <Select label="Related categories" value={record.relatedCategories ?? []} multiple options={[
            ...categories.map((category) => ({ value: category.slug, label: category.name })),
          ]} onChange={(value) => update("relatedCategories", value)} />
          <ReadOnlyValue label="Book relationships" value="Managed by book products; preserved when editing a collection." />
        </>}
      </div>
      {isCategory ? <div className="admin-detail-grid">
        <ReadOnlyValue label="Product usage" value={`${record.bookCount ?? 0} total · ${record.publishedBookCount ?? 0} published · ${record.draftBookCount ?? 0} draft`} />
        <ReadOnlyValue label="Collection references" value={record.collectionCount ?? 0} />
      </div> : null}
      {!isCategory && !record.categoryId
        ? <p className="admin-inline-error" role="status">This legacy collection has no resolved category. Assign one before using it for a book product.</p>
        : null}
      <Toggle label={isCategory ? "Active in public catalog" : "Published in catalog"} checked={record.isPublished} onChange={(value) => update("isPublished", value)} />
    </>;
  }

  if (section === "templates") {
    return <div className="admin-form-grid">
      <Input label="Template name" required value={record.name} onChange={(value) => update("name", value)} maxLength={160} />
      <Input label="Slug" required value={record.slug} onChange={(value) => update("slug", value)} maxLength={180} />
      <Textarea label="Description" value={record.description} onChange={(value) => update("description", value)} maxLength={5000} />
      <Select label="Category" value={record.categoryId ?? ""} options={[
        { value: "", label: "No category" },
        ...categories.map((category) => ({ value: category.id, label: category.name })),
      ]} onChange={(value) => update("categoryId", value)} />
      <Select label="Book product" value={record.productId ?? ""} options={[
        { value: "", label: "Not linked to a product" },
        ...books.map((book) => ({ value: book.id, label: book.title || book.name })),
      ]} onChange={(value) => update("productId", value)} />
    </div>;
  }

  if (section === "settings") {
    return <>
      <Input label="Setting key" required value={record.key} onChange={(value) => update("key", value)} maxLength={120} />
      {record.key === "paypal_pkr_to_usd_rate"
        ? <p className="admin-form-hint">PayPal PKR to USD rate: set the USD amount for 1 PKR as JSON, for example {"{\"rate\":\"0.0036\"}"}.</p>
        : null}
      <Textarea label="Configuration object (JSON)" rows={8} value={settingValueText} onChange={(value) => {
        setSettingValueText(value);
        try {
          const parsed = JSON.parse(value);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) update("value", parsed);
        } catch { /* Keep the typed value visible until it becomes valid JSON. */ }
      }} />
      {(() => {
        try {
          const parsed = JSON.parse(settingValueText);
          return !parsed || typeof parsed !== "object" || Array.isArray(parsed)
            ? <p className="admin-inline-error" role="alert">Enter a JSON object before saving.</p>
            : null;
        } catch {
          return <p className="admin-inline-error" role="alert">Enter a valid JSON object before saving.</p>;
        }
      })()}
      <Toggle label="Public setting" checked={record.public} onChange={(value) => update("public", value)} />
    </>;
  }

  if (section === "pdf-orders" || section === "print-orders") {
    const options = section === "pdf-orders"
      ? ["cancellation_requested", "cancelled"]
      : PRINT_ORDER_STATUSES;
    return <>
      <div className="admin-detail-grid">
        <ReadOnlyValue label="Order reference" value={record.orderNumber} />
        <ReadOnlyValue label="Customer" value={record.customer
          ? `${record.customer.name || "Name not provided"} · ${record.customer.email || "No email"}`
          : record.userEmail} />
        <ReadOnlyValue label="Payment status" value={record.paymentStatus} />
        <ReadOnlyValue label="Amount" value={record.amount ? `${record.currency || "USD"} ${record.amount}` : null} />
        <ReadOnlyValue label="Placed" value={record.createdAt ? new Date(record.createdAt).toLocaleString() : null} />
        {section === "print-orders" ? <ReadOnlyValue label="Page count" value={record.pageCount} /> : null}
        {section === "print-orders" ? <ReadOnlyValue label="Configuration" value={record.configuration} /> : null}
        {section === "print-orders" ? <ReadOnlyValue label="Price snapshot" value={record.priceSnapshot} /> : null}
        {section === "print-orders" ? <ReadOnlyValue label="Delivery address" value={formatDeliveryAddress(record.deliveryAddress)} /> : null}
      </div>
      <Select label="Order status" value={record.status} options={options.map((status) => ({ value: status, label: labelFor(status) }))} onChange={(value) => update("status", value)} />
      {section === "print-orders" ? <>
        <Input label="Carrier" value={record.carrier} onChange={(value) => update("carrier", value)} maxLength={100} />
        <Input label="Tracking number" value={record.trackingNumber} onChange={(value) => update("trackingNumber", value)} maxLength={160} />
        <Input label="Estimated delivery" type="datetime-local" value={record.estimatedDeliveryAt?.slice(0, 16)} onChange={(value) => update("estimatedDeliveryAt", value ? new Date(value).toISOString() : null)} />
        <section className="admin-order-tracking">
          <h3>Order timeline</h3>
          {orderHistoryLoading ? <p role="status">Loading order timeline…</p>
            : <OrderTimeline items={orderHistory} shipment={record.shipment} />}
        </section>
      </> : null}
    </>;
  }

  if (section === "support") {
    return <>
      <div className="admin-detail-grid">
        <ReadOnlyValue label="Ticket" value={record.ticketNumber} />
        <ReadOnlyValue label="Customer" value={record.userEmail} />
        <ReadOnlyValue label="Subject" value={record.subject} />
        <ReadOnlyValue label="Category" value={record.category} />
      </div>
      <div className="admin-support-messages">{(record.messages ?? []).map((message) => <article key={message.id}>
        <header><strong>{message.internal ? "Internal note" : "Customer message"}</strong><time>{new Date(message.createdAt).toLocaleString()}</time></header>
        <p>{message.body}</p>
      </article>)}</div>
      <Select label="Status" value={record.status} options={SUPPORT_STATUSES.map((value) => ({ value, label: labelFor(value) }))} onChange={(value) => update("status", value)} />
      <Select label="Priority" value={record.priority} options={SUPPORT_PRIORITIES.map((value) => ({ value, label: labelFor(value) }))} onChange={(value) => update("priority", value)} />
      <Textarea label="Reply to customer" value={record.reply} onChange={(value) => update("reply", value)} maxLength={10000} />
      <Textarea label="Internal note" value={record.internalNote} onChange={(value) => update("internalNote", value)} maxLength={10000} />
    </>;
  }

  if (section === "pricing" || section === "shipping") {
    if (record.kind === "variant") {
      return <>
        {record.__create ? <div className="admin-form-grid">
          <Input label="SKU" required value={record.sku} onChange={(value) => update("sku", value)} maxLength={80} />
          <Select label="Book product" value={record.productId} options={[
            { value: "", label: "Select a book" },
            ...books.map((book) => ({ value: book.id, label: `${book.title || book.name} · ${book.currency || "USD"}` })),
          ]} onChange={(value) => update("productId", value)} required />
          <Select label="Size" value={record.sizeId} options={[
            { value: "", label: "Select a size" },
            ...(pricingOptions?.sizes ?? []).filter((size) => size.active).map((size) => ({ value: size.id, label: size.name })),
          ]} onChange={(value) => update("sizeId", value)} required />
          <Select label="Cover type" value={record.coverTypeId} options={[
            { value: "", label: "Select a cover" },
            ...(pricingOptions?.covers ?? []).filter((cover) => cover.active).map((cover) => ({ value: cover.id, label: cover.name })),
          ]} onChange={(value) => update("coverTypeId", value)} required />
          <Select label="Paper type" value={record.paperTypeId} options={[
            { value: "", label: "Select paper" },
            ...(pricingOptions?.papers ?? []).filter((paper) => paper.active).map((paper) => ({ value: paper.id, label: paper.name })),
          ]} onChange={(value) => update("paperTypeId", value)} required />
          <Input label="Printing price" type="number" value={record.basePrice} onChange={(value) => update("basePrice", value)} min="0" step="0.01" required />
          <Input label="Currency" value={record.currency} onChange={(value) => update("currency", value.toUpperCase())} maxLength={3} required />
        </div> : <div className="admin-detail-grid">
          <ReadOnlyValue label="Book" value={record.book} />
          <ReadOnlyValue label="Size" value={record.size} />
          <ReadOnlyValue label="Cover" value={record.cover} />
          <ReadOnlyValue label="Paper" value={record.paper} />
          <Input label="Printing price" type="number" value={record.basePrice} onChange={(value) => update("basePrice", value)} min="0" step="0.01" required />
          <Input label="Currency" value={record.currency} onChange={(value) => update("currency", value.toUpperCase())} maxLength={3} required />
        </div>}
        <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
      </>;
    }
    const activeTiers = (pricingOptions?.tiers ?? []).filter((tier) => tier.active || tier.id === record.tierId);
    if (record.kind === "tier") return <div className="admin-form-grid">
      <Input label="Tier code" required value={record.code} onChange={(value) => update("code", value.toUpperCase())} maxLength={40} pattern="[A-Za-z0-9_-]+" />
      <Input label="Tier name" required value={record.name} onChange={(value) => update("name", value)} maxLength={100} />
      <Textarea label="Description" value={record.description} onChange={(value) => update("description", value)} maxLength={5000} />
      <Input label="Base price" required type="number" min="0" step="0.01" value={record.basePrice} onChange={(value) => update("basePrice", value)} />
      <Input label="Currency" required value={record.currency} maxLength={3} onChange={(value) => update("currency", value.toUpperCase())} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
      <p className="admin-list-message">Tier base price is retained as catalog metadata; print quotes use the selected variant price and applicable page charges.</p>
    </div>;
    if (record.kind === "pagePricing") return <div className="admin-form-grid">
      <Select label="Printing tier" value={record.tierId} required options={[
        { value: "", label: "Select a tier" },
        ...activeTiers.map((tier) => ({ value: tier.id, label: `${tier.name} (${tier.code})${tier.active ? "" : " · inactive"}` })),
      ]} onChange={(value) => update("tierId", value)} />
      <Input label="Minimum pages" required type="number" min="1" step="1" value={record.minimumPages} onChange={(value) => update("minimumPages", value === "" ? "" : Number(value))} />
      <Input label="Maximum pages" required type="number" min="1" step="1" value={record.maximumPages} onChange={(value) => update("maximumPages", value === "" ? "" : Number(value))} />
      <Input label="Price per additional page" required type="number" min="0" step="0.01" value={record.pricePerPage} onChange={(value) => update("pricePerPage", value)} />
    </div>;
    if (record.kind === "shipping") return <div className="admin-form-grid">
      <Input label="Country code" required value={record.countryCode} onChange={(value) => update("countryCode", value.toUpperCase())} maxLength={2} />
      <Input label="Region code (optional)" value={record.regionCode} onChange={(value) => update("regionCode", value)} maxLength={20} />
      <Input label="Service code" required value={record.serviceCode} onChange={(value) => update("serviceCode", value)} maxLength={40} />
      <Input label="Service name" required value={record.serviceName} onChange={(value) => update("serviceName", value)} maxLength={100} />
      <Input label="Shipping price" required type="number" min="0" step="0.01" value={record.price} onChange={(value) => update("price", value)} />
      <Input label="Currency" required value={record.currency} maxLength={3} onChange={(value) => update("currency", value.toUpperCase())} />
      <Input label="Minimum delivery days" type="number" min="1" step="1" value={record.estimatedDaysMin} onChange={(value) => update("estimatedDaysMin", value === "" ? "" : Number(value))} />
      <Input label="Maximum delivery days" type="number" min="1" step="1" value={record.estimatedDaysMax} onChange={(value) => update("estimatedDaysMax", value === "" ? "" : Number(value))} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    if (record.kind === "size") return <div className="admin-form-grid">
      <Input label="Size code" required value={record.code} onChange={(value) => update("code", value)} maxLength={40} />
      <Input label="Size name" required value={record.name} onChange={(value) => update("name", value)} maxLength={100} />
      <Input label="Width (mm)" required type="number" min="0.01" step="0.01" value={record.widthMm} onChange={(value) => update("widthMm", value)} />
      <Input label="Height (mm)" required type="number" min="0.01" step="0.01" value={record.heightMm} onChange={(value) => update("heightMm", value)} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    if (record.kind === "cover") return <div className="admin-form-grid">
      <Input label="Cover type" required value={record.name} onChange={(value) => update("name", value)} maxLength={100} />
      <Textarea label="Description" value={record.description} onChange={(value) => update("description", value)} maxLength={500} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    if (record.kind === "paper") return <div className="admin-form-grid">
      <Input label="Paper type" required value={record.name} onChange={(value) => update("name", value)} maxLength={100} />
      <Textarea label="Description" value={record.description} onChange={(value) => update("description", value)} maxLength={500} />
      <Input label="Weight (gsm)" type="number" min="1" step="1" value={record.weightGsm} onChange={(value) => update("weightGsm", value === "" ? "" : Number(value))} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    if (record.kind === "rule") return <div className="admin-form-grid">
      <Input label="Rule name" required value={record.name} onChange={(value) => update("name", value)} maxLength={160} />
      <Select label="Adjustment type" value={record.adjustmentType ?? record.type} options={[
        { value: "fixed", label: "Fixed amount" },
        { value: "percent", label: "Percentage" },
      ]} onChange={(value) => update("adjustmentType", value)} />
      <Input label="Adjustment amount" required type="number" min="0" step="0.01" value={record.amount} onChange={(value) => update("amount", value)} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    if (record.kind === "discount") return <div className="admin-form-grid">
      <ReadOnlyValue label="Discount code" value={record.code} />
      <Select label="Discount type" value={record.type} options={[
        { value: "fixed", label: "Fixed amount" },
        { value: "percent", label: "Percentage" },
      ]} onChange={(value) => update("type", value)} />
      <Input label="Discount value" required type="number" min="0.01" step="0.01" value={record.value} onChange={(value) => update("value", value)} />
      <Input label="Maximum uses (optional)" type="number" min="1" step="1" value={record.maximumUses} onChange={(value) => update("maximumUses", value === "" ? "" : Number(value))} />
      <ReadOnlyValue label="Uses" value={record.usesCount} />
      <Toggle label="Active" checked={record.active} onChange={(value) => update("active", value)} />
    </div>;
    return null;
  }

  return <div className="admin-detail-grid">
    {Object.entries(record).filter(([key]) => !["id", "password", "passwordHash", "otpSecret", "refreshToken"].includes(key))
      .map(([key, value]) => <ReadOnlyValue key={key} label={labelFor(key)} value={value} />)}
  </div>;
}

export default function AdminRecordEditor({ section, record, setRecord, onSave, onClose, onUpload, saveError, saving, orderHistory = [], orderHistoryLoading = false }) {
  const [uploading, setUploading] = useState(false);
  const [imageUploadError, setImageUploadError] = useState("");
  const [categoryValidationError, setCategoryValidationError] = useState("");
  const [pricingValidationError, setPricingValidationError] = useState("");
  const [settingValueText, setSettingValueText] = useState(() => JSON.stringify(record.value ?? {}, null, 2));
  const [relatedCategories, setRelatedCategories] = useState([]);
  const [relatedBooks, setRelatedBooks] = useState([]);
  const [pricingOptions, setPricingOptions] = useState(null);
  const [optionsError, setOptionsError] = useState("");
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [privatePhotos, setPrivatePhotos] = useState([]);
  const [privatePhotosLoading, setPrivatePhotosLoading] = useState(false);
  const [privatePhotosError, setPrivatePhotosError] = useState("");
  const [printPdfLoading, setPrintPdfLoading] = useState(false);
  const [printPdfError, setPrintPdfError] = useState("");
  const readOnly = ["users", "payments", "refunds", "notifications"].includes(section);
  const title = record.title || record.name || record.email || record.orderNumber || record.ticketNumber || record.code || record.key || "Record details";
  const imageTarget = section === "templates" ? "previewAssetKey" : "heroAssetKey";
  const imageSource = record.image || record.heroImage || "";

  useEffect(() => {
    setUploading(false);
    setImageUploadError("");
    setCategoryValidationError("");
    setPricingValidationError("");
    setPrivatePhotos([]);
    setPrivatePhotosError("");
    setPrintPdfLoading(false);
    setPrintPdfError("");
    setSettingValueText(JSON.stringify(record.value ?? {}, null, 2));
  }, [record.id, record.kind, record.__create, section]);

  useEffect(() => () => privatePhotos.forEach((photo) => URL.revokeObjectURL(photo.src)), [privatePhotos]);

  useEffect(() => {
    let active = true;
    if (!["templates", "collections", "pricing", "shipping"].includes(section)) return undefined;
    setOptionsLoading(true);
    setOptionsError("");
    Promise.all([
      ["templates", "collections"].includes(section)
        ? loadAllAdminCategories().then((items) => ({ items }))
        : Promise.resolve({ items: [] }),
      ["templates", "pricing"].includes(section) || (section === "shipping" && record.kind === "variant")
        ? loadAdminBookReferences() : Promise.resolve([]),
      ["pricing", "shipping"].includes(section) ? loadAdminSection("pricing") : Promise.resolve(null),
    ]).then(([categoryResult, bookResult, pricingResult]) => {
      if (!active) return;
      setRelatedCategories(categoryResult.items ?? []);
      setRelatedBooks(bookResult);
      if (pricingResult) setPricingOptions(pricingResult);
    }).catch((failure) => {
      if (active) setOptionsError(failure instanceof Error ? failure.message : "Category and book options could not be loaded.");
    }).finally(() => {
      if (active) setOptionsLoading(false);
    });
    return () => { active = false; };
  }, [section, record.kind]);

  function update(key, value) {
    setRecord((current) => ({ ...current, [key]: value }));
    if (section === "categories" || section === "collections") setCategoryValidationError("");
    if (section === "pricing" || section === "shipping") setPricingValidationError("");
    if (key === "productId" && record.__create) {
      const product = relatedBooks.find((book) => book.id === value);
      if (product?.currency) setRecord((current) => ({ ...current, currency: product.currency.toUpperCase() }));
    }
  }

  async function uploadImage(file) {
    if (!file) return;
    setUploading(true);
    setImageUploadError("");
    try {
      const asset = await onUpload(file);
      if (!asset) return;
      setRecord((current) => section === "templates"
        ? { ...current, previewAssetKey: asset.assetKey }
        : { ...current, heroAssetKey: asset.assetKey, image: asset.url, heroImage: asset.url });
    } catch (failure) {
      setImageUploadError(failure instanceof Error ? failure.message : "The catalog image could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  async function openPrivatePhotos() {
    setPrivatePhotosLoading(true);
    setPrivatePhotosError("");
    setPrivatePhotos([]);
    try {
      const items = await loadPrivatePrintOrderPhotos(record.id);
      const blobs = await Promise.all(items.map(async (item) => {
        const response = await fetch(apiUrl(item.url), { credentials: "include" });
        if (!response.ok) throw new Error("A private customer photo could not be loaded.");
        return { id: item.id, name: item.name, blob: await response.blob() };
      }));
      setPrivatePhotos(blobs.map(({ blob, ...photo }) => ({ ...photo, src: URL.createObjectURL(blob) })));
    } catch (failure) {
      setPrivatePhotosError(failure instanceof Error ? failure.message : "Private customer photos could not be loaded.");
    } finally {
      setPrivatePhotosLoading(false);
    }
  }

  async function downloadPrintPdf() {
    setPrintPdfLoading(true);
    setPrintPdfError("");
    try {
      const download = await loadAdminPrintOrderPdf(record.id);
      window.location.assign(apiUrl(download.url));
    } catch (failure) {
      setPrintPdfError(failure instanceof Error ? failure.message : "The print PDF could not be downloaded.");
    } finally {
      setPrintPdfLoading(false);
    }
  }

  function changePages(transform) {
    setRecord((current) => ({ ...current, pages: transform(current.pages ?? []) }));
  }

  const templatePages = section === "templates" ? record.pages ?? [] : [];
  return <aside className="admin-editor" aria-label={readOnly ? "Record details" : "Record form"}>
    <div className="admin-editor-head">
      <div><span className="admin-kicker">{record.id ? (readOnly ? "Details" : "Edit record") : "New record"}</span><h2>{record.id ? title : `Create ${section.replace(/s$/, "")}`}</h2></div>
      <button className="admin-icon-button" type="button" aria-label="Close editor" onClick={onClose}>×</button>
    </div>
    {["categories", "collections", "templates"].includes(section) ? <div className="admin-record-image-preview">
      <SafeImage src={imageSource} alt={`${title} preview`} />
      {!readOnly ? <label className="admin-upload-button">{uploading ? "Uploading…" : section === "templates" ? "Upload template preview" : "Upload catalog image"}
        <input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={(event) => { void uploadImage(event.target.files?.[0]); event.target.value = ""; }} />
      </label> : null}
      {record[imageTarget] ? <small>Asset key saved</small> : null}
    </div> : null}
    {section === "templates" && !readOnly ? <div className="admin-template-tools">
      <div className="admin-template-preview">
        {templatePages.map((page, index) => <div className="admin-mini-page" key={`${page.pageNumber}-${index}`} style={{ background: page.background || "#f6f1e9" }}>
          <span>Page {page.pageNumber}</span>
          {(page.elements || []).map((element, elementIndex) => <i key={elementIndex} className={`admin-placeholder admin-placeholder-${element.type}`}
            style={{ left: `${(element.x || 0) * 100}%`, top: `${(element.y || 0) * 100}%`, width: `${(element.width || 0.5) * 100}%`, height: `${(element.height || 0.12) * 100}%` }}>
            {element.type === "text" ? (element.content?.text || "Text placeholder") : element.type === "image" ? "Photo" : "Element"}
          </i>)}
        </div>)}
        {!templatePages.length ? <p>Add a page to begin the template preview.</p> : null}
      </div>
      <div className="admin-template-actions">
        <button type="button" onClick={() => changePages((pages) => [...pages, { pageNumber: pages.length + 1, type: "interior", layout: "single-photo", background: "#F4F0E8", elements: [] }])}><FilePlus2 size={15} /> Add page</button>
        <button type="button" onClick={() => changePages((pages) => pages.map((page, index) => index === pages.length - 1 ? { ...page, layout: "two-photos", elements: [{ type: "image", x: 0.06, y: 0.08, width: 0.42, height: 0.84, content: { placeholder: "Photo one" } }, { type: "image", x: 0.52, y: 0.08, width: 0.42, height: 0.84, content: { placeholder: "Photo two" } }] } : page))}><Plus size={15} /> Apply two-photo layout</button>
        <button type="button" onClick={() => changePages((pages) => pages.map((page, index) => index === pages.length - 1 ? { ...page, elements: [...(page.elements || []), { type: "image", x: 0.12, y: 0.16, width: 0.76, height: 0.64, content: { placeholder: "Photo" } }] } : page))}><Plus size={15} /> Add image placeholder</button>
        <button type="button" onClick={() => changePages((pages) => pages.map((page, index) => index === pages.length - 1 ? { ...page, elements: [...(page.elements || []), { type: "text", x: 0.1, y: 0.82, width: 0.8, height: 0.1, content: { text: "Your story", fontFamily: "Georgia", fontSize: 24 } }] } : page))}><Plus size={15} /> Add text placeholder</button>
        <button type="button" onClick={() => changePages((pages) => pages.map((page, index) => index === pages.length - 1 ? { ...page, background: "#E5E9E0" } : page))}>Set sage page background</button>
      </div>
    </div> : null}
    {section === "print-orders" && record.photosAvailable ? <section className="admin-private-photos">
      <div><strong>Private customer photos</strong><p>Access is logged and limited to this paid order in production.</p></div>
      <button className="admin-button admin-button-secondary" type="button" disabled={privatePhotosLoading} onClick={() => void openPrivatePhotos()}><Eye size={15} />{privatePhotosLoading ? "Loading photos…" : "Review photos"}</button>
      {privatePhotosError ? <p role="alert">{privatePhotosError}</p> : null}
      {privatePhotos.length ? <div className="admin-private-photo-grid">{privatePhotos.map((photo) => <figure key={photo.id}><img src={photo.src} alt={photo.name} /><figcaption>{photo.name}</figcaption></figure>)}</div> : null}
    </section> : null}
    {section === "print-orders" ? <section className="admin-private-photos">
      <div>
        <strong>Print PDF</strong>
        <p>Generation status: {labelFor(record.printPdf?.print?.status || "not started")}</p>
        {record.printPdf?.print?.error?.message ? <p role="alert">{record.printPdf.print.error.message}</p> : null}
      </div>
      <button className="admin-button admin-button-secondary" type="button"
        disabled={printPdfLoading || record.printPdf?.print?.status !== "completed"}
        onClick={() => void downloadPrintPdf()}>
        {printPdfLoading ? "Preparing download…" : "Download print PDF"}
      </button>
      {printPdfError ? <p role="alert">{printPdfError}</p> : null}
    </section> : null}
    <FormFields section={section} record={record} update={update} categories={relatedCategories} books={relatedBooks} pricingOptions={pricingOptions}
      settingValueText={settingValueText} setSettingValueText={setSettingValueText} />
    {optionsLoading && (section === "pricing" || section === "shipping")
      ? <p className="admin-list-message" role="status">Loading pricing options…</p>
      : null}
    {optionsError ? <p className="admin-inline-error" role="alert"><AlertCircle size={15} /> {optionsError}</p> : null}
    {imageUploadError ? <p className="admin-inline-error" role="alert"><AlertCircle size={15} /> {imageUploadError}</p> : null}
    {categoryValidationError ? <p className="admin-inline-error" role="alert"><AlertCircle size={15} /> {categoryValidationError}</p> : null}
    {pricingValidationError ? <p className="admin-inline-error" role="alert"><AlertCircle size={15} /> {pricingValidationError}</p> : null}
    {saveError ? <p className="admin-inline-error" role="alert"><AlertCircle size={15} /> {saveError}</p> : null}
    <div className="admin-editor-actions">
      <button className="admin-button admin-button-quiet" type="button" onClick={onClose}>Close</button>
      {!readOnly ? <button className="admin-button admin-button-primary" type="button" disabled={saving || uploading
        || (section === "collections" && (optionsLoading || Boolean(optionsError)))
        || (["pricing", "shipping"].includes(section) && (optionsLoading || Boolean(optionsError) || !pricingOptions))
        || (section === "settings" && (() => {
        try { const parsed = JSON.parse(settingValueText); return !parsed || typeof parsed !== "object" || Array.isArray(parsed); }
        catch { return true; }
      })())}
        onClick={() => {
          if (section === "categories") {
            const validationError = validateCategoryRecord(record);
            if (validationError) {
              setCategoryValidationError(validationError);
              return;
            }
            return onSave(categoryFormPayload(record));
          }
          if (section === "collections" && !record.categoryId) {
            setCategoryValidationError("Choose a category for this collection before saving.");
            return;
          }
          if (section === "pricing" || section === "shipping") {
            if (["tier", "pagePricing", "shipping", "size", "cover", "paper", "variant", "rule", "discount"].includes(record.kind)) {
              const errors = validatePricingRecord(record.kind, record);
              if (Object.keys(errors).length) {
                setPricingValidationError(Object.entries(errors)
                  .map(([field, message]) => `${labelFor(field)}: ${message}`)
                  .join(" "));
                return;
              }
            }
            return onSave(record);
          }
          if (section !== "settings") return onSave(record);
          try {
            const value = JSON.parse(settingValueText);
            if (value && typeof value === "object" && !Array.isArray(value)) onSave({ ...record, value });
          } catch { return; }
        }}><Save size={15} /> {saving ? "Saving…" : "Save changes"}</button> : null}
    </div>
  </aside>;
}
