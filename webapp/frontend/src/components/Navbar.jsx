import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { useApp } from "../context/AppContext";

const LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/history", label: "History" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/profile", label: "Profile" },
];

export function Navbar() {
  const { account } = useApp();
  const [open, setOpen] = useState(false);

  return (
    <header className="navbar">
      <div className="navbar__row">
        <NavLink to="/" className="navbar__brand" onClick={() => setOpen(false)}>
          <Logo size={26} />
          <strong>TradingAgents</strong>
        </NavLink>

        <button
          type="button"
          className="navbar__menu-toggle"
          aria-expanded={open}
          aria-controls="navbar-links"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Close" : "Menu"}
        </button>

        <div className="navbar__right">
          {account && (
            <span className="navbar__quota">
              {account.plan} · {account.jobs_this_month}/{account.free_tier_limit} this month
            </span>
          )}
          <ThemeToggle />
        </div>
      </div>

      <nav id="navbar-links" className={`navbar__links${open ? " navbar__links--open" : ""}`} aria-label="Primary">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) => "navbar__link" + (isActive ? " navbar__link--active" : "")}
            onClick={() => setOpen(false)}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
