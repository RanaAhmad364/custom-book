import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BadgeCheck, BookOpen, Check, CircleAlert, Clock3, LoaderCircle, MapPin, PackageCheck, Printer, RefreshCw, ShieldCheck, Truck } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../../features/auth/AuthContext.jsx";
import { PaymentMethodSelect } from "../../../components/commerce/PaymentMethodSelect.jsx";
import { ManualPaymentPanel } from "../../../components/commerce/ManualPaymentPanel.jsx";
import { PayPalSmartCheckout } from "../../../components/commerce/PayPalSmartCheckout.jsx";
import { printOrderService } from "../../../services/printOrderService.js";
import { projectService } from "../../../services/projectService.js";
import "./PrintOrder.css";

const steps = [
  { id: "print", label: "Book" },
  { id: "tier", label: "Tier" },
  { id: "paper", label: "Paper" },
  { id: "cover", label: "Cover" },
  { id: "quantity", label: "Quantity" },
  { id: "shipping", label: "Delivery" },
  { id: "checkout", label: "Review" },
];

const tierOptions = [
  { id: "light", title: "LIGHT", description: "A simple, thoughtful way to hold your story." },
  { id: "basic", title: "BASIC", description: "A balanced everyday keepsake with a little more finish." },
  { id: "premium", title: "PREMIUM", description: "A considered keepsake with elevated materials and finish." },
];

const paperOptions = [
  { id: "standard", title: "Standard", description: "A smooth, versatile finish for everyday stories." },
  { id: "premium", title: "Premium", description: "A richer feel with a refined print surface." },
  { id: "archival", title: "Archival", description: "A substantial paper option for lasting keepsakes." },
];

const coverOptions = [
  { id: "softcover", title: "Softcover", description: "A flexible cover with a clean, contemporary feel." },
  { id: "hardcover", title: "Hardcover", description: "A sturdy, classic book finish." },
  { id: "layflat", title: "Layflat", description: "A seamless opening for wide photographs and spreads." },
];

const productionSteps = [
  ["pending_payment", "Pending payment"],
  ["order_placed", "Order placed"],
  ["payment_confirmed", "Payment confirmed"],
  ["processing", "Processing"],
  ["printed", "Printed"],
  ["shipped", "Shipped"],
  ["out_for_delivery", "Out for delivery"],
  ["delivered", "Delivered"],
  ["cancelled", "Cancelled"],
  ["refunded", "Refunded"],
];

const emptyAddress = { fullName: "", line1: "", line2: "", city: "", region: "", postalCode: "", country: "", phone: "" };

function formatPrice(value, currency) {
  if (!Number.isFinite(Number(value)) || !currency) return "Price unavailable";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
  } catch {
    return `${currency} ${Number(value).toFixed(2)}`;
  }
}

function formatDate(value) {
  if (!value) return "Not provided by the service";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(parsed);
}

function readConfiguration(owner, projectId) {
  const key = `memorybook-print:${owner}::${projectId}`;
  try {
    const saved = sessionStorage.getItem(key);
    if (!saved) return { tier: "basic", paper: "standard", cover: "hardcover", quantity: 1, discountCode: "", address: emptyAddress };
    const parsed = JSON.parse(saved);
    return {
      tier: tierOptions.some((item) => item.id === parsed.tier) ? parsed.tier : "basic",
      paper: paperOptions.some((item) => item.id === parsed.paper) ? parsed.paper : "standard",
      cover: coverOptions.some((item) => item.id === parsed.cover) ? parsed.cover : "hardcover",
      quantity: Number.isInteger(parsed.quantity) && parsed.quantity > 0 && parsed.quantity <= 100 ? parsed.quantity : 1,
      discountCode: typeof parsed.discountCode === "string" ? parsed.discountCode.slice(0, 80) : "",
      address: { ...emptyAddress, ...(parsed.address ?? {}) },
    };
  } catch (failure) {
    throw new Error(failure instanceof Error ? `Saved print selections could not be read: ${failure.message}` : "Saved print selections could not be read.");
  }
}

function usePrintProject(projectId) {
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const saved = await projectService.getProject(user.email, projectId);
      if (!saved?.document) throw new Error("This saved book could not be found in your account.");
      setProject(saved);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Your saved book could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [projectId, user.email]);
  useEffect(() => { reload(); }, [reload]);
  return { project, loading, error, reload };
}

