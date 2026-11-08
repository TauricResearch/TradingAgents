/* Persistent usage monitor. All provider/model values are rendered as text. */
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("usage-filters");
  const number = (value) => new Intl.NumberFormat().format(value || 0);
  const money = (value) => new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", minimumFractionDigits: 4}).format(value);
  let requestId = 0;
  function query() {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) if (value) params.set(key, value);
    return params;
  }
  function row(values) {
    const tr = document.createElement("tr");
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    return tr;
  }
  async function request(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`Richiesta non riuscita (${response.status})`);
    return response.json();
  }
  async function refresh() {
    const current = ++requestId;
    $("usage-error").hidden = true;
    try {
      const data = await request(`/api/usage?${query()}`);
      if (current !== requestId) return;
      const t = data.totals;
      $("usage-summary").replaceChildren(...[
        ["Chiamate", number(t.calls)], ["Token input", number(t.tokens_in)],
        ["Token output", number(t.tokens_out)], ["Token cache", number(t.cached_tokens)],
        ["Costo stimato noto", t.calls && t.unpriced === t.calls ? "Non disponibile" : money(t.cost_usd)],
        ["Tempo chiamate cumulato", `${t.duration.toFixed(1)} s`],
      ].map(([label, value]) => {
        const card = document.createElement("div");
        const title = document.createElement("span"); title.textContent = label;
        const amount = document.createElement("strong"); amount.textContent = value;
        card.append(title, amount); return card;
      }));
      $("usage-note").textContent = `${t.failed} fallite · ${t.unfinished} in corso o interrotte · ${t.unknown_usage} senza token comunicati · ${t.unpriced} senza costo disponibile. Date in UTC; tempi delle chiamate parallele sommati.`;
      $("usage-models").replaceChildren(...data.models.map((m) => row([
        m.provider, m.model, number(m.calls), number(m.tokens_in), number(m.tokens_out),
        m.unpriced === m.calls ? "Non disponibile" : money(m.cost_usd) + (m.unpriced ? " (parziale)" : ""),
      ])));
      $("usage-calls").replaceChildren(...data.calls.map((c) => row([
        new Date(c.started_at * 1000).toLocaleString(), c.ticker || "—", c.run_id,
        c.source, c.agent, `${c.provider} / ${c.model}`, c.status,
        c.tokens_in === null ? "—" : number(c.tokens_in),
        c.tokens_out === null ? "—" : number(c.tokens_out),
        c.duration === null ? "—" : `${c.duration.toFixed(1)} s`,
        c.cost_usd === null ? "Non disponibile" : money(c.cost_usd),
      ])));
      $("usage-empty").hidden = t.calls > 0;
      $("usage-limit").textContent = t.calls > data.calls.length ? `Visualizzate le ultime ${data.calls.length} chiamate su ${t.calls}. Il CSV contiene tutte le chiamate filtrate.` : "";
      $("usage-csv").href = `/api/usage.csv?${query()}`;
      const prices = await request("/api/usage/prices");
      if (current !== requestId) return;
      $("usage-prices").replaceChildren(...prices.prices.map((p) => row([
        p.provider, p.model, p.input_rate, p.output_rate, p.cache_rate ?? "—",
        new Date(p.updated_at * 1000).toLocaleString(),
      ])));
    } catch (error) {
      if (current !== requestId) return;
      $("usage-error").textContent = error.message;
      $("usage-error").hidden = false;
    }
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); refresh(); });
  $("usage-reset").addEventListener("click", () => { form.reset(); refresh(); });
  $("usage-price-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    const values = Object.fromEntries(new FormData(event.target));
    for (const key of ["input_rate", "output_rate", "cache_rate"]) values[key] = values[key] === "" ? null : Number(values[key]);
    try {
      await request("/api/usage/prices", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values)});
      $("usage-price-message").textContent = "Tariffa salvata. Si applica alle nuove chiamate.";
      refresh();
    } catch (error) { $("usage-price-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  document.querySelector('[data-mode="usage"]').addEventListener("click", refresh);
  setInterval(() => { if (!document.querySelector('[data-mode-panel="usage"]').hidden) refresh(); }, 10000);
})();
