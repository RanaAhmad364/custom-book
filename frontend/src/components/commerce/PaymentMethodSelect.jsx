import "./PaymentMethodSelect.css";

export function PaymentMethodSelect({ methods, value, onChange, loading = false, usdAmount, exchangeRate }) {
  const selected = methods.find((method) => method.id === value);
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
    {selected?.provider === "paypal" && Number.isFinite(Number(usdAmount)) && exchangeRate
      ? <p className="payment-method-instructions" role="note">
        PayPal will charge {new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(usdAmount))}
        {" "}at {new Intl.NumberFormat(undefined, { maximumSignificantDigits: 8 }).format(Number(exchangeRate))} USD per PKR.
      </p>
      : null}
  </div>;
}