function PageHeading({ eyebrow, title, description }) {
  return <header className="print-page-heading"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></header>;
}

function LoadError({ loading, error, onRetry }) {
  if (loading) return <div className="print-message"><LoaderCircle className="print-spin" size={20} /> Loading your saved book…</div>;
  if (error) return <div className="print-message print-error" role="alert"><CircleAlert size={19} /><span>{error}</span><button className="button button-outline" type="button" onClick={onRetry}><RefreshCw size={14} /> Try again</button></div>;
  return null;
}

function BookSummary({ project }) {
  const document = project.document;
  return <section className="print-book-summary" aria-label="Book details">
    <span className="print-book-icon"><BookOpen size={22} /></span>
    <div><span className="eyebrow">Your saved book</span><h2>{document.metadata.title}</h2><p>{document.book.pageCount} pages <span>·</span> {document.book.size.width} × {document.book.size.height} in</p></div>
    <Link to={`/create/design/${encodeURIComponent(project.id)}`} className="print-inline-link">Edit book <ArrowRight size={14} /></Link>
  </section>;
}

function StepNavigation({ active }) {
  const activeIndex = steps.findIndex((step) => step.id === active);
  return <nav className="print-steps" aria-label="Print order steps">{steps.map((step, index) => <span className={index === activeIndex ? "active" : index < activeIndex ? "complete" : ""} key={step.id}><i>{index < activeIndex ? <Check size={13} /> : index + 1}</i><span>{step.label}</span></span>)}</nav>;
}

function OptionCards({ items, value, onChange, name }) {
  return <div className="print-option-grid">{items.map((item) => <label className={`print-option-card${value === item.id ? " selected" : ""}`} key={item.id}>
    <input type="radio" name={name} value={item.id} checked={value === item.id} onChange={() => onChange(item.id)} />
    <span className="print-option-check"><Check size={14} /></span>
    <strong>{item.title}</strong><small>{item.description}</small>
  </label>)}</div>;
}

function QuoteBreakdown({ quote, compact = false }) {
  if (!quote) return <div className="print-quote-unavailable"><CircleAlert size={17} /><span>A current server quote is not available. No prices are estimated in this browser.</span></div>;
  return <section className={`print-quote${compact ? " compact" : ""}`} aria-label="Server-calculated quote">
    <div><span>Book price</span><strong>{formatPrice(quote.bookPrice, quote.currency)}</strong></div>
    <div><span>Printing charge</span><strong>{formatPrice(quote.printingCharge, quote.currency)}</strong></div>
    <div><span>Additional pages</span><strong>{formatPrice(quote.additionalPages, quote.currency)}</strong></div>
    <div><span>Shipping</span><strong>{formatPrice(quote.shipping, quote.currency)}</strong></div>
    <div><span>Discount</span><strong>{quote.discount ? `−${formatPrice(quote.discount, quote.currency)}` : formatPrice(0, quote.currency)}</strong></div>
    <div><span>Tax</span><strong>{quote.taxApplicable ? formatPrice(quote.tax, quote.currency) : "Not applicable"}</strong></div>
    <div className="print-quote-total"><span>Total</span><strong>{formatPrice(quote.total, quote.currency)}</strong></div>
    <p>Quote supplied by the printing service. It may change if your configuration or delivery details change.</p>
  </section>;
}

