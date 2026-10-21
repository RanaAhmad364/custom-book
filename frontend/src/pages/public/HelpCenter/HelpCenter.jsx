import { ArrowRight, BookOpen, CreditCard, HelpCircle, Truck } from "lucide-react";
import { Link } from "react-router-dom";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";

const helpTopics = [
  { title: "Creating a book", description: "Choosing a design, planned editing tools, and previews.", icon: BookOpen, to: "/how-it-works" },
  { title: "Pricing and payment", description: "Sample tier prices and costs still awaiting configuration.", icon: CreditCard, to: "/pricing" },
  { title: "Printing and delivery", description: "Read the current shipping information draft.", icon: Truck, to: "/shipping" },
  { title: "Frequently asked questions", description: "Search answers by topic or browse the expandable list.", icon: HelpCircle, to: "/faq" },
];

export default function HelpCenter() {
  return (
    <main className="page-shell public-info-page help-center-page">
      <DemoNotice />
      <section className="page-intro">
        <span className="eyebrow">A little help along the way</span>
        <h1>Find your way<br /><em>through MemoryBook.</em></h1>
        <p>Browse the guidance for making, pricing, printing, and getting support.</p>
      </section>
      <section className="help-topic-grid">
        {helpTopics.map(({ title, description, icon: Icon, to }) => (
          <Link className="help-topic-card" to={to} key={title}>
            <Icon size={21} />
            <h2>{title}</h2>
            <p>{description}</p>
            <span className="text-link">Explore topic <ArrowRight size={14} /></span>
          </Link>
        ))}
      </section>
      <section className="help-contact-callout">
        <div><span className="eyebrow">Still need a hand?</span><h2>Send us a note.</h2><p>The contact form is in preview mode; message delivery is not configured.</p></div>
        <Link className="button button-dark" to="/contact">Go to Contact <ArrowRight size={15} /></Link>
      </section>
    </main>
  );
}
