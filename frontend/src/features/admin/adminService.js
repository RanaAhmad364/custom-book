import { apiRequest } from "../../services/apiClient.js";

const paths = {
  dashboard: "/dashboard",
  books: "/books",
  categories: "/categories",
  collections: "/collections",
  templates: "/templates",
  users: "/users",
  "pdf-orders": "/orders?type=pdf",
  "print-orders": "/orders?type=print",
  payments: "/payments",
  refunds: "/refunds",
  pricing: "/pricing",
  shipping: "/pricing",
  notifications: "/notifications",
  reports: "/reports",
  support: "/support",
  settings: "/settings",
  activity: "/activity",
};

const bookDesignVersions = new Map();

export async function loadAdminSection(section, search = "", filters = {}) {
  const path = paths[section];
  if (!path) throw new Error("This admin section is not available.");
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const queryString = params.toString();
  const query = queryString ? `${path.includes("?") ? "&" : "?"}${queryString}` : "";
  const { data } = await apiRequest(`/admin${path}${query}`);
  return data;
}

export async function loadAdminBookReferences() {
  const pageSize = 100;
  const first = await loadAdminSection("books", "", { page: 1, perPage: pageSize });
  if (!Array.isArray(first.items)) throw new Error("The book service returned an invalid list.");
  const totalPages = first.pagination?.totalPages;
  if (!Number.isInteger(totalPages) || totalPages < 1) return first.items;
  const remaining = await Promise.all(Array.from({ length: totalPages - 1 }, (_, index) =>
    loadAdminSection("books", "", { page: index + 2, perPage: pageSize })));
  if (remaining.some((result) => !Array.isArray(result.items))) {
    throw new Error("The book service returned an invalid list.");
  }
  return [...first.items, ...remaining.flatMap((result) => result.items)];
}

export async function saveAdminRecord(section, record) {
  const path = paths[section]?.split("?")[0];
  if (!path) throw new Error("This admin section cannot be edited.");
  const id = record?.id;
  const method = id ? "PATCH" : "POST";
  const url = id ? `/admin${path}/${encodeURIComponent(id)}` : `/admin${path}`;
  return (await apiRequest(url, { method, body: record })).data;
}

export async function removeAdminRecord(section, id) {
  const path = paths[section]?.split("?")[0];
  if (!path || !id) throw new Error("This admin record cannot be deleted.");
  return apiRequest(`/admin${path}/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function publishAdminRecord(section, id, published) {
  const action = published ? "publish" : "unpublish";
  const path = paths[section]?.split("?")[0];
  if (!path || !["books", "templates"].includes(section)) throw new Error("Publishing is not supported for this record.");
  return (await apiRequest(`/admin${path}/${encodeURIComponent(id)}/${action}`, { method: "POST" })).data;
}

export async function updateAdminOrder(order) {
  return (await apiRequest(`/admin/orders/${order.type}/${encodeURIComponent(order.id)}`, {
    method: "PATCH",
    body: order,
  })).data;
}

export async function updateAdminUser(user) {
  return (await apiRequest(`/admin/users/${encodeURIComponent(user.id)}`, {
    method: "PATCH",
    body: { isActive: user.isActive },
  })).data;
}

export async function updateAdminPricing(record) {
  return (await apiRequest(`/admin/pricing/${record.kind}/${encodeURIComponent(record.id)}`, {
    method: "PATCH",
    body: record.changes,
  })).data;
}

export async function createAdminPricing(kind, pricing) {
  return (await apiRequest(`/admin/pricing/${encodeURIComponent(kind)}`, {
    method: "POST",
    body: pricing,
  })).data;
}

export async function removeAdminPricing(kind, id) {
  if (!kind || !id) throw new Error("This pricing record cannot be deleted.");
  return apiRequest(`/admin/pricing/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function createAdminVariant(variant) {
  return (await apiRequest("/admin/pricing/variants", { method: "POST", body: variant })).data;
}

export async function updateAdminSupport(ticket) {
  return (await apiRequest(`/admin/support/${encodeURIComponent(ticket.id)}`, {
    method: "PATCH",
    body: ticket.changes,
  })).data;
}

export async function updateAdminRefund(refundId, changes) {
  return (await apiRequest(`/admin/refunds/${encodeURIComponent(refundId)}`, {
    method: "PATCH",
    body: changes,
  })).data;
}

export async function sendAdminEmail(email) {
  return (await apiRequest("/admin/emails", { method: "POST", body: email })).data;
}

export async function uploadAdminAsset(file) {
  const form = new FormData();
  form.append("file", file);
  return (await apiRequest("/admin/assets", { method: "POST", body: form })).data.asset;
}

export async function uploadAdminDesignAsset(file) {
  const form = new FormData();
  form.append("file", file);
  return (await apiRequest("/admin/design-assets", { method: "POST", body: form })).data.asset;
}

function bookDesignResult(productId, data) {
  const template = data?.template;
  if (!template?.id || !Number.isInteger(template.version) || !template.designDocument) {
    throw new Error("The book design service returned an invalid response.");
  }
  bookDesignVersions.set(productId, template.version);
  return {
    product: data.product,
    template,
    document: template.designDocument,
    version: template.version,
    published: Boolean(template.published),
  };
}

export async function getAdminBookDesign(productId) {
  const { data } = await apiRequest(`/admin/books/${encodeURIComponent(productId)}/design`, { method: "POST", body: {} });
  return bookDesignResult(productId, data);
}

export async function saveAdminBookDesign(productId, document) {
  const version = bookDesignVersions.get(productId);
  if (!Number.isInteger(version)) throw new Error("The book design version is unavailable. Reload the design before saving.");
  const { data } = await apiRequest(`/admin/books/${encodeURIComponent(productId)}/design`, {
    method: "PUT",
    body: { document },
    headers: { "If-Match": `"${version}"` },
  });
  return bookDesignResult(productId, data);
}

export async function publishAdminBookDesign(productId) {
  const version = bookDesignVersions.get(productId);
  if (!Number.isInteger(version)) throw new Error("The book design version is unavailable. Reload the design before publishing.");
  const { data } = await apiRequest(`/admin/books/${encodeURIComponent(productId)}/design/publish`, {
    method: "POST",
    headers: { "If-Match": `"${version}"` },
  });
  return bookDesignResult(productId, data);
}

export async function unpublishAdminBookDesign(productId) {
  const { data } = await apiRequest(`/admin/books/${encodeURIComponent(productId)}/design/unpublish`, { method: "POST" });
  return bookDesignResult(productId, data);
}