export function PrintOrderFlow() {
  const { projectId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { project, loading, error: projectError, reload } = usePrintProject(projectId);
  const currentStep = location.pathname.split("/").filter(Boolean).at(-1) || "print";
  const step = steps.some((item) => item.id === currentStep) ? currentStep : "print";
  const configKey = `memorybook-print:${user.email.trim().toLowerCase()}::${projectId}`;
  const [configuration, setConfiguration] = useState(() => readConfiguration(user.email.trim().toLowerCase(), projectId));
  const [storageError, setStorageError] = useState("");
  const [quote, setQuote] = useState(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState("");
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [methodsLoading, setMethodsLoading] = useState(false);
  const [methodsError, setMethodsError] = useState("");
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [paypalCheckoutOrder, setPaypalCheckoutOrder] = useState(null);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const locationReady = Boolean(
    configuration.address.country
    && configuration.address.fullName.trim()
    && configuration.address.line1.trim()
    && configuration.address.city.trim()
    && configuration.address.region.trim()
    && configuration.address.postalCode.trim()
    && configuration.address.phone.trim(),
  );

  useEffect(() => {
    try {
      sessionStorage.setItem(configKey, JSON.stringify(configuration));
      setStorageError("");
    } catch (failure) {
      setStorageError(failure instanceof Error ? `Print selections could not be saved for this tab: ${failure.message}` : "Print selections could not be saved for this tab.");
    }
  }, [configKey, configuration]);

  useEffect(() => {
    let active = true;
    let timer;
    setQuote(null);
    setQuoteError("");
    if (!project || !locationReady) {
      setQuoteLoading(false);
      return () => { active = false; };
    }
    setQuoteLoading(true);
    timer = window.setTimeout(() => {
      printOrderService.getQuote(projectId, {
        tier: configuration.tier,
        paper: configuration.paper,
        cover: configuration.cover,
        quantity: configuration.quantity,
        discountCode: configuration.discountCode,
      }, configuration.address).then((updatedQuote) => {
        if (active) setQuote(updatedQuote);
      }).catch((failure) => {
        if (active) setQuoteError(failure instanceof Error ? failure.message : "A current print quote could not be loaded.");
      }).finally(() => {
        if (active) setQuoteLoading(false);
      });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [configuration, locationReady, project, projectId]);

  useEffect(() => {
    let active = true;
    setPaymentMethods([]);
    setMethodsError("");
    if (!quote) {
      setMethodsLoading(false);
      return () => { active = false; };
    }
    setMethodsLoading(true);
    printOrderService.getPaymentMethods(quote.currency).then((methods) => {
      if (active) setPaymentMethods(methods);
    }).catch((failure) => {
      if (active) setMethodsError(failure instanceof Error ? failure.message : "Payment methods could not be loaded.");
    }).finally(() => {
      if (active) setMethodsLoading(false);
    });
    return () => { active = false; };
  }, [quote]);

  useEffect(() => {
    if (paymentMethods.length && !paymentMethods.some((method) => method.id === selectedMethod?.id)) {
      setSelectedMethod(paymentMethods[0]);
    }
  }, [paymentMethods, selectedMethod]);

  const updateConfiguration = useCallback((changes) => {
    setConfiguration((current) => ({ ...current, ...changes }));
  }, []);

  function updateAddress(field, value) {
    setConfiguration((current) => ({ ...current, address: { ...current.address, [field]: value } }));
  }

  const stepIndex = steps.findIndex((item) => item.id === step);
  const nextStep = steps[Math.min(stepIndex + 1, steps.length - 1)];
  const previousStep = steps[Math.max(stepIndex - 1, 0)];

  async function placeOrder(event) {
    event.preventDefault();
    setSubmitError("");
    if (!quote || quoteLoading) {
      setSubmitError("Wait for a current server quote before continuing.");
      return;
    }
    if (!selectedMethod) {
      setSubmitError("No verified payment method is currently available for this currency.");
      return;
    }
    setSubmitting(true);
    try {
      const order = await printOrderService.createOrder(projectId, {
        tier: configuration.tier,
        paper: configuration.paper,
        cover: configuration.cover,
        quantity: configuration.quantity,
        discountCode: configuration.discountCode,
      }, configuration.address, quote.id, selectedMethod);
      if (selectedMethod.provider === "paypal") {
        setPaypalCheckoutOrder(order);
        return;
      }
      if (order.checkoutUrl) {
        window.location.assign(order.checkoutUrl);
        return;
      }
      navigate(`/print/orders/${encodeURIComponent(order.id)}/processing`, { replace: true });
    } catch (failure) {
      setSubmitError(failure instanceof Error ? failure.message : "Your print checkout could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  async function retryPaypalCheckout() {
    const retried = await printOrderService.retryPayment(paypalCheckoutOrder.paymentId, "paypal");
    setPaypalCheckoutOrder(retried);
  }

  const headings = {
    print: ["Print configuration", "A book made to hold onto.", "Your saved design is the starting point. Choose the print details that feel right for your story."],
    tier: ["Printing tier", "Choose how it will be made.", "Select a print tier. Final availability and pricing are confirmed by the printing service."],
    paper: ["Paper selection", "Set the feel of each page.", "Choose a paper finish for your photographs and stories."],
    cover: ["Cover selection", "Choose its first impression.", "Select the cover finish for your printed keepsake."],
    quantity: ["Quantity", "How many copies would you like?", "The printing service will calculate quantity discounts, if available."],
    shipping: ["Shipping address", "Where should your book go?", "Add a delivery address to request an accurate shipping quote."],
    checkout: ["Order review", "Review every detail.", "Your quote is calculated by the printing service using your saved book, print choices, quantity, and delivery address."],
  };
  const [eyebrow, title, description] = headings[step];

  return <main className="print-order-page">
    <Link to="/dashboard/orders" className="print-back-link"><ArrowLeft size={15} /> Orders</Link>
    <PageHeading eyebrow={eyebrow} title={title} description={description} />
    <StepNavigation active={step} />
    <LoadError loading={loading} error={projectError} onRetry={reload} />
    {!loading && !projectError && project ? <>
      <BookSummary project={project} />
      {storageError ? <p className="print-inline-error" role="alert"><CircleAlert size={15} />{storageError}</p> : null}
      <div className="print-workflow-layout">
        <section className="print-step-panel">
          {step === "print" ? <div className="print-configuration-intro"><span className="print-feature-icon"><Printer size={20} /></span><h2>From your saved pages to a printed keepsake.</h2><p>We use your existing design, book dimensions, and page count. Final print compatibility is checked by the production service.</p><dl><div><dt>Book size</dt><dd>{project.document.book.size.width} × {project.document.book.size.height} in</dd></div><div><dt>Interior pages</dt><dd>{project.document.book.pageCount}</dd></div><div><dt>Current cover setup</dt><dd>{project.document.book.coverType || "Not specified"}</dd></div></dl><div className="print-note"><ShieldCheck size={17} /><span>Print orders are separate from PDF purchases. Payment and production status come from the order service.</span></div></div> : null}

          {step === "tier" ? <><h2>Choose a printing tier</h2><OptionCards name="tier" items={tierOptions} value={configuration.tier} onChange={(tier) => updateConfiguration({ tier })} /></> : null}
          {step === "paper" ? <><h2>Choose your paper</h2><OptionCards name="paper" items={paperOptions} value={configuration.paper} onChange={(paper) => updateConfiguration({ paper })} /></> : null}
          {step === "cover" ? <><h2>Choose a cover finish</h2><OptionCards name="cover" items={coverOptions} value={configuration.cover} onChange={(cover) => updateConfiguration({ cover })} /></> : null}
          {step === "quantity" ? <div className="print-quantity-control"><h2>Choose a quantity</h2><p>Order between 1 and 100 copies. The backend confirms availability and any quantity pricing.</p><label htmlFor="print-quantity">Copies</label><div><button type="button" aria-label="Decrease quantity" disabled={configuration.quantity <= 1} onClick={() => updateConfiguration({ quantity: Math.max(1, configuration.quantity - 1) })}>−</button><input id="print-quantity" type="number" min="1" max="100" value={configuration.quantity} onChange={(event) => updateConfiguration({ quantity: Math.min(100, Math.max(1, Number(event.target.value) || 1)) })} /><button type="button" aria-label="Increase quantity" disabled={configuration.quantity >= 100} onClick={() => updateConfiguration({ quantity: Math.min(100, configuration.quantity + 1) })}>+</button></div></div> : null}

          {step === "shipping" ? <form className="print-address-form" onSubmit={(event) => { event.preventDefault(); navigate(`/create/design/${encodeURIComponent(projectId)}/print/checkout`); }}>
            <h2>Delivery address</h2><div className="print-form-grid">
              <label>Full name<input required autoComplete="name" value={configuration.address.fullName} onChange={(event) => updateAddress("fullName", event.target.value)} /></label>
              <label>Phone<input required type="tel" autoComplete="tel" value={configuration.address.phone} onChange={(event) => updateAddress("phone", event.target.value)} /></label>
              <label className="wide">Address line 1<input required autoComplete="address-line1" value={configuration.address.line1} onChange={(event) => updateAddress("line1", event.target.value)} /></label>
              <label className="wide">Address line 2 <span>(optional)</span><input autoComplete="address-line2" value={configuration.address.line2} onChange={(event) => updateAddress("line2", event.target.value)} /></label>
              <label>City<input required autoComplete="address-level2" value={configuration.address.city} onChange={(event) => updateAddress("city", event.target.value)} /></label>
              <label>State / region<input required autoComplete="address-level1" value={configuration.address.region} onChange={(event) => updateAddress("region", event.target.value)} /></label>
              <label>Postal code<input required autoComplete="postal-code" value={configuration.address.postalCode} onChange={(event) => updateAddress("postalCode", event.target.value)} /></label>
              <label>Country<select required autoComplete="country" value={configuration.address.country} onChange={(event) => updateAddress("country", event.target.value)}><option value="">Choose country</option><option value="PK">Pakistan</option><option value="US">United States</option><option value="CA">Canada</option><option value="GB">United Kingdom</option><option value="AU">Australia</option><option value="OTHER">Other</option></select></label>
            </div><button className="button button-dark print-address-submit" type="submit">Save address and review <ArrowRight size={15} /></button>
          </form> : null}

          {step === "checkout" ? <><h2>Print order summary</h2><div className="print-choice-summary"><div><span>Tier</span><strong>{configuration.tier.toUpperCase()}</strong></div><div><span>Paper</span><strong>{paperOptions.find((item) => item.id === configuration.paper)?.title}</strong></div><div><span>Cover</span><strong>{coverOptions.find((item) => item.id === configuration.cover)?.title}</strong></div><div><span>Quantity</span><strong>{configuration.quantity}</strong></div><div><span>Delivery to</span><strong>{configuration.address.fullName}<br />{configuration.address.line1}, {configuration.address.city} {configuration.address.postalCode}</strong></div></div><label className="print-discount-field">Discount code<input value={configuration.discountCode} maxLength={80} autoCapitalize="characters" onChange={(event) => updateConfiguration({ discountCode: event.target.value })} placeholder="Enter code (optional)" /></label><p className="print-discount-note">Your code is validated by the server and reflected in the refreshed quote.</p><button className="print-refresh-quote" type="button" onClick={() => updateConfiguration({})} disabled={quoteLoading}><RefreshCw size={14} /> Refresh server quote</button></> : null}

          {step === "checkout" ? <><QuoteBreakdown quote={quote} /><PaymentMethodSelect methods={paymentMethods} value={selectedMethod?.id ?? ""} onChange={setSelectedMethod} loading={methodsLoading || Boolean(paypalCheckoutOrder)} pkrAmount={quote?.total} usdAmount={quote?.usdAmount} exchangeRate={quote?.exchangeRate} />{methodsError ? <p className="print-inline-error" role="alert">{methodsError}</p> : null}{paypalCheckoutOrder && selectedMethod?.provider === "paypal" ? <PayPalSmartCheckout paymentId={paypalCheckoutOrder.paymentId} pkrAmount={paypalCheckoutOrder.pkrAmount ?? quote?.total} usdAmount={paypalCheckoutOrder.usdAmount ?? quote?.usdAmount} onRetry={retryPaypalCheckout} onSuccess={() => navigate(`/print/orders/${encodeURIComponent(paypalCheckoutOrder.id)}/processing`, { replace: true })} /> : null}</> : null}
          {quoteLoading ? <div className="print-message"><LoaderCircle className="print-spin" size={18} /> Requesting a current quote from the printing service…</div> : null}
          {quoteError ? <div className="print-message print-error" role="alert"><CircleAlert size={18} /><span>{quoteError}</span><button className="button button-outline" type="button" onClick={() => updateConfiguration({})}><RefreshCw size={14} /> Try quote again</button></div> : null}
          {step !== "checkout" && step !== "shipping" ? <QuoteBreakdown quote={quote} compact /> : null}
          {submitError ? <p className="print-inline-error" role="alert"><CircleAlert size={16} />{submitError}</p> : null}

          <div className="print-step-actions">
            {stepIndex > 0 ? <Link className="button button-outline" to={`/create/design/${encodeURIComponent(projectId)}/print${previousStep.id === "print" ? "" : `/${previousStep.id}`}`}><ArrowLeft size={15} /> Back</Link> : <Link className="button button-outline" to={`/create/design/${encodeURIComponent(projectId)}`}><ArrowLeft size={15} /> Back to editor</Link>}
            {step === "checkout" && !paypalCheckoutOrder ? <button className="button button-dark" type="button" onClick={placeOrder} disabled={submitting || quoteLoading || methodsLoading || !quote || !selectedMethod}>{submitting ? <><LoaderCircle className="print-spin" size={16} /> Starting secure checkout…</> : <>Continue to payment <ArrowRight size={15} /></>}</button>
              : step === "checkout" || step === "shipping" ? null
                : <Link className="button button-dark" to={`/create/design/${encodeURIComponent(projectId)}/print/${nextStep.id}`}>Continue <ArrowRight size={15} /></Link>}
          </div>
        </section>
        <aside className="print-sidebar-card"><span className="eyebrow">Production & delivery</span><h2>Thoughtfully made, carefully sent.</h2><p>Estimated dates are provided with the server quote once your delivery details are entered.</p><div><Clock3 size={16} /><span>Production estimate<strong>{quote ? formatDate(quote.productionEstimate) : "Pending quote"}</strong></span></div><div><Truck size={16} /><span>Delivery estimate<strong>{quote ? formatDate(quote.deliveryEstimate) : "Pending quote"}</strong></span></div><Link to="/print/orders">View print order history <ArrowRight size={14} /></Link></aside>
      </div>
    </> : null}
  </main>;
}

function OrderState({ loading, error, onRefresh }) {
  if (loading) return <div className="print-message"><LoaderCircle className="print-spin" size={19} /> Checking your order with the printing service…</div>;
  if (error) return <div className="print-message print-error" role="alert"><CircleAlert size={19} /><span>{error}</span><button className="button button-outline" type="button" onClick={onRefresh}><RefreshCw size={14} /> Try again</button></div>;
  return null;
}

function usePrintOrder(orderId) {
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    let timer;
    async function load() {
      try {
        const item = await printOrderService.getOrder(orderId);
        if (!active) return;
        setOrder(item);
        setError("");
        if ((!item.paymentExpired && item.paymentStatus === "pending")
          || !["delivered", "cancelled", "refunded"].includes(item.productionStatus)) {
          timer = window.setTimeout(load, 15000);
        }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "Order status could not be loaded.");
      } finally {
        if (active) setLoading(false);
      }
    }
    setLoading(true);
    load();
    return () => { active = false; window.clearTimeout(timer); };
  }, [orderId, refreshKey]);
  return { order, loading, error, refresh };
}

export function PrintOrderResult() {
  const { orderId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const isTracking = location.pathname.endsWith("/tracking");
  const { order, loading, error, refresh } = usePrintOrder(orderId);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelStatus, setCancelStatus] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");
  const [pdfRetrying, setPdfRetrying] = useState(false);
  const [pdfRetryError, setPdfRetryError] = useState("");
  const statusIndex = order ? productionSteps.findIndex(([id]) => id === order.productionStatus) : -1;
  const cancellationAllowed = order?.paymentStatus === "successful"
    && statusIndex >= 0
    && statusIndex < productionSteps.findIndex(([id]) => id === "shipped")
    && !order?.cancellationStatus;

  async function requestCancellation(event) {
    event.preventDefault();
    setCancelling(true);
    setCancelError("");
    try {
      const result = await printOrderService.requestCancellation(order.id, cancelReason.trim());
      setCancelStatus(result.message || `Cancellation request status: ${result.status}.`);
      refresh();
    } catch (failure) {
      setCancelError(failure instanceof Error ? failure.message : "Cancellation request could not be submitted.");
    } finally {
      setCancelling(false);
    }
  }

  async function retryCheckout() {
    setRetrying(true);
    setRetryError("");
    try {
      const retried = await printOrderService.retryPayment(order.paymentId, order.paymentProvider);
      if (retried.checkoutUrl) {
        window.location.assign(retried.checkoutUrl);
        return;
      }

      async function cancelUnpaidOrder() {
        if (!window.confirm("Cancel this unpaid print order? It cannot be paid after cancellation.")) return;
        setCancelling(true);
        setCancelError("");
        try {
          await printOrderService.cancelUnpaidOrder(order.id);
          setCancelStatus("Your unpaid order has been cancelled.");
          refresh();
        } catch (failure) {
          setCancelError(failure instanceof Error ? failure.message : "The unpaid order could not be cancelled.");
        } finally {
          setCancelling(false);
        }
      }

      async function retryPrintPdf() {
        setPdfRetrying(true);
        setPdfRetryError("");
        try {
          await printOrderService.retryPrintPdf(order.id);
          refresh();
        } catch (failure) {
          setPdfRetryError(failure instanceof Error ? failure.message : "The print PDF could not be retried.");
        } finally {
          setPdfRetrying(false);
        }
      }
      refresh();
    } catch (failure) {
      setRetryError(failure instanceof Error ? failure.message : "Checkout could not be retried.");
    } finally {
      setRetrying(false);
    }
  }

  return <main className="print-order-page print-result-page">
    <Link to="/print/orders" className="print-back-link"><ArrowLeft size={15} /> All print orders</Link>
    <PageHeading eyebrow={isTracking ? "Delivery updates" : "Print order"} title={isTracking ? "Follow your book home." : order?.paymentStatus === "successful" ? "Your book is in good hands." : "Checking your order."} description={isTracking ? "Production and delivery updates are retrieved from your order record." : "Your order and payment are confirmed by the printing service, never by this browser."} />
    <OrderState loading={loading && !order} error={error} onRefresh={refresh} />
    {order ? <>
      <section className="print-order-status-card">
        <div className="print-order-status-heading"><span className={`print-order-status-icon${order.paymentStatus === "successful" ? " confirmed" : ""}`}>{order.paymentStatus === "successful" ? <BadgeCheck size={23} /> : <Clock3 size={23} />}</span><div><span className="eyebrow">Order {order.id}</span><h2>{order.paymentStatus === "successful" ? "Payment confirmed" : order.paymentStatus === "failed" ? "Payment failed" : "Payment pending"}</h2><p>{order.bookTitle || "Your MemoryBook"}{order.quantity ? ` · ${order.quantity} ${order.quantity === 1 ? "copy" : "copies"}` : ""}</p></div><strong>{order.quote ? formatPrice(order.quote.total, order.quote.currency) : ""}</strong></div>
        {order.paymentStatus === "failed" ? <div className="print-inline-error"><CircleAlert size={15} /> Payment was not confirmed. Your book will not enter production until payment is verified. <button className="button button-outline" type="button" onClick={retryCheckout} disabled={retrying}>{retrying ? "Starting retry…" : "Retry payment"}</button>{retryError ? <span role="alert">{retryError}</span> : null}</div> : null}
        {order.paymentStatus === "pending" ? <div className="print-order-note"><Clock3 size={15} /><span>{order.paymentExpired ? "The payment window has expired. This order can no longer be paid." : "We are waiting for the payment service to confirm your transaction."}</span>{!order.paymentExpired && order.checkoutUrl ? <button className="button button-outline" type="button" onClick={() => window.location.assign(order.checkoutUrl)}>Pay now</button> : null}{!order.paymentExpired ? <button className="button button-outline" type="button" disabled={cancelling} onClick={cancelUnpaidOrder}>{cancelling ? "Cancelling…" : "Cancel order"}</button> : null}</div> : null}
        {order.printPdf?.print?.status === "failed" ? <div className="print-inline-error" role="alert"><CircleAlert size={15} /><span>{order.printPdf.print.error?.message || "The print-ready PDF could not be generated."}</span><button className="button button-outline" type="button" disabled={pdfRetrying} onClick={retryPrintPdf}>{pdfRetrying ? "Retrying…" : "Retry PDF generation"}</button>{pdfRetryError ? <small>{pdfRetryError}</small> : null}</div> : null}
        {!isTracking ? <div className="print-order-dates"><div><Clock3 size={16} /><span>Estimated production<strong>{formatDate(order.productionEstimate)}</strong></span></div><div><Truck size={16} /><span>Estimated delivery<strong>{formatDate(order.deliveryEstimate)}</strong></span></div></div> : null}
      </section>
      <ManualPaymentPanel order={order} onSubmitted={refresh} />
      {order.paymentStatus === "pending" && !order.paymentExpired && order.paymentProvider === "paypal" ? <PayPalSmartCheckout paymentId={order.paymentId} pkrAmount={order.pkrAmount ?? order.amount ?? order.quote?.total} usdAmount={order.usdAmount} onRetry={retryCheckout} onSuccess={() => navigate(`/print/orders/${encodeURIComponent(order.id)}/processing`, { replace: true })} /> : null}
      <section className="print-timeline-card"><div className="print-timeline-heading"><div><span className="eyebrow">{isTracking ? "Live order progress" : "What happens next"}</span><h2>{productionSteps[statusIndex]?.[1] || "Order status"}</h2></div><button className="print-refresh-quote" type="button" onClick={refresh}><RefreshCw size={14} /> Refresh status</button></div>
        <ol className="print-production-timeline">{productionSteps.map(([id, label], index) => <li className={index < statusIndex ? "complete" : index === statusIndex ? "current" : ""} key={id}><span>{index < statusIndex ? <Check size={13} /> : index === statusIndex ? <PackageCheck size={13} /> : null}</span><div><strong>{label}</strong>{id === "shipped" && order.trackingNumber ? <small>Tracking number: {order.trackingNumber}</small> : null}</div></li>)}</ol>
      </section>
      <div className="print-result-links"><Link className="button button-outline" to={`/print/orders/${encodeURIComponent(order.id)}/${isTracking ? "confirmation" : "tracking"}`}>{isTracking ? "Order details" : "Track order"} <ArrowRight size={15} /></Link><Link className="button button-outline" to="/help">Contact support <ArrowRight size={15} /></Link></div>
      {order.shippingAddress ? <section className="print-address-summary"><MapPin size={18} /><div><span className="eyebrow">Delivery address</span><p>{order.shippingAddress.fullName}<br />{order.shippingAddress.line1}{order.shippingAddress.line2 ? `, ${order.shippingAddress.line2}` : ""}<br />{order.shippingAddress.city}, {order.shippingAddress.region} {order.shippingAddress.postalCode}<br />{order.shippingAddress.country}</p></div></section> : null}
      {cancellationAllowed ? <form className="print-cancellation-form" onSubmit={requestCancellation}><h2>Need to cancel?</h2><p>Send a cancellation request. It is not cancelled unless the printing service accepts it.</p><label htmlFor="print-cancel-reason">Reason<textarea id="print-cancel-reason" required minLength="5" maxLength="500" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} /></label><button className="button button-outline" type="submit" disabled={cancelling}>{cancelling ? <LoaderCircle className="print-spin" size={15} /> : null} Request cancellation</button>{cancelStatus ? <p role="status">{cancelStatus}</p> : null}{cancelError ? <p className="print-inline-error" role="alert">{cancelError}</p> : null}</form> : order.cancellationStatus ? <p className="print-order-note"><Clock3 size={15} /> Cancellation request: {order.cancellationStatus}</p> : null}
    </> : null}
  </main>;
}

export function PrintOrderHistory() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    printOrderService.listOrders().then((items) => { if (active) setOrders(items); }).catch((failure) => { if (active) setError(failure instanceof Error ? failure.message : "Print order history could not be loaded."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  return <main className="print-order-page print-history-page">
    <Link to="/dashboard/orders" className="print-back-link"><ArrowLeft size={15} /> Dashboard orders</Link>
    <PageHeading eyebrow="Your orders" title="Printed stories, in one place." description="Your order history and fulfillment status come from the printing service." />
    {loading ? <div className="print-message"><LoaderCircle className="print-spin" size={19} /> Loading print orders…</div> : null}
    {error ? <div className="print-message print-error" role="alert"><CircleAlert size={19} /><span>{error}</span><button className="button button-outline" type="button" onClick={() => { setError(""); setLoading(true); setReload((value) => value + 1); }}><RefreshCw size={14} /> Try again</button></div> : null}
    {!loading && !error && !orders.length ? <div className="print-empty-state"><Printer size={25} /><h2>No print orders yet</h2><p>Once you place a confirmed print order, its production and delivery updates will appear here.</p><Link to="/dashboard/projects" className="button button-outline">Choose a saved book</Link></div> : null}
    <div className="print-history-list">{orders.map((order) => <article key={order.id} className="print-history-row"><span><PackageCheck size={20} /></span><div><small>Order {order.id} · {order.createdAt ? formatDate(order.createdAt) : "Date unavailable"} · {order.paymentStatus === "successful" ? "Payment confirmed" : `Payment ${order.paymentStatus}`}</small><h2>{order.bookTitle || "MemoryBook print order"}</h2><p>{productionSteps.find(([id]) => id === order.productionStatus)?.[1]} · {formatPrice(order.quote.total, order.quote.currency)}{order.deliveryEstimate ? ` · Estimated delivery ${formatDate(order.deliveryEstimate)}` : ""}</p></div><Link className="button button-outline" to={`/print/orders/${encodeURIComponent(order.id)}/tracking`}>Track <ArrowRight size={14} /></Link></article>)}</div>
  </main>;
}
