import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Eye, Search } from "lucide-react";
import { catalogService } from "../../../services/catalog.js";
import { BookPreviewDialog } from "../../../components/book/BookPreviewDialog.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { useBookCreation } from "../../../features/bookCreation/BookCreationContext.jsx";
import { CreationFooter, CreationHeading, CreationShell } from "./CreationShell.jsx";

export default function TemplateSelection() {
  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState(null);
  const { selections, selectTemplate } = useBookCreation();
  const query = useQuery({ queryKey: ["creation-templates"], queryFn: () => catalogService.listBooks() });
  const books = query.data ?? [];
  const categories = ["All", ...new Set(books.map((book) => book.category))];
  const filtered = useMemo(() => books.filter((book) => (category === "All" || book.category === category) && `${book.title} ${book.category} ${book.style}`.toLowerCase().includes(search.trim().toLowerCase())), [books, category, search]);

  return <CreationShell current="/create/templates">
    <CreationHeading eyebrow="A thoughtful place to begin" title={<>Choose your<br /><em>starting design.</em></>} description="Each template is a flexible starting point. Change the photos, layouts, and words as you make it yours." />
    <div className="creation-template-tools">
      <label className="creation-search"><Search size={16} /><input aria-label="Search templates" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search designs" /></label>
      <div className="creation-category-tabs" aria-label="Template categories">{categories.map((item) => <button type="button" className={category === item ? "active" : ""} key={item} onClick={() => setCategory(item)}>{item}</button>)}</div>
    </div>
    {query.isPending ? <LoadingState /> : query.isError ? <ErrorState onRetry={query.refetch} /> : filtered.length ? <div className="creation-template-grid">
      {filtered.map((book) => {
        const selected = selections.selectedTemplate?.id === book.id;
        return <article className={`creation-template-card${selected ? " selected" : ""}`} key={book.id}>
          <div className="creation-template-image"><img src={book.image} alt={book.imageAlt} loading="lazy" /><button type="button" aria-label={`Preview ${book.title}`} onClick={() => setPreview(book)}><Eye size={15} /> Preview</button><span>{book.category}</span></div>
          <div className="creation-template-copy"><div><span className="eyebrow">{book.style} · {book.bookType}</span><h2>{book.title}</h2><p>{book.pages} · from ${book.startingPrice.toFixed(2)}</p></div><button className="button button-outline" type="button" onClick={() => selectTemplate(book)}>{selected ? "Selected" : "Apply template"}</button></div>
        </article>;
      })}
    </div> : <div className="creation-no-results"><h2>No designs found.</h2><p>Try another title or category.</p></div>}
    <CreationFooter backTo="/create" backLabel="Back to start" nextLabel="Continue to setup" nextTo="/create/setup" disabled={!selections.selectedTemplate} />
    {preview ? <BookPreviewDialog book={preview} onClose={() => setPreview(null)} /> : null}
  </CreationShell>;
}
