import { useState } from "react";
import { CheckCircle2, CircleAlert, Mail, MessageCircle, Send } from "lucide-react";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { contactService } from "../../../services/contact.js";

const initialForm = { name: "", email: "", subject: "", message: "" };

export default function Contact() {
  const [form, setForm] = useState(initialForm);
  const [status, setStatus] = useState("idle");
  const [errorMessage, setErrorMessage] = useState("");

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    if (status !== "idle") setStatus("idle");
    setErrorMessage("");
  }

  async function submitForm(event) {
    event.preventDefault();
    setStatus("submitting");
    setErrorMessage("");
    try {
      const result = await contactService.submitMessage(
        Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim()])),
      );
      setStatus(result.validated ? "success" : "error");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn’t validate your message. Please try again.");
      setStatus("error");
    }
  }

  return (
    <main className="page-shell public-info-page contact-page">
      <DemoNotice />
      <section className="page-intro">
        <span className="eyebrow">We’re here to help</span>
        <h1>Let’s talk about<br /><em>your next story.</em></h1>
        <p>Send a note about the catalog, the product, or a question you’d like us to consider.</p>
      </section>
      <div className="contact-layout">
        <aside className="contact-aside">
          <span className="eyebrow">A note about this preview</span>
          <h2>Your message matters.</h2>
          <p>The contact form currently validates your message in this browser. Email delivery and message storage are not configured, so nothing is sent or saved.</p>
          <div className="contact-aside-detail"><Mail size={17} /><span><strong>Email support</strong><small>Contact delivery is not configured yet.</small></span></div>
          <div className="contact-aside-detail"><MessageCircle size={17} /><span><strong>Common questions</strong><small>Browse the searchable Help Center.</small></span></div>
        </aside>
        <form className="contact-form" onSubmit={submitForm}>
          <div className="contact-form-row">
            <label>Name<input autoComplete="name" name="name" required maxLength={100} value={form.name} onChange={updateField} /></label>
            <label>Email<input autoComplete="email" name="email" type="email" required maxLength={254} value={form.email} onChange={updateField} /></label>
          </div>
          <label>What can we help with?
            <select name="subject" required value={form.subject} onChange={updateField}>
              <option value="">Choose a topic</option>
              <option>Book design</option>
              <option>Pricing and orders</option>
              <option>Printing and delivery</option>
              <option>Account and support</option>
              <option>Something else</option>
            </select>
          </label>
          <label>Your message<textarea name="message" required minLength={10} maxLength={3000} rows={6} value={form.message} onChange={updateField} /></label>
          <p className="contact-privacy-note">Please don’t include payment details or other sensitive information.</p>
          {status === "success" ? (
            <div className="contact-status is-success" role="status"><CheckCircle2 size={18} /><span><strong>Message validated.</strong> This preview does not send or store it. Please use a configured contact channel when one is provided.</span></div>
          ) : null}
          {status === "error" ? (
            <div className="contact-status is-error" role="alert"><CircleAlert size={18} /><span>{errorMessage || "We couldn’t validate your message. Please check the fields and try again."}</span></div>
          ) : null}
          <button className="button button-dark contact-submit" type="submit" disabled={status === "submitting"}>
            {status === "submitting" ? <><span className="loading-spinner" /> Validating…</> : <>Validate message <Send size={15} /></>}
          </button>
        </form>
      </div>
    </main>
  );
}
