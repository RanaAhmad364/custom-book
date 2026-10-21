import { ArrowRight, BookOpen } from "lucide-react";
import { Link } from "react-router-dom";
import { BookCard } from "./BookCard.jsx";

export function BookGrid({
  books,
  emptyTitle = "No books found",
  emptyMessage,
  onPreview,
  onCreate,
}) {
  if (books.length === 0) {
    return (
      <div className="empty-state">
        <BookOpen size={27} strokeWidth={1.4} />
        <h3>{emptyTitle}</h3>
        <p>{emptyMessage ?? "Try a different search or category."}</p>
        <Link className="text-link" to="/books">
          See all books <ArrowRight size={15} />
        </Link>
      </div>
    );
  }

  return (
    <div className="book-grid discovery-book-grid">
      {books.map((book, index) => (
        <BookCard
          key={book.id}
          book={book}
          index={index}
          onPreview={onPreview}
          onCreate={onCreate}
        />
      ))}
    </div>
  );
}
