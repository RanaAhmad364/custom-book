const photo = (id) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=900&q=85`;

export function createDashboardData(email) {
  const owner = email.trim().toLowerCase();
  const seed = owner.split("").reduce((total, character) => total + character.charCodeAt(0), 0);
  const ownerName = owner.split("@")[0].replace(/[._-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

  return {
    owner,
    profile: {
      name: ownerName || "MemoryBook member",
      email: owner,
      phone: "",
      photo: "",
      emailUpdates: true,
      orderUpdates: true,
      inspiration: false,
    },
    projects: [
      { id: `project-${seed}-1`, title: "Our weekend in the hills", category: "Travel", image: photo("photo-1470770841072-f978cf4d019e"), status: "draft", updated: "Today", progress: 68, pages: 24 },
      { id: `project-${seed}-2`, title: "The little things", category: "Family", image: photo("photo-1511895426328-dc8714191300"), status: "draft", updated: "Yesterday", progress: 32, pages: 20 },
      { id: `project-${seed}-3`, title: "A day to remember", category: "Wedding", image: photo("photo-1519741497674-611481863552"), status: "completed", updated: "Oct 12, 2026", progress: 100, pages: 40 },
      { id: `project-${seed}-4`, title: "First summer together", category: "Family", image: photo("photo-1492725764893-90b379c2b6e7"), status: "draft", updated: "Oct 09, 2026", progress: 54, pages: 28 },
    ],
    orders: [
      { id: `MB-${String(seed).slice(-3)}-2841`, title: "A day to remember", image: photo("photo-1519741497674-611481863552"), date: "Oct 12, 2026", payment: "Paid", status: "In production", tracking: "Tracking details will appear once your book ships.", total: "$84.00" },
      { id: `MB-${String(seed).slice(-3)}-1976`, title: "Little moments, lately", image: photo("photo-1511895426328-dc8714191300"), date: "Sep 28, 2026", payment: "Paid", status: "Delivered", tracking: "Delivered to your saved address.", total: "$62.50" },
    ],
    downloads: [
      { id: `PDF-${String(seed).slice(-3)}-061`, title: "The year we found our way", date: "Oct 16, 2026", status: "Ready", size: "38.4 MB", image: photo("photo-1470252649378-9c29740c9fa8") },
      { id: `PDF-${String(seed).slice(-3)}-052`, title: "Our European Journey", date: "Oct 08, 2026", status: "Generating", size: "Preparing your file", image: photo("photo-1470770841072-f978cf4d019e") },
    ],
    notifications: [
      { id: "note-order", category: "Order", title: "Your book is being made", message: "A day to remember is now in production.", date: "2 hours ago", read: false },
      { id: "note-download", category: "Download", title: "Your PDF is ready", message: "The year we found our way is ready to download.", date: "Yesterday", read: false },
      { id: "note-design", category: "Design tip", title: "A little layout inspiration", message: "Try a full-bleed image to give a favorite moment room to breathe.", date: "Oct 14, 2026", read: true },
    ],
    billing: [
      { id: "INV-2841", date: "Oct 12, 2026", description: "A day to remember · Hardcover", amount: "$84.00", status: "Paid" },
      { id: "INV-1976", date: "Sep 28, 2026", description: "Little moments, lately · PDF + print", amount: "$62.50", status: "Paid" },
    ],
    addresses: [],
    settings: { orderEmails: true, productNews: false, twoStep: false },
  };
}
