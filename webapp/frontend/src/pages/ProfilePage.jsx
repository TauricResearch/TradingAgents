import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";

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
      <div>
        <section className="desk-section" aria-labelledby="profile-heading">
          <h2 className="panel-heading" id="profile-heading">
            profile
          </h2>
          {account && (
            <dl className="account-grid">
              <dt>email</dt>
              <dd>{account.email}</dd>
              <dt>plan</dt>
              <dd>{account.plan}</dd>
              <dt>member since</dt>
              <dd>{formatMemberSince(account.member_since)}</dd>
              <dt>runs this month</dt>
              <dd>{account.jobs_this_month}</dd>
              <dt>free-tier limit</dt>
              <dd>{account.free_tier_limit}</dd>
            </dl>
          )}
          {accountStatus === "error" && (
            <p className="status-line" data-tone="error" role="alert">
              {accountMessage}
            </p>
          )}
        </section>

        <section className="desk-section" aria-labelledby="display-name-heading">
          <h2 className="panel-heading" id="display-name-heading">
            display name
          </h2>
          <form onSubmit={handleSaveName}>
            <div className="field">
              <label htmlFor="display-name-input">shown on reports you export (optional)</label>
              <input
                id="display-name-input"
                type="text"
                maxLength={80}
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <button type="submit" className="btn" disabled={nameStatus === "loading"}>
              {nameStatus === "loading" ? "Saving…" : "Save changes"}
            </button>
          </form>
          <p className="status-line" role="status" aria-live="polite" data-tone={nameStatus === "error" ? "error" : undefined}>
            {nameMessage}
          </p>
        </section>

        <section className="desk-section" aria-labelledby="plan-heading">
          <h2 className="panel-heading" id="plan-heading">
            plan
          </h2>
          <button type="button" className="btn" onClick={handleUpgrade} disabled={checkoutStatus === "loading"}>
            {checkoutStatus === "loading" ? "Opening…" : "Upgrade to Pro"}
          </button>
        </section>

        <section className="desk-section" aria-labelledby="key-heading">
          <h2 className="panel-heading" id="key-heading">
            api key
          </h2>
          <p className="step-help">Rotate your key if you think it leaked. The old key stops working immediately.</p>
          <button type="button" className="btn btn--ghost" onClick={handleRegenerateKey} disabled={keyStatus === "loading"}>
            {keyStatus === "loading" ? "Rotating…" : "Regenerate key"}
          </button>
          <p className="status-line" role="status" aria-live="polite" data-tone={keyStatus === "error" ? "error" : undefined}>
            {keyMessage}
          </p>
          {revealedKey && <code className="key-display">{revealedKey}</code>}
        </section>

        <section className="desk-section" aria-labelledby="signout-heading">
          <h2 className="panel-heading" id="signout-heading">
            session
          </h2>
          <button type="button" className="btn btn--ghost" onClick={handleSignOut}>
            Sign out of this device
          </button>
        </section>
      </div>
    </main>
  );
}
