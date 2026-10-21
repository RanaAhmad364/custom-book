import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { BookDiscovery } from "../../../features/books/components/BookDiscovery.jsx";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";

function CategoryDetailPage() {
  const { categorySlug } = useParams();
  const {
    data: category,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["category", categorySlug],
    queryFn: () => catalogService.getCategory(categorySlug),
  });

  if (isPending) return <main className="page-shell"><LoadingState /></main>;
  if (isError) return <main className="page-shell"><ErrorState onRetry={refetch} /></main>;
  if (!category) {
    return (
      <main className="page-shell not-found">
        <span className="eyebrow">A story not found</span>
        <h1>That category<br /><em>isn’t on this shelf.</em></h1>
        <Link className="button button-dark" to="/categories">Browse categories</Link>
      </main>
    );
  }

  return (
    <main className="discovery-page category-detail-page page-shell">
      <DemoNotice />
      <section
        className="discovery-collection-hero category-detail-hero"
        style={{ "--discovery-hero-image": `url("${category.heroImage}")` }}
      >
        <div>
          <span className="eyebrow">{category.style} stories · {category.name}</span>
          <h1>{category.name}<br /><em>photo books.</em></h1>
          <p>{category.description}</p>
          <Link className="button button-light" to="/books">
            Explore all books <ArrowRight size={15} />
          </Link>
        </div>
      </section>
      <nav className="discovery-breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link><ArrowRight size={12} />
        <Link to="/categories">Categories</Link><ArrowRight size={12} />
        <span>{category.name}</span>
      </nav>
      <BookDiscovery
        lockedCategory={category.name}
        listTitle={`${category.name} designs`}
      />
      <section className="related-category-strip">
        <span className="eyebrow">A different kind of story?</span>
        <Link to="/categories">Explore all categories <ArrowRight size={15} /></Link>
      </section>
    </main>
  );
}

export default CategoryDetailPage;
