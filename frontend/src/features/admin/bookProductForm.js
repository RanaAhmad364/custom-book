const DEFAULT_BOOK_METADATA = {
  dimensions: { widthMm: "203.00", heightMm: "203.00" },
  pageCountOptions: [24, 32, 40],
  sizeOptions: [],
  coverOptions: [],
  paperOptions: [],
  previewImageKeys: [],
  printingTiers: [],
  pdfPrice: "0.00",
  printingPrice: "0.00",
  productionDays: 10,
};

function arrayOrDefault(value, fallback = []) {
  return Array.isArray(value) ? [...value] : [...fallback];
}

export function bookFormValues(record = {}) {
  const metadata = record.adminMetadata ?? {};
  return {
    title: record.title ?? "",
    slug: record.slug ?? "",
    description: record.description ?? "",
    categoryId: record.categoryId ?? "",
    collectionId: record.collectionId ?? "",
    style: record.style ?? "",
    occasion: record.occasion ?? "",
    bookType: record.bookType ?? "BASIC",
    pageCountMin: record.pageCountMin ?? 24,
    pageCountMax: record.pageCountMax ?? 80,
    startingPrice: String(record.startingPrice ?? "0.00"),
    currency: record.currency ?? "USD",
    featured: record.featured ?? false,
    coverAssetKey: record.coverAssetKey ?? "",
    adminMetadata: {
      ...DEFAULT_BOOK_METADATA,
      ...metadata,
      dimensions: {
        ...DEFAULT_BOOK_METADATA.dimensions,
        ...(metadata.dimensions ?? {}),
        widthMm: metadata.dimensions?.widthMm ?? DEFAULT_BOOK_METADATA.dimensions.widthMm,
        heightMm: metadata.dimensions?.heightMm ?? DEFAULT_BOOK_METADATA.dimensions.heightMm,
      },
      pageCountOptions: arrayOrDefault(metadata.pageCountOptions, DEFAULT_BOOK_METADATA.pageCountOptions),
      sizeOptions: arrayOrDefault(metadata.sizeOptions).map(String),
      coverOptions: arrayOrDefault(metadata.coverOptions).map(String),
      paperOptions: arrayOrDefault(metadata.paperOptions).map(String),
      previewImageKeys: arrayOrDefault(metadata.previewImageKeys),
      printingTiers: arrayOrDefault(metadata.printingTiers, DEFAULT_BOOK_METADATA.printingTiers),
      pdfPrice: metadata.pdfPrice ?? DEFAULT_BOOK_METADATA.pdfPrice,
      printingPrice: metadata.printingPrice ?? DEFAULT_BOOK_METADATA.printingPrice,
      productionDays: metadata.productionDays ?? DEFAULT_BOOK_METADATA.productionDays,
    },
  };
}

export function collectionsForCategory(collections, categoryId) {
  if (!categoryId || !Array.isArray(collections)) return [];
  return collections.filter(
    (collection) => collection.categoryId === categoryId && collection.isPublished !== false,
  );
}

export function validateBookForm(values) {
  const errors = {};
  if (!values.title.trim()) errors.title = "Enter a book title.";
  if (!values.slug.trim()) errors.slug = "Enter a URL slug.";
  if (!values.description.trim()) errors.description = "Enter a book description.";
  if (!values.categoryId) errors.categoryId = "Choose a category.";
  if (!/^[A-Za-z]{3}$/.test(values.currency.trim())) errors.currency = "Use a three-letter currency code.";

  const startingPrice = String(values.startingPrice).trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(startingPrice)) {
    errors.startingPrice = "Enter a non-negative amount with up to two decimal places.";
  }
  for (const field of ["pdfPrice", "printingPrice"]) {
    const value = values.adminMetadata[field];
    if (!/^\d+(?:\.\d{1,2})?$/.test(String(value).trim())) {
      errors[field] = "Enter a non-negative amount with up to two decimal places.";
    }
  }

  const minimum = Number(values.pageCountMin);
  const maximum = Number(values.pageCountMax);
  if (!Number.isInteger(minimum) || minimum < 1) errors.pageCountMin = "Enter a positive minimum page count.";
  if (!Number.isInteger(maximum) || maximum < 1) errors.pageCountMax = "Enter a positive maximum page count.";
  if (Number.isInteger(minimum) && Number.isInteger(maximum) && minimum > maximum) {
    errors.pageCountMax = "Maximum pages must be at least the minimum.";
  }

  const { widthMm, heightMm } = values.adminMetadata.dimensions;
  for (const [field, dimension] of [["widthMm", widthMm], ["heightMm", heightMm]]) {
    if (!/^\d+(?:\.\d{1,2})?$/.test(String(dimension).trim()) || Number(dimension) <= 0) {
      errors[field] = "Enter a positive dimension in millimetres.";
    }
  }
  const productionDays = Number(values.adminMetadata.productionDays);
  if (!Number.isInteger(productionDays) || productionDays < 1) {
    errors.productionDays = "Enter a positive number of production days.";
  }
  if (!values.adminMetadata.pageCountOptions.length ||
      values.adminMetadata.pageCountOptions.length > 100 ||
      values.adminMetadata.pageCountOptions.some((count) => !Number.isInteger(count) || count < 1)) {
    errors.pageCountOptions = "Enter up to 100 positive page-count options.";
  }
  for (const field of ["sizeOptions", "coverOptions", "paperOptions"]) {
    if (values.adminMetadata[field].length > 50) {
      errors[field] = "Select no more than 50 options.";
    }
  }
  if (values.adminMetadata.previewImageKeys.length > 12) {
    errors.previewImageKeys = "A book can have at most 12 gallery preview images.";
  }
  return errors;
}

export function buildBookPayload(values) {
  return {
    title: values.title.trim(),
    slug: values.slug.trim(),
    description: values.description.trim(),
    categoryId: values.categoryId,
    collectionId: values.collectionId || null,
    style: values.style.trim() || null,
    occasion: values.occasion.trim() || null,
    bookType: values.bookType,
    pageCountMin: Number(values.pageCountMin),
    pageCountMax: Number(values.pageCountMax),
    startingPrice: String(values.startingPrice).trim(),
    currency: values.currency.trim().toUpperCase(),
    featured: values.featured,
    coverAssetKey: values.coverAssetKey || null,
    adminMetadata: {
      ...values.adminMetadata,
      dimensions: {
        widthMm: String(values.adminMetadata.dimensions.widthMm).trim(),
        heightMm: String(values.adminMetadata.dimensions.heightMm).trim(),
      },
      pageCountOptions: values.adminMetadata.pageCountOptions.map(Number),
      pdfPrice: String(values.adminMetadata.pdfPrice).trim(),
      printingPrice: String(values.adminMetadata.printingPrice).trim(),
      productionDays: Number(values.adminMetadata.productionDays),
      sizeOptions: [...values.adminMetadata.sizeOptions],
      coverOptions: [...values.adminMetadata.coverOptions],
      paperOptions: [...values.adminMetadata.paperOptions],
      printingTiers: [...values.adminMetadata.printingTiers],
      previewImageKeys: [...values.adminMetadata.previewImageKeys],
    },
  };
}
