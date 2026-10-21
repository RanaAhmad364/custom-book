import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { BookDiscovery } from "../../../features/books/components/BookDiscovery.jsx";

function BooksPage() {
  const { data: categories = [], isPending, isError, refetch } = useQuery({
    queryKey: ["categories"],
    queryFn: () => catalogService.listCategories(),
  });

  return (
    <main className="discovery-page page-shell">
      <DemoNotice />
      <section className="page-intro discovery-page-intro">
        <span className="eyebrow">A thoughtful place to begin</span>
        <h1>Find a book for<br /><em>your kind of story.</em></h1>
        <p>Explore sample designs by occasion, style, format, and more.</p>
      </section>
      <BookDiscovery listTitle="Explore books" />
      <section className="discovery-category-links">
        <div>
          <span className="eyebrow">Find a place to start</span>
          <h2>Browse categories</h2>
        </div>
        {isPending ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : (
          <div className="discovery-category-link-list">
            {categories.map((category) => (
              <Link to={`/categories/${category.slug}`} key={category.slug}>
                {category.name} <ArrowRight size={13} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default BooksPage;
