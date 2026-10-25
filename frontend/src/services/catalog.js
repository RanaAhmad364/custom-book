import { apiRequest } from "./apiClient.js";

const tierPresentation = [
  {
    id: "light",
    name: "LIGHT",
    tagline: "Simple & beautiful",
    features: ["20–40 pages", "Soft cover", "Standard paper"],
  },
  {
    id: "basic",
    name: "BASIC",
    tagline: "More to discover",
    features: ["20–60 pages", "Hard cover options", "Premium paper"],
  },
  {
    id: "premium",
    name: "PREMIUM",
    tagline: "A keepsake for special moments",
    features: ["20–100 pages", "Premium cover", "High-quality paper"],
  },
];

function buildQuery(values) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  return params.toString();
}

async function listBooks(filters = {}) {
  const { data } = await apiRequest(`/books?${buildQuery({ ...filters, perPage: 100 })}`);
  return data.items;
}

async function getBook(id) {
  try {
    const { data } = await apiRequest(`/books/${encodeURIComponent(id)}`);
    return data.book;
  } catch (failure) {
    if (failure.status === 404) return null;
    throw failure;
  }
}

export const catalogService = {
  listBooks,

  async listBooksPage(filters = {}, page = 1, perPage = 6) {
    const { data } = await apiRequest(`/books?${buildQuery({ ...filters, page, perPage })}`);
    return data;
  },

  getBook,

  async getBookDetails(id) {
    const book = await getBook(id);
    if (!book) return null;
    const pageRanges = {
      LIGHT: ["20", "24", "32", "40"],
      BASIC: ["20", "24", "32", "40", "60"],
      PREMIUM: ["20", "24", "32", "40", "60", "80", "100"],
    }[book.bookType] ?? ["20", "24", "32", "40", "60"];
    return {
      ...book,
      dimensions: book.bookType === "LIGHT" ? "8 × 8 in" : "10 × 10 in",
      availablePageRanges: pageRanges,
      coverOptions: ["Softcover", "Hardcover", "Linen hardcover"],
      paperOptions: ["Standard matte", "Premium matte", "Lustre"],
      customizationFeatures: [
        "Choose a layout for every page",
        "Add captions and personal notes",
        "Adjust type, colors, and page order",
        "Create a cover with your own title",
      ],
      pdfAvailability: "High-quality PDF available as a separate purchase.",
      printingAvailability: "Printed to order with multiple paper and cover options.",
      productionTime: "About 1 week before shipping",
      deliveryInformation: "Carefully packed and shipped to your home. Delivery timing varies by destination.",
      gallery: Array.isArray(book.gallery) && book.gallery.length
        ? book.gallery
        : [{ image: book.image, imageAlt: book.imageAlt || book.title, label: "Cover" }],
    };
  },

  async listRelatedBooks(id) {
    const book = await getBook(id);
    if (!book) return [];
    const related = await listBooks({ category: book.category, collection: book.collection });
    return related.filter((item) => item.id !== book.id);
  },

  async listCategories() {
    const { data } = await apiRequest("/categories");
    return data.items;
  },

  async getCategory(slug) {
    try {
      const { data } = await apiRequest(`/categories/${encodeURIComponent(slug)}`);
      return data.category;
    } catch (failure) {
      if (failure.status === 404) return null;
      throw failure;
    }
  },

  async listCollections() {
    const { data } = await apiRequest("/collections");
    return data.items;
  },

  async getCollection(slug) {
    try {
      const { data } = await apiRequest(`/collections/${encodeURIComponent(slug)}`);
      return data.collection;
    } catch (failure) {
      if (failure.status === 404) return null;
      throw failure;
    }
  },

  async listFilterOptions() {
    const [categories, books] = await Promise.all([this.listCategories(), listBooks()]);
    return {
      categories: categories.map(({ name }) => name),
      occasions: [...new Set(books.map(({ occasion }) => occasion).filter(Boolean))],
      styles: [...new Set(books.map(({ style }) => style).filter(Boolean))],
      pageCounts: ["20-24", "25-32", "33-48", "49+"],
      bookTypes: [...new Set(books.map(({ bookType }) => bookType).filter(Boolean))],
    };
  },

  listFeaturedCategories() {
    return this.listCategories();
  },

  async listHomepageFilters() {
    const categories = await this.listCategories();
    return ["All", ...categories.map(({ name }) => name)];
  },

  async listBookTiers() {
    const books = await listBooks();
    return tierPresentation.map((tier) => {
      const tierBooks = books.filter((book) => book.bookType === tier.name);
      return {
        ...tier,
        startingPrice: tierBooks.reduce(
          (minimum, book) => Math.min(minimum, book.startingPrice),
          Number.POSITIVE_INFINITY,
        ),
        currency: tierBooks[0]?.currency ?? "USD",
      };
    }).filter((tier) => Number.isFinite(tier.startingPrice));
  },

  async listTemplates(filters = {}) {
    const { data } = await apiRequest(`/templates?${buildQuery({ ...filters, perPage: 100 })}`);
    return data.items;
  },

  async getTemplate(id) {
    try {
      const { data } = await apiRequest(`/templates/${encodeURIComponent(id)}`);
      return data.template;
    } catch (failure) {
      if (failure.status === 404) return null;
      throw failure;
    }
  },
};
