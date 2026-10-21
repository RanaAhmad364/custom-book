import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

function NotFoundPage() {
  return (
    <main className="page-shell not-found">
      <span className="eyebrow">A page turned</span>
      <h1>This story isn’t<br /><em>on this shelf.</em></h1>
      <Link className="button button-dark" to="/">
        Back to the beginning <ArrowRight size={16} />
      </Link>
      <nav className="not-found-links" aria-label="Popular pages">
        <Link to="/books">Explore books</Link>
        <Link to="/how-it-works">How it works</Link>
        <Link to="/help">Help Center</Link>
      </nav>
    </main>
  );
}

export default NotFoundPage;
