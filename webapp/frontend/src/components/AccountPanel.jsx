import { useState } from "react";

export function AccountPanel({ api, account, accountStatus, accountMessage, onLoad }) {
  const [checkoutStatus, setCheckoutStatus] = useState("idle");
  const [checkoutError, setCheckoutError] = useState("");

  async function upgrade() {
    setCheckoutStatus("loading");
    setCheckoutError("");
    try {
      const data = await api.checkout();
      window.location.href = data.checkout_url;
    } catch (err) {
      setCheckoutStatus("idle");
      setCheckoutError(err.message);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="account-heading">
      <h2 className="panel-heading" id="account-heading">
        your account
      </h2>
      <div className="field">
        <label htmlFor="api-key-input">api key</label>
        <input
          id="api-key-input"
          type="text"
          placeholder="ta_..."
          autoComplete="off"
          value={api.apiKey}
          onChange={(e) => api.setApiKey(e.target.value)}
        />
      </div>
      <label className="remember-row">
        <input
          type="checkbox"
          checked={api.remember}
          onChange={(e) => api.setRemember(e.target.checked)}
        />
        remember this key on this device
      </label>
      <button type="button" className="btn" onClick={onLoad} disabled={accountStatus === "loading"}>
        {accountStatus === "loading" ? "Loading…" : "Load account"}
      </button>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={upgrade}
        disabled={checkoutStatus === "loading" || !api.apiKey}
      >
        {checkoutStatus === "loading" ? "Opening…" : "Upgrade to Pro"}
      </button>
      <p
        className="status-line"
        role="status"
        aria-live="polite"
        data-tone={accountStatus === "error" || checkoutError ? "error" : undefined}
      >
        {checkoutError || accountMessage}
      </p>
      {account && (
        <dl className="account-grid">
          <dt>plan</dt>
          <dd>{account.plan}</dd>
          <dt>runs this month</dt>
          <dd>{account.jobs_this_month}</dd>
          <dt>free-tier limit</dt>
          <dd>{account.free_tier_limit}</dd>
        </dl>
      )}
    </section>
  );
}
