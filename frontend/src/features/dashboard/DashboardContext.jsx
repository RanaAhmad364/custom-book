import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import { createDashboardData } from "./dashboardService.js";
import { projectService } from "../../services/projectService.js";

const DashboardContext = createContext(null);

function DashboardUserScope({ user, children }) {
  const [storageError, setStorageError] = useState("");
  const [data, setData] = useState(() => {
    return createDashboardData(user.email);
  });
  useEffect(() => {
    let active = true;
    projectService.listProjects(user.email).then((projects) => {
      if (active) setData((current) => ({ ...current, projects: [...projects, ...current.projects.filter((project) => !projects.some((saved) => saved.id === project.id))] }));
    }).catch((failure) => {
      if (active) setStorageError(failure instanceof Error ? failure.message : "Saved projects could not be loaded.");
    });
    return () => { active = false; };
  }, [user.email]);
  const value = useMemo(() => ({
    data,
    storageError,
    updateProject(id, changes) {
      setData((current) => ({ ...current, projects: current.projects.map((project) => project.id === id ? { ...project, ...changes } : project) }));
      projectService.updateProject(user.email, id, changes).catch((failure) => {
        setStorageError(failure instanceof Error ? failure.message : "The project update could not be saved.");
      });
    },
    deleteProject(id) {
      setData((current) => ({ ...current, projects: current.projects.filter((project) => project.id !== id) }));
      projectService.deleteProject(user.email, id).catch((failure) => {
        setStorageError(failure instanceof Error ? failure.message : "The project could not be deleted.");
      });
    },
    duplicateProject(id) {
      projectService.duplicateProject(user.email, id).then((copy) => {
        if (copy) setData((current) => ({ ...current, projects: [copy, ...current.projects] }));
      }).catch((failure) => {
        setStorageError(failure instanceof Error ? failure.message : "The project could not be duplicated.");
      });
    },
    setNotifications(notifications) {
      setData((current) => ({ ...current, notifications }));
    },
    updateProfile(changes) {
      setData((current) => ({ ...current, profile: { ...current.profile, ...changes } }));
    },
    updateSettings(changes) {
      setData((current) => ({ ...current, settings: { ...current.settings, ...changes } }));
    },
    addAddress(address) {
      setData((current) => ({ ...current, addresses: [...current.addresses, { ...address, id: `address-${Date.now()}` }] }));
    },
    deleteAddress(id) {
      setData((current) => ({ ...current, addresses: current.addresses.filter((address) => address.id !== id) }));
    },
  }), [data, storageError, user.email]);

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
