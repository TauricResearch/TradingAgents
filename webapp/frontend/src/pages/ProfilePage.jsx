import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { Avatar } from "../components/Avatar";
import { QuotaBar } from "../components/QuotaBar";

function formatMemberSince(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

export function ProfilePage() {
  const { api, account, accountStatus, accountMessage, loadAccount } = useApp();
  const navigate = useNavigate();
  const [name, setName] = useState(account?.display_name || "");
  const [nameStatus, setNameStatus] = useState("idle");
  const [nameMessage, setNameMessage] = useState("");
  const [keyStatus, setKeyStatus] = useState("idle");
  const [keyMessage, setKeyMessage] = useState("");
  const [revealedKey, setRevealedKey] = useState("");
  const [checkoutStatus, setCheckoutStatus] = useState("idle");

  async function handleSaveName(event) {
    event.preventDefault();
    setNameStatus("loading");
    setNameMessage("Saving…");
    try {
      await api.updateProfile(name);
      await loadAccount();
      setNameStatus("idle");
      setNameMessage("Saved.");
    } catch (err) {
      setNameStatus("error");
      setNameMessage(err.message);
    }
  }

  async function handleRegenerateKey() {
    const confirmed = window.confirm(
      "Rotate your API key? The current key stops working immediately."
    );
    if (!confirmed) return;
    setKeyStatus("loading");
    setKeyMessage("Rotating…");
    try {
      const data = await api.regenerateKey();
      api.setApiKey(data.api_key);
      setRevealedKey(data.api_key);
      setKeyStatus("idle");
      setKeyMessage("New key issued — save it now, it will not be shown again.");
    } catch (err) {
      setKeyStatus("error");
      setKeyMessage(err.message);
    }
  }

  async function handleUpgrade() {
    setCheckoutStatus("loading");
    try {
      const data = await api.checkout();
      window.location.href = data.checkout_url;
    } catch (err) {
      setCheckoutStatus("idle");
      setNameStatus("error");
      setNameMessage(err.message);
    }
  }

  function handleSignOut() {
    api.setRemember(false);
    api.setApiKey("");
    navigate("/");
  }

  if (!account && accountStatus === "loading") {
    return (
      <main className="app-main app-main--single">
        <p className="status-line">Loading…</p>
      </main>
    );
  }

  return (
    <main className="app-main app-main--single">
      <div className="profile-page">
        <section className="card profile-header">
          <Avatar name={account?.display_name} email={account?.email} size={64} />
          <div className="profile-header__info">
            <h1 className="profile-header__name">{account?.display_name || "Unnamed trader"}</h1>
            <p className="profile-header__email">{account?.email}</p>
            <div className="profile-header__meta">
              <span className="badge" data-tone={account?.plan === "pro" ? "brand" : undefined}>
                {account?.plan}
              </span>
              <span className="profile-header__since">
                member since {formatMemberSince(account?.member_since)}
              </span>
            </div>
          </div>
        </section>

        {account && (
          <section className="card">
            <h2 className="card__title">usage</h2>
            <QuotaBar used={account.jobs_this_month} limit={account.free_tier_limit} />
            {account.plan === "free" && (
              <button type="button" className="btn btn--primary" onClick={handleUpgrade} disabled={checkoutStatus === "loading"}>
                {checkoutStatus === "loading" ? "Opening…" : "Upgrade to Pro for unlimited runs"}
              </button>
            )}
          </section>
        )}

        {accountStatus === "error" && (
          <p className="status-line" data-tone="error" role="alert">
            {accountMessage}
          </p>
        )}

        <section className="card">
          <h2 className="card__title">display name</h2>
          <p className="card__hint">Shown in the navbar and on reports you export.</p>
          <form onSubmit={handleSaveName} className="profile-form">
            <input
              id="display-name-input"
              type="text"
              maxLength={80}
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="Display name"
            />
            <button type="submit" className="btn btn--primary" disabled={nameStatus === "loading"}>
              {nameStatus === "loading" ? "Saving…" : "Save changes"}
            </button>
          </form>
          <p className="status-line" role="status" aria-live="polite" data-tone={nameStatus === "error" ? "error" : undefined}>
            {nameMessage}
          </p>
        </section>

        <section className="card">
          <h2 className="card__title">api key</h2>
          <p className="card__hint">Rotate your key if you think it leaked. The old key stops working immediately.</p>
          <button type="button" className="btn btn--ghost" onClick={handleRegenerateKey} disabled={keyStatus === "loading"}>
            {keyStatus === "loading" ? "Rotating…" : "Regenerate key"}
          </button>
          <p className="status-line" role="status" aria-live="polite" data-tone={keyStatus === "error" ? "error" : undefined}>
            {keyMessage}
          </p>
          {revealedKey && <code className="key-display">{revealedKey}</code>}
        </section>

        <section className="card">
          <h2 className="card__title">session</h2>
          <button type="button" className="btn btn--ghost" onClick={handleSignOut}>
            Sign out of this device
          </button>
        </section>
      </div>
    </main>
  );
}
