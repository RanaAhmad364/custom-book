import { authApi } from "../auth/authApi.js";
import { apiRequest } from "../../services/apiClient.js";
import { projectService } from "../../services/projectService.js";

const formatDate = (value) => value ? new Date(value).toLocaleDateString() : "—";
const formatMoney = (value, currency) => new Intl.NumberFormat(undefined, {
  style: "currency",
  currency: currency || "PKR",
}).format(Number(value));

function label(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function mapPrintOrder(order) {
  const statuses = {
    pending_payment: "Pending payment",
    order_placed: "Order placed",
    production_started: "In production",
    quality_check: "Quality check completed",
    shipped: "Shipped",
    delivered: "Delivered",
    cancellation_requested: "Cancellation requested",
    cancelled: "Cancelled",
  };
  const status = statuses[order.productionStatus] || label(order.productionStatus);
  return {
    id: order.id,
    reference: order.orderNumber || order.id,
    title: `Print order ${order.orderNumber || order.id}`,
    image: "",
    date: formatDate(order.createdAt),
    payment: order.paymentStatus === "successful" ? "Paid" : label(order.paymentStatus),
    status,
    paymentStatus: order.paymentStatus,
    paymentId: order.paymentId,
    paymentProvider: order.paymentProvider,
    checkoutUrl: order.checkoutUrl,
    paymentExpired: Boolean(order.paymentExpired),
    productionStatus: order.productionStatus,
    printPdf: order.printPdf || {},
    tracking: order.trackingNumber || null,
    total: formatMoney(order.quote?.total ?? order.amount, order.currency),
    deliveryEstimate: order.deliveryEstimate,
  };
}

function mapPdfOrder(order) {
  const ready = order.paymentStatus === "successful"
    && order.generationStatus === "ready"
    && typeof order.downloadId === "string";
  const status = ready
    ? "Ready"
    : order.paymentStatus !== "successful"
      ? label(order.paymentStatus)
      : label(order.generationStatus);
  return {
    id: order.id,
    projectId: order.projectId,
    paymentId: order.paymentId,
    paymentStatus: order.paymentStatus,
    title: order.title || "MemoryBook PDF",
    date: formatDate(order.createdAt),
    status,
    size: order.pageCount ? `${order.pageCount} pages` : "PDF file",
    generationStatus: order.generationStatus,
    generationError: order.generationError,
    downloadId: order.downloadId,
    image: "",
  };
}

function mapNotification(item) {
  const categories = {
    order: "Order",
    pdf: "Download",
    payment: "Payment",
    account: "Account",
  };
  return {
    id: item.id,
    category: categories[item.category] || label(item.category),
    title: item.title,
    message: item.message,
    date: formatDate(item.createdAt),
    read: Boolean(item.readAt),
  };
}

function mapAddress(address) {
  return {
    id: address.id,
    name: address.recipientName,
    line: [address.addressLine1, address.addressLine2].filter(Boolean).join(", "),
    city: [address.city, address.region].filter(Boolean).join(", "),
    postal: address.postalCode,
    countryCode: address.countryCode,
  };
}

function mapSettings(preferences) {
  const enabled = (category) => preferences.some(
    (item) => item.channel === "email" && item.category === category && item.enabled,
  );
  return {
    orderEmails: enabled("order"),
    productNews: enabled("product_news"),
  };
}

export async function loadDashboardData(user) {
  const [projects, printResponse, pdfResponse, notificationResponse, addressResponse, preferenceResponse, favorites] =
    await Promise.all([
      projectService.listProjects(user.email),
      apiRequest("/print/orders"),
      apiRequest("/pdf/orders"),
      apiRequest("/payments/notifications"),
      authApi.listAddresses(),
      authApi.notificationPreferences(),
      apiRequest("/favorites"),
    ]);

  const printOrders = printResponse.data?.items;
  const pdfOrders = pdfResponse.data?.items;
  const notifications = notificationResponse.data?.items;
  const addresses = addressResponse?.items;
  const preferences = preferenceResponse?.items;
  const favoriteBooks = favorites.data?.items;
  if (!Array.isArray(printOrders) || !Array.isArray(pdfOrders)
    || !Array.isArray(notifications) || !Array.isArray(addresses) || !Array.isArray(preferences)
    || !Array.isArray(favoriteBooks)) {
    throw new Error("The dashboard services returned an invalid response.");
  }

  return {
    profile: {
      name: user.name || user.email,
      email: user.email,
      phone: user.phone || "",
      privacyMode: Boolean(user.privacyMode),
      photo: "",
    },
    projects: projects.map((project) => {
      const order = pdfOrders.map(mapPdfOrder).find((item) => item.projectId === project.id);
      return {
        ...project,
        pdfAccess: order
          ? {
            state: order.paymentStatus === "successful"
              ? order.generationStatus === "ready" ? "ready" : "generating"
              : "payment_pending",
            orderId: order.id,
            paymentId: order.paymentId,
            paymentStatus: order.paymentStatus,
            generationStatus: order.generationStatus,
            generationError: order.generationError,
            downloadId: order.downloadId,
          }
          : { state: "not_purchased" },
      };
    }),
    orders: printOrders.map(mapPrintOrder).filter((order) => order.paymentStatus === "successful"),
    pendingOrders: printOrders.map(mapPrintOrder).filter((order) =>
      ["pending", "failed"].includes(order.paymentStatus)
      && ["pending_payment", "order_placed"].includes(order.productionStatus)),
    downloads: pdfOrders.map(mapPdfOrder),
    notifications: notifications.map(mapNotification),
    billing: [],
    addresses: addresses.map(mapAddress),
    settings: { ...mapSettings(preferences), privacyMode: Boolean(user.privacyMode) },
    favorites: favoriteBooks,
  };
}

export function mapShippingAddress(address) {
  return {
    recipientName: address.name,
    addressLine1: address.line,
    city: address.city,
    postalCode: address.postal,
    countryCode: address.countryCode || "PK",
  };
}
