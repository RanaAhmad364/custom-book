import { useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { SafeImage } from "../../../../components/common/SafeImage.jsx";

export default function BookGallery({ book }) {
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const activeImage = book.gallery[activeImageIndex] ?? book.gallery[0];

  function selectImage(index) {
    setActiveImageIndex(index);
  }

  function moveImage(direction) {
    setActiveImageIndex((index) =>
      (index + direction + book.gallery.length) % book.gallery.length,
    );
  }

  return (
    <div className="book-gallery" id="book-preview">
      <div className="book-gallery-stage">
        <SafeImage
          className="book-gallery-main-image"
          src={activeImage.image}
          alt={activeImage.imageAlt}
          loading="eager"
        />
        <span className="book-gallery-caption">{activeImage.label}</span>
        <button
          className="book-gallery-arrow book-gallery-previous"
          type="button"
          aria-label="Previous book preview"
          onClick={() => moveImage(-1)}
        >
          <ArrowLeft size={17} />
        </button>
        <button
          className="book-gallery-arrow book-gallery-next"
          type="button"
          aria-label="Next book preview"
          onClick={() => moveImage(1)}
        >
          <ArrowRight size={17} />
        </button>
        <span className="book-gallery-count" aria-live="polite">
          {activeImageIndex + 1} / {book.gallery.length}
        </span>
      </div>
      <div className="book-gallery-thumbnails" role="group" aria-label="Book preview images">
        {book.gallery.map((image, index) => (
          <button
            className={`book-gallery-thumbnail ${index === activeImageIndex ? "is-active" : ""}`}
            key={`${image.label}-${index}`}
            type="button"
            aria-label={`Show ${image.label.toLowerCase()}`}
            aria-pressed={index === activeImageIndex}
            onClick={() => selectImage(index)}
          >
            <SafeImage src={image.image} alt="" />
            <span>{image.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
