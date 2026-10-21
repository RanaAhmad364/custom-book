import { ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { BookCard } from "../../../../components/book/BookCard.jsx";
import { BookPreviewDialog } from "../../../../components/book/BookPreviewDialog.jsx";
import { ErrorState } from "../../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../../components/common/LoadingState.jsx";

export default function RelatedBooks({
  books,
  isPending,
  isError,
  onRetry,
  currentBookId,
}) {
  const navigate = useNavigate();
  const [previewBook, setPreviewBook] = useState(null);
  const related = books.filter((book) => book.id !== currentBookId).slice(0, 3);

  return (
    <section className="related-books-section">
      <div className="book-details-section-heading related-books-heading">
        <div>
          <span className="eyebrow">Keep turning pages</span>
          <h2>More stories to explore.</h2>
        </div>
        <Link className="text-link" to="/books">
          Explore all books <ArrowRight size={15} />
        </Link>
      </div>
      {isPending ? <LoadingState /> : null}
      {isError ? <ErrorState onRetry={onRetry} /> : null}
      {!isPending && !isError && related.length ? (
        <div className="book-grid related-book-grid">
          {related.map((book, index) => (
            <BookCard
              book={book}
              index={index}
              key={book.id}
              onPreview={setPreviewBook}
              onCreate={(selectedBook) =>
                navigate(`/create/${selectedBook.id}`, { state: { book: selectedBook } })
              }
            />
          ))}
        </div>
      ) : null}
      {previewBook ? (
        <BookPreviewDialog book={previewBook} onClose={() => setPreviewBook(null)} />
      ) : null}
    </section>
  );
}
