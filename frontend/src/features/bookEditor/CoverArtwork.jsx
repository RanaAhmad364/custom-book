export function CoverArtwork({ cover, document, side = "front", className = "" }) {
  const design = cover?.design ?? {};
  const face = design[side] ?? {};
  const photo = document?.assets?.find((asset) => asset.id === face.photoAssetId);
  const backgroundColor = face.backgroundColor ?? (side === "front" ? "#e8ece5" : "#f4eee5");
  const title = face.title ?? document?.metadata?.title ?? "Your story";
  const subtitle = face.subtitle ?? "";
  const fontFamily = face.fontFamily ?? "Georgia";
  const textColor = face.textColor ?? "#20352d";
  const size = document?.book?.size;
  const faceRatio = side === "spine" ? "0.14 / 1" : size ? `${size.width} / ${size.height}` : "1 / 1";

  if (side === "spine") {
    return <div className={`cover-artwork cover-artwork-spine ${className}`} style={{ backgroundColor, color: textColor, fontFamily, aspectRatio: faceRatio }}>
      <span>{face.title ?? title}</span>
    </div>;
  }

  return <div className={`cover-artwork cover-artwork-${side} layout-${face.layout ?? "center"} ${className}`} style={{ backgroundColor, color: textColor, fontFamily, aspectRatio: faceRatio, backgroundImage: photo?.src ? `linear-gradient(180deg, rgba(20,30,25,.04), rgba(20,30,25,.42)), url("${photo.src}")` : undefined }}>
    <div className="cover-artwork-copy">
      {side === "back" ? <p>{face.description || "A collection of moments, gathered close and made to keep."}</p> : null}
      <strong>{title}</strong>
      {subtitle ? <span>{subtitle}</span> : null}
    </div>
  </div>;
}
