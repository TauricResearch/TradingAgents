import { useState } from "react";
import { useApp } from "../context/AppContext";

/** For a returning user who already has a key but didn't (or can't) have
 * it remembered on this device. */
export function SignInPanel() {
  const { api } = useApp();
  const [value, setValue] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    api.setApiKey(value.trim());
  }

  return (
    <section className="desk-section" aria-labelledby="signin-heading">
      <h2 className="panel-heading" id="signin-heading">
        already have a key?
      </h2>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="signin-key">api key</label>
          <input
            id="signin-key"
            type="text"
            autoComplete="off"
            placeholder="ta_..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>
        <label className="remember-row">
          <input type="checkbox" checked={api.remember} onChange={(e) => api.setRemember(e.target.checked)} />
          remember this key on this device
        </label>
        <button type="submit" className="btn" disabled={!value.trim()}>
          Continue
        </button>
      </form>
    </section>
  );
}
