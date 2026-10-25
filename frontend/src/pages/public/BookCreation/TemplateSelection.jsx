import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Eye, Search } from "lucide-react";
import { catalogService } from "../../../services/catalog.js";
import { BookPreviewDialog } from "../../../components/book/BookPreviewDialog.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { SafeImage } from "../../../components/common/SafeImage.jsx";
import { useBookCreation } from "../../../features/bookCreation/BookCreationContext.jsx";
import { CreationFooter, CreationHeading, CreationShell } from "./CreationShell.jsx";

export default function TemplateSelection() {
  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState(null);
  const { selections, selectTemplate } = useBookCreation();
  const query = useQuery({ queryKey: ["creation-templates"], queryFn: () => catalogService.listTemplates() });
  const templates = query.data ?? [];
  const categories = ["All", ...new Set(templates.map((template) => template.category))];
  const filtered = useMemo(() => templates.filter((template) => (category === "All" || template.category === category) && `${template.name} ${template.category} ${template.description}`.toLowerCase().includes(search.trim().toLowerCase())), [templates, category, search]);

  return <CreationShell current="/create/templates">
    <CreationHeading eyebrow="A thoughtful place to begin" title={<>Choose your<br /><em>starting design.</em></>} description="Each template is a flexible starting point. Change the photos, layouts, and words as you make it yours." />
    <div className="creation-template-tools">
      <label className="creation-search"><Search size={16} /><input aria-label="Search templates" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search designs" /></label>
      <div className="creation-category-tabs" aria-label="Template categories">{categories.map((item) => <button type="button" className={category === item ? "active" : ""} key={item} onClick={() => setCategory(item)}>{item}</button>)}</div>
    </div>
    {query.isPending ? <LoadingState /> : query.isError ? <ErrorState onRetry={query.refetch} /> : filtered.length ? <div className="creation-template-grid">
      {filtered.map((template) => {
        const selected = selections.selectedTemplate?.id === template.id;
        const previewBook = {
          ...template,
          title: template.name,
          image: template.previewImage,
          imageAlt: template.name,
          pages: "Template pages",
          format: "Customizable design",
          startingPrice: 0,
        };
        return <article className={`creation-template-card${selected ? " selected" : ""}`} key={template.id}>
          <div className="creation-template-image"><SafeImage src={template.previewImage} alt={template.name} /><button type="button" aria-label={`Preview ${template.name}`} onClick={() => setPreview(previewBook)}><Eye size={15} /> Preview</button><span>{template.category}</span></div>
          <div className="creation-template-copy"><div><span className="eyebrow">{template.category} · Template</span><h2>{template.name}</h2><p>{template.description}</p></div><button className="button button-outline" type="button" onClick={() => selectTemplate(template)}>{selected ? "Selected" : "Apply template"}</button></div>
        </article>;
      })}
    </div> : <div className="creation-no-results"><h2>No designs found.</h2><p>Try another title or category.</p></div>}
    <CreationFooter backTo="/create" backLabel="Back to start" nextLabel="Continue to setup" nextTo="/create/setup" disabled={!selections.selectedTemplate} />
    {preview ? <BookPreviewDialog book={preview} onClose={() => setPreview(null)} /> : null}
  </CreationShell>;
}
