import { useEffect, useRef } from "react";
import { ArrowRight, X } from "lucide-react";

export function setDiscoveryParam(setSearchParams, searchParams, key, value) {
  const nextParams = new URLSearchParams(searchParams);
  if (value) nextParams.set(key, value);
  else nextParams.delete(key);
  if (key !== "page") nextParams.delete("page");
  setSearchParams(nextParams, { replace: true });
}

function FilterSelect({ id, label, value, options, onChange }) {
  return (
    <label className="discovery-filter-field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Any {label.toLowerCase()}</option>
        {options.map((option) => (
          <option
            key={typeof option === "string" ? option : option.value}
            value={typeof option === "string" ? option : option.value}
          >
            {typeof option === "string" ? option : option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function DiscoveryFilterFields({
  prefix,
  searchParams,
  updateParam,
  options,
  lockedCategory,
}) {
  return (
    <div className="discovery-filter-fields">
      {!lockedCategory ? (
        <FilterSelect
          id={`${prefix}-category`}
          label="Category"
          value={searchParams.get("category") ?? ""}
          options={options.categories ?? []}
          onChange={(value) => updateParam("category", value)}
        />
      ) : null}
      <FilterSelect
        id={`${prefix}-occasion`}
        label="Occasion"
        value={searchParams.get("occasion") ?? ""}
        options={options.occasions ?? []}
        onChange={(value) => updateParam("occasion", value)}
      />
      <FilterSelect
        id={`${prefix}-style`}
        label="Style"
        value={searchParams.get("style") ?? ""}
        options={options.styles ?? []}
        onChange={(value) => updateParam("style", value)}
      />
      <FilterSelect
        id={`${prefix}-page-count`}
        label="Page count"
        value={searchParams.get("pageCount") ?? ""}
        options={(options.pageCounts ?? []).map((range) =>
          ({
            value: range,
            label: range === "49+" ? "49+ pages" : `${range.replace("-", "–")} pages`,
          }),
        )}
        onChange={(value) => updateParam("pageCount", value)}
      />
      <FilterSelect
        id={`${prefix}-book-type`}
        label="Book type"
        value={searchParams.get("bookType") ?? ""}
        options={options.bookTypes ?? []}
        onChange={(value) => updateParam("bookType", value)}
      />
      <fieldset className="discovery-price-field">
        <legend>Starting price</legend>
        <label htmlFor={`${prefix}-min-price`}>
          <span className="sr-only">Minimum price</span>
          <span aria-hidden="true">$</span>
          <input
            id={`${prefix}-min-price`}
            type="number"
            min="0"
            step="1"
            inputMode="decimal"
            placeholder="Min"
            value={searchParams.get("minPrice") ?? ""}
            onChange={(event) => updateParam("minPrice", event.target.value)}
          />
        </label>
        <span aria-hidden="true">to</span>
        <label htmlFor={`${prefix}-max-price`}>
          <span className="sr-only">Maximum price</span>
          <span aria-hidden="true">$</span>
          <input
            id={`${prefix}-max-price`}
            type="number"
            min="0"
            step="1"
            inputMode="decimal"
            placeholder="Max"
            value={searchParams.get("maxPrice") ?? ""}
            onChange={(event) => updateParam("maxPrice", event.target.value)}
          />
        </label>
      </fieldset>
    </div>
  );
}

export function MobileFilterDrawer({
  open,
  onClose,
  searchParams,
  updateParam,
  options,
  lockedCategory,
  onClear,
}) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
    const handleClose = () => closeRef.current();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="discovery-filter-dialog"
      aria-label="Book filters"
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <div className="filter-drawer-head">
        <div>
          <span className="eyebrow">Refine the selection</span>
          <h2>Filters</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Close filters"
          onClick={() => dialogRef.current?.close()}
        >
          <X size={20} />
        </button>
      </div>
      <DiscoveryFilterFields
        prefix="mobile"
        searchParams={searchParams}
        updateParam={updateParam}
        options={options}
        lockedCategory={lockedCategory}
      />
      <div className="filter-drawer-actions">
        <button className="button button-outline" type="button" onClick={onClear}>
          Clear all
        </button>
        <button
          className="button button-dark"
          type="button"
          onClick={() => dialogRef.current?.close()}
        >
          Show books <ArrowRight size={15} />
        </button>
      </div>
    </dialog>
  );
}

export function FilterSidebar({ searchParams, updateParam, options, lockedCategory, onClear }) {
  return (
<aside className="discovery-sidebar" aria-label="Filter books">
          <div className="discovery-sidebar-heading">
            <span className="eyebrow">Narrow your search</span>
            <button type="button" onClick={onClear}>Clear</button>
          </div>
          <DiscoveryFilterFields
            prefix="desktop"
            searchParams={searchParams}
            updateParam={updateParam}
            options={options}
            lockedCategory={lockedCategory}
          />
        </aside>
  );
}
