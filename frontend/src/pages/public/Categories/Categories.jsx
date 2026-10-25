import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { catalogService } from "../../../services/catalog.js";
import { DemoNotice } from "../../../components/common/DemoNotice.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { SafeImage } from "../../../components/common/SafeImage.jsx";

function CategoriesPage() {
  const { data: categories = [], isPending, isError, refetch } = useQuery({
    queryKey: ["categories"],
    queryFn: () => catalogService.listCategories(),
  });

  return (
    <main className="discovery-page page-shell">
      <DemoNotice />
      <section className="page-intro discovery-page-intro">
        <span className="eyebrow">A story for every occasion</span>
        <h1>Browse by<br /><em>what matters.</em></h1>
        <p>Find a thoughtful starting point for the people, places, and milestones you want to remember.</p>
      </section>
      {isPending ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState onRetry={refetch} />
      ) : (
        <div className="discovery-category-grid">
          {categories.map((category) => (
            <Link
              className="discovery-category-card"
              key={category.slug}
              to={`/categories/${category.slug}`}
            >
              <SafeImage src={category.image} alt={category.imageAlt || category.name} />
              <span className="discovery-category-number">{category.name}</span>
              <div>
                <h2>{category.name}</h2>
                <p>{category.description}</p>
                <span className="text-link">Explore category <ArrowRight size={14} /></span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}


export default CategoriesPage;
