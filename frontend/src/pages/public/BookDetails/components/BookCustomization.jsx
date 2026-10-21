import { Check } from "lucide-react";

export default function BookCustomization({ book }) {
  return (
    <section className="book-customization">
      <span className="eyebrow">Your story, your way</span>
      <h2>Make every page feel like yours.</h2>
      <p>Choose the details that bring your photographs and memories together.</p>
      <ul>
        {book.customizationFeatures.map((feature) => (
          <li key={feature}><Check size={15} /> {feature}</li>
        ))}
      </ul>
      <div className="book-customization-note">
        <span className="eyebrow">A little more about making</span>
        <p>{book.deliveryInformation}</p>
      </div>
    </section>
  );
}
