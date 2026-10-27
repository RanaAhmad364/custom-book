import { apiRequest, apiUrl } from "./apiClient.js";

export const paymentMethodService = {
  async list(currency) {
    if (typeof currency !== "string" || !/^[A-Za-z]{3}$/.test(currency)) {
      throw new Error("A valid currency is required to load payment methods.");
    }
    let response;
    try {
      response = await fetch(apiUrl(`/payments/methods?currency=${encodeURIComponent(currency.toUpperCase())}`), {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
    } catch (failure) {
      throw new Error(failure instanceof Error ? `Payment methods are unavailable: ${failure.message}` : "Payment methods are unavailable.");
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.message || `Payment methods could not be loaded (${response.status}).`);
    if (!payload || payload.currency !== currency.toUpperCase() || !Array.isArray(payload.items)) {
      throw new Error("Payment service returned an invalid method list.");
    }
    return payload.items.map((method) => {
      if (
        !method
        || typeof method.provider !== "string"
        || typeof method.method !== "string"
        || typeof method.label !== "string"
      ) {
        throw new Error("Payment service returned an invalid payment method.");
      }
      return { ...method, id: `${method.provider}:${method.method}` };
    });
  },

  async submitManualReference(paymentId, reference) {
    if (typeof paymentId !== "string" || !paymentId || typeof reference !== "string" || !reference.trim()) {
      throw new Error("Enter the transfer reference shown on your receipt.");
    }
    const { data } = await apiRequest(`/payments/${encodeURIComponent(paymentId)}/manual-confirmation`, {
      method: "POST",
      body: { reference: reference.trim() },
    });
    if (!data?.payment || data.payment.status !== "pending") {
      throw new Error("The payment service returned an invalid manual payment status.");
    }
    return data.payment;
  },
};
