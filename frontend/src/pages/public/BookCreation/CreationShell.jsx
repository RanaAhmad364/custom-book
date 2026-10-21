import { ArrowLeft, ArrowRight, BookOpen, Check } from "lucide-react";
import { Link } from "react-router-dom";

const steps = [
  { path: "/create", label: "Start" },
  { path: "/create/templates", label: "Template" },
  { path: "/create/setup", label: "Book setup" },
  { path: "/create/photos", label: "Photos" },
];

export function CreationShell({ current, children }) {
  const currentIndex = steps.findIndex((step) => step.path === current);
  return (
    <main className="creation-page">
      <div className="creation-shell">
        <Link className="creation-brand" to="/"><span><BookOpen size={18} /></span> MemoryBook <small>STUDIO</small></Link>
        <nav className="creation-progress" aria-label="Book creation progress">
          {steps.map((step, index) => (
            <div className={`creation-progress-step${index === currentIndex ? " active" : ""}${index < currentIndex ? " complete" : ""}`} key={step.path}>
              <span>{index < currentIndex ? <Check size={13} /> : `0${index + 1}`}</span><small>{step.label}</small>
            </div>
          ))}
        </nav>
        {children}
      </div>
    </main>
  );
}

export function CreationHeading({ eyebrow, title, description }) {
  return <header className="creation-heading"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description ? <p>{description}</p> : null}</header>;
}

export function CreationFooter({ backTo, backLabel, nextLabel, onNext, nextTo, disabled = false, busy = false }) {
  return <div className="creation-footer">
    <Link className="creation-back-link" to={backTo}><ArrowLeft size={15} /> {backLabel}</Link>
    {nextTo ? disabled ? <button className="button button-dark" type="button" disabled>{nextLabel} <ArrowRight size={15} /></button> : <Link className="button button-dark" to={nextTo}>{nextLabel} <ArrowRight size={15} /></Link> : <button className="button button-dark" type="button" disabled={disabled || busy} onClick={onNext}>{busy ? <><span className="loading-spinner" /> Preparing…</> : <>{nextLabel} <ArrowRight size={15} /></>}</button>}
  </div>;
}
