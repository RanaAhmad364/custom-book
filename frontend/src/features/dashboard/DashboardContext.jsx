import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import { authApi } from "../auth/authApi.js";
import { apiRequest } from "../../services/apiClient.js";
import { projectService } from "../../services/projectService.js";
import { loadDashboardData, mapShippingAddress } from "./dashboardService.js";

const DashboardContext = createContext(null);

function DashboardUserScope({ user, children }) {
  const [isLoading, setIsLoading] = useState(true);
  const [storageError, setStorageError] = useState("");
  const [data, setData] = useState({
    profile: { name: user.name || user.email, email: user.email, phone: "", photo: "" },
    projects: [],
    orders: [],
    downloads: [],
    notifications: [],
    billing: [],
    addresses: [],
    settings: { orderEmails: true, productNews: false },
  });

  useEffect(() => {
    let active = true;
    loadDashboardData(user).then((dashboard) => {
      if (active) {
        setData(dashboard);
        setStorageError("");
      }
    }).catch((failure) => {
      if (active) setStorageError(failure instanceof Error ? failure.message : "Your dashboard could not be loaded.");
    }).finally(() => {
      if (active) setIsLoading(false);
    });
    return () => { active = false; };
  }, [user.email, user.name]);

  const value = useMemo(() => ({
    data,
    isLoading,
    storageError,
    async updateProject(id, changes) {
      try {
        const saved = await projectService.updateProject(user.email, id, changes);
        setData((current) => ({
          ...current,
          projects: current.projects.map((project) => project.id === id ? saved : project),
        }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "The project update could not be saved.");
        return false;
      }
    },
    async deleteProject(id) {
      try {
        await projectService.deleteProject(user.email, id);
        setData((current) => ({ ...current, projects: current.projects.filter((project) => project.id !== id) }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "The project could not be deleted.");
        return false;
      }
    },
    async duplicateProject(id) {
      try {
        const copy = await projectService.duplicateProject(user.email, id);
        if (copy) setData((current) => ({ ...current, projects: [copy, ...current.projects] }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "The project could not be duplicated.");
        return false;
      }
    },
    async setNotifications(notifications) {
      const toRead = notifications.filter((notification) => {
        const previous = data.notifications.find((item) => item.id === notification.id);
        return previous && !previous.read && notification.read;
      });
      try {
        await Promise.all(toRead.map((notification) => apiRequest(
          `/payments/notifications/${encodeURIComponent(notification.id)}/read`,
          { method: "POST" },
        )));
        setData((current) => ({ ...current, notifications }));
        setStorageError("");
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "Notification status could not be saved.");
      }
    },
    async updateProfile(changes) {
      try {
        const response = await authApi.updateProfile({ name: changes.name, phone: changes.phone });
        if (!response?.user) throw new Error("The profile service returned an invalid response.");
        setData((current) => ({
          ...current,
          profile: { ...current.profile, name: response.user.name, phone: response.user.phone || "" },
        }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "Profile changes could not be saved.");
        return false;
      }
    },
    async updateSettings(changes) {
      const preferences = [];
      if (Object.prototype.hasOwnProperty.call(changes, "orderEmails")) {
        preferences.push({ channel: "email", category: "order", enabled: changes.orderEmails });
      }
      if (Object.prototype.hasOwnProperty.call(changes, "productNews")) {
        preferences.push({ channel: "email", category: "product_news", enabled: changes.productNews });
      }
      try {
        await Promise.all(preferences.map((preference) => authApi.updateNotificationPreference(preference)));
        setData((current) => ({ ...current, settings: { ...current.settings, ...changes } }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "Notification preferences could not be saved.");
        return false;
      }
    },
    async addAddress(address) {
      try {
        const response = await authApi.createAddress(mapShippingAddress(address));
        if (!response?.address) throw new Error("The address service returned an invalid response.");
        const item = response.address;
        setData((current) => ({
          ...current,
          addresses: [{
            id: item.id,
            name: item.recipientName,
            line: [item.addressLine1, item.addressLine2].filter(Boolean).join(", "),
            city: [item.city, item.region].filter(Boolean).join(", "),
            postal: item.postalCode,
            countryCode: item.countryCode,
          }, ...current.addresses],
        }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "The address could not be saved.");
        return false;
      }
    },
    async deleteAddress(id) {
      try {
        await authApi.deleteAddress(id);
        setData((current) => ({ ...current, addresses: current.addresses.filter((address) => address.id !== id) }));
        setStorageError("");
        return true;
      } catch (failure) {
        setStorageError(failure instanceof Error ? failure.message : "The address could not be deleted.");
        return false;
      }
    },
  }), [data, isLoading, storageError, user.email]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function DashboardProvider({ children }) {
  const { user } = useAuth();
  if (!user?.email) throw new Error("DashboardProvider requires an authenticated user.");
  return <DashboardUserScope key={user.email.toLowerCase()} user={user}>{children}</DashboardUserScope>;
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard must be used within DashboardProvider.");
  return context;
}
