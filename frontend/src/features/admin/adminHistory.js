const HISTORY_FILTERS = ["search", "dateFrom", "dateTo", "user", "book", "paymentStatus", "status", "type"];

export function buildAdminHistoryQuery(filters = {}) {
  const params = new URLSearchParams();
  for (const key of HISTORY_FILTERS) {
    const value = filters[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, String(value).trim());
    }
  }
  return params.toString();
}
