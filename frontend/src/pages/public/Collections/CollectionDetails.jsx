import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { BookDiscovery } from "../../../features/books/components/BookDiscovery.jsx";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";

function CollectionDetailPage() {
  const { collectionSlug } = useParams();
  const {
    data: collection,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["collection", collectionSlug],
    queryFn: () => catalogService.getCollection(collectionSlug),
  });

  if (isPending) return <main className="page-shell"><LoadingState /></main>;
  if (isError) return <main className="page-shell"><ErrorState onRetry={refetch} /></main>;
  if (!collection) {
    return (
      <main className="page-shell not-found">
        <span className="eyebrow">A collection not found</span>
        <h1>This story<br /><em>isn’t gathered yet.</em></h1>
        <Link className="button button-dark" to="/collections">Browse collections</Link>
      </main>
    );
  }

  return (
    <main className="discovery-page collection-detail-page page-shell">
      <DemoNotice />
      <section
        className="discovery-collection-hero"
        style={collection.image ? { "--discovery-hero-image": `url("${collection.image}")` } : undefined}
      >
        <div>
          <span className="eyebrow">{collection.eyebrow}</span>
          <h1>{collection.name}<br /><em>collection.</em></h1>
          <p>{collection.description}</p>
          <Link className="button button-light" to="/books">
            Find your book <ArrowRight size={15} />
          </Link>
        </div>
      </section>
      <nav className="discovery-breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link><ArrowRight size={12} />
        <Link to="/collections">Collections</Link><ArrowRight size={12} />
        <span>{collection.name}</span>
      </nav>
      <BookDiscovery
        collection={collection.name}
        listTitle="Featured designs"
      />
      <section className="collection-detail-extras">
        <div className="recommended-layouts">
          <span className="eyebrow">A few ways to begin</span>
          <h2>Recommended layouts</h2>
          <div>
            {(collection.recommendedLayouts ?? []).map((layout, index) => (
              <article key={layout}>
                <span>0{index + 1}</span>
                <h3>{layout}</h3>
                <p>A considered page sequence for your photographs.</p>
              </article>
            ))}
          </div>
        </div>
        <div className="related-categories">
          <span className="eyebrow">Keep exploring</span>
          <h2>Related categories</h2>
          <div>
            {(collection.relatedCategories ?? []).map((name) => (
              <Link
                key={name}
                to={`/categories/${name.toLowerCase().replace(/\s+/g, "-")}`}
              >
                {name} <ArrowUpRight size={13} />
              </Link>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

export default CollectionDetailPage;
