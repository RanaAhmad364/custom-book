export function validateCategoryRecord(record) {
  if (!record.name?.trim()) return "Enter a category name.";
  if (!record.slug?.trim()) return "Enter a category slug.";
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(record.slug.trim())) {
    return "Use lowercase letters, numbers, and single hyphens for the slug.";
  }
  if (!Number.isInteger(record.sortOrder) || record.sortOrder < 0) {
    return "Sort order must be a non-negative whole number.";
  }
  return "";
}

export function categoryFormPayload(record) {
  return {
    ...(record.id ? { id: record.id } : {}),
    name: record.name.trim(),
    slug: record.slug.trim(),
    description: record.description ?? "",
    style: record.style ?? "",
    heroAssetKey: record.heroAssetKey ?? "",
    sortOrder: record.sortOrder,
    isPublished: Boolean(record.isPublished),
  };
}
