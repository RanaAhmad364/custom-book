import AuthLayout from "./AuthLayout.jsx";

export default function AuthPageShell({ eyebrow, title, description, children }) {
  return (
    <AuthLayout>
      <section className="auth-card">
        <div className="auth-card-heading">
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          {description ? <p>{description}</p> : null}
        </div>
        {children}
      </section>
    </AuthLayout>
  );
}
