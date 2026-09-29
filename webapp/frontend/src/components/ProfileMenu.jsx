import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "./Avatar";
import { useApp } from "../context/AppContext";

export function ProfileMenu() {
  const { api, account } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function handlePointer(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function go(path) {
    setOpen(false);
    navigate(path);
  }

  function signOut() {
    setOpen(false);
    api.setRemember(false);
    api.setApiKey("");
    navigate("/");
  }

  return (
    <div className="profile-menu" ref={rootRef}>
      <button
        type="button"
        className="profile-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Avatar name={account?.display_name} email={account?.email} size={30} />
      </button>

      {open && (
        <div className="profile-menu__panel" role="menu">
          <div className="profile-menu__identity">
            <Avatar name={account?.display_name} email={account?.email} size={36} />
            <div>
              <div className="profile-menu__name">{account?.display_name || account?.email || "Account"}</div>
              {account?.display_name && <div className="profile-menu__email">{account.email}</div>}
            </div>
          </div>
          {account && (
            <div className="profile-menu__plan">
              <span className="badge" data-tone={account.plan === "pro" ? "brand" : undefined}>
                {account.plan}
              </span>
              <span className="profile-menu__usage">
                {account.jobs_this_month}/{account.free_tier_limit} runs this month
              </span>
            </div>
          )}
          <div className="profile-menu__divider" />
          <button type="button" role="menuitem" className="profile-menu__item" onClick={() => go("/profile")}>
            Profile settings
          </button>
          <button type="button" role="menuitem" className="profile-menu__item" onClick={() => go("/watchlist")}>
            Watchlist
          </button>
          <div className="profile-menu__divider" />
          <button type="button" role="menuitem" className="profile-menu__item profile-menu__item--danger" onClick={signOut}>
            Sign out of this device
          </button>
        </div>
      )}
    </div>
  );
}
