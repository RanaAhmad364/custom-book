import { useCallback, useEffect, useRef, useState } from "react";
import { Heart } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext.jsx";
import { favoritesService } from "../../services/favorites.js";

export function FavoriteButton({ book }) {
  const { ready, user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [isFavorite, setIsFavorite] = useState(Boolean(book.is_favorite));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const handledIntent = useRef(null);

  const toggleFavorite = useCallback(async () => {
    if (!user || isSaving) return;
    const previous = isFavorite;
    setIsFavorite(!previous);
    setIsSaving(true);
    setError("");
    try {
      if (previous) await favoritesService.remove(book.id);
      else await favoritesService.add(book.id);
    } catch (failure) {
      setIsFavorite(previous);
      setError(failure instanceof Error ? failure.message : "Your favorite could not be updated.");
    } finally {
      setIsSaving(false);
    }
  }, [book.id, isFavorite, isSaving, user]);

  useEffect(() => {
    if (!ready || !user || new URLSearchParams(location.search).get("favorite") !== book.id
      || handledIntent.current === book.id) return;
    handledIntent.current = book.id;
    const params = new URLSearchParams(location.search);
    params.delete("favorite");
    navigate({ pathname: location.pathname, search: params.toString() ? `?${params}` : "", hash: location.hash }, { replace: true });
    void toggleFavorite();
  }, [book.id, location.hash, location.pathname, location.search, navigate, ready, toggleFavorite, user]);

  function handleClick() {
    if (!ready) return;
    if (!user) {
      const params = new URLSearchParams(location.search);
      params.set("favorite", book.id);
      const returnTo = `${location.pathname}?${params.toString()}${location.hash}`;
      navigate(`/login?returnTo=${encodeURIComponent(returnTo)}`);
      return;
    }
    void toggleFavorite();
  }

  return (
    <span className="favorite-control">
      <button
        className={`favorite-button${isFavorite ? " is-favorite" : ""}`}
        type="button"
        aria-label={isFavorite ? `Remove ${book.title} from favorites` : `Add ${book.title} to favorites`}
        aria-pressed={isFavorite}
        disabled={!ready || isSaving}
        onClick={handleClick}
      >
        <Heart size={17} fill={isFavorite ? "currentColor" : "none"} />
      </button>
      {error ? <span className="favorite-error" role="alert">{error}</span> : null}
    </span>
  );
}
