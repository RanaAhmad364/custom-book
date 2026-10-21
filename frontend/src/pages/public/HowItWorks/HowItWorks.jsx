import { ArrowRight, BookOpen, Check, Download, Image, Layout, Printer, ScanEye } from "lucide-react";
import { Link } from "react-router-dom";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";

const steps = [
  { title: "Choose a template", description: "Find a design that suits the story you want to tell. Browse by occasion, style, or collection.", icon: BookOpen },
  { title: "Upload photos", description: "Add images in the creation preview, review their resolution, and arrange them before you continue. Uploads stay in this browser session.", icon: Image },
  { title: "Customize pages", description: "Arrange your pictures, choose layouts, add captions, and make the cover your own.", icon: Layout },
  { title: "Preview your book", description: "Review the cover and pages, then make adjustments before you decide what comes next.", icon: ScanEye },
  { title: "Download or print", description: "Choose a digital PDF or a printed book. Pricing and ordering will be confirmed before checkout is available.", icon: Download },
];

export default function HowItWorks() {
  return (
    <main className="page-shell public-info-page how-it-works-page">
      <DemoNotice />
      <section className="page-intro">
        <span className="eyebrow">A story, thoughtfully made</span>
        <h1>From camera roll<br /><em>to something you can hold.</em></h1>
        <p>Five considered steps take your favorite moments toward a book worth keeping.</p>
      </section>
      <section className="how-steps" aria-label="How to create a photo book">
        {steps.map(({ title, description, icon: Icon }, index) => (
          <article className="how-step" key={title}>
            <div className="how-step-number">0{index + 1}</div>
            <div className="how-step-icon"><Icon size={20} /></div>
            <div className="how-step-copy">
              <span className="eyebrow">Step 0{index + 1}</span>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
            {index < steps.length - 1 ? <span className="how-step-connector" aria-hidden="true" /> : null}
          </article>
        ))}
      </section>
      <section className="how-editor-note">
        <div>
          <span className="eyebrow">The editor is in development</span>
          <h2>Your design comes first.</h2>
          <p>Start a project, set up your book, and preview selected photos today. The full page editor, remote photo storage, PDF delivery, printing, and checkout are not connected in this preview.</p>
        </div>
        <Printer size={28} strokeWidth={1.3} aria-hidden="true" />
      </section>
      <div className="public-page-actions">
        <Link className="button button-dark" to="/books">Choose a design <ArrowRight size={16} /></Link>
        <Link className="text-link" to="/pricing">Understand the pricing <Check size={14} /></Link>
      </div>
    </main>
  );
}
