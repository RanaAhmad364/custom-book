import { useEffect, useState } from "react";
import { PayPalButtons, PayPalScriptProvider, usePayPalScriptReducer } from "@paypal/react-paypal-js";
import { paypalPaymentService } from "../../services/paypalPaymentService.js";

const clientId = import.meta.env.VITE_PAYPAL_CLIENT_ID?.trim();

function currency(value, code) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${code} amount unavailable`;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: code,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function number(value) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "unavailable";
}

export function PayPalSmartCheckout({
  paymentId,
  pkrAmount,
  usdAmount,
  onSuccess,
  onRetry,
}) {
  const [message, setMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [renderKey, setRenderKey] = useState(0);
  const [scriptKey, setScriptKey] = useState(0);
  const [retryRequired, setRetryRequired] = useState(false);
  const [needsReview, setNeedsReview] = useState(false);

  if (!clientId) {
    return <p className="paypal-smart-error" role="alert">
      PayPal checkout is enabled, but VITE_PAYPAL_CLIENT_ID is not configured in the frontend.
    </p>;
  }

  async function createOrder() {
    setMessage("");
    setNeedsReview(false);
    const result = await paypalPaymentService.createOrder(paymentId);
    return result.paypalOrderId;
  }

  async function captureOrder(data) {
    try {
      const result = await paypalPaymentService.captureOrder(paymentId, data.orderID);
      if (result.status === "needs_review") {
        setNeedsReview(true);
        setRetryRequired(false);
        setMessage("PayPal reports that your payment needs review. Please do not pay again; the MemoryBook team will review it.");
        return;
      }
      if (result.status !== "successful") {
        setNeedsReview(false);
        setRetryRequired(true);
        setMessage("PayPal did not complete the payment. Retry checkout to try again.");
        return;
      }
      setRetryRequired(false);
      await onSuccess?.(result);
    } catch (failure) {
      setNeedsReview(false);
      setMessage(failure instanceof Error
        ? `${failure.message} You can retry checkout.`
        : "PayPal could not confirm the payment. You can retry checkout.");
      setRetryRequired(false);
    }
  }

  function cancelOrder() {
    setRetryRequired(false);
    setMessage("PayPal checkout was cancelled. Retry when you are ready to pay.");
  }

  async function handleRetry() {
    setRetrying(true);
    setMessage("");
    try {
      if (retryRequired) await onRetry?.();
      setRetryRequired(false);
      setScriptKey((key) => key + 1);
      setRenderKey((key) => key + 1);
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : "The payment could not be retried.");
    } finally {
      setRetrying(false);
    }
  }

  return <section className="paypal-smart-checkout" aria-label="PayPal checkout">
    <p className="paypal-charge-summary">
      You will be charged {currency(usdAmount, "USD")} USD
      {pkrAmount !== null && pkrAmount !== undefined && pkrAmount !== ""
        ? ` (PKR ${number(pkrAmount)})`
        : ""}.
    </p>
    <PayPalScriptProvider key={scriptKey} options={{ "client-id": clientId, currency: "USD", intent: "capture" }}>
      <PayPalButtonsState
        renderKey={renderKey}
        createOrder={createOrder}
        captureOrder={captureOrder}
        cancelOrder={cancelOrder}
        setMessage={setMessage}
        onError={() => {
          setMessage("PayPal could not complete checkout. Check your connection and try again.");
          setRetryRequired(false);
        }}
      />
    </PayPalScriptProvider>
    {message ? <p className="paypal-smart-error" role="alert">{message}</p> : null}
    {message && !needsReview ? <button className="button button-outline" type="button" onClick={handleRetry} disabled={retrying}>
      {retrying ? "Preparing retry…" : "Try PayPal again"}
    </button> : null}
  </section>;
}

function PayPalButtonsState({ renderKey, createOrder, captureOrder, cancelOrder, onError, setMessage }) {
  const [{ isPending, isRejected }] = usePayPalScriptReducer();
  useEffect(() => {
    if (isRejected) setMessage("The PayPal checkout could not load. Check your connection and try again.");
  }, [isRejected, setMessage]);
  if (isRejected) {
    return null;
  }
  if (isPending) return <p role="status">Loading secure PayPal checkout…</p>;
  return <PayPalButtons
    key={renderKey}
    createOrder={createOrder}
    onApprove={captureOrder}
    onCancel={cancelOrder}
    onError={onError}
    style={{ layout: "vertical", shape: "rect", label: "pay" }}
  />;
}
