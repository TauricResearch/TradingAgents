const form = document.querySelector("#run-form");
const submit = document.querySelector("#submit");
const statusBox = document.querySelector("#status");
const reportLink = document.querySelector("#report");
const dateInput = document.querySelector("#date");
const today = new Date();
dateInput.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

fetch("/api/config")
  .then((response) => response.ok ? response.json() : Promise.reject())
  .then(({ provider, model }) => {
    document.querySelector("#model-info").textContent = `Configured provider: ${provider} · model: ${model}`;
  })
  .catch(() => {
    document.querySelector("#model-info").textContent = "Could not load the configured provider and model.";
  });

function showStatus(message, isError = false) {
  statusBox.hidden = false;
  statusBox.classList.toggle("error", isError);
  statusBox.textContent = message;
}

async function watchRun(id) {
  while (true) {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "Could not read analysis status.");
    if (job.status === "complete") {
      showStatus(`Analysis complete for ${job.ticker} (${job.date}).`);
      reportLink.href = job.report_url;
      reportLink.hidden = false;
      return;
    }
    if (job.status === "failed") throw new Error(job.error);
    showStatus(job.status === "queued"
      ? "Your analysis is queued."
      : "Analysis is running. This can take several minutes.");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  reportLink.hidden = true;
  submit.disabled = true;
  showStatus("Starting analysis...");
  const body = {
    ticker: form.elements.ticker.value,
    date: form.elements.date.value,
    analysts: [...form.querySelectorAll('input[name="analysts"]:checked')].map((input) => input.value),
  };
  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start analysis.");
    await watchRun(result.id);
  } catch (error) {
    showStatus(error.message || "The web server could not be reached.", true);
  } finally {
    submit.disabled = false;
  }
});
