import { useState } from "react";

export function SignupPanel({ api, onKeyIssued }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [message, setMessage] = useState("");
  const [issuedKey, setIssuedKey] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus("loading");
    setMessage("Requesting a key...");
    try {
      const data = await api.signup(email);
      setIssuedKey(data.api_key);
      setStatus("done");
      setMessage("Key issued — save it now, it will not be shown again.");
      onKeyIssued(data.api_key);
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="signup-heading">
      <h2 className="panel-heading" id="signup-heading">
        get your key
      </h2>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="signup-email">email</label>
          <input
            id="signup-email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <button type="submit" className="btn" disabled={status === "loading"}>
          {status === "loading" ? "Requesting…" : "Get key"}
        </button>
      </form>
      <p className="status-line" role="status" aria-live="polite" data-tone={status === "error" ? "error" : undefined}>
        {message}
      </p>
      {issuedKey && <code className="key-display">{issuedKey}</code>}
    </section>
  );
}
