import { useMemo, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";

const faqItems = [
  { category: "Getting started", question: "How do I start a photo book?", answer: "Choose a design from Explore Books and select Start Designing, or begin with a template, a blank book, or Quick Start. Set up the book, add photos in the browser preview, then sign in to initialize a project. The full page editor is still in development." },
  { category: "Getting started", question: "Can I begin with a blank design?", answer: "The catalog currently shows sample starting points. Blank-book creation is not available in this preview." },
  { category: "Designing", question: "Can I change the layouts and add captions?", answer: "The planned editor supports page layouts, captions, typography, and cover customization. Editing tools are not yet connected." },
  { category: "Designing", question: "Can I preview my book before ordering?", answer: "Yes. Book design pages include sample cover and interior previews. A final print proof workflow is not configured yet." },
  { category: "Pricing & orders", question: "Are the prices on this site final?", answer: "No. Catalog prices are examples for demonstration. Final prices for printing, extra pages, PDF service, and shipping still need configuration." },
  { category: "Pricing & orders", question: "Is a PDF included with a printed book?", answer: "The intended catalog model treats a PDF as a separate service. The final PDF price and ordering process are not configured." },
  { category: "Pricing & orders", question: "How are shipping charges calculated?", answer: "Shipping charges have not been configured. A production checkout should show the applicable amount before an order is placed." },
  { category: "Printing & delivery", question: "How long does printing take?", answer: "The catalog currently displays an approximate production estimate. It is not a confirmed service commitment; delivery timing will depend on production and destination." },
  { category: "Printing & delivery", question: "What paper and cover options are available?", answer: "Sample book details show possible cover and paper choices. Actual availability should be confirmed before ordering." },
  { category: "Account & support", question: "How do I contact MemoryBook?", answer: "Use the Contact page to validate a message. Email delivery is not connected in this preview, so the form does not send or store submissions." },
  { category: "Account & support", question: "Are my projects saved?", answer: "Account and project storage are not implemented in this preview. The selected book design is carried through the creation URL, but no project is persisted." },
];

const faqCategories = ["All", ...new Set(faqItems.map((item) => item.category))];

function FAQPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeCategory, setActiveCategory] = useState("All");
  const [openItems, setOpenItems] = useState([0]);
  const search = searchParams.get("q") ?? "";
  const visibleItems = useMemo(() => faqItems.filter((item) => {
    const matchesCategory = activeCategory === "All" || item.category === activeCategory;
    const content = `${item.question} ${item.answer} ${item.category}`.toLowerCase();
    return matchesCategory && content.includes(search.trim().toLowerCase());
  }), [activeCategory, search]);

  function updateSearch(value) {
    const params = new URLSearchParams(searchParams);
    if (value) params.set("q", value);
    else params.delete("q");
    setSearchParams(params, { replace: true });
  }

  function toggleItem(question) {
    setOpenItems((current) =>
      current.includes(question)
        ? current.filter((item) => item !== question)
        : [...current, question],
    );
  }

  return (
    <main className="page-shell public-info-page faq-page">
      <DemoNotice />
      <section className="page-intro faq-intro">
        <span className="eyebrow">A few things worth knowing</span>
        <h1>Good questions,<br /><em>thoughtful answers.</em></h1>
        <p>Search common questions about creating, pricing, printing, and support.</p>
      </section>
      <label className="faq-search">
        <Search size={17} aria-hidden="true" />
        <span className="sr-only">Search frequently asked questions</span>
        <input value={search} onChange={(event) => updateSearch(event.target.value)} placeholder="What would you like to know?" />
      </label>
      <div className="faq-category-tabs" role="group" aria-label="FAQ categories">
        {faqCategories.map((category) => (
          <button className={activeCategory === category ? "is-active" : ""} type="button" key={category} aria-pressed={activeCategory === category} onClick={() => setActiveCategory(category)}>
            {category}
          </button>
        ))}
      </div>
      <section className="faq-list" aria-label="Frequently asked questions">
        {visibleItems.length ? visibleItems.map((item) => {
          const isOpen = openItems.includes(item.question);
          return (
            <article className={`faq-item ${isOpen ? "is-open" : ""}`} key={item.question}>
              <span className="faq-item-category">{item.category}</span>
              <h2>
                <button type="button" aria-expanded={isOpen} onClick={() => toggleItem(item.question)}>
                  <span>{item.question}</span>
                  <ChevronDown size={19} aria-hidden="true" />
                </button>
              </h2>
              <div className="faq-answer" hidden={!isOpen}><p>{item.answer}</p></div>
            </article>
          );
        }) : (
          <div className="empty-state"><h3>No answers found</h3><p>Try a different phrase or select another topic.</p></div>
        )}
      </section>
      <section className="faq-contact">
        <p>Still wondering about something?</p>
        <Link className="text-link" to="/contact">Get in touch <span aria-hidden="true">→</span></Link>
      </section>
    </main>
  );
}

export default FAQPage;
