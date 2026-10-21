import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Ruler } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { useBookCreation } from "../../../features/bookCreation/BookCreationContext.jsx";
import { CreationFooter, CreationHeading, CreationShell } from "./CreationShell.jsx";

const sizes = ["8 × 8 in", "10 × 10 in", "11 × 8.5 in"];
const layouts = ["Balanced story", "Photo-led", "A little of everything"];

export default function BookSetup() {
  const { bookId } = useParams();
  const { selections, updateSelections, beginWithTemplate } = useBookCreation();
  const bookQuery = useQuery({ queryKey: ["creation-book", bookId], queryFn: () => catalogService.getBook(bookId), enabled: Boolean(bookId) });
  useEffect(() => {
    if (bookQuery.data) beginWithTemplate(bookQuery.data);
  }, [bookQuery.data, beginWithTemplate]);

  if (bookId && bookQuery.isPending) return <main className="page-shell"><LoadingState /></main>;
  if (bookId && bookQuery.isError) return <main className="page-shell"><ErrorState onRetry={bookQuery.refetch} /></main>;
  if (bookId && !bookQuery.data && !bookQuery.isPending) return <main className="page-shell not-found"><h1>We couldn’t find that book.</h1><Link className="button button-dark" to="/books">Browse books <ArrowRight size={15} /></Link></main>;

  const pageOptions = selections.selectedTemplate?.bookType === "LIGHT" ? [20, 24, 32, 40] : selections.selectedTemplate?.bookType === "BASIC" ? [20, 24, 32, 40, 60] : [20, 24, 32, 40, 60, 80, 100];

  return <CreationShell current="/create/setup">
    <CreationHeading eyebrow="Make it yours" title={<>Set the shape<br /><em>of your book.</em></>} description="You can change these details later. First, give your story a name and choose how it will feel in your hands." />
    {selections.selectedTemplate ? <div className="creation-selected-template"><img src={selections.selectedTemplate.image} alt="" /><span><small>Starting with {selections.selectedTemplate.category}</small><strong>{selections.selectedTemplate.title}</strong></span><Link to="/create/templates">Change template</Link></div> : <div className="creation-blank-note"><Ruler size={17} /> Starting with a blank design. Choose a layout style below to guide your first pages.</div>}
    <section className="creation-setup-card">
      <label className="creation-field creation-title-field">What would you like to call your book?<input autoFocus maxLength={80} value={selections.title} onChange={(event) => updateSelections({ title: event.target.value })} placeholder="A title to remember" /></label>
      <fieldset className="creation-fieldset"><legend>Choose a book size</legend><div className="creation-choice-grid">{sizes.map((size) => <button type="button" className={`creation-choice-card${selections.bookSize === size ? " active" : ""}`} key={size} onClick={() => updateSelections({ bookSize: size })}><Ruler size={18} /><strong>{size}</strong><small>{size === "11 × 8.5 in" ? "Landscape" : "Square"}</small>{selections.bookSize === size ? <Check size={15} /> : null}</button>)}</div></fieldset>
      <label className="creation-field">Page count<select value={selections.pageCount} onChange={(event) => updateSelections({ pageCount: Number(event.target.value) })}>{pageOptions.map((count) => <option key={count} value={count}>{count} pages</option>)}</select><small>More pages give your photos room to tell the whole story.</small></label>
      <fieldset className="creation-fieldset"><legend>Cover type</legend><div className="creation-choice-grid creation-cover-choices">{["Softcover", "Hardcover", "Linen hardcover"].map((cover) => <button type="button" className={`creation-choice-card${selections.coverType === cover ? " active" : ""}`} key={cover} onClick={() => updateSelections({ coverType: cover })}><strong>{cover}</strong><small>{cover === "Softcover" ? "Light, flexible and lovely" : cover === "Hardcover" ? "A classic keepsake finish" : "A tactile, elevated cover"}</small>{selections.coverType === cover ? <Check size={15} /> : null}</button>)}</div></fieldset>
      <label className="creation-field">Starting layout<select value={selections.startingLayout} onChange={(event) => updateSelections({ startingLayout: event.target.value })}>{layouts.map((layout) => <option key={layout}>{layout}</option>)}</select><small>This sets the initial page rhythm; every page can be changed later.</small></label>
    </section>
    <CreationFooter backTo={selections.selectedTemplate ? "/create/templates" : "/create"} backLabel="Back" nextLabel="Add your photos" nextTo="/create/photos" disabled={!selections.title.trim()} />
  </CreationShell>;
}
