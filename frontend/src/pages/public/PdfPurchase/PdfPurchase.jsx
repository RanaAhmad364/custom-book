import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BadgeCheck, BookOpen, Check, CircleAlert, Clock3, Download, FileDown, LoaderCircle, LockKeyhole, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../../features/auth/AuthContext.jsx";
import { PaymentMethodSelect } from "../../../components/commerce/PaymentMethodSelect.jsx";
import { ManualPaymentPanel } from "../../../components/commerce/ManualPaymentPanel.jsx";
import { PayPalSmartCheckout } from "../../../components/commerce/PayPalSmartCheckout.jsx";
import { canDownloadPdf, pdfOrderService } from "../../../services/pdfOrderService.js";
import { projectService } from "../../../services/projectService.js";
import { SafeImage } from "../../../components/common/SafeImage.jsx";
import { ProjectPdfAccessAction } from "../../../features/pdfPurchase/ProjectPdfAccessAction.jsx";
import "./PdfPurchase.css";

function formatPrice(value, currency) {
  if (!Number.isFinite(Number(value)) || !currency) return "Price unavailable";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
  } catch {
    return `${currency} ${Number(value).toFixed(2)}`;
  }
}

function PdfPage({ eyebrow, title, description, children }) {
  return <main className="pdf-purchase-page"><div className="pdf-page-heading"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{children}</main>;
}

function PdfProjectCard({ project, price }) {
  const doc = project.document;
  return <article className="pdf-project-card">
    <SafeImage src={project.image} alt="" className="pdf-project-image" />
    <div className="pdf-project-info"><span className="eyebrow">Your book</span><h2>{doc.metadata.title}</h2><p><BookOpen size={15} /> {doc.book.pageCount} pages <span>·</span> {doc.book.size.width} × {doc.book.size.height} in</p><small>High-resolution PDF · Separate purchase</small></div>
    <strong className="pdf-price">{price ? formatPrice(price.amount, price.currency) : "—"}</strong>
  </article>;
}

function usePdfProject() {
  const { projectId } = useParams();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [price, setPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const saved = await projectService.getProject(user.email, projectId);
      if (!saved?.document) throw new Error("This saved book could not be found in your account.");
      setProject(saved);
      const offer = await pdfOrderService.getOffer(projectId);
      setPrice(offer);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Book or PDF pricing could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [projectId, user.email]);
  useEffect(() => { load(); }, [load]);
  return { project, price, loading, error, reload: load, projectId };
}

function LoadState({ loading, error, onRetry }) {
  if (loading) return <div className="pdf-state"><LoaderCircle className="pdf-spin" size={20} /> Loading your book and current PDF price…</div>;
  if (error) return <div className="pdf-state pdf-error" role="alert"><CircleAlert size={20} /><span>{error}</span><button className="button button-outline" type="button" onClick={onRetry}><RefreshCw size={15} /> Try again</button></div>;
  return null;
}

export function PdfServiceDetails() {
  const { project, price, loading, error, reload, projectId } = usePdfProject();
  return <PdfPage eyebrow="A separate digital purchase" title="Keep your book, wherever you go." description="Order a high-resolution PDF after your design is reviewed. Payment must be confirmed by our payment service before generation or download is enabled.">
    <LoadState loading={loading} error={error} onRetry={reload} />
    {project && !loading && !error ? <><PdfProjectCard project={project} price={price} /><div className="pdf-info-grid"><article><FileDown size={19} /><h3>Print-ready PDF</h3><p>Exported from your saved book document after payment confirmation.</p></article><article><LockKeyhole size={19} /><h3>Separate purchase</h3><p>A PDF is not included with the book design or any print order.</p></article><article><Clock3 size={19} /><h3>Server-generated</h3><p>We’ll show progress and a download link only after the server confirms payment and finishes generating your file.</p></article></div><div className="pdf-actions"><Link className="button button-outline" to={`/create/design/${projectId}`}><ArrowLeft size={15} /> Back to editor</Link><Link className="button button-dark" to={`/create/design/${projectId}/pdf/summary`}>Review order <ArrowRight size={15} /></Link></div></> : null}
  </PdfPage>;
}

