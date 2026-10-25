import { useState } from "react";
import { BookOpen } from "lucide-react";

export function SafeImage({ src, alt, className = "", loading = "lazy" }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className={`image-fallback ${className}`} role="img" aria-label={alt}>
        <BookOpen size={24} strokeWidth={1.4} />
      </div>
    );
  }

  return (
    <img
      className={className}
      src={src}
      alt={alt}
      loading={loading}
      onError={() => setFailed(true)}
    />
  );
}
