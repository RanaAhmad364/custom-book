import { apiRequest } from "./apiClient.js";
import { paymentMethodService } from "./paymentMethodService.js";

const API_ROOT = "/print";
const paymentStates = new Set(["pending", "successful", "failed", "partially_refunded", "refunded"]);
const productionStates = [
  "order_placed",
  "payment_confirmed",
  "design_verified",
  "in_production",
  "quality_check",
  "packed",
  "printed",
  "shipped",
  "out_for_delivery",
  "delivered",
  "cancelled",
  "refunded",
];
const cancellationStates = new Set(["requested", "accepted", "rejected", "pending"]);

async function request(path, options = {}) {
  const { data } = await apiRequest(`${API_ROOT}${path}`, options);
  if (!data || typeof data !== "object") throw new Error("Printing service returned an invalid response.");
  return data;
}

function amount(value, label, nullable = false) {
  if (nullable && (value === null || value === undefined)) return null;
  if (value === null || value === undefined || value === "") throw new Error(`Printing quote omitted ${label}.`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Printing quote returned an invalid ${label}.`);
  return parsed;
}

export function normalizePrintQuote(quote) {
  if (!quote || typeof quote !== "object" || typeof quote.id !== "string" || !quote.id.trim()) {
    throw new Error("Printing service returned an invalid quote.");
  }
  if (typeof quote.currency !== "string" || !quote.currency.trim()) {
    throw new Error("Printing quote did not include a currency.");
  }
  if (typeof quote.taxApplicable !== "boolean") {
    throw new Error("Printing quote did not specify whether tax applies.");
  }
  if (!quote.productionEstimate || !quote.deliveryEstimate) {
    throw new Error("Printing quote omitted production or delivery estimates.");
  }

  const tax = quote.taxApplicable ? amount(quote.tax, "tax") : amount(quote.tax ?? 0, "tax");
  if (!quote.taxApplicable && tax !== 0) throw new Error("Printing quote included tax while marking it as not applicable.");
  return {
    ...quote,
    bookPrice: amount(quote.bookPrice, "book price"),
    printingCharge: amount(quote.printingCharge, "printing charge"),
    additionalPages: amount(quote.additionalPages, "additional-page charge"),
    shipping: amount(quote.shipping, "shipping"),
    discount: amount(quote.discount, "discount"),
    tax,
    total: amount(quote.total, "total"),
    currency: quote.currency.trim(),
  };
}

function normalizeProductionStatus(status) {
  const normalized = String(status ?? "").trim().toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
  if (!productionStates.includes(normalized)) throw new Error("Printing service returned an unsupported production status.");
  return normalized;
}

function normalizeCheckoutUrl(url) {
  if (typeof url !== "string" || !url.trim()) return null;
  try {
    const parsed = new URL(url, globalThis.location?.origin ?? "https://memorybook.invalid");
    if (parsed.protocol !== "https:" && parsed.origin !== globalThis.location?.origin) return null;
    return url;
  } catch {
    return null;
  }
}

export function normalizePrintOrder(order) {
  if (!order || typeof order !== "object" || typeof order.id !== "string" || !order.id.trim()) {
    throw new Error("Printing service returned an invalid order.");
  }
  if (!paymentStates.has(order.paymentStatus)) {
    throw new Error("Printing service returned an unsupported payment status.");
  }
  const quote = normalizePrintQuote(order.quote);
  const normalized = {
    ...order,
    productionStatus: normalizeProductionStatus(order.productionStatus),
    checkoutUrl: order.paymentStatus === "pending" ? normalizeCheckoutUrl(order.checkoutUrl) : null,
    quote,
    productionEstimate: order.productionEstimate ?? quote.productionEstimate,
    deliveryEstimate: order.deliveryEstimate ?? quote.deliveryEstimate,
  };
  if (order.cancellationStatus && !cancellationStates.has(order.cancellationStatus)) {
    throw new Error("Printing service returned an unsupported cancellation status.");
  }
  return normalized;
}

export const printOrderService = {
  async getQuote(projectId, configuration, shippingAddress) {
    const quote = await request("/quotes", {
      method: "POST",
      body: { projectId, configuration, shippingAddress },
    });
    return normalizePrintQuote(quote);
  },

  async getPaymentMethods(currency) {
    return paymentMethodService.list(currency);
  },

  async createOrder(projectId, configuration, shippingAddress, quoteId, paymentMethod) {
    if (!quoteId) throw new Error("Refresh the server quote before placing your print order.");
    const order = await request("/orders", {
      method: "POST",
      body: {
        projectId,
        configuration,
        shippingAddress,
        quoteId,
        provider: paymentMethod?.provider,
        paymentMethod: paymentMethod?.method,
      },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    return normalizePrintOrder(order);
  },

  async getOrder(orderId) {
    return normalizePrintOrder(await request(`/orders/${encodeURIComponent(orderId)}`));
  },

  async listOrders() {
    const result = await request("/orders");
    if (!Array.isArray(result.items)) throw new Error("Printing service returned an invalid order history.");
    return result.items.map(normalizePrintOrder);
  },

  async requestCancellation(orderId, reason) {
    if (typeof reason !== "string" || reason.trim().length < 5) {
      throw new Error("Add a short reason for your cancellation request.");
    }
    const result = await request(`/orders/${encodeURIComponent(orderId)}/cancellation-requests`, {
      method: "POST",
      body: { reason },
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    if (!cancellationStates.has(result.status)) {
      throw new Error("Printing service returned an unsupported cancellation request status.");
    }
    return { status: result.status, message: typeof result.message === "string" ? result.message : "" };
  },
};
