import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

export default function PasswordField({ id, label, name, value, onChange, autoComplete, required = true, minLength = 8 }) {
  const [visible, setVisible] = useState(false);

  return (
    <label className="auth-field" htmlFor={id}>
      <span>{label}</span>
      <span className="auth-password-wrap">
        <input
          id={id}
          name={name}
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          required={required}
          minLength={minLength}
        />
        <button
          type="button"
          className="auth-password-toggle"
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </span>
    </label>
  );
}
