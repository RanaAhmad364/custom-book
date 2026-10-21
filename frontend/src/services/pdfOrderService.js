const API_ROOT = "/api/pdf";
const paymentStates = new Set(["pending", "successful", "failed"]);
const generationStates = new Set(["queued", "generating", "ready", "failed", "not_started"]);

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      credentials: "include",
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (failure) {
    throw new Error(failure instanceof Error ? `PDF service is unavailable: ${failure.message}` : "PDF service is unavailable.");
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.message || `PDF service request failed (${response.status}).`);
  }
  if (!body || typeof body !== "object") throw new Error("PDF service returned an invalid response.");
  return body;
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
    && typeof order.downloadUrl === "string"
    && order.downloadUrl.length > 0;
}

export const pdfOrderService = {
  async getOffer(projectId) {
    const offer = await request(`/offer?projectId=${encodeURIComponent(projectId)}`);
    return normalizeOffer(offer);
  },

  async createOrder(projectId) {
    const order = await request("/orders", {
      method: "POST",
      body: JSON.stringify({ projectId }),
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
    return result.items.map(normalizePdfOrder);
  },

  async getDownload(downloadId) {
    const order = await request(`/downloads/${encodeURIComponent(downloadId)}`);
    return normalizePdfOrder(order);
  },
};
