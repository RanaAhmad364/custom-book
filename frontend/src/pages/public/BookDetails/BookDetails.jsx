import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import BookCustomization from "./components/BookCustomization.jsx";
import BookGallery from "./components/BookGallery.jsx";
import BookPricing from "./components/BookPricing.jsx";
import BookSpecifications from "./components/BookSpecifications.jsx";
import RelatedBooks from "./components/RelatedBooks.jsx";
import "./BookDetails.css";

export default function BookDetails() {
  const { bookId } = useParams();
  const bookQuery = useQuery({
    queryKey: ["book-details", bookId],
    queryFn: () => catalogService.getBookDetails(bookId),
  });
  const relatedQuery = useQuery({
    queryKey: ["related-books", bookId],
    queryFn: () => catalogService.listRelatedBooks(bookId),
    enabled: Boolean(bookQuery.data),
  });

  if (bookQuery.isPending) {
    return <main className="page-shell"><LoadingState /></main>;
  }
  if (bookQuery.isError) {
    return <main className="page-shell"><ErrorState onRetry={bookQuery.refetch} /></main>;
  }
  if (!bookQuery.data) {
    return (
      <main className="page-shell not-found">
        <span className="eyebrow">A page turned</span>
        <h1>We couldn’t find<br /><em>that book.</em></h1>
        <Link className="button button-dark" to="/books">
          Browse all books <ArrowRight size={16} />
        </Link>
      </main>
    );
  }

  const book = bookQuery.data;

  return (
    <main className="book-details-page">
      <DemoNotice />
      <div className="book-details-shell">
        <Link className="book-details-back back-link" to="/books">
          <ArrowLeft size={15} /> All books
        </Link>
        <section className="book-details-overview">
          <BookGallery book={book} />
          <div className="book-details-summary">
            <span className="eyebrow">{book.category} · {book.bookType} COLLECTION</span>
            <h1>{book.title}<br /><em>starts here.</em></h1>
            <p className="book-details-description">{book.description}</p>
            <BookPricing book={book} />
            <div className="book-details-actions">
              <Link className="button button-dark" to={`/create/${book.id}`} state={{ book }}>
                Start Designing <ArrowRight size={16} />
              </Link>
              <a className="button button-outline" href="#book-preview">
                Preview Book
              </a>
            </div>
            <p className="book-details-availability">
              Designed around your photographs, with print and PDF options.
            </p>
          </div>
        </section>

        <section className="book-details-information" aria-label="Book information">
          <BookSpecifications book={book} />
          <BookCustomization book={book} />
        </section>

        <RelatedBooks
          books={relatedQuery.data ?? []}
          isPending={relatedQuery.isPending}
          isError={relatedQuery.isError}
          onRetry={relatedQuery.refetch}
          currentBookId={book.id}
        />
      </div>
    </main>
  );
}
