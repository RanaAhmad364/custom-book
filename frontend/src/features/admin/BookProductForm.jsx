import { useEffect, useMemo, useState } from "react";
import { AlertCircle, ImagePlus, LoaderCircle, Save } from "lucide-react";
import { SafeImage } from "../../components/common/SafeImage.jsx";
import { loadAdminSection } from "./adminService.js";
import { bookFormValues, buildBookPayload, collectionsForCategory, validateBookForm } from "./bookProductForm.js";

function errorMessage(failure) {
  return failure instanceof Error ? failure.message : "The catalog options could not be loaded.";
}

async function loadAllItems(section) {
  const perPage = 100;
  const first = await loadAdminSection(section, "", { page: 1, perPage });
  if (!Array.isArray(first.items)) throw new Error(`The ${section} service returned an invalid list.`);
  const totalPages = first.pagination?.totalPages;
  if (!Number.isInteger(totalPages) || totalPages < 1) return first.items;
  const remaining = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) =>
      loadAdminSection(section, "", { page: index + 2, perPage })),
  );
  for (const page of remaining) {
    if (!Array.isArray(page.items)) throw new Error(`The ${section} service returned an invalid list.`);
  }
  return [...first.items, ...remaining.flatMap((page) => page.items)];
}

function Field({ label, name, value, onChange, error, type = "text", ...props }) {
  const id = `book-product-${name}`;
  return <label className="book-form-field" htmlFor={id}>
    <span>{label}</span>
    <input id={id} name={name} type={type} value={value} onChange={onChange}
      aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} {...props} />
    {error ? <small className="book-form-field-error" id={`${id}-error`}>{error}</small> : null}
  </label>;
}

function SelectField({ label, name, value, onChange, error, children, ...props }) {
  const id = `book-product-${name}`;
  return <label className="book-form-field" htmlFor={id}>
    <span>{label}</span>
    <select id={id} name={name} value={value} onChange={onChange}
      aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} {...props}>
      {children}
    </select>
    {error ? <small className="book-form-field-error" id={`${id}-error`}>{error}</small> : null}
  </label>;
}

function MultiSelectField({ label, name, options, selected, onChange, loading, emptyLabel, error }) {
  const id = `book-product-${name}`;
  return <label className="book-form-field" htmlFor={id}>
    <span>{label}</span>
    {loading ? <small className="book-form-help">Loading pricing options…</small> : null}
    {!loading && options.length === 0 ? <small className="book-form-help">{emptyLabel}</small> : null}
    <select id={id} name={name} multiple value={selected} onChange={(event) => {
      onChange([...event.target.selectedOptions].map((option) => option.value));
    }} disabled={loading || options.length === 0} aria-invalid={Boolean(error)}>
      {options.map((option) => <option key={option.id} value={option.id}
        disabled={option.active === false && !selected.includes(option.id)}>{option.name}{option.active === false ? " (inactive)" : ""}</option>)}
    </select>
    {error ? <small className="book-form-field-error">{error}</small> : null}
    {options.length ? <small className="book-form-help">Use Ctrl or Command to select multiple options.</small> : null}
  </label>;
}

