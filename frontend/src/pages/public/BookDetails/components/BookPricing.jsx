import { Check } from "lucide-react";
import { formatCurrency } from "../../../../services/money.js";

export default function BookPricing({ book }) {
  return (
    <div className="book-pricing">
      <div>
        <span className="eyebrow">Starting at</span>
        <strong>{formatCurrency(book.startingPrice, book.currency)}</strong>
        <span className="book-pricing-note">Final price depends on your options</span>
      </div>
      <ul>
        <li><Check size={14} /> Printed to order</li>
        <li><Check size={14} /> Digital PDF available</li>
      </ul>
    </div>
  );
}
