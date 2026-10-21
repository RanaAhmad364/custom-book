import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";

function CollectionsPage() {
  const {
    data: collections = [],
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["collections"],
    queryFn: () => catalogService.listCollections(),
  });
  const booksQuery = useQuery({
    queryKey: ["books", "collection-counts"],
    queryFn: () => catalogService.listBooks(),
  });

  return (
    <main className="discovery-page page-shell">
      <DemoNotice />
      <section className="page-intro discovery-page-intro">
        <span className="eyebrow">Gathered with care</span>
        <h1>Stories have a way<br />of <em>finding each other.</em></h1>
        <p>Explore collections made to bring the right memories together.</p>
      </section>
      {isPending ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : (
        <section className="collections-list discovery-collections-list">
          {collections.map((collection, index) => {
            const count = (booksQuery.data ?? []).filter(
              (book) => book.collection === collection.name,
            ).length;
            return (
              <Link
                className={`collection-row ${collection.tone ?? ""}`}
                key={collection.slug}
                to={`/collections/${collection.slug}`}
              >
                <div className="collection-image">
                  <img src={collection.image} alt={collection.imageAlt} loading="lazy" />
                  <span>0{index + 1}</span>
                </div>
                <div className="collection-copy">
                  <span className="eyebrow">{collection.eyebrow}</span>
                  <h2>{collection.name}</h2>
                  <p>{collection.description}</p>
                  <span className="text-link">
                    Explore {count} designs <ArrowRight size={16} />
                  </span>
                </div>
              </Link>
            );
          })}
        </section>
      )}
    </main>
  );
}


export default CollectionsPage;
