import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext.jsx";
import { DashboardPageHeading } from "../../dashboard/DashboardUI.jsx";

export default function AdminProfilePage() {
  const { user, updateProfile } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(user?.name || "");
    setPhone(user?.phone || "");
  }, [user]);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    setSaving(true);
    try {
      await updateProfile({ name, phone });
      setMessage("Profile updated.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Profile could not be updated.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="admin-page">
    <DashboardPageHeading eyebrow="Platform" title="Admin profile" description="Manage the name and contact number on your administrator account." />
    <form className="admin-panel admin-profile-form" onSubmit={submit}>
      {message ? <p className="admin-flash admin-flash-success" role="status">{message}</p> : null}
      {error ? <p className="admin-flash admin-flash-error" role="alert">{error}</p> : null}
      <label>Name<input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} required /></label>
      <label>Email<input value={user?.email || ""} readOnly /></label>
      <label>Phone<input value={phone} maxLength={40} onChange={(event) => setPhone(event.target.value)} /></label>
      <button className="admin-button admin-button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
    </form>
  </div>;
}