export function PdfOrderSummary() {
  const { project, price, loading, error, reload, projectId } = usePdfProject();
  return <PdfPage eyebrow="Order summary" title="One more way to keep it close." description="Check the book and the server-provided PDF price before continuing to checkout.">
    <LoadState loading={loading} error={error} onRetry={reload} />
    {project && !loading && !error ? <><PdfProjectCard project={project} price={price} /><section className="pdf-summary-card"><div><span>PDF download service</span><strong>{formatPrice(price.amount, price.currency)}</strong></div><div><span>Printing and shipping</span><strong>Not included</strong></div><div className="pdf-summary-total"><span>Total due for this PDF order</span><strong>{formatPrice(price.amount, price.currency)}</strong></div><p>Price is supplied by the purchase service. No payment has been taken yet.</p></section><div className="pdf-actions"><Link className="button button-outline" to={`/create/design/${projectId}/pdf`}><ArrowLeft size={15} /> Back</Link><Link className="button button-dark" to={`/create/design/${projectId}/pdf/checkout`}>Continue to checkout <ArrowRight size={15} /></Link></div></> : null}
  </PdfPage>;
}

export function PdfCheckout() {
  const { project, price, loading, error, reload, projectId } = usePdfProject();
  const navigate = useNavigate();
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [methodsLoading, setMethodsLoading] = useState(false);
  const [methodsError, setMethodsError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [paypalCheckoutOrder, setPaypalCheckoutOrder] = useState(null);
  useEffect(() => {
    let active = true;
    setPaymentMethods([]);
    setMethodsError("");
    if (!price) {
      setMethodsLoading(false);
      return () => { active = false; };
    }
    setMethodsLoading(true);
    pdfOrderService.getPaymentMethods(price.currency).then((methods) => {
      if (active) setPaymentMethods(methods);
    }).catch((failure) => {
      if (active) setMethodsError(failure instanceof Error ? failure.message : "Payment methods could not be loaded.");
    }).finally(() => {
      if (active) setMethodsLoading(false);
    });
    return () => { active = false; };
  }, [price]);
  useEffect(() => {
    if (paymentMethods.length && !paymentMethods.some((method) => method.id === selectedMethod?.id)) {
      setSelectedMethod(paymentMethods[0]);
    }
  }, [paymentMethods, selectedMethod]);
  async function submitOrder() {
    setSubmitting(true);
    setSubmitError("");
    try {
      if (!selectedMethod) throw new Error("No verified payment method is available for this currency.");
      const order = await pdfOrderService.createOrder(projectId, selectedMethod);
      if (selectedMethod.provider === "paypal") {
        setPaypalCheckoutOrder(order);
        return;
      }
      if (order.checkoutUrl) {
        window.location.assign(order.checkoutUrl);
        return;
      }
      navigate(`/pdf/orders/${encodeURIComponent(order.id)}/processing`, { replace: true });
    } catch (failure) {
      setSubmitError(failure instanceof Error ? failure.message : "Checkout could not be started.");
    } finally {
      setSubmitting(false);
    }
  }
  async function retryPaypalCheckout() {
    const retried = await pdfOrderService.retryPayment(paypalCheckoutOrder.paymentId, "paypal");
    setPaypalCheckoutOrder(retried);
  }
  return <PdfPage eyebrow="Secure checkout" title="Your PDF, ordered with care." description="The server determines the final charge and payment status. This browser cannot mark an order paid or unlock a file.">
    <LoadState loading={loading} error={error} onRetry={reload} />
    {project && !loading && !error ? <><PdfProjectCard project={project} price={price} />    <section className="pdf-checkout-card"><LockKeyhole size={20} /><div><h2>Payment verification</h2><p>Continue to create a payment order. Payment remains pending until verified by the backend; PDF generation starts only after that confirmation.</p><strong>{formatPrice(price.amount, price.currency)} due</strong><PaymentMethodSelect methods={paymentMethods} value={selectedMethod?.id ?? ""} onChange={setSelectedMethod} loading={methodsLoading || Boolean(paypalCheckoutOrder)} pkrAmount={price.amount} usdAmount={price.usdAmount} exchangeRate={price.exchangeRate} />{methodsError ? <p className="pdf-inline-error" role="alert">{methodsError}</p> : null}</div></section>{submitError ? <p className="pdf-inline-error" role="alert"><CircleAlert size={16} />{submitError}</p> : null}{paypalCheckoutOrder && selectedMethod?.provider === "paypal" ? <PayPalSmartCheckout paymentId={paypalCheckoutOrder.paymentId} pkrAmount={paypalCheckoutOrder.pkrAmount ?? price.amount} usdAmount={paypalCheckoutOrder.usdAmount ?? price.usdAmount} onRetry={retryPaypalCheckout} onSuccess={() => navigate(`/pdf/orders/${encodeURIComponent(paypalCheckoutOrder.id)}/processing`, { replace: true })} /> : null}<div className="pdf-actions"><Link className="button button-outline" to={`/create/design/${projectId}/pdf/summary`}><ArrowLeft size={15} /> Back to summary</Link>{!paypalCheckoutOrder ? <button className="button button-dark" type="button" onClick={submitOrder} disabled={submitting || !price || methodsLoading || !selectedMethod}>{submitting ? <><LoaderCircle className="pdf-spin" size={16} /> Starting checkout…</> : <>Continue to payment <ArrowRight size={15} /></>}</button> : null}</div></> : null}
  </PdfPage>;
}

const paymentLabels = { pending: "Payment pending", successful: "Payment successful", failed: "Payment failed" };
const generationLabels = { queued: "Generation queued", generating: "Generating PDF", ready: "PDF ready", failed: "Generation failed", not_started: "Waiting for payment confirmation" };

export function PdfOrderProcessing() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");
  useEffect(() => {
    let active = true;
    let timer;
    async function refresh() {
      try {
        const updated = await pdfOrderService.getOrder(orderId);
        if (!active) return;
        setOrder(updated);
        setError("");
        if (updated.paymentStatus === "pending" || updated.generationStatus === "queued" || updated.generationStatus === "generating") {
          timer = window.setTimeout(refresh, 5000);
        }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "Order status could not be retrieved.");
      } finally {
        if (active) setLoading(false);
      }
    }
    refresh();
    return () => { active = false; window.clearTimeout(timer); };
  }, [orderId, refreshKey]);

  const downloadable = canDownloadPdf(order);
  async function retryCheckout() {
    setRetrying(true);
    setRetryError("");
    try {
      const retried = await pdfOrderService.retryPayment(order.paymentId, order.paymentProvider);
      if (retried.checkoutUrl) {
        window.location.assign(retried.checkoutUrl);
        return;
      }
      setOrder(retried);
    } catch (failure) {
      setRetryError(failure instanceof Error ? failure.message : "Checkout could not be retried.");
    } finally {
      setRetrying(false);
    }
  }
  return <PdfPage eyebrow="Order status" title={downloadable ? "Your PDF is ready." : "We’re checking on your book."} description="Payment and generation states below are read from the backend order record.">
    {loading && !order ? <div className="pdf-state"><LoaderCircle className="pdf-spin" size={20} /> Checking payment and generation status…</div> : null}
    {error ? <div className="pdf-state pdf-error" role="alert"><CircleAlert size={20} /><span>{error}</span><button className="button button-outline" type="button" onClick={() => { setLoading(true); setRefreshKey((value) => value + 1); }}><RefreshCw size={15} /> Check again</button></div> : null}
    {order ? <><div className="pdf-status-card"><div className="pdf-state-row"><span><span className="eyebrow">Payment</span><strong>{paymentLabels[order.paymentStatus]}</strong></span>{order.paymentStatus === "successful" ? <BadgeCheck /> : order.paymentStatus === "failed" ? <CircleAlert /> : <Clock3 />}</div><div className="pdf-state-row"><span><span className="eyebrow">PDF generation</span><strong>{generationLabels[order.generationStatus]}</strong></span>{order.generationStatus === "ready" ? <Check /> : order.generationStatus === "failed" ? <CircleAlert /> : <LoaderCircle className={order.generationStatus === "generating" || order.generationStatus === "queued" ? "pdf-spin" : ""} />}</div><div className="pdf-status-meta"><span>Order {order.id}</span>{order.amount !== null ? <strong>{formatPrice(order.amount, order.currency)}</strong> : null}</div></div>
      <ManualPaymentPanel order={order} onSubmitted={() => { setLoading(true); setRefreshKey((value) => value + 1); }} />
      {order.paymentStatus === "failed" ? <div className="pdf-inline-error" role="alert"><span>Payment was not confirmed. No PDF is available.</span><button className="button button-outline" type="button" onClick={retryCheckout} disabled={retrying}>{retrying ? "Starting retry…" : "Retry payment"}</button>{retryError ? <span>{retryError}</span> : null}</div> : null}
      {order.paymentStatus === "pending" && order.paymentProvider === "paypal" ? <PayPalSmartCheckout paymentId={order.paymentId} pkrAmount={order.pkrAmount ?? order.amount} usdAmount={order.usdAmount} onRetry={retryCheckout} onSuccess={() => navigate(`/pdf/orders/${encodeURIComponent(order.id)}/processing`, { replace: true })} /> : null}
      {order.generationStatus === "failed" && order.paymentStatus === "successful" ? <p className="pdf-inline-error" role="alert">Payment is valid, but PDF generation failed. Use the retry option to generate it again without paying again.</p> : null}
      {downloadable ? <div className="pdf-actions"><Link className="button button-outline" to={`/pdf/downloads/${encodeURIComponent(order.id)}`}>View download details <ArrowRight size={15} /></Link><ProjectPdfAccessAction projectId={order.projectId} className="button button-dark" /></div> : <div className="pdf-actions"><ProjectPdfAccessAction projectId={order.projectId} className="button button-outline" /><button className="button button-outline" type="button" onClick={() => { setLoading(true); setRefreshKey((value) => value + 1); }}><RefreshCw size={15} /> Refresh status</button><Link className="pdf-text-link" to="/dashboard/downloads">PDF download history</Link></div>}
    </> : null}
  </PdfPage>;
}

