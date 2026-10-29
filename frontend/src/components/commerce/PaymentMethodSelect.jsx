import "./PaymentMethodSelect.css";

export function PaymentMethodSelect({
  methods,
  value,
  onChange,
  loading = false,
  pkrAmount,
  usdAmount,
  exchangeRate,
}) {
  const selected = methods.find((method) => method.id === value);
  const hasPkrAmount = pkrAmount !== null && pkrAmount !== undefined && pkrAmount !== "";
  const resolvedPkrAmount = hasPkrAmount && Number.isFinite(Number(pkrAmount))
    ? Number(pkrAmount)
    : usdAmount !== null && usdAmount !== undefined && usdAmount !== ""
      && exchangeRate !== null && exchangeRate !== undefined && exchangeRate !== ""
      && Number.isFinite(Number(usdAmount)) && Number.isFinite(Number(exchangeRate))
      ? Number(usdAmount) / Number(exchangeRate)
      : null;
  return <div className="payment-method-select">
    <label htmlFor="payment-method">Payment method</label>
    {methods.length ? <select
      id="payment-method"
      value={value}
      disabled={loading}
      onChange={(event) => onChange(methods.find((method) => method.id === event.target.value) ?? null)}
    >
      {methods.map((method) => <option key={method.id} value={method.id}>{method.label}</option>)}
    </select> : <p role="status">{loading ? "Loading available payment methods…" : "No verified payment methods are currently available for this currency."}</p>}
    {selected?.instructions ? <div className="payment-method-instructions" role="note">
      {Object.entries(selected.instructions).filter(([, detail]) => detail).map(([key, detail]) => (
        <p key={key}><strong>{key.replaceAll(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase())}:</strong> {detail}</p>
      ))}
    </div> : null}
    {selected?.provider === "paypal" && usdAmount !== null && usdAmount !== undefined && usdAmount !== ""
      && Number.isFinite(Number(usdAmount)) && resolvedPkrAmount !== null
      ? <p className="payment-method-instructions" role="note">
        You will be charged {new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(usdAmount))}
        {" "}USD (PKR {resolvedPkrAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}).
      </p>
      : null}
  </div>;
}
