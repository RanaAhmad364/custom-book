import { apiRequest } from "./apiClient.js";

export const favoritesService = {
  async list() {
    const { data } = await apiRequest("/favorites");
    return data.items;
  },

  async add(bookId) {
    const { data } = await apiRequest(`/favorites/${encodeURIComponent(bookId)}`, { method: "POST" });
    return data;
  },

  async remove(bookId) {
    await apiRequest(`/favorites/${encodeURIComponent(bookId)}`, { method: "DELETE" });
  },
};
