import { useEffect, useRef } from "react";
import { ArrowRight, X } from "lucide-react";
import { Link } from "react-router-dom";
import { SafeImage } from "../common/SafeImage.jsx";
import { formatCurrency } from "../../services/money.js";

export function BookPreviewDialog({ book, onClose }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    dialog.showModal();
    const handleClose = () => closeRef.current();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, []);

  return (
    <dialog
      className="book-preview-dialog"
      ref={dialogRef}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <button
        className="dialog-close"
        type="button"
        aria-label="Close book preview"
        onClick={() => dialogRef.current?.close()}
      >
        <X size={18} />
      </button>
      <div className="preview-dialog-image">
        <SafeImage src={book.image} alt={book.imageAlt} loading="eager" />
      </div>
      <div className="preview-dialog-copy">
        <span className="eyebrow">{book.category} · {book.pages}</span>
        <h2>{book.title}</h2>
        <p>{book.description}</p>
        <div className="preview-details">
          <span>{book.pages}</span>
          <span>{book.format}</span>
          <span>From {formatCurrency(book.startingPrice, book.currency)}</span>
        </div>
        <Link
          className="button button-dark"
          to={`/books/${book.id}`}
          onClick={() => dialogRef.current?.close()}
        >
          See book details <ArrowRight size={16} />
        </Link>
      </div>
    </dialog>
  );
}
