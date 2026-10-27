const STATUS_LABELS = {
  pending_payment: "Placed",
  order_placed: "Placed",
  payment_confirmed: "Payment confirmed",
  processing: "Processing",
  printed: "Printed",
  shipped: "Shipped",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
};

export function orderTimelineLabel(status) {
  return STATUS_LABELS[status] || String(status || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function normalizeOrderTimeline(items = []) {
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item.status === "string" && typeof item.createdAt === "string")
    .map((item, index) => ({ ...item, id: item.id || `${item.status}-${item.createdAt}-${index}` }))
    .sort((left, right) => new Date(left.createdAt) - new Date(right.createdAt));
}
