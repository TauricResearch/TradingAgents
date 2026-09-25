import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { ProfileMenu } from "./ProfileMenu";
import { useApp } from "../context/AppContext";

const LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/history", label: "History" },
  { to: "/watchlist", label: "Watchlist" },
];

export function Navbar() {
  const { api } = useApp();
  const [open, setOpen] = useState(false);

  return (
    <header className="navbar">
      <div className="navbar__row">
        <NavLink to="/" className="navbar__brand" onClick={() => setOpen(false)}>
          <Logo size={30} />
          <strong>TradingAgents</strong>
        </NavLink>

        <nav className="navbar__links navbar__links--desktop" aria-label="Primary">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => "navbar__link" + (isActive ? " navbar__link--active" : "")}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="navbar__right">
          <ThemeToggle />
          {api.apiKey && <ProfileMenu />}
          <button
            type="button"
            className="navbar__menu-toggle"
            aria-expanded={open}
            aria-controls="navbar-links-mobile"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      {open && (
        <nav id="navbar-links-mobile" className="navbar__links navbar__links--mobile" aria-label="Primary">
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
      )}
    </header>
  );
}
