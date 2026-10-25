import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ChevronLeft, ChevronRight, Search, SlidersHorizontal, X,
} from "lucide-react";
import { catalogService } from "../../../services/catalog.js";
import { FilterSidebar, MobileFilterDrawer, setDiscoveryParam } from "./FilterSidebar.jsx";
import { BookGrid } from "../../../components/book/BookGrid.jsx";
import { BookPreviewDialog } from "../../../components/book/BookPreviewDialog.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

  return (
    <nav className="discovery-pagination" aria-label="Book pages">
      <button
        type="button"
        aria-label="Previous page"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft size={17} />
      </button>
      {pages.map((pageNumber) => (
        <button
          key={pageNumber}
          type="button"
          aria-current={pageNumber === page ? "page" : undefined}
          onClick={() => onPageChange(pageNumber)}
        >
          {pageNumber}
        </button>
      ))}
      <button
        type="button"
        aria-label="Next page"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight size={17} />
      </button>
    </nav>
  );
}

export function BookDiscovery({
  lockedCategory = "",
  collection = "",
  listTitle = "Explore books",
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [previewBook, setPreviewBook] = useState(null);
  const navigate = useNavigate();
  const optionsQuery = useQuery({
    queryKey: ["discovery-filter-options"],
    queryFn: () => catalogService.listFilterOptions(),
  });
  const filters = {
    category: lockedCategory || searchParams.get("category") || "",
    collection,
    search: searchParams.get("q") ?? "",
    occasion: searchParams.get("occasion") ?? "",
    style: searchParams.get("style") ?? "",
    pageCount: searchParams.get("pageCount") ?? "",
    bookType: searchParams.get("bookType") ?? "",
    minPrice: searchParams.get("minPrice") ?? "",
    maxPrice: searchParams.get("maxPrice") ?? "",
    sort: searchParams.get("sort") ?? "featured",
  };
  const pageSize = 6;
  const requestedPage = Math.max(1, Number(searchParams.get("page") ?? 1) || 1);
  const booksQuery = useQuery({
    queryKey: ["books", "discovery", filters, requestedPage],
    queryFn: () => catalogService.listBooksPage(filters, requestedPage, pageSize),
  });
  const totalPages = Math.max(1, booksQuery.data?.pagination?.totalPages ?? 1);
  const currentPage = Math.min(requestedPage, totalPages);
  const visibleBooks = booksQuery.data?.items ?? [];
  const options = optionsQuery.data ?? {
    categories: [],
    occasions: [],
    styles: [],
    pageCounts: [],
    bookTypes: [],
  };
  const locked = Boolean(lockedCategory);
  const activeFilterKeys = [
    "category",
    "occasion",
    "style",
    "pageCount",
    "bookType",
    "minPrice",
    "maxPrice",
  ];
  const activeFilterCount = activeFilterKeys.filter(
    (key) => searchParams.has(key),
  ).length;

  useEffect(() => {
    if (requestedPage > totalPages && !booksQuery.isPending) {
      setDiscoveryParam(setSearchParams, searchParams, "page", String(totalPages));
    }
  }, [booksQuery.isPending, requestedPage, searchParams, setSearchParams, totalPages]);

  function updateParam(key, value) {
    setDiscoveryParam(setSearchParams, searchParams, key, value);
  }

  function clearFilters() {
    const next = new URLSearchParams();
    const search = searchParams.get("q");
    const sort = searchParams.get("sort");
    if (search) next.set("q", search);
    if (sort && sort !== "featured") next.set("sort", sort);
    setSearchParams(next, { replace: true });
  }

  return (
    <section className="discovery-area" id="discovery-results">
      <div className="discovery-tools">
        <label className="discovery-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search books</span>
          <input
            type="search"
            value={filters.search}
            placeholder="Search books and stories"
            onChange={(event) => updateParam("q", event.target.value)}
          />
          {filters.search ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => updateParam("q", "")}
            >
              <X size={15} />
            </button>
          ) : null}
        </label>
        <button
          className="button button-outline mobile-filter-trigger"
          type="button"
          aria-haspopup="dialog"
          onClick={() => setMobileFiltersOpen(true)}
        >
          <SlidersHorizontal size={15} /> Filters
          {activeFilterCount > 0 ? <span>{activeFilterCount}</span> : null}
        </button>
        <label className="discovery-sort">
          <span>Sort by</span>
          <select
            value={filters.sort}
            onChange={(event) => updateParam("sort", event.target.value)}
            aria-label="Sort books"
          >
            <option value="featured">Featured</option>
            <option value="price-low">Price: low to high</option>
            <option value="price-high">Price: high to low</option>
            <option value="title">Title A–Z</option>
            <option value="pages">Page count</option>
          </select>
        </label>
      </div>
      {optionsQuery.isError ? (
        <p className="inline-error" role="alert">
          Filters are temporarily unavailable. You can still search and sort books.
        </p>
      ) : null}
      <div className="discovery-layout">
        <FilterSidebar
          searchParams={searchParams}
          updateParam={updateParam}
          options={options}
          lockedCategory={locked}
          onClear={clearFilters}
        />

        <div className="discovery-results">
          <div className="discovery-results-heading">
            <div>
              <h2>{listTitle}</h2>
              <p aria-live="polite">
                {booksQuery.isPending
                  ? "Finding the right designs…"
                  : `${booksQuery.data?.pagination?.totalItems ?? 0} designs to explore`}
              </p>
            </div>
            {activeFilterCount > 0 ? (
              <button className="clear-filters-mobile" type="button" onClick={clearFilters}>
                Clear filters
              </button>
            ) : null}
          </div>
          {booksQuery.isPending ? (
            <LoadingState />
          ) : booksQuery.isError ? (
            <ErrorState onRetry={booksQuery.refetch} />
          ) : (
            <>
              <BookGrid
                books={visibleBooks}
                emptyTitle="No designs match those filters"
                emptyMessage="Try widening the price range or choosing different filters."
                onPreview={setPreviewBook}
                onCreate={(book) =>
                  navigate(`/create/${book.id}`, { state: { book } })
                }
              />
              <Pagination
                page={currentPage}
                totalPages={totalPages}
                onPageChange={(nextPage) => updateParam("page", String(nextPage))}
              />
            </>
          )}
        </div>
      </div>
      <MobileFilterDrawer
        open={mobileFiltersOpen}
        onClose={() => setMobileFiltersOpen(false)}
        searchParams={searchParams}
        updateParam={updateParam}
        options={options}
        lockedCategory={locked}
        onClear={clearFilters}
      />
      {previewBook ? (
        <BookPreviewDialog book={previewBook} onClose={() => setPreviewBook(null)} />
      ) : null}
    </section>
  );
}
