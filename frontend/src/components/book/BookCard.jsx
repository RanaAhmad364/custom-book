import { ArrowRight, Eye } from "lucide-react";
import { Link } from "react-router-dom";

export function BookCard({ book, index = 0, onPreview, onCreate }) {
  return (
    <article
      className={`book-card discovery-book-card book-card-${book.color}`}
      style={{ "--card-index": index }}
    >
      <div className="book-card-image">
        <img src={book.image} alt={book.imageAlt} loading="lazy" />
        <button
          className="book-card-preview"
          type="button"
          onClick={() => onPreview(book)}
        >
          <Eye size={14} /> Preview
        </button>
      </div>
      <div className="book-card-meta">
        <div>
          <span className="eyebrow">{book.category}</span>
          <h3>
            <Link to={`/books/${book.id}`}>{book.title}</Link>
          </h3>
        </div>
        <span className="book-card-price">From ${book.startingPrice.toFixed(2)}</span>
      </div>
      <p>{book.description}</p>
      <div className="discovery-card-specs">
        <span>{book.pages}</span><span>·</span><span>{book.format}</span>
        <span>·</span><span>{book.bookType}</span>
      </div>
      <button
        className="button button-dark discovery-create-button"
        type="button"
        onClick={() => onCreate(book)}
      >
        Create <ArrowRight size={14} />
      </button>
    </article>
  );
}
