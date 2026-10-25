export function formatCurrency(value, currency = "USD") {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "Price unavailable";

  const code = typeof currency === "string" && /^[A-Za-z]{3}$/.test(currency)
    ? currency.toUpperCase()
    : "USD";

  return new Intl.NumberFormat("en-PK", {
    style: "currency",
    currency: code,
  }).format(amount);
}
