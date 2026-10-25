import { useState } from "react";
import { ArrowRight, LogOut, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import PasswordField from "../../features/auth/PasswordField.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";

export default function Account() {
  const { user, logout, updateProfile, changePassword } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState({ name: user?.name ?? "", phone: user?.phone ?? "" });
  const [password, setPassword] = useState({ currentPassword: "", newPassword: "" });
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function endSession() {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    setMessage("");
    try {
      await updateProfile(profile);
      setMessage("Your profile has been updated.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Profile update failed.");
    } finally {
      setStatus("idle");
    }
  }

  async function savePassword(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    setMessage("");
    try {
      await changePassword(password);
      navigate("/login", { replace: true, state: { passwordChanged: true } });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Password update failed.");
      setStatus("idle");
    }
  }

  return (
    <AuthPageShell eyebrow="Your MemoryBook" title="Your account." description="Manage your profile and account security.">
      <div className="auth-status-illustration"><UserRound size={25} /><span>Signed in as <strong>{user?.email}</strong></span></div>
      <form className="auth-form" onSubmit={saveProfile}>
        <label className="auth-field"><span>Name</span><input autoComplete="name" maxLength={100} value={profile.name} onChange={(event) => setProfile((current) => ({ ...current, name: event.target.value }))} /></label>
        <label className="auth-field"><span>Phone</span><input autoComplete="tel" maxLength={40} value={profile.phone} onChange={(event) => setProfile((current) => ({ ...current, phone: event.target.value }))} /></label>
        <button className="button button-dark auth-submit" type="submit" disabled={status === "loading"}>Save profile</button>
      </form>
      <form className="auth-form" onSubmit={savePassword}>
        <h2>Change password</h2>
        <PasswordField id="account-current-password" label="Current password" name="currentPassword" value={password.currentPassword} onChange={(event) => setPassword((current) => ({ ...current, currentPassword: event.target.value }))} autoComplete="current-password" />
        <PasswordField id="account-new-password" label="New password" name="newPassword" value={password.newPassword} onChange={(event) => setPassword((current) => ({ ...current, newPassword: event.target.value }))} autoComplete="new-password" />
        <button className="button button-outline auth-submit" type="submit" disabled={status === "loading"}>Update password</button>
      </form>
      {message ? <p className="auth-message auth-message-success" role="status">{message}</p> : null}
      {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
      <button className="button button-outline auth-submit" type="button" onClick={endSession}>Log out <LogOut size={15} /></button>
      <Link className="auth-switch auth-center-link" to="/books">Explore books <ArrowRight size={14} /></Link>
    </AuthPageShell>
  );
}
