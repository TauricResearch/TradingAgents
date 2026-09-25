import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { ProfileMenu } from "./ProfileMenu";
import { useApp } from "../context/AppContext";

const APP_LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/history", label: "History" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/rates", label: "Rates" },
];

const MARKETING_LINKS = [
  { to: "#how-it-works", label: "How it works" },
  { to: "#features", label: "Features" },
  { to: "#pricing", label: "Pricing" },
  { to: "#faq", label: "FAQ" },
];

export function Navbar() {
  const { api, openAuthModal } = useApp();
  const [open, setOpen] = useState(false);
  const signedIn = Boolean(api.apiKey);
  const links = signedIn ? APP_LINKS : MARKETING_LINKS;

  function renderLink(link) {
    if (link.to.startsWith("#")) {
      return (
        <a key={link.to} href={link.to} className="navbar__link" onClick={() => setOpen(false)}>
          {link.label}
        </a>
      );
    }
    return (
      <NavLink
        key={link.to}
        to={link.to}
        end={link.end}
        className={({ isActive }) => "navbar__link" + (isActive ? " navbar__link--active" : "")}
        onClick={() => setOpen(false)}
      >
        {link.label}
      </NavLink>
    );
  }

  return (
    <header className="navbar">
      <div className="navbar__row">
        <NavLink to="/" className="navbar__brand" onClick={() => setOpen(false)}>
          <Logo size={30} />
          <strong>TradingAgents</strong>
        </NavLink>

        <nav className="navbar__links navbar__links--desktop" aria-label="Primary">
          {links.map(renderLink)}
        </nav>

        <div className="navbar__right">
          <ThemeToggle />
          {signedIn ? (
            <ProfileMenu />
          ) : (
            <div className="navbar__auth-actions">
              <button type="button" className="btn btn--ghost" onClick={() => openAuthModal("signin")}>
                Sign in
              </button>
              <button type="button" className="btn btn--primary" onClick={() => openAuthModal("signup")}>
                Get started
              </button>
            </div>
          )}
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
          {links.map(renderLink)}
        </nav>
      )}
    </header>
  );
}
