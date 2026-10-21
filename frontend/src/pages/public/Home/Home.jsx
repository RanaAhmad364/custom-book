import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, ArrowUpRight, BadgeCheck, BookOpen, Check, ChevronDown,
  ChevronLeft, ChevronRight, CircleHelp, Eye, FileText, Heart,
  Image as ImageIcon, Layout, LockKeyhole, Move, Palette, Sparkles, Truck, Type,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { BookPreviewDialog } from "../../../components/book/BookPreviewDialog.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { SafeImage } from "../../../components/common/SafeImage.jsx";

const homepageFaqs = [
  {
    question: "How long does it take to create a book?",
    answer:
      "You can take your time choosing photos, trying layouts, and making the details feel right. Printed books are made to order; production is estimated at about a week before shipping.",
  },
  {
    question: "Can I preview my book before ordering?",
    answer:
      "Yes. Review your pages and cover before you finalize a book. The public preview currently shows example catalog designs while the editor is being developed.",
  },
  {
    question: "Is a digital PDF included with a printed book?",
    answer:
      "A digital PDF is a separate purchase from printing. Once a PDF order is paid and verified, the high-quality file can be made available in your account.",
  },
  {
    question: "What are the LIGHT, BASIC, and PREMIUM options?",
    answer:
      "The tiers offer different page counts, cover options, and paper finishes. The final print price depends on your selected size, page count, materials, quantity, and shipping.",
  },
];

const processSteps = [
  {
    number: "01",
    title: "Choose",
    copy: "Pick a template or begin with a blank page.",
    icon: BookOpen,
  },
  {
    number: "02",
    title: "Create",
    copy: "Add your photographs, words, and little details.",
    icon: ImageIcon,
  },
  {
    number: "03",
    title: "Perfect",
    copy: "Arrange every page until it feels just right.",
    icon: Layout,
  },
  {
    number: "04",
    title: "Keep",
    copy: "Choose a digital copy or a beautifully printed book.",
    icon: Truck,
  },
];

const editorTools = [
  { label: "Layout", icon: Layout },
  { label: "Photos", icon: ImageIcon },
  { label: "Text", icon: Type },
  { label: "Cover", icon: Palette },
];

const reasonsToChoose = [
  { label: "Premium quality", icon: BadgeCheck },
  { label: "Secure checkout", icon: LockKeyhole },
  { label: "Saved projects", icon: FileText },
  { label: "Easy editing", icon: Sparkles },
  { label: "Home delivery", icon: Truck },
  { label: "Customer support", icon: CircleHelp },
];

