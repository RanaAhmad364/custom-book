import { apiRequest } from "./apiClient.js";

function paymentPath(paymentId, action) {
  if (typeof paymentId !== "string" || !paymentId.trim()) {
    throw new Error("A payment reference is required for PayPal checkout.");
  }
  return `/payments/${encodeURIComponent(paymentId)}/paypal/${action}`;
}

export const paypalPaymentService = {
  async createOrder(paymentId) {
    const { data } = await apiRequest(paymentPath(paymentId, "create-order"), {
      method: "POST",
    });
    if (
      !data
      || typeof data.paypalOrderId !== "string"
      || !data.paypalOrderId
      || !Number.isFinite(Number(data.chargedAmountUsd))
      || !Number.isFinite(Number(data.rate))
    ) {
      throw new Error("Payment service returned an invalid PayPal order.");
    }
    return data;
  },

  async captureOrder(paymentId, paypalOrderId) {
    if (typeof paypalOrderId !== "string" || !paypalOrderId.trim()) {
      throw new Error("PayPal did not provide an order reference to capture.");
    }
    const { data } = await apiRequest(paymentPath(paymentId, "capture-order"), {
      method: "POST",
      body: { paypalOrderId },
    });
    if (!data || !["successful", "failed"].includes(data.status)) {
      throw new Error("Payment service returned an invalid PayPal capture status.");
    }
    return data;
  },
};