export function PdfDownloadHistory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    pdfOrderService.listOrders().then((result) => { if (active) setItems(result); }).catch((failure) => { if (active) setError(failure instanceof Error ? failure.message : "Download history could not be loaded."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  return <PdfPage eyebrow="Your digital library" title="PDF download history" description="Your purchase and file status are retrieved from the account service.">
    {loading ? <div className="pdf-state"><LoaderCircle className="pdf-spin" size={20} /> Loading download history…</div> : null}
    {error ? <div className="pdf-state pdf-error" role="alert"><CircleAlert size={20} /><span>{error}</span><button className="button button-outline" type="button" onClick={() => { setError(""); setLoading(true); setReload((value) => value + 1); }}><RefreshCw size={15} /> Try again</button></div> : null}
    {!loading && !error && !items.length ? <div className="pdf-empty"><FileDown size={28} /><h2>No purchased PDFs yet</h2><p>After a confirmed purchase, your PDF order and generation status will appear here.</p><Link className="button button-outline" to="/dashboard/projects">Choose a book</Link></div> : null}
    <div className="pdf-history-list">{items.map((item) => <article className="pdf-history-row" key={item.id}><span className="pdf-history-icon"><FileDown size={19} /></span><div><span className="eyebrow">Order {item.id}</span><h2>{item.bookTitle || "MemoryBook PDF"}</h2><p>{item.pageCount ? `${item.pageCount} pages · ` : ""}{paymentLabels[item.paymentStatus]} · {generationLabels[item.generationStatus]}</p></div><Link className="button button-outline" to={`/pdf/downloads/${encodeURIComponent(item.id)}`}>Details <ArrowRight size={14} /></Link></article>)}</div>
  </PdfPage>;
}

export function PdfDownloadDetails() {
  const { downloadId } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    pdfOrderService.getOrder(downloadId).then((item) => { if (active) setOrder(item); }).catch((failure) => { if (active) setError(failure instanceof Error ? failure.message : "Download details could not be loaded."); });
    return () => { active = false; };
  }, [downloadId]);
  const downloadable = canDownloadPdf(order);
  return <PdfPage eyebrow="Download details" title={order?.bookTitle || (order ? "Your MemoryBook PDF" : "Your PDF order")} description="File access is available only when the backend confirms both payment and generation.">
    {!order && !error ? <div className="pdf-state"><LoaderCircle className="pdf-spin" size={20} /> Loading secure download details…</div> : null}
    {error ? <div className="pdf-state pdf-error" role="alert"><CircleAlert size={20} />{error}</div> : null}
    {order ? <><div className="pdf-project-card pdf-detail-card"><span className="pdf-project-symbol"><FileDown size={25} /></span><div className="pdf-project-info"><span className="eyebrow">Order {order.id}</span><h2>{order.bookTitle || "MemoryBook PDF"}</h2><p><BookOpen size={15} /> {order.pageCount ?? "—"} pages</p></div><strong className="pdf-price">{formatPrice(order.amount, order.currency)}</strong></div><div className="pdf-status-card"><div className="pdf-state-row"><span><span className="eyebrow">Payment</span><strong>{paymentLabels[order.paymentStatus]}</strong></span></div><div className="pdf-state-row"><span><span className="eyebrow">PDF</span><strong>{generationLabels[order.generationStatus]}</strong></span></div></div><div className="pdf-actions"><Link className="button button-outline" to="/dashboard/downloads"><ArrowLeft size={15} /> Download history</Link><ProjectPdfAccessAction projectId={order.projectId} className={downloadable ? "button button-dark" : "button button-outline"} /></div></> : null}
  </PdfPage>;
}