export default function BookProductForm({
  record,
  onUpload,
  onSave,
  onDesignBook,
  onCreateVariant,
  onClose,
  onDirtyChange,
  saveError,
  saving,
}) {
  const initialValues = useMemo(() => bookFormValues(record), [record]);
  const [values, setValues] = useState(initialValues);
  const [initialPayload, setInitialPayload] = useState(() => JSON.stringify(buildBookPayload(initialValues)));
  const [categories, setCategories] = useState([]);
  const [collections, setCollections] = useState([]);
  const [pricing, setPricing] = useState({ sizes: [], covers: [], papers: [], tiers: [], variants: [], currency: "PKR" });
  const [variantDraft, setVariantDraft] = useState({ sizeId: "", coverTypeId: "", paperTypeId: "", sku: "", basePrice: "" });
  const [variantSaving, setVariantSaving] = useState(false);
  const [variantError, setVariantError] = useState("");
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [uploading, setUploading] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [coverPreviewUrl, setCoverPreviewUrl] = useState(record.image || "");
  const [newGalleryPreviews, setNewGalleryPreviews] = useState([]);
  const availableCollections = useMemo(
    () => collectionsForCategory(collections, values.categoryId),
    [collections, values.categoryId],
  );
  const availableCategories = categories.filter((category) => category.isPublished !== false);
  const selectedCategory = categories.find((category) => category.id === values.categoryId);
  const selectedCollection = collections.find((collection) => collection.id === values.collectionId);
  const isDirty = JSON.stringify(buildBookPayload(values)) !== initialPayload;

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    let active = true;
    setOptionsLoading(true);
    setOptionsError("");
    Promise.all([
      loadAllItems("categories"),
      loadAllItems("collections"),
      loadAdminSection("pricing"),
    ]).then(([nextCategories, nextCollections, nextPricing]) => {
      if (!active) return;
      if (!Array.isArray(nextPricing.sizes) || !Array.isArray(nextPricing.covers) ||
          !Array.isArray(nextPricing.papers) || !Array.isArray(nextPricing.tiers) ||
          !Array.isArray(nextPricing.variants) || !/^[A-Z]{3}$/.test(nextPricing.currency ?? "")) {
        throw new Error("The pricing service returned invalid book configuration options.");
      }
      setCategories(nextCategories);
      setCollections(nextCollections);
      setPricing({
        sizes: nextPricing.sizes,
        covers: nextPricing.covers,
        papers: nextPricing.papers,
        tiers: nextPricing.tiers,
        variants: nextPricing.variants.filter((variant) => variant.productId === record.id),
        currency: nextPricing.currency,
      });
      if (!record.id && typeof nextPricing.currency === "string") {
        setValues((current) => ({ ...current, currency: nextPricing.currency }));
        setInitialPayload(JSON.stringify(buildBookPayload({ ...initialValues, currency: nextPricing.currency })));
      }
    }).catch((failure) => {
      if (active) setOptionsError(errorMessage(failure));
    }).finally(() => {
      if (active) setOptionsLoading(false);
    });
    return () => { active = false; };
  }, [record.id]);

  function updateField(name, value) {
    setValues((current) => ({
      ...current,
      [name]: value,
      ...(name === "categoryId" && current.collectionId
        && collections.find((collection) => collection.id === current.collectionId)?.categoryId !== value
        ? { collectionId: "" }
        : {}),
    }));
    setFieldErrors((current) => ({ ...current, [name]: undefined }));
  }

  function updateMetadata(name, value) {
    setValues((current) => ({
      ...current,
      adminMetadata: { ...current.adminMetadata, [name]: value },
    }));
    setFieldErrors((current) => ({ ...current, [name]: undefined }));
  }

  function updateDimension(name, value) {
    setValues((current) => ({
      ...current,
      adminMetadata: {
        ...current.adminMetadata,
        dimensions: { ...current.adminMetadata.dimensions, [name]: value },
      },
    }));
    setFieldErrors((current) => ({ ...current, [name]: undefined }));
  }

  async function uploadImage(file, target) {
    if (!file) return;
    if (target === "gallery" && values.adminMetadata.previewImageKeys.length >= 12) {
      setUploadError("A book can have at most 12 gallery preview images.");
      return;
    }
    setUploading(target);
    setUploadError("");
    try {
      const asset = await onUpload(file);
      if (!asset?.assetKey || !asset?.url) {
        setUploadError("The upload did not return a storage key and preview URL.");
        return;
      }
      if (target === "cover") {
        updateField("coverAssetKey", asset.assetKey);
        setCoverPreviewUrl(asset.url);
      } else {
        const existing = values.adminMetadata.previewImageKeys;
        updateMetadata("previewImageKeys", [...existing, asset.assetKey]);
        setNewGalleryPreviews((current) => [...current, { assetKey: asset.assetKey, url: asset.url }]);
      }
    } catch (failure) {
      setUploadError(errorMessage(failure));
    } finally {
      setUploading("");
    }
  }

  function closeForm() {
    if (isDirty && !window.confirm("Discard your unsaved book changes? Uploaded images may remain in storage.")) return;
    onClose();
  }

  async function submit(event, designAfterSave = false) {
    event.preventDefault();
    const errors = validateBookForm(values);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    await onSave(buildBookPayload(values), { designAfterSave });
  }

  async function submitVariant(event) {
    event.preventDefault();
    setVariantError("");
    if (!record.id) {
      setVariantError("Save the product before adding a variant.");
      return;
    }
    if (!variantDraft.sizeId || !variantDraft.coverTypeId || !variantDraft.paperTypeId ||
        !variantDraft.sku.trim() || !/^\d+(?:\.\d{1,2})?$/.test(variantDraft.basePrice.trim())) {
      setVariantError("Choose active options, enter a unique SKU, and provide a valid nonnegative price.");
      return;
    }
    setVariantSaving(true);
    try {
      const result = await onCreateVariant({
        productId: record.id,
        sizeId: variantDraft.sizeId,
        coverTypeId: variantDraft.coverTypeId,
        paperTypeId: variantDraft.paperTypeId,
        sku: variantDraft.sku.trim(),
        basePrice: variantDraft.basePrice.trim(),
        currency: values.currency,
      });
      const variant = result?.variant || result;
      if (!variant?.id) throw new Error("The pricing service did not return the created variant.");
      setPricing((current) => ({ ...current, variants: [...current.variants, variant] }));
      setVariantDraft({ sizeId: "", coverTypeId: "", paperTypeId: "", sku: "", basePrice: "" });
    } catch (failure) {
      setVariantError(errorMessage(failure));
    } finally {
      setVariantSaving(false);
    }
  }

  const status = record.isPublished ? "Published" : "Draft";
  return <aside className="admin-editor book-product-editor" aria-label="Book product editor">
    <div className="admin-editor-head">
      <div>
        <span className="admin-kicker">{record.id ? "Edit product" : "New product"}</span>
        <h2>{record.title || "Create a book product"}</h2>
      </div>
      <button className="admin-icon-button" type="button" aria-label="Close editor" onClick={closeForm}>×</button>
    </div>

    <div className={`book-form-status${record.isPublished ? " is-published" : ""}`} role="status">
      <span /> {status}{record.isPublished ? " · visible in the public catalog" : " · not visible in the public catalog"}
    </div>
    {record.id ? <div className="book-form-status" role="status">
      <span /> Master design: {(record.masterDesignStatus || "not_started").replaceAll("_", " ")}
      {record.masterDesignVersion ? ` · version ${record.masterDesignVersion}` : ""}
      {record.publishedDesignVersion ? ` · published v${record.publishedDesignVersion}` : ""}
    </div> : null}
    <div className="admin-book-preview">
      <div className="admin-book-preview-image"><SafeImage src={coverPreviewUrl} alt={`${values.title || "Book"} cover preview`} /></div>
      <div>
        <span className="admin-kicker">Product preview</span>
        <h3>{values.title || "Untitled book"}</h3>
        <p>{values.description || "Add a description to preview the public book card."}</p>
        <small>{values.bookType || "BASIC"} · {values.pageCountMin || 24} pages · From {values.currency || "USD"} {values.startingPrice || "0.00"}</small>
      </div>
    </div>

    {optionsError ? <div className="admin-inline-error" role="alert"><AlertCircle size={15} />{optionsError}</div> : null}
    {saveError ? <div className="admin-inline-error" role="alert"><AlertCircle size={15} />{saveError}</div> : null}
    {uploadError ? <div className="admin-inline-error" role="alert"><AlertCircle size={15} />{uploadError}</div> : null}

    <form className="book-product-form" noValidate onSubmit={(event) => submit(event)}>
      <section className="book-form-section">
        <div className="book-form-section-heading"><span>01</span><div><h3>Basic information</h3><p>Give this book a clear title and description.</p></div></div>
        <Field label="Book title" name="title" value={values.title} onChange={(event) => updateField("title", event.target.value)}
          error={fieldErrors.title} maxLength={200} required />
        <Field label="URL slug" name="slug" value={values.slug} onChange={(event) => updateField("slug", event.target.value)}
          error={fieldErrors.slug} maxLength={220} required />
        <label className="book-form-field" htmlFor="book-product-description">
          <span>Description</span>
          <textarea id="book-product-description" value={values.description} maxLength={10000} required
            aria-invalid={Boolean(fieldErrors.description)}
            onChange={(event) => updateField("description", event.target.value)} />
          {fieldErrors.description ? <small className="book-form-field-error">{fieldErrors.description}</small> : null}
        </label>
      </section>

      <section className="book-form-section">
        <div className="book-form-section-heading"><span>02</span><div><h3>Classification</h3><p>Choose the catalog category and collection for this product.</p></div></div>
        <div className="book-form-grid">
          <SelectField label="Category" name="categoryId" value={values.categoryId}
            onChange={(event) => updateField("categoryId", event.target.value)} error={fieldErrors.categoryId}
            disabled={optionsLoading || Boolean(optionsError)} required>
            <option value="">{optionsLoading ? "Loading categories…" : availableCategories.length ? "Choose a category" : "No active categories available"}</option>
            {selectedCategory && selectedCategory.isPublished === false
              ? <option value={selectedCategory.id} disabled>{selectedCategory.name} (inactive)</option> : null}
            {availableCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </SelectField>
          <SelectField label="Collection" name="collectionId" value={values.collectionId}
            onChange={(event) => updateField("collectionId", event.target.value)}
            disabled={optionsLoading || Boolean(optionsError)}>
            <option value="">{optionsLoading ? "Loading collections…" : "No collection"}</option>
            {selectedCollection && !availableCollections.some((collection) => collection.id === selectedCollection.id)
              ? <option value={selectedCollection.id} disabled>
                {selectedCollection.name} ({!selectedCollection.categoryId
                  ? "category unresolved"
                  : selectedCollection.categoryId !== values.categoryId
                    ? "category mismatch"
                    : "inactive"} - select another option)
              </option> : null}
            {availableCollections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
          </SelectField>
          <Field label="Style" name="style" value={values.style} onChange={(event) => updateField("style", event.target.value)} maxLength={60} />
          <Field label="Occasion" name="occasion" value={values.occasion} onChange={(event) => updateField("occasion", event.target.value)} maxLength={60} />
        </div>
        {!optionsLoading && !optionsError && availableCategories.length === 0
          ? <small className="book-form-help">Create or activate a category before saving a book product.</small> : null}
        {!optionsLoading && !optionsError && values.categoryId && availableCollections.length === 0
          ? <small className="book-form-help">No collections are assigned to this category.</small> : null}
      </section>

      <section className="book-form-section">
        <div className="book-form-section-heading"><span>03</span><div><h3>Book configuration</h3><p>Set format, page ranges, and available print options.</p></div></div>
        <div className="book-form-grid">
          <SelectField label="Book type" name="bookType" value={values.bookType} onChange={(event) => updateField("bookType", event.target.value)}>
            {["LIGHT", "BASIC", "PREMIUM"].map((type) => <option key={type} value={type}>{type}</option>)}
            {!["LIGHT", "BASIC", "PREMIUM"].includes(values.bookType)
              ? <option value={values.bookType}>{values.bookType}</option> : null}
          </SelectField>
          <Field label="Minimum pages" name="pageCountMin" type="number" min="1" step="1" value={values.pageCountMin}
            onChange={(event) => updateField("pageCountMin", event.target.value)} error={fieldErrors.pageCountMin} required />
          <Field label="Maximum pages" name="pageCountMax" type="number" min="1" step="1" value={values.pageCountMax}
            onChange={(event) => updateField("pageCountMax", event.target.value)} error={fieldErrors.pageCountMax} required />
          <Field label="Page-count options" name="pageCountOptions" value={values.adminMetadata.pageCountOptions.join(", ")}
            onChange={(event) => updateMetadata("pageCountOptions", event.target.value.split(",").map((value) => value.trim()).filter(Boolean).map(Number))}
            error={fieldErrors.pageCountOptions} />
          <Field label="Width (mm)" name="widthMm" type="number" min="0.01" step="0.01"
            value={values.adminMetadata.dimensions.widthMm} onChange={(event) => updateDimension("widthMm", event.target.value)}
            error={fieldErrors.widthMm} />
          <Field label="Height (mm)" name="heightMm" type="number" min="0.01" step="0.01"
            value={values.adminMetadata.dimensions.heightMm} onChange={(event) => updateDimension("heightMm", event.target.value)}
            error={fieldErrors.heightMm} />
        </div>
        <div className="book-form-grid book-form-pricing-options">
          <MultiSelectField label="Book sizes" name="sizeOptions" options={pricing.sizes}
            selected={values.adminMetadata.sizeOptions} loading={optionsLoading}
            error={fieldErrors.sizeOptions}
            emptyLabel="No book sizes are configured in Pricing."
            onChange={(selected) => updateMetadata("sizeOptions", selected)} />
          <MultiSelectField label="Cover types" name="coverOptions" options={pricing.covers}
            selected={values.adminMetadata.coverOptions} loading={optionsLoading}
            error={fieldErrors.coverOptions}
            emptyLabel="No cover types are configured in Pricing."
            onChange={(selected) => updateMetadata("coverOptions", selected)} />
          <MultiSelectField label="Paper types" name="paperOptions" options={pricing.papers}
            selected={values.adminMetadata.paperOptions} loading={optionsLoading}
            error={fieldErrors.paperOptions}
            emptyLabel="No paper types are configured in Pricing."
            onChange={(selected) => updateMetadata("paperOptions", selected)} />
        </div>
        <div className="book-form-tier-options">
          <span>Printing tiers</span>
          {pricing.tiers.length ? <div>{pricing.tiers.map((tier) => <label key={tier.code}>
            <input type="checkbox" checked={values.adminMetadata.printingTiers.includes(tier.code)}
              disabled={!tier.active && !values.adminMetadata.printingTiers.includes(tier.code)}
              onChange={(event) => updateMetadata("printingTiers", event.target.checked
                ? [...values.adminMetadata.printingTiers, tier.code]
                : values.adminMetadata.printingTiers.filter((item) => item !== tier.code))} />
            {tier.name}{tier.active ? "" : " (inactive)"}
          </label>)}</div> : <small className="book-form-help">No printing tiers are configured in Pricing.</small>}
        </div>
      </section>

      {record.id ? <section className="book-form-section">
        <div className="book-form-section-heading"><span>04</span><div><h3>Product variants</h3><p>Manage the product's size, cover, paper, and currency-specific options.</p></div></div>
        {pricing.variants.length ? <ul className="book-variant-list">{pricing.variants.map((variant) => <li key={variant.id}>
          <strong>{variant.sku}</strong><span>{variant.size} · {variant.cover} · {variant.paper}</span>
          <span>{variant.currency} {variant.basePrice}{variant.active ? "" : " · inactive"}</span>
        </li>)}</ul> : <p className="book-form-help">No variants are linked to this product yet.</p>}
        {variantError ? <div className="admin-inline-error" role="alert"><AlertCircle size={15} />{variantError}</div> : null}
        <form className="book-form-grid" onSubmit={(event) => { void submitVariant(event); }}>
          <SelectField label="Size" name="variant-size" value={variantDraft.sizeId} onChange={(event) => setVariantDraft((current) => ({ ...current, sizeId: event.target.value }))} required>
            <option value="">Choose size</option>{pricing.sizes.filter((option) => option.active).map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </SelectField>
          <SelectField label="Cover" name="variant-cover" value={variantDraft.coverTypeId} onChange={(event) => setVariantDraft((current) => ({ ...current, coverTypeId: event.target.value }))} required>
            <option value="">Choose cover</option>{pricing.covers.filter((option) => option.active).map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </SelectField>
          <SelectField label="Paper" name="variant-paper" value={variantDraft.paperTypeId} onChange={(event) => setVariantDraft((current) => ({ ...current, paperTypeId: event.target.value }))} required>
            <option value="">Choose paper</option>{pricing.papers.filter((option) => option.active).map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </SelectField>
          <Field label="SKU" name="variant-sku" value={variantDraft.sku} onChange={(event) => setVariantDraft((current) => ({ ...current, sku: event.target.value }))} maxLength={80} required />
          <Field label={`Variant price (${values.currency})`} name="variant-price" type="number" min="0" step="0.01" value={variantDraft.basePrice}
            onChange={(event) => setVariantDraft((current) => ({ ...current, basePrice: event.target.value }))} required />
          <button className="admin-button admin-button-primary" type="submit" disabled={variantSaving || saving || optionsLoading}>
            {variantSaving ? <LoaderCircle size={15} className="admin-spin" /> : null} Add variant
          </button>
        </form>
      </section> : null}

      <section className="book-form-section">
        <div className="book-form-section-heading"><span>05</span><div><h3>Pricing</h3><p>Prices use the currency code saved with the product.</p></div></div>
        <div className="book-form-grid">
          <Field label="Currency code" name="currency" value={values.currency} disabled
            onChange={() => {}} error={fieldErrors.currency} maxLength={3} required />
          <Field label="Starting price" name="startingPrice" type="number" min="0" step="0.01" value={values.startingPrice}
            onChange={(event) => updateField("startingPrice", event.target.value)} error={fieldErrors.startingPrice} required />
          <Field label="PDF price" name="pdfPrice" type="number" min="0" step="0.01"
            value={values.adminMetadata.pdfPrice} onChange={(event) => updateMetadata("pdfPrice", event.target.value)}
            error={fieldErrors.pdfPrice} />
          <Field label="Printing price" name="printingPrice" type="number" min="0" step="0.01"
            value={values.adminMetadata.printingPrice} onChange={(event) => updateMetadata("printingPrice", event.target.value)}
            error={fieldErrors.printingPrice} />
          <Field label="Base page count" name="basePageCount" type="number" min={values.pageCountMin} max={values.pageCountMax} step="1"
            value={values.adminMetadata.basePageCount} onChange={(event) => updateMetadata("basePageCount", event.target.value)}
            error={fieldErrors.basePageCount} />
          <Field label="Price per extra page" name="extraPagePrice" type="number" min="0" step="0.01"
            value={values.adminMetadata.extraPagePrice} onChange={(event) => updateMetadata("extraPagePrice", event.target.value)}
            error={fieldErrors.extraPagePrice} />
          <Field label="Production estimate (days)" name="productionDays" type="number" min="1" step="1"
            value={values.adminMetadata.productionDays} onChange={(event) => updateMetadata("productionDays", event.target.value)}
            error={fieldErrors.productionDays} />
        </div>
        <label className="book-form-checkbox">
          <input type="checkbox" checked={values.adminMetadata.evenPageCountRequired}
            onChange={(event) => updateMetadata("evenPageCountRequired", event.target.checked)} />
          Require even page counts for print orders
        </label>
        {fieldErrors.evenPageCountRequired ? <small className="book-form-field-error">{fieldErrors.evenPageCountRequired}</small> : null}
      </section>

      <section className="book-form-section">
        <div className="book-form-section-heading"><span>06</span><div><h3>Images</h3><p>Upload image files; saved records retain storage keys, not temporary preview links.</p></div></div>
        <div className="book-form-image-grid">
          <div className="book-form-image-card">
            <span>Cover image</span>
            <div className="book-form-cover-preview">
              {coverPreviewUrl ? <SafeImage src={coverPreviewUrl} alt={`${values.title || "Book"} cover preview`} />
                : <span className="book-form-empty-image"><ImagePlus size={22} />No cover uploaded</span>}
            </div>
            <label className="admin-upload-button">
              {uploading === "cover" ? <><LoaderCircle size={14} className="admin-spin" /> Uploading…</> : "Upload cover"}
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={Boolean(uploading) || saving}
                onChange={(event) => { void uploadImage(event.target.files?.[0], "cover"); event.target.value = ""; }} />
            </label>
            {values.coverAssetKey ? <small className="book-form-help">Saved asset key: {values.coverAssetKey}</small> : null}
          </div>
          <div className="book-form-image-card">
            <span>Gallery and preview images</span>
            <label className="admin-upload-button">
              {uploading === "gallery" ? <><LoaderCircle size={14} className="admin-spin" /> Uploading…</> : "Add preview image"}
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={Boolean(uploading) || saving}
                onChange={(event) => { void uploadImage(event.target.files?.[0], "gallery"); event.target.value = ""; }} />
            </label>
            <div className="book-form-gallery-preview" aria-label="Book gallery previews">
              {newGalleryPreviews.map((preview, index) => <figure key={`${preview.assetKey}-${index}`}>
                <SafeImage src={preview.url} alt={`New gallery preview ${index + 1}`} />
                <figcaption>New preview</figcaption>
              </figure>)}
              {values.adminMetadata.previewImageKeys.filter((key) => !newGalleryPreviews.some((preview) => preview.assetKey === key)).map((key) => <div className="book-form-saved-image" key={key}>
                <ImagePlus size={18} /><span>Saved image · preview URL unavailable</span>
              </div>)}
              {!values.adminMetadata.previewImageKeys.length && newGalleryPreviews.length === 0
                ? <small className="book-form-help">No preview images added yet.</small> : null}
            </div>
            {fieldErrors.previewImageKeys ? <small className="book-form-field-error">{fieldErrors.previewImageKeys}</small> : null}
          </div>
        </div>
      </section>

      <section className="book-form-section book-form-publication">
        <div className="book-form-section-heading"><span>06</span><div><h3>Publishing</h3><p>New products are saved as drafts. Publish after the product details are ready.</p></div></div>
        <label className="book-form-checkbox"><input type="checkbox" checked={values.featured}
          onChange={(event) => updateField("featured", event.target.checked)} /> Feature this book in the catalog</label>
      </section>

      <div className="book-form-actions">
        <button className="admin-button admin-button-quiet" type="button" onClick={closeForm} disabled={saving || Boolean(uploading)}>Cancel</button>
        {record.id ? <button className="admin-button admin-button-quiet" type="button" onClick={onDesignBook}
          disabled={saving || Boolean(uploading) || isDirty}>Design Book</button> : null}
        <button className="admin-button admin-button-primary" type="submit" disabled={saving || Boolean(uploading) || optionsLoading || Boolean(optionsError) || categories.length === 0}>
          {saving ? <LoaderCircle size={15} className="admin-spin" /> : <Save size={15} />}
          {record.id ? "Save changes" : "Save draft"}
        </button>
        {!record.isPublished ? <button className="admin-button admin-button-publish" type="button"
          disabled={saving || Boolean(uploading) || optionsLoading || Boolean(optionsError) || categories.length === 0}
          onClick={(event) => submit(event, true)}>
          {saving ? <LoaderCircle size={15} className="admin-spin" /> : null} Save and open designer
        </button> : null}
      </div>
      {saving ? <p className="book-form-help" role="status">Saving product…</p> : null}
    </form>
  </aside>;
}
