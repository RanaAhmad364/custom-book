import { ArrowLeft, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { policyContent } from "./policyContent.js";

export default function PolicyPage({ policyKey }) {
  const policy = policyContent[policyKey];

  return (
    <main className="page-shell public-info-page policy-page">
      <DemoNotice />
      <div className="policy-draft-banner" role="note">
        <FileText size={18} />
        <p><strong>Draft for internal review — not approved for publication.</strong> This content is a review structure, not legal advice or a complete policy.</p>
      </div>
      <section className="page-intro policy-intro">
        <span className="eyebrow">{policy.eyebrow}</span>
        <h1>{policy.title}</h1>
        <p>{policy.introduction}</p>
      </section>
      <div className="policy-layout">
        <nav className="policy-toc" aria-label="Policy sections">
          <span className="eyebrow">On this page</span>
          {policy.sections.map(([heading], index) => (
            <a key={heading} href={`#policy-section-${index}`}>{heading}</a>
          ))}
        </nav>
        <article className="policy-content">
          {policy.sections.map(([heading, body], index) => (
            <section id={`policy-section-${index}`} key={heading}>
              <h2>{heading}</h2>
              <p>{body}</p>
            </section>
          ))}
          <p className="policy-review-note">Publication requires business-owner and qualified legal review, plus confirmation that every statement matches the live service.</p>
        </article>
      </div>
      <Link className="back-link policy-back" to="/help"><ArrowLeft size={15} /> Help Center</Link>
    </main>
  );
}
