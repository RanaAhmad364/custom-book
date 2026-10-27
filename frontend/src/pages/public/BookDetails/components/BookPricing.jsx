import { Check } from "lucide-react";
import { formatCurrency } from "../../../../services/money.js";

export default function BookPricing({ book }) {
  return (
    <div className="book-pricing">
      <div>
        <span className="eyebrow">Book starting price</span>
        <strong>{formatCurrency(book.startingPrice, book.currency)}</strong>
        <span className="book-pricing-note">Print options and shipping are quoted at checkout</span>
        {book.pdfPrice !== null && book.pdfPrice !== undefined
          ? <span className="book-pricing-note">PDF {formatCurrency(book.pdfPrice, book.currency)}</span>
          : null}
      </div>
      <ul>
        <li><Check size={14} /> Printed to order</li>
        <li><Check size={14} /> Digital PDF available</li>
      </ul>
    </div>
  );
}
