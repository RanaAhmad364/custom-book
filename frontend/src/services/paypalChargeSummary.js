function amount(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "unavailable";
}

export function paypalChargeSummary({ orderCurrency, usdAmount, pkrAmount, exchangeRate }) {
  const usd = Number(usdAmount);
  const usdLabel = Number.isFinite(usd)
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(usd)
    : "USD amount unavailable";
  const rate = Number(exchangeRate);
  const pkrValue = Number(pkrAmount);
  const hasPkrSnapshot = orderCurrency?.toUpperCase() === "PKR"
    && Number.isFinite(pkrValue)
    && Number.isFinite(rate)
    && rate > 0;
  return `You will be charged ${usdLabel} USD${hasPkrSnapshot ? ` (PKR ${amount(pkrAmount)})` : ""}.`;
}
