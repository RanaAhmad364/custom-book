const photo = (id, width = 900) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=85`;

const demoBooks = [
  {
    id: "our-european-journey",
    title: "Our European Journey",
    category: "Travel",
    collection: "Far & near",
    description: "A thoughtful journal of the places that stay with you.",
    image: photo("photo-1470770841072-f978cf4d019e"),
    imageAlt: "Mountain lake reflecting a quiet alpine landscape",
    color: "blue",
    pages: "24 pages",
    format: "Hardcover",
    startingPrice: 52.99,
    featured: true,
  },
  {
    id: "the-wedding-album",
    title: "The Wedding Album",
    category: "Wedding",
    collection: "The people we love",
    description: "Keep the feeling of your day, and the people who made it.",
    image: photo("photo-1519741497674-611481863552"),
    imageAlt: "An intimate outdoor wedding in warm afternoon light",
    color: "sand",
    pages: "32 pages",
    format: "Hardcover",
    startingPrice: 59.99,
    featured: true,
  },
  {
    id: "little-moments",
    title: "Little Moments",
    category: "Family",
    collection: "A life well lived",
    description: "A home for the days that somehow become your favorites.",
    image: photo("photo-1511895426328-dc8714191300"),
    imageAlt: "A family sharing time together outdoors",
    color: "sage",
    pages: "20 pages",
    format: "Softcover",
    startingPrice: 34.99,
    featured: true,
  },
  {
    id: "our-little-one",
    title: "Our Little One",
    category: "Baby",
    collection: "The people we love",
    description: "All those firsts, gathered into a book to grow up with.",
    image: photo("photo-1492725764893-90b379c2b6e7"),
    imageAlt: "A parent holding a young child close",
    color: "rose",
    pages: "24 pages",
    format: "Hardcover",
    startingPrice: 39.99,
    featured: true,
  },
  {
    id: "a-little-celebration",
    title: "A Little Celebration",
    category: "Birthday",
    collection: "The people we love",
    description: "A bright keepsake for one very good reason to celebrate.",
    image: photo("photo-1558636508-e0db3814bd1d"),
    imageAlt: "A beautifully decorated celebration cake",
    color: "clay",
    pages: "20 pages",
    format: "Softcover",
    startingPrice: 32.99,
    featured: true,
  },
  {
    id: "still-us",
    title: "Still Us",
    category: "Anniversary",
    collection: "The people we love",
    description: "A little time capsule for all the years you made together.",
    image: photo("photo-1516589178581-6cd7833ae3b2"),
    imageAlt: "A couple sharing a quiet, affectionate moment",
    color: "rose",
    pages: "28 pages",
    format: "Hardcover",
    startingPrice: 49.99,
    featured: true,
  },
  {
    id: "the-makers-book",
    title: "The Maker’s Book",
    category: "Portfolio",
    collection: "A life well lived",
    description: "A considered presentation of the work you care about.",
    image: photo("photo-1455390582262-044cdead277a"),
    imageAlt: "A creative workspace with a notebook and camera",
    color: "stone",
    pages: "24 pages",
    format: "Hardcover",
    startingPrice: 54.99,
    featured: true,
  },
  {
    id: "light-and-shadow",
    title: "Light & Shadow",
    category: "Photography",
    collection: "Far & near",
    description: "Give your favorite photographs a place of their own.",
    image: photo("photo-1470252649378-9c29740c9fa8"),
    imageAlt: "Soft light spreading across a peaceful field",
    color: "sage",
    pages: "24 pages",
    format: "Hardcover",
    startingPrice: 52.99,
    featured: true,
  },
  {
    id: "our-everyday",
    title: "Our Everyday",
    category: "Custom",
    collection: "A life well lived",
    description: "A flexible canvas for the story only you can tell.",
    image: photo("photo-1441986300917-64674bd600d8"),
    imageAlt: "A warm, sunlit space with a relaxed lived-in feel",
    color: "sand",
    pages: "20 pages",
    format: "Softcover",
    startingPrice: 34.99,
    featured: true,
  },
  {
    id: "the-everyday",
    title: "The Everyday",
    category: "Family",
    collection: "A life well lived",
    description: "The little rituals and familiar corners that make a life yours.",
    image: photo("photo-1470252649378-9c29740c9fa8"),
    imageAlt: "Golden morning light falling across a quiet countryside",
    color: "sage",
    pages: "24–80 pages",
    format: "Hardcover",
    startingPrice: 39.99,
    featured: false,
  },
  {
    id: "growing-together",
    title: "Growing Together",
    category: "Family",
    collection: "The people we love",
    description: "A warm, open-hearted home for all the years that changed you.",
    image: photo("photo-1511895426328-dc8714191300"),
    imageAlt: "A family spending a sunny afternoon together",
    color: "sand",
    pages: "24–100 pages",
    format: "Hardcover",
    startingPrice: 44.99,
    featured: false,
  },
  {
    id: "somewhere-new",
    title: "Somewhere New",
    category: "Travel",
    collection: "Far & near",
    description: "Bring home the colors, quiet moments, and unexpected turns.",
    image: photo("photo-1470770841072-f978cf4d019e"),
    imageAlt: "A lakeside mountain landscape beneath a soft blue sky",
    color: "stone",
    pages: "20–80 pages",
    format: "Hardcover",
    startingPrice: 42.99,
    featured: false,
  },
  {
    id: "the-open-road",
    title: "The Open Road",
    category: "Travel",
    collection: "Far & near",
    description: "A visual journal for long weekends and roads without a plan.",
    image: photo("photo-1464822759023-fed622ff2c3b"),
    imageAlt: "A winding trail through a mountain range",
    color: "blue",
    pages: "20–80 pages",
    format: "Hardcover",
    startingPrice: 42.99,
    featured: false,
  },
  {
    id: "our-kind-of-day",
    title: "Our Kind of Day",
    category: "Wedding",
    collection: "The people we love",
    description: "A considered keepsake for the day your story took a new shape.",
    image: photo("photo-1519741497674-611481863552"),
    imageAlt: "An intimate outdoor wedding ceremony",
    color: "rose",
    pages: "24–100 pages",
    format: "Hardcover",
    startingPrice: 59.99,
    featured: false,
  },
  {
    id: "little-seasons",
    title: "Little Seasons",
    category: "Family",
    collection: "A life well lived",
    description: "Make room for the small milestones and the everyday magic.",
    image: photo("photo-1492725764893-90b379c2b6e7"),
    imageAlt: "A parent and child sharing a quiet moment",
    color: "clay",
    pages: "24–80 pages",
    format: "Hardcover",
    startingPrice: 39.99,
    featured: false,
  },
  {
    id: "first-day-of-school",
    title: "First Day, Always",
    category: "Education",
    collection: "A life well lived",
    description: "A bright little archive of learning, growing, and trying again.",
    image: photo("photo-1497633762265-9d179a990aa6"),
    imageAlt: "Books and notes on a study table",
    color: "sage",
    pages: "32 pages",
    format: "Hardcover",
    startingPrice: 42.99,
    featured: false,
  },
  {
    id: "work-in-progress",
    title: "Work in Progress",
    category: "Business",
    collection: "A life well lived",
    description: "A polished way to bring your work, craft, and ideas together.",
    image: photo("photo-1454165804606-c3d57bc86b40"),
    imageAlt: "A notebook and papers arranged on a work desk",
    color: "stone",
    pages: "40 pages",
    format: "Hardcover",
    startingPrice: 54.99,
    featured: false,
  },
  {
    id: "the-slower-days",
    title: "The Slower Days",
    category: "Lifestyle",
    collection: "A life well lived",
    description: "A little gratitude for the rituals that make a day yours.",
    image: photo("photo-1441986300917-64674bd600d8"),
    imageAlt: "A quiet, warmly lit interior",
    color: "sand",
    pages: "24 pages",
    format: "Softcover",
    startingPrice: 34.99,
    featured: false,
  },
  {
    id: "the-memory-book",
    title: "The Memory Book",
    category: "Memories",
    collection: "A life well lived",
    description: "A blank canvas for the people and places you call yours.",
    image: photo("photo-1507842217343-583bb7270b66"),
    imageAlt: "A peaceful library of books and stories",
    color: "clay",
    pages: "48 pages",
    format: "Hardcover",
    startingPrice: 49.99,
    featured: false,
  },
];

const bookTiers = [
  {
    id: "light",
    name: "LIGHT",
    tagline: "Simple & beautiful",
    startingPrice: 32.99,
    features: ["20–40 pages", "Soft cover", "Standard paper"],
  },
  {
    id: "basic",
    name: "BASIC",
    tagline: "More to discover",
    startingPrice: 39.99,
    features: ["20–60 pages", "Hard cover options", "Premium paper"],
  },
  {
    id: "premium",
    name: "PREMIUM",
    tagline: "A keepsake for special moments",
    startingPrice: 58.99,
    features: ["20–100 pages", "Premium cover", "High-quality paper"],
  },
];

const bookGalleryPhotos = {
  Wedding: [
    ["photo-1519741497674-611481863552", "A celebration in golden afternoon light"],
    ["photo-1511285560929-80b456fea0bc", "A quiet moment from the celebration"],
    ["photo-1519225421980-715cb0215aed", "Details gathered from a special day"],
    ["photo-1511895426328-dc8714191300", "A favorite moment with the people you love"],
  ],
  Travel: [
    ["photo-1470770841072-f978cf4d019e", "A mountain lake beneath an alpine sky"],
    ["photo-1464822759023-fed622ff2c3b", "A trail through the mountains"],
    ["photo-1470252649378-9c29740c9fa8", "Soft light over a quiet landscape"],
    ["photo-1500530855697-b586d89ba3ee", "A faraway place worth remembering"],
  ],
  Family: [
    ["photo-1511895426328-dc8714191300", "A family sharing an afternoon outdoors"],
    ["photo-1492725764893-90b379c2b6e7", "A tender family moment"],
    ["photo-1511988617509-a57c8a288659", "The people who make a place feel like home"],
    ["photo-1511632765486-a01980e01a18", "A day together in the sunshine"],
  ],
};

const fallbackGalleryPhotos = [
  ["photo-1519682337058-a94d519337bc", "A favorite memory, held close"],
  ["photo-1470252649378-9c29740c9fa8", "A quiet moment in beautiful light"],
  ["photo-1500530855697-b586d89ba3ee", "A place to return to"],
  ["photo-1511895426328-dc8714191300", "A moment with the people you love"],
];

const categories = [
  {
    name: "Wedding",
    image: photo("photo-1519741497674-611481863552", 520),
    imageAlt: "An intimate outdoor wedding",
  },
  {
    name: "Travel",
    image: photo("photo-1470770841072-f978cf4d019e", 520),
    imageAlt: "A mountain lake and alpine landscape",
  },
  {
    name: "Family",
    image: photo("photo-1511895426328-dc8714191300", 520),
    imageAlt: "A family sharing an afternoon together",
  },
  {
    name: "Baby",
    image: photo("photo-1492725764893-90b379c2b6e7", 520),
    imageAlt: "A parent holding their young child",
  },
  {
    name: "Birthday",
    image: photo("photo-1558636508-e0db3814bd1d", 520),
    imageAlt: "A celebration cake with candles",
  },
  {
    name: "Portfolio",
    image: photo("photo-1455390582262-044cdead277a", 520),
    imageAlt: "A creative studio desk",
  },
  {
    name: "Memories",
    image: photo("photo-1470252649378-9c29740c9fa8", 520),
    imageAlt: "Golden morning light across a field",
  },
  {
    name: "Anniversary",
    image: photo("photo-1516589178581-6cd7833ae3b2", 520),
    imageAlt: "A couple sharing a quiet moment",
  },
  {
    name: "Photography",
    image: photo("photo-1470252649378-9c29740c9fa8", 520),
    imageAlt: "Soft light spreading across a peaceful landscape",
  },
  {
    name: "Education",
    image: photo("photo-1497633762265-9d179a990aa6", 520),
    imageAlt: "Books and notes on a study table",
  },
  {
    name: "Business",
    image: photo("photo-1454165804606-c3d57bc86b40", 520),
    imageAlt: "A work desk with notes and ideas",
  },
  {
    name: "Lifestyle",
    image: photo("photo-1441986300917-64674bd600d8", 520),
    imageAlt: "A calm, sunlit interior",
  },
  {
    name: "Custom",
    image: photo("photo-1519682337058-a94d519337bc", 520),
    imageAlt: "A collection of personal travel memories",
  },
];

const categoryDetails = [
  {
    name: "Wedding",
    description: "Gather the vows, happy tears, and familiar faces from a day that felt like yours.",
    style: "Romantic",
  },
  {
    name: "Travel",
    description: "Bring home the colors, little discoveries, and places you still think about.",
    style: "Editorial",
  },
  {
    name: "Family",
    description: "Keep the everyday rituals and people who make every place feel like home.",
    style: "Classic",
  },
  {
    name: "Baby",
    description: "Make space for all the firsts, small changes, and new beginnings.",
    style: "Playful",
  },
  {
    name: "Birthday",
    description: "Celebrate another trip around the sun with the people who made it special.",
    style: "Playful",
  },
  {
    name: "Anniversary",
    description: "A quiet collection of the years, places, and laughter you made together.",
    style: "Romantic",
  },
  {
    name: "Portfolio",
    description: "Present your creative work with a considered, tactile point of view.",
    style: "Modern",
  },
  {
    name: "Photography",
    description: "Give your favorite photographs a beautifully edited place of their own.",
    style: "Minimal",
  },
  {
    name: "Memories",
    description: "A flexible home for the photographs you want to return to most.",
    style: "Classic",
  },
  {
    name: "Education",
    description: "Remember the lessons, milestones, and people who helped you grow.",
    style: "Minimal",
  },
  {
    name: "Business",
    description: "Bring your work and ideas together in a polished printed presentation.",
    style: "Editorial",
  },
  {
    name: "Lifestyle",
    description: "Notice the everyday details and rituals that make a life your own.",
    style: "Modern",
  },
  {
    name: "Custom",
    description: "Start with a blank page and shape a photo book around your own idea.",
    style: "Classic",
  },
].map((category) => {
  const media = categories.find((item) => item.name === category.name);
  return {
    ...category,
    slug: slugify(category.name),
    image: media.image,
    imageAlt: media.imageAlt,
    heroImage: media.image.replace("w=520", "w=1400"),
    color: category.name === "Wedding" ? "rose" : "sage",
  };
});

const collections = [
  {
    name: "The people we love",
    slug: "the-people-we-love",
    eyebrow: "Together, through the years",
    description: "A place for the celebrations, the growing-up, and the in-between moments you share.",
    image: photo("photo-1511895426328-dc8714191300", 1400),
    imageAlt: "A family spending an afternoon together",
    tone: "sand",
    recommendedLayouts: ["A year together", "The celebration", "Little chapters"],
    relatedCategories: ["Family", "Wedding", "Baby", "Birthday", "Anniversary"],
  },
  {
    name: "A life well lived",
    slug: "a-life-well-lived",
    eyebrow: "The everyday, made lasting",
    description: "For the small rituals, familiar rooms, and ordinary days that turn out to be everything.",
    image: photo("photo-1470252649378-9c29740c9fa8", 1400),
    imageAlt: "Warm light over a peaceful countryside",
    tone: "sage",
    recommendedLayouts: ["A day in details", "Our favorite things", "Small celebrations"],
    relatedCategories: ["Family", "Lifestyle", "Memories", "Education", "Custom"],
  },
  {
    name: "Far & near",
    slug: "far-and-near",
    eyebrow: "A little further afield",
    description: "For the places that stay with you long after you’ve found your way back home.",
    image: photo("photo-1470770841072-f978cf4d019e", 1400),
    imageAlt: "A still lake beneath an alpine mountain range",
    tone: "blue",
    recommendedLayouts: ["The long weekend", "Postcards from here", "A map of us"],
    relatedCategories: ["Travel", "Photography", "Portfolio"],
  },
];

const styles = [
  "Minimal",
  "Editorial",
  "Luxury",
  "Modern",
  "Classic",
  "Romantic",
  "Playful",
];

const occasionByCategory = {
  Wedding: "Wedding",
  Travel: "Travel",
  Family: "Family",
  Baby: "Baby",
  Birthday: "Birthday",
  Anniversary: "Anniversary",
  Portfolio: "Creative project",
  Photography: "Creative project",
  Memories: "Everyday",
  Education: "Graduation",
  Business: "Business",
  Lifestyle: "Everyday",
  Custom: "Everyday",
};

const styleByCategory = {
  Wedding: "Romantic",
  Travel: "Editorial",
  Family: "Classic",
  Baby: "Playful",
  Birthday: "Playful",
  Anniversary: "Romantic",
  Portfolio: "Modern",
  Photography: "Minimal",
  Memories: "Classic",
  Education: "Minimal",
  Business: "Editorial",
  Lifestyle: "Modern",
  Custom: "Classic",
};

const bookTypeById = {
  "our-european-journey": "PREMIUM",
  "the-wedding-album": "PREMIUM",
  "little-moments": "LIGHT",
  "our-little-one": "BASIC",
  "a-little-celebration": "LIGHT",
  "still-us": "BASIC",
  "the-makers-book": "PREMIUM",
  "light-and-shadow": "PREMIUM",
  "our-everyday": "LIGHT",
  "the-everyday": "BASIC",
  "growing-together": "BASIC",
  "somewhere-new": "BASIC",
  "the-open-road": "BASIC",
  "our-kind-of-day": "PREMIUM",
  "little-seasons": "BASIC",
  "first-day-of-school": "BASIC",
  "work-in-progress": "PREMIUM",
  "the-slower-days": "LIGHT",
  "the-memory-book": "BASIC",
};

function slugify(value) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

const catalogBooks = demoBooks.map((book) => {
  const [pageCountMin, pageCountMax = pageCountMin] = (
    book.pages.match(/\d+/g) ?? ["24"]
  ).map(Number);
  return {
    ...book,
    slug: book.id,
    occasion: occasionByCategory[book.category] ?? "Everyday",
    style: styleByCategory[book.category] ?? "Classic",
    pageCount: pageCountMin,
    pageCountMin,
    pageCountMax,
    bookType: bookTypeById[book.id],
  };
});

const homepageFilters = [
  "All",
  "Wedding",
  "Travel",
  "Family",
  "Baby",
  "Birthday",
  "Anniversary",
  "Portfolio",
  "Photography",
  "Memories",
  "Education",
  "Business",
  "Lifestyle",
  "Custom",
];

const wait = (duration = 180) =>
  new Promise((resolve) => window.setTimeout(resolve, duration));

export const catalogService = {
  async listBooks({
    category,
    collection,
    search,
    featured,
    occasion,
    style,
    pageCount,
    bookType,
    minPrice,
    maxPrice,
    sort,
  } = {}) {
    await wait();
    const normalizedSearch = search?.trim().toLowerCase();

    const filteredBooks = catalogBooks.filter((book) => {
      const matchesCategory =
        !category ||
        category === "All" ||
        slugify(book.category) === slugify(category);
      const matchesCollection = !collection || book.collection === collection;
      const matchesSearch =
        !normalizedSearch ||
        `${book.title} ${book.category} ${book.collection} ${book.description} ${book.style} ${book.occasion} ${book.bookType}`
          .toLowerCase()
          .includes(normalizedSearch);
      const matchesFeatured =
        featured === undefined || book.featured === featured;
      const matchesOccasion = !occasion || book.occasion === occasion;
      const matchesStyle = !style || book.style === style;
      const matchesPageCount =
        !pageCount ||
        (pageCount === "49+"
          ? book.pageCountMax >= 49
          : (() => {
              const [minimum, maximum] = pageCount.split("-").map(Number);
              return (
                Number.isFinite(minimum) &&
                Number.isFinite(maximum) &&
                book.pageCountMin <= maximum &&
                book.pageCountMax >= minimum
              );
            })());
      const matchesBookType = !bookType || book.bookType === bookType;
      const parsedMinimum = minPrice === "" || minPrice == null
        ? null
        : Number(minPrice);
      const parsedMaximum = maxPrice === "" || maxPrice == null
        ? null
        : Number(maxPrice);
      const matchesMinPrice =
        parsedMinimum === null ||
        !Number.isFinite(parsedMinimum) ||
        book.startingPrice >= parsedMinimum;
      const matchesMaxPrice =
        parsedMaximum === null ||
        !Number.isFinite(parsedMaximum) ||
        book.startingPrice <= parsedMaximum;

      return (
        matchesCategory &&
        matchesCollection &&
        matchesSearch &&
        matchesFeatured &&
        matchesOccasion &&
        matchesStyle &&
        matchesPageCount &&
        matchesBookType &&
        matchesMinPrice &&
        matchesMaxPrice
      );
    });

    const sorters = {
      "price-low": (a, b) => a.startingPrice - b.startingPrice,
      "price-high": (a, b) => b.startingPrice - a.startingPrice,
      title: (a, b) => a.title.localeCompare(b.title),
      pages: (a, b) => a.pageCount - b.pageCount,
      featured: (a, b) =>
        Number(b.featured) - Number(a.featured) ||
        a.title.localeCompare(b.title),
    };

    return [...filteredBooks].sort(sorters[sort] ?? sorters.featured);
  },

  async getBook(id) {
    await wait();
    return catalogBooks.find((book) => book.id === id) ?? null;
  },

  async getBookDetails(id) {
    await wait();
    const book = catalogBooks.find((item) => item.id === id);
    if (!book) return null;

    const galleryPhotos = bookGalleryPhotos[book.category] ?? fallbackGalleryPhotos;
    const pageRanges = {
      LIGHT: ["20", "24", "32", "40"],
      BASIC: ["20", "24", "32", "40", "60"],
      PREMIUM: ["20", "24", "32", "40", "60", "80", "100"],
    }[book.bookType];

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
      deliveryInformation:
        "Carefully packed and shipped to your home. Delivery timing varies by destination.",
      gallery: [
        { image: book.image, imageAlt: book.imageAlt, label: "Cover" },
        ...galleryPhotos.map(([id, imageAlt], index) => ({
          image: photo(id, 1200),
          imageAlt,
          label: `Inside page ${index + 1}`,
        })),
      ],
    };
  },

  async listRelatedBooks(id) {
    await wait();
    const book = catalogBooks.find((item) => item.id === id);
    if (!book) return [];
    return catalogBooks
      .filter((item) => item.id !== id && (item.category === book.category || item.collection === book.collection))
      .sort((first, second) =>
        Number(second.category === book.category) - Number(first.category === book.category),
      );
  },

  async listCategories() {
    await wait();
    return categoryDetails;
  },

  async getCategory(slug) {
    await wait();
    return categoryDetails.find((category) => category.slug === slug) ?? null;
  },

  async listCollections() {
    await wait();
    return collections;
  },

  async getCollection(slug) {
    await wait();
    return collections.find((collection) => collection.slug === slug) ?? null;
  },

  async listFilterOptions() {
    await wait();
    return {
      categories: categoryDetails.map(({ name }) => name),
      occasions: [...new Set(Object.values(occasionByCategory))],
      styles,
      pageCounts: ["20-24", "25-32", "33-48", "49+"],
      bookTypes: bookTiers.map(({ name }) => name),
    };
  },

  async listFeaturedCategories() {
    await wait();
    return categoryDetails;
  },

  async listHomepageFilters() {
    await wait();
    return homepageFilters;
  },

  async listBookTiers() {
    await wait();
    return bookTiers;
  },
};