function HomeFAQ() {
  const [openItems, setOpenItems] = useState([0]);

  function toggleItem(index) {
    setOpenItems((current) =>
      current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index],
    );
  }

  return (
    <div className="home-faq-list">
      {homepageFaqs.map((item, index) => {
        const isOpen = openItems.includes(index);
        return (
          <article className={`faq-item ${isOpen ? "is-open" : ""}`} key={item.question}>
            <h3>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={`home-faq-answer-${index}`}
                onClick={() => toggleItem(index)}
              >
                <span>{item.question}</span>
                <ChevronDown size={17} aria-hidden="true" />
              </button>
            </h3>
            <div
              className="faq-answer"
              id={`home-faq-answer-${index}`}
              hidden={!isOpen}
            >
              <p>{item.answer}</p>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function HomePage() {
  const [activeCategory, setActiveCategory] = useState("All");
  const [previewBook, setPreviewBook] = useState(null);
  const navigate = useNavigate();
  const [editorPage, setEditorPage] = useState(1);
  const [activeEditorTool, setActiveEditorTool] = useState("Layout");
  const [activeTier, setActiveTier] = useState("basic");
  const booksQuery = useQuery({
    queryKey: ["books", "homepage-featured"],
    queryFn: () => catalogService.listBooks({ featured: true }),
  });
  const filtersQuery = useQuery({
    queryKey: ["homepage-filters"],
    queryFn: () => catalogService.listHomepageFilters(),
  });
  const categoriesQuery = useQuery({
    queryKey: ["featured-categories"],
    queryFn: () => catalogService.listFeaturedCategories(),
  });
  const tiersQuery = useQuery({
    queryKey: ["book-tiers"],
    queryFn: () => catalogService.listBookTiers(),
  });
  const visibleBooks = (booksQuery.data ?? []).filter(
    (book) => activeCategory === "All" || book.category === activeCategory,
  );
  const tierList = tiersQuery.data ?? [];

  return (
    <main className="premium-home">
      <section className="premium-hero">
        <div className="premium-hero-copy">
          <span className="eyebrow">Custom photo books & prints</span>
          <h1>
            Turn your memories
            <br />
            into something
            <br />
            <em>worth keeping.</em>
          </h1>
          <p>
            Gather the photographs, people, and places that mean the most.
            Shape them into a personal book, made to revisit for years.
          </p>
          <div className="premium-hero-actions">
            <Link className="button button-dark" to="/create">
              Start Creating <ArrowRight size={16} />
            </Link>
            <Link className="button button-light-outline" to="/books">
              Explore Books
            </Link>
          </div>
          <div className="hero-assurances">
            <span><BadgeCheck size={14} /> Premium quality</span>
            <span><LockKeyhole size={14} /> Secure checkout</span>
            <span><Truck size={14} /> Made for delivery</span>
          </div>
        </div>
        <div className="premium-hero-art" aria-label="A personalized travel photo book">
          <div className="hero-lifestyle-photo">
            <SafeImage
              src="https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?auto=format&fit=crop&w=1100&q=88"
              alt="Soft morning light over a peaceful landscape"
              loading="eager"
            />
          </div>
          <div className="hero-prop hero-prop-cloth" />
          <div className="hero-book-mockup">
            <div className="mockup-spine" />
            <SafeImage
              src="https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1000&q=88"
              alt="Mountain lake photograph on a sample book cover"
              loading="eager"
            />
            <div className="mockup-cover-caption">
              <span>The Adventure</span>
              <span>Continues</span>
              <small>OUR FAVORITE PLACES</small>
            </div>
          </div>
          <div className="hero-camera-prop">
            <SafeImage
              src="https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=480&q=82"
              alt="A camera ready to capture the next memory"
            />
          </div>
          <div className="product-labels" aria-label="Book details">
            <span><BookOpen size={14} /> 24 Pages</span>
            <span><FileText size={14} /> Hardcover</span>
            <span><Heart size={14} /> Personalized</span>
          </div>
          <span className="hero-image-caption">A LITTLE WORLD, ALL YOUR OWN</span>
        </div>
      </section>

      <section className="home-section category-discovery" id="designed-for-stories">
        <div className="home-section-heading compact-heading">
          <div>
            <span className="eyebrow">A good place to begin</span>
            <h2>Designed for your stories.</h2>
            <p>Beautiful starting points for the things worth remembering.</p>
          </div>
          <Link className="text-link desktop-only-link" to="/collections">
            View all collections <ArrowRight size={15} />
          </Link>
        </div>
        {categoriesQuery.isPending ? (
          <LoadingState />
        ) : categoriesQuery.isError ? (
          <ErrorState onRetry={categoriesQuery.refetch} />
        ) : (
          <div className="category-photo-grid">
            {categoriesQuery.data.slice(0, 8).map((category) => (
              <Link
                className="category-photo-card"
                key={category.name}
                to={`/categories/${category.slug}`}
              >
                <SafeImage src={category.image} alt={category.imageAlt} />
                <span>{category.name}</span>
                <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="home-section featured-designs" id="featured-books">
        <div className="home-section-heading">
          <div>
            <span className="eyebrow">Made to make your own</span>
            <h2>Featured book designs.</h2>
            <p>Thoughtful templates, ready for your photographs.</p>
          </div>
          <Link className="text-link desktop-only-link" to="/books">
            Explore every book <ArrowRight size={15} />
          </Link>
        </div>
        {filtersQuery.isError ? (
          <p className="inline-error" role="alert">
            Book filters are temporarily unavailable.
          </p>
        ) : (
          <div className="home-filter-list" role="group" aria-label="Filter featured books">
            {(filtersQuery.data ?? []).map((category) => (
              <button
                className={`home-filter-chip ${activeCategory === category ? "selected" : ""}`}
                key={category}
                type="button"
                aria-pressed={activeCategory === category}
                onClick={() => setActiveCategory(category)}
              >
                {category}
              </button>
            ))}
          </div>
        )}
        <p className="catalog-sample-note">
          Preview catalog · Sample designs and starting prices for demonstration
        </p>
        {booksQuery.isPending ? (
          <LoadingState />
        ) : booksQuery.isError ? (
          <ErrorState onRetry={booksQuery.refetch} />
        ) : visibleBooks.length === 0 ? (
          <div className="empty-state compact-empty-state">
            <BookOpen size={25} />
            <h3>A new design is on its way.</h3>
            <p>Explore all books to find another starting point.</p>
            <Link className="text-link" to="/books">
              Browse the catalog <ArrowRight size={15} />
            </Link>
          </div>
        ) : (
          <div className="featured-book-grid">
            {visibleBooks.map((book) => (
              <article className={`featured-book-card tone-${book.color}`} key={book.id}>
                <div className="featured-book-image">
                  <SafeImage src={book.image} alt={book.imageAlt} />
                  <button
                    className="preview-icon-button"
                    type="button"
                    aria-label={`Preview ${book.title}`}
                    onClick={() => setPreviewBook(book)}
                  >
                    <Eye size={16} />
                  </button>
                </div>
                <div className="featured-book-copy">
                  <span className="eyebrow">{book.category}</span>
                  <h3>{book.title}</h3>
                  <div className="featured-book-specs">
                    <span>{book.pages}</span><span>·</span><span>{book.format}</span>
                  </div>
                  <span className="featured-book-price">
                    From ${book.startingPrice.toFixed(2)}
                  </span>
                  <div className="featured-book-actions">
                    <button
                      className="button button-outline"
                      type="button"
                      onClick={() => setPreviewBook(book)}
                    >
                      Preview
                    </button>
                    <button
                      className="button button-dark"
                      type="button"
                      onClick={() => navigate(`/create/${book.id}`, { state: { book } })}
                    >
                      Create
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="home-section how-section" id="how-it-works">
        <div className="home-section-heading">
          <div>
            <span className="eyebrow">From camera roll to coffee table</span>
            <h2>How it works.</h2>
            <p>A few thoughtful steps turn your favorite photographs into a book.</p>
          </div>
          <div className="step-pagination" aria-hidden="true">
            <span>01</span><span className="step-line" /><span>04</span>
          </div>
        </div>
        <div className="process-step-grid">
          {processSteps.map(({ number, title, copy, icon: Icon }) => (
            <article className="process-step-card" key={title}>
              <div className="process-step-top">
                <span>{number}</span>
                <span className="process-step-icon"><Icon size={19} /></span>
              </div>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
          <div className="process-book-preview">
            <SafeImage
              src="https://images.unsplash.com/photo-1519682337058-a94d519337bc?auto=format&fit=crop&w=800&q=85"
              alt="An open photo book filled with travel memories"
            />
            <span>Turn moments<br />into memories <Heart size={13} /></span>
          </div>
        </div>
      </section>

      <section className="home-section editor-feature" id="editor-preview">
        <div className="editor-feature-copy">
          <span className="eyebrow">Your ideas, in your hands</span>
          <h2>A little room<br />to make it <em>yours.</em></h2>
          <p>
            Arrange the photographs, words, and details of your story. Our
            editor is being built to make the creative part feel simple.
          </p>
          <ul className="editor-feature-list">
            <li><Move size={15} /> Drag and drop your photos</li>
            <li><Layout size={15} /> Change layouts and rearrange pages</li>
            <li><Type size={15} /> Add text and customize typography</li>
            <li><Palette size={15} /> Design a cover that feels like yours</li>
          </ul>
          <span className="editor-phase-note">
            Editor preview · Book creation arrives in a later phase
          </span>
        </div>
        <div className="editor-preview-shell" aria-label="Book editor preview">
          <div className="editor-topbar">
            <span className="editor-document-name">Our little book <span>Saved</span></span>
            <div className="editor-top-actions">
              <button type="button" aria-label="Previous spread" onClick={() => setEditorPage((page) => Math.max(1, page - 1))}>
                <ChevronLeft size={16} />
              </button>
              <span>{editorPage} / 24</span>
              <button type="button" aria-label="Next spread" onClick={() => setEditorPage((page) => Math.min(24, page + 1))}>
                <ChevronRight size={16} />
              </button>
              <span className="editor-preview-label">Editor preview</span>
            </div>
          </div>
          <div className="editor-workspace">
            <aside className="editor-tool-rail" aria-label="Editor tools">
              {editorTools.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  className={activeEditorTool === label ? "is-selected" : ""}
                  type="button"
                  aria-label={`${label} tool`}
                  aria-pressed={activeEditorTool === label}
                  onClick={() => setActiveEditorTool(label)}
                >
                  <Icon size={17} />
                </button>
              ))}
            </aside>
            <div className="editor-canvas-wrap">
              <div className="editor-canvas">
                <div className="editor-page editor-page-text">
                  <span className="eyebrow">{activeEditorTool} · PAGE {editorPage}</span>
                  <h3>{editorPage === 1 ? "The days we keep" : "Somewhere, together"}</h3>
                  <p>A collection of little things that became everything.</p>
                  <SafeImage
                    src={editorPage % 2 ? "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=600&q=80" : "https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=600&q=80"}
                    alt="A sample photograph placed on an editor page"
                  />
                </div>
                <div className="editor-page editor-page-photo">
                  <SafeImage
                    src={editorPage % 2 ? "https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=600&q=80" : "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=600&q=80"}
                    alt="A second sample photograph in the book spread"
                  />
                  <span>THIS MOMENT, ALWAYS</span>
                </div>
              </div>
              <div className="editor-zoom"><span>−</span><span>100%</span><span>+</span></div>
            </div>
            <aside className="editor-properties">
              <span className="eyebrow">{activeEditorTool}</span>
              <div className="property-line" />
              <div className="property-line short" />
              <div className="property-swatch-row"><i /><i /><i /><i /></div>
              <span className="eyebrow">Pages</span>
              <button type="button" aria-label="Go to previous page" onClick={() => setEditorPage((page) => Math.max(1, page - 1))}>
                <SafeImage src="https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=220&q=75" alt="" />
                <span>0{editorPage}</span>
              </button>
              <button type="button" aria-label="Go to next page" onClick={() => setEditorPage((page) => Math.min(24, page + 1))}>
                <SafeImage src="https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=220&q=75" alt="" />
                <span>0{Math.min(24, editorPage + 1)}</span>
              </button>
            </aside>
          </div>
        </div>
      </section>

      <section className="home-section fulfillment-section" id="digital-and-print">
        <article className="fulfillment-card digital-card">
          <div className="fulfillment-copy">
            <span className="eyebrow">Take it with you</span>
            <h2>Digital download</h2>
            <p>Keep a high-quality PDF of your finished book, ready to revisit and share.</p>
            <ul>
              <li><Check size={14} /> High-quality PDF</li>
              <li><Check size={14} /> Separate PDF purchase</li>
              <li><Check size={14} /> Secure download access</li>
            </ul>
            <Link className="text-link" to="/pricing">Learn more <ArrowRight size={14} /></Link>
          </div>
          <div className="fulfillment-art tablet-art">
            <div className="tablet-device">
              <SafeImage src="https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=650&q=82" alt="A family memory shown on a digital book preview" />
            </div>
            <span className="art-stem">✳</span>
          </div>
        </article>
        <article className="fulfillment-card print-card">
          <div className="fulfillment-copy">
            <span className="eyebrow">Something to hold</span>
            <h2>Professional printing</h2>
            <p>A real book, made to last with considered papers and beautiful finishes.</p>
            <ul>
              <li><Check size={14} /> Light, Basic & Premium tiers</li>
              <li><Check size={14} /> Hardcover and softcover choices</li>
              <li><Check size={14} /> Made to order, delivered home</li>
            </ul>
            <Link className="text-link" to="/pricing">Explore print options <ArrowRight size={14} /></Link>
          </div>
          <div className="fulfillment-art print-stack">
            <SafeImage src="https://images.unsplash.com/photo-1507842217343-583bb7270b66?auto=format&fit=crop&w=750&q=82" alt="A stack of beautifully bound books" />
          </div>
        </article>
      </section>

      <section className="home-section book-type-category-section" id="book-types">
        <div className="book-types-column">
          <div className="home-section-heading">
            <div>
              <span className="eyebrow">Find your finish</span>
              <h2>Book types.</h2>
              <p>Choose a tier that feels right for your story.</p>
            </div>
          </div>
          {tiersQuery.isPending ? (
            <LoadingState />
          ) : tiersQuery.isError ? (
            <ErrorState onRetry={tiersQuery.refetch} />
          ) : (
            <div className="book-tier-grid">
              {tierList.map((tier) => (
                <article
                  className={`book-tier-card ${tier.id === activeTier ? "tier-selected" : ""}`}
                  key={tier.id}
                >
                  <button
                    className="tier-select"
                    type="button"
                    aria-label={`Show ${tier.name} tier`}
                    aria-pressed={tier.id === activeTier}
                    onClick={() => setActiveTier(tier.id)}
                  >
                    <span className="eyebrow">{tier.name}</span>
                    <h3>{tier.tagline}</h3>
                    <ul>
                      {tier.features.map((feature) => (
                        <li key={feature}><Check size={13} /> {feature}</li>
                      ))}
                    </ul>
                    <span className="tier-price">
                      From ${tier.startingPrice.toFixed(2)}
                    </span>
                  </button>
                </article>
              ))}
            </div>
          )}
          <p className="price-footnote">
            Preview starting prices only. Final print pricing depends on book
            specifications and shipping.
          </p>
        </div>
        <div className="featured-categories-column" id="featured-categories">
          <div className="home-section-heading">
            <div>
              <span className="eyebrow">Stories, gathered by feeling</span>
              <h2>Featured categories.</h2>
              <p>A few lovely reasons to begin.</p>
            </div>
          </div>
          {categoriesQuery.isPending ? (
            <LoadingState />
          ) : categoriesQuery.isError ? (
            <ErrorState onRetry={categoriesQuery.refetch} />
          ) : (
            <div className="featured-category-grid">
              {categoriesQuery.data.slice(0, 8).map((category) => (
                <Link
                  className="featured-category-tile"
                  key={category.name}
                  to={`/categories/${category.slug}`}
                >
                  <SafeImage src={category.image} alt={category.imageAlt} />
                  <span>{category.name}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="home-section why-section" id="why-choose-us">
        <div className="why-intro">
          <span className="eyebrow">Made with care, from start to finish</span>
          <h2>Why choose us?</h2>
          <p>More than a book. A keepsake, made around your life.</p>
        </div>
        <div className="why-feature-grid">
          {reasonsToChoose.map(({ label, icon: Icon }) => (
            <div className="why-feature" key={label}>
              <span><Icon size={17} /></span>
              <strong>{label}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="home-section home-faq-section" id="frequently-asked-questions">
        <div className="faq-image-panel">
          <SafeImage
            src="https://images.unsplash.com/photo-1507842217343-583bb7270b66?auto=format&fit=crop&w=900&q=85"
            alt="A calm reading corner with books to return to"
          />
          <span className="image-caption">MADE FOR THE MOMENTS THAT STAY</span>
        </div>
        <div className="faq-content-panel">
          <span className="eyebrow">A little more to know</span>
          <h2>Frequently asked<br />questions.</h2>
          <p>Find a few answers before your story begins.</p>
          <HomeFAQ />
          <Link className="text-link faq-more-link" to="/faq">
            Read all the answers <ArrowRight size={14} />
          </Link>
        </div>
        <blockquote className="home-testimonial">
          <span>“</span>
          <p>
            A good book takes you back to the feeling, not just the place.
          </p>
          <footer>A small thought from the MemoryBook studio</footer>
        </blockquote>
      </section>

      <section className="home-final-cta">
        <SafeImage
          src="https://images.unsplash.com/photo-1472396961693-142e6e269027?auto=format&fit=crop&w=1900&q=88"
          alt="A quiet mountain landscape at the end of the day"
          loading="eager"
        />
        <div className="final-cta-content">
          <span className="eyebrow">Your memories. Our craft.</span>
          <h2>Your story deserves more than<br /><em>a camera roll.</em></h2>
          <p>Create a custom photo book made for your life, beautifully.</p>
          <Link className="button button-dark" to="/create">
            Create Your Book <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {previewBook ? (
        <BookPreviewDialog book={previewBook} onClose={() => setPreviewBook(null)} />
      ) : null}
    </main>
  );
}

export default HomePage;
