import { apiRequest } from "./apiClient.js";
import { paymentMethodService } from "./paymentMethodService.js";

const API_ROOT = "/pdf";
const paymentStates = new Set(["pending", "successful", "failed", "partially_refunded", "refunded"]);
const generationStates = new Set(["queued", "generating", "ready", "failed", "not_started"]);

async function request(path, options = {}) {
  const { data } = await apiRequest(`${API_ROOT}${path}`, options);
  if (!data || typeof data !== "object") throw new Error("PDF service returned an invalid response.");
  return data;
}

function normalizeOffer(offer) {
  if (!offer || typeof offer !== "object" || typeof offer.currency !== "string" || !offer.currency.trim()) {
    throw new Error("PDF pricing is not available from the payment service.");
  }
  if (offer.amount === null || offer.amount === undefined || offer.amount === "") {
    throw new Error("PDF pricing returned no amount.");
  }
  const amount = Number(offer.amount);
  if (!Number.isFinite(amount) || amount < 0) throw new Error("PDF pricing returned an invalid amount.");
  return { amount, currency: offer.currency, description: offer.description ?? "High-quality PDF download" };
}

function normalizeDownloadUrl(url) {
  if (typeof url !== "string" || !url.trim()) return null;
  try {
    const parsed = new URL(url, globalThis.location?.origin ?? "https://memorybook.invalid");
    if (parsed.protocol !== "https:" && parsed.origin !== globalThis.location?.origin) return null;
    return url;
  } catch {
    return null;
  }
}

export function normalizePdfOrder(order) {
  if (!order || typeof order !== "object" || typeof order.id !== "string" || !order.id) {
    throw new Error("PDF service returned an invalid order.");
  }
  if (!paymentStates.has(order.paymentStatus) || !generationStates.has(order.generationStatus)) {
    throw new Error("PDF service returned an unsupported payment or generation status.");
  }
  const downloadUrl = order.paymentStatus === "successful" && order.generationStatus === "ready"
    ? normalizeDownloadUrl(order.downloadUrl)
    : null;
  const checkoutUrl = order.paymentStatus === "pending" ? normalizeDownloadUrl(order.checkoutUrl) : null;
  return {
    ...order,
    bookTitle: order.bookTitle ?? order.title ?? "MemoryBook PDF",
    amount: order.amount !== null && order.amount !== undefined && order.amount !== "" && Number.isFinite(Number(order.amount))
      ? Number(order.amount)
      : null,
    currency: typeof order.currency === "string" ? order.currency : null,
    downloadUrl,
    checkoutUrl,
  };
}

export function canDownloadPdf(order) {
  return order?.paymentStatus === "successful"
    && order?.generationStatus === "ready"
    && typeof order.downloadId === "string"
    && order.downloadId.length > 0;
}

export const pdfOrderService = {
  async getOffer(projectId) {
    const offer = await request(`/offer?projectId=${encodeURIComponent(projectId)}`);
    return normalizeOffer(offer);
  },

  async getPaymentMethods(currency) {
    return paymentMethodService.list(currency);
  },

  async createOrder(projectId, paymentMethod) {
    const order = await request("/orders", {
      method: "POST",
      body: {
        projectId,
        provider: paymentMethod?.provider,
        paymentMethod: paymentMethod?.method,
      },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    return normalizePdfOrder(order);
  },

  async getOrder(orderId) {
    const order = await request(`/orders/${encodeURIComponent(orderId)}`);
    return normalizePdfOrder(order);
  },

  async listDownloads() {
    const result = await request("/downloads");
    if (!Array.isArray(result.items)) throw new Error("PDF service returned an invalid download history.");
    return result.items;
  },

  async getDownload(downloadId) {
    const result = await request(`/downloads/${encodeURIComponent(downloadId)}`);
    const download = result.download;
    if (!download || typeof download.id !== "string" || typeof download.url !== "string") {
      throw new Error("PDF service returned an invalid secure download.");
    }
    const url = normalizeDownloadUrl(download.url);
    if (!url) throw new Error("PDF service returned an unsafe download URL.");
    return { ...download, url };
  },

  async listOrders() {
    const result = await request("/orders");
    if (!Array.isArray(result.items)) throw new Error("PDF service returned an invalid order history.");
    return result.items.map(normalizePdfOrder);
  },
};
