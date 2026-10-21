import { useState } from "react";
import { ChevronDown, Ruler, BookOpen, Truck } from "lucide-react";

export default function BookSpecifications({ book }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="book-specifications">
      <div className="book-details-section-heading">
        <span className="eyebrow">Made to fit your story</span>
        <h2>Book details</h2>
      </div>
      <div className="book-specification-highlights">
        <div><BookOpen size={17} /><span><strong>{book.pages}</strong>Starting pages</span></div>
        <div><Ruler size={17} /><span><strong>{book.dimensions}</strong>Book dimensions</span></div>
        <div><Truck size={17} /><span><strong>{book.productionTime}</strong>Production estimate</span></div>
      </div>
      <button
        className="book-specifications-toggle"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? "Hide specifications" : "Explore specifications"}
        <ChevronDown className={expanded ? "is-expanded" : ""} size={17} />
      </button>
      {expanded ? (
        <dl className="book-specifications-list">
          <div><dt>Page ranges</dt><dd>{book.availablePageRanges.join(" · ")}</dd></div>
          <div><dt>Cover options</dt><dd>{book.coverOptions.join(" · ")}</dd></div>
          <div><dt>Paper options</dt><dd>{book.paperOptions.join(" · ")}</dd></div>
          <div><dt>Printing</dt><dd>{book.printingAvailability}</dd></div>
          <div><dt>Digital copy</dt><dd>{book.pdfAvailability}</dd></div>
          <div><dt>Delivery</dt><dd>{book.deliveryInformation}</dd></div>
        </dl>
      ) : null}
    </section>
  );
}
