import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi } from "./authApi.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [pendingEmail, setPendingEmail] = useState("");

  useEffect(() => {
    let active = true;
    authApi.currentUser()
      .then((result) => {
        if (active) setUser(result.user);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const register = useCallback(async (values) => {
    const result = await authApi.register(values);
    setPendingEmail(result.user.email);
    return result;
  }, []);
  const login = useCallback(async (values) => {
    const result = await authApi.login(values);
    setUser(result.user);
    return result.user;
  }, []);
  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
    }
  }, []);
  const updateProfile = useCallback(async (profile) => {
    const result = await authApi.updateProfile(profile);
    setUser(result.user);
    return result.user;
  }, []);
  const changePassword = useCallback(async (values) => {
    const result = await authApi.changePassword(values);
    setUser(null);
    return result;
  }, []);
  const requestPasswordReset = useCallback((email) => authApi.requestPasswordReset(email), []);
  const resetPassword = useCallback((values) => authApi.resetPassword(values), []);
  const verifyOtp = useCallback(async (email, code) => {
    const result = await authApi.verifyOtp({ email: email || pendingEmail, code });
    return result;
  }, [pendingEmail]);
  const resendOtp = useCallback((email = pendingEmail) => authApi.resendOtp(email), [pendingEmail]);
  const clearPendingEmail = useCallback(() => setPendingEmail(""), []);

  const value = useMemo(() => ({
    ready,
    user,
    pendingEmail,
    register,
    login,
    logout,
    updateProfile,
    changePassword,
    requestPasswordReset,
    resetPassword,
    verifyOtp,
    resendOtp,
    clearPendingEmail,
  }), [
    ready, user, pendingEmail, register, login, logout, updateProfile, changePassword,
    requestPasswordReset, resetPassword, verifyOtp, resendOtp, clearPendingEmail,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
