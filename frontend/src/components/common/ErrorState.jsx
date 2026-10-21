import { ArrowRight } from "lucide-react";

export function ErrorState({ onRetry }) {
  return (
    <div className="error-state" role="alert">
      <h3>We couldn’t load the books just now.</h3>
      <p>Please try again in a moment.</p>
      <button className="button button-outline" type="button" onClick={onRetry}>
        Try again <ArrowRight size={16} />
      </button>
    </div>
  );
}
