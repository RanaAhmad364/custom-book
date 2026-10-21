import { ArrowRight, BookOpen, Heart, Image } from "lucide-react";
import { Link } from "react-router-dom";
import { SafeImage } from "../../../components/common/SafeImage.jsx";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";

export default function About() {
  return (
    <main className="public-info-page about-page">
      <DemoNotice />
      <section className="about-editorial-hero">
        <div className="about-editorial-copy">
          <span className="eyebrow">A note from the MemoryBook studio</span>
          <h1>Some moments<br />deserve <em>their own shelf.</em></h1>
          <p>MemoryBook is being made for the photographs that mean more than a quick scroll—the people, places, and small everyday things we want to return to.</p>
        </div>
        <div className="about-editorial-image">
          <SafeImage src="https://images.unsplash.com/photo-1519682337058-a94d519337bc?auto=format&fit=crop&w=1200&q=88" alt="A thoughtfully arranged open book with a photograph" loading="eager" />
          <span>For all the little things that become everything.</span>
        </div>
      </section>
      <section className="about-story">
        <span className="eyebrow">Why we’re making this</span>
        <h2>A home for stories<br /><em>you can hold.</em></h2>
        <p>Our idea is simple: make it easier to gather photographs into something personal. A book gives a story room to breathe—a beginning, a few favorite pages, and a place to revisit it later.</p>
        <p>We’re building MemoryBook step by step. The public catalog is a preview of the experience we’re working toward, not a promise that every editing or ordering feature is already available.</p>
      </section>
      <section className="about-values">
        <article><BookOpen size={21} /><h3>Made with intention</h3><p>Clear choices and considered starting points for different kinds of stories.</p></article>
        <article><Heart size={21} /><h3>Personal by nature</h3><p>Your photographs and words should be at the center of the finished book.</p></article>
        <article><Image size={21} /><h3>Designed to revisit</h3><p>A tactile way to return to the moments that matter to you.</p></article>
      </section>
      <div className="about-cta">
        <div><span className="eyebrow">Your story can start here</span><h2>Find a design that feels like you.</h2></div>
        <Link className="button button-dark" to="/books">Explore books <ArrowRight size={16} /></Link>
      </div>
    </main>
  );
}
