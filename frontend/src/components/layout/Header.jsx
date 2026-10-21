import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, BookOpen, Menu, Search, X } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext.jsx";

const navItems = [
  { to: "/", label: "Home", end: true },
  { to: "/books", label: "Explore Books" },
  { to: "/collections", label: "Collections" },
  { to: "/how-it-works", label: "How It Works" },
  { to: "/pricing", label: "Pricing" },
  { to: "/about", label: "About" },
];

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <>
      <header className="site-header premium-header">
        <Link className="wordmark" to="/" aria-label="MemoryBook home">
          <span className="wordmark-mark">
            <BookOpen size={20} strokeWidth={1.65} />
          </span>
          <span className="wordmark-name">MemoryBook</span>
        </Link>
        <button
          className="icon-button menu-toggle"
          type="button"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
        <nav className={`primary-nav ${menuOpen ? "is-open" : ""}`}>
          {navItems.map((item) =>
            item.to.includes("#") ? (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </Link>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMenuOpen(false)}
                end={item.end}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                {item.label}
              </NavLink>
            ),
          )}
          <button
            className="header-search"
            type="button"
            aria-label={searchOpen ? "Close book search" : "Search books"}
            aria-expanded={searchOpen}
            onClick={() => {
              setSearchOpen((open) => !open);
              setMenuOpen(false);
            }}
          >
            {searchOpen ? <X size={16} /> : <Search size={16} />}
            <span className="search-word">Search</span>
          </button>
          {user ? (
            <>
              <NavLink className="header-login" to="/dashboard" onClick={() => setMenuOpen(false)}>
                My workspace
              </NavLink>
              <button
                className="header-login"
                type="button"
                onClick={() => {
                  logout();
                  setMenuOpen(false);
                  navigate("/");
                }}
              >
                Log out
              </button>
            </>
          ) : (
            <Link className="header-login" to="/login" onClick={() => setMenuOpen(false)}>
              Login
            </Link>
          )}
          <Link
            className="button button-small button-dark nav-cta"
            to="/books"
            onClick={() => setMenuOpen(false)}
          >
            Create a Book <ArrowUpRight size={15} />
          </Link>
        </nav>
        {searchOpen ? (
          <form
            className="header-search-popover"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              const term = searchTerm.trim();
              navigate(term ? `/books?q=${encodeURIComponent(term)}` : "/books");
              setSearchOpen(false);
              setSearchTerm("");
            }}
          >
            <Search size={16} aria-hidden="true" />
            <label className="sr-only" htmlFor="site-book-search">
              Search books and stories
            </label>
            <input
              id="site-book-search"
              autoFocus
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search books and stories"
            />
            <button type="submit">Search</button>
          </form>
        ) : null}
      </header>
    </>
  );
}
