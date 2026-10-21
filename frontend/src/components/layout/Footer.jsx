import { BookOpen } from "lucide-react";
import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="site-footer premium-footer">
      <div className="premium-footer-main">
        <div className="footer-brand-block">
          <Link className="wordmark footer-wordmark" to="/">
            <span className="wordmark-mark">
              <BookOpen size={20} strokeWidth={1.65} />
            </span>
            <span className="wordmark-name">MemoryBook</span>
          </Link>
          <p className="footer-note">
            Your stories, thoughtfully made.
          </p>
          <span className="footer-smallprint">© {new Date().getFullYear()} MemoryBook. All rights reserved.</span>
        </div>
        <div className="footer-links footer-link-groups">
          <div className="footer-link-group">
            <span className="footer-label">Quick links</span>
            <Link to="/">Home</Link>
            <Link to="/books">Explore books</Link>
            <Link to="/collections">Collections</Link>
            <Link to="/pricing">Pricing</Link>
          </div>
          <div className="footer-link-group">
            <span className="footer-label">Discover</span>
            <Link to="/how-it-works">How it works</Link>
            <Link to="/about">About MemoryBook</Link>
            <Link to="/faq">Frequently asked questions</Link>
          </div>
          <div className="footer-link-group">
            <span className="footer-label">Support & policies</span>
            <Link to="/help">Help center</Link>
            <Link to="/contact">Contact</Link>
            <Link to="/privacy">Privacy</Link>
            <Link to="/terms">Terms</Link>
            <Link to="/shipping">Shipping</Link>
            <Link to="/refunds">Refunds</Link>
          </div>
        </div>
      </div>
      <div className="footer-bottom premium-footer-bottom">
        <span>Made for the moments that matter.</span>
        <span>Thoughtfully printed. Happily kept.</span>
      </div>
    </footer>
  );
}
