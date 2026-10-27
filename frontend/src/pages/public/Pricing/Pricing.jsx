import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, CircleHelp } from "lucide-react";
import { Link } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { formatCurrency } from "../../../services/money.js";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";

const priceItems = [
  {
    title: "Digital PDF service",
    description: "A high-resolution PDF of your completed book.",
    amount: "Book-specific price",
  },
  {
    title: "Printing",
    description: "Depends on book size, cover, paper, page count, and quantity.",
    amount: "Quoted before checkout",
  },
  {
    title: "Additional pages",
    description: "Any price beyond a tier’s included pages will be shown with final options.",
    amount: "Calculated per extra page",
  },
  {
    title: "Shipping",
    description: "Destination and delivery method affect the final charge.",
    amount: "Shown before checkout",
  },
];

function PricingPage() {
  const tiersQuery = useQuery({
    queryKey: ["book-tiers"],
    queryFn: () => catalogService.listBookTiers(),
  });

  return (
    <main className="page-shell public-info-page pricing-page">
      <DemoNotice />
      <section className="page-intro pricing-intro">
        <span className="eyebrow">A book made for keeping</span>
        <h1>Good things take<br /><em>a little thought.</em></h1>
        <p>
          Start with a book tier, then choose the details that suit your story.
          Final totals depend on your design and order choices.
        </p>
      </section>

      <section className="pricing-tier-grid" aria-label="Book tiers">
        {tiersQuery.isPending ? <LoadingState /> : null}
        {tiersQuery.isError ? <ErrorState onRetry={tiersQuery.refetch} /> : null}
        {tiersQuery.data?.map((tier, index) => (
          <article className={`pricing-tier-card ${tier.id === "basic" ? "is-featured" : ""}`} key={tier.id}>
            <span className="pricing-number">0{index + 1}</span>
            <span className="eyebrow">{tier.tagline}</span>
            <h2>{tier.name}</h2>
            <p className="pricing-tier-price">
              <small>Catalog starting price</small>
              <strong>{tier.startingPrice === null ? "Explore books" : <>{formatCurrency(tier.startingPrice, tier.currency)}<span>+</span></>}</strong>
            </p>
            <ul>
              {tier.features.map((feature) => (
                <li key={feature}><Check size={15} /> {feature}</li>
              ))}
            </ul>
            <Link className="text-link" to="/books">
              Explore designs <ArrowRight size={15} />
            </Link>
          </article>
        ))}
      </section>

      <p className="pricing-disclaimer" role="note">
        <strong>Starting prices are indicative.</strong> Final print totals are calculated by the server from the selected book, page count, print options, discounts, and shipping.
      </p>

      <section className="pricing-components">
        <div className="book-details-section-heading">
          <span className="eyebrow">A clear view of the total</span>
          <h2>What goes into your price?</h2>
          <p>PDF and print estimates come from the catalog and backend pricing rules. Your final order total is confirmed before checkout.</p>
        </div>
        <div className="pricing-component-list">
          {priceItems.map((item) => (
            <article key={item.title}>
              <div><h3>{item.title}</h3><p>{item.description}</p></div>
              <span>{item.amount}</span>
            </article>
          ))}
        </div>
      </section>
      <section className="pricing-bottom">
        <h2>Need help choosing?</h2>
        <Link className="button button-outline" to="/help">
          Visit the Help Center <CircleHelp size={16} />
        </Link>
      </section>
    </main>
  );
}

export default PricingPage;
