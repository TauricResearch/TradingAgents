const form = document.querySelector("#analysis-form");
const runButton = document.querySelector("#run-button");
const clearButton = document.querySelector("#clear-checkpoints");
const statusText = document.querySelector("#status-text");
const runMeta = document.querySelector("#run-meta");
const agentsEl = document.querySelector("#agents");
const statsEl = document.querySelector("#stats");
const reportsEl = document.querySelector("#reports");
const messagesEl = document.querySelector("#messages");
const analysisDateInput = document.querySelector("#analysis-date");
const providerInput = document.querySelector("#llm-provider");
const backendUrlInput = document.querySelector("#backend-url");
const quickModelInput = document.querySelector("#quick-model");
const deepModelInput = document.querySelector("#deep-model");
const memoTitle = document.querySelector("#memo-title");
const memoSubtitle = document.querySelector("#memo-subtitle");
const memoDecision = document.querySelector("#memo-decision");
const memoThesis = document.querySelector("#memo-thesis");
const memoTakeaways = document.querySelector("#memo-takeaways");
const memoSections = document.querySelector("#memo-sections");
const refreshReportsButton = document.querySelector("#refresh-reports");
const savedReportsList = document.querySelector("#saved-reports-list");

const reportSections = new Map();
const runContext = {
  ticker: "",
  analysisDate: "",
  assetType: ""
};

const providerDefaults = {
  openai: {
    backendUrl: "https://api.openai.com/v1",
    quickModel: "gpt-5.4-mini",
    deepModel: "gpt-5.4"
  },
  google: {
    backendUrl: "",
    quickModel: "gemini-3-flash-preview",
    deepModel: "gemini-3.1-pro-preview"
  },
  anthropic: {
    backendUrl: "https://api.anthropic.com/",
    quickModel: "claude-sonnet-4-6",
    deepModel: "claude-opus-4-7"
  },
  xai: {
    backendUrl: "https://api.x.ai/v1",
    quickModel: "grok-4.20-non-reasoning",
    deepModel: "grok-4.20-reasoning"
  },
  deepseek: {
    backendUrl: "https://api.deepseek.com",
    quickModel: "deepseek-v4-flash",
    deepModel: "deepseek-v4-pro"
  },
  qwen: {
    backendUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    quickModel: "qwen3.6-flash",
    deepModel: "qwen3.6-plus"
  },
  "qwen-cn": {
    backendUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    quickModel: "qwen3.6-flash",
    deepModel: "qwen3.6-plus"
  },
  glm: {
    backendUrl: "https://api.z.ai/api/paas/v4/",
    quickModel: "glm-5-turbo",
    deepModel: "glm-5.1"
  },
  "glm-cn": {
    backendUrl: "https://open.bigmodel.cn/api/paas/v4/",
    quickModel: "glm-5-turbo",
    deepModel: "glm-5.1"
  },
  minimax: {
    backendUrl: "https://api.minimax.io/v1",
    quickModel: "MiniMax-M2.7-highspeed",
    deepModel: "MiniMax-M2.7"
  },
  "minimax-cn": {
    backendUrl: "https://api.minimaxi.com/v1",
    quickModel: "MiniMax-M2.7-highspeed",
    deepModel: "MiniMax-M2.7"
  },
  openrouter: {
    backendUrl: "https://openrouter.ai/api/v1",
    quickModel: "",
    deepModel: ""
  },
  azure: {
    backendUrl: "",
    quickModel: "",
    deepModel: ""
  },
  ollama: {
    backendUrl: "http://localhost:11434/v1",
    quickModel: "qwen3:latest",
    deepModel: "qwen3:latest"
  }
};

function setDefaultDate() {
  if (!analysisDateInput.value) {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    analysisDateInput.value = `${year}-${month}-${day}`;
  }
}

function applyProviderDefaults() {
  const defaults = providerDefaults[providerInput.value];
  if (!defaults) {
    backendUrlInput.placeholder = "";
    backendUrlInput.value = "";
    quickModelInput.value = "";
    deepModelInput.value = "";
    return;
  }

  backendUrlInput.placeholder = defaults.backendUrl || "Provider default";
  backendUrlInput.value = "";
  quickModelInput.value = defaults.quickModel;
  deepModelInput.value = defaults.deepModel;
}

function setStatus(status, meta) {
  statusText.textContent = status;
  if (meta !== undefined) {
    runMeta.textContent = meta;
  }
}

function clearDashboard() {
  reportSections.clear();
  agentsEl.textContent = "Waiting for run.";
  agentsEl.className = "empty-state";
  statsEl.textContent = "No stats yet.";
  statsEl.className = "empty-state";
  reportsEl.textContent = "No report sections yet.";
  reportsEl.className = "report-list empty-state";
  messagesEl.textContent = "No events yet.";
  messagesEl.className = "empty-state";
  memoTitle.textContent = "Awaiting analysis";
  memoSubtitle.textContent = "Run an analysis to build the research memo.";
  memoDecision.textContent = "Pending";
  memoDecision.className = "decision-badge neutral";
  memoThesis.textContent = "The investment thesis will appear as report sections stream in.";
  memoTakeaways.replaceChildren(makeListItem("No takeaways yet."));
  memoSections.textContent = "No research sections yet.";
  memoSections.className = "memo-sections empty-state";
  runContext.ticker = "";
  runContext.analysisDate = "";
  runContext.assetType = "";
}

function resetMemo() {
  reportSections.clear();
  memoTitle.textContent = "Awaiting analysis";
  memoSubtitle.textContent = "Run an analysis to build the research memo.";
  memoDecision.textContent = "Pending";
  memoDecision.className = "decision-badge neutral";
  memoThesis.textContent = "The investment thesis will appear as report sections stream in.";
  memoTakeaways.replaceChildren(makeListItem("No takeaways yet."));
  memoSections.textContent = "No research sections yet.";
  memoSections.className = "memo-sections empty-state";
  runContext.ticker = "";
  runContext.analysisDate = "";
  runContext.assetType = "";
}

function normalizeStatus(status) {
  return String(status || "pending").replaceAll("_", " ");
}

function renderAgents(agents) {
  agentsEl.className = "";
  agentsEl.replaceChildren(
    ...Object.entries(agents || {}).map(([name, status]) => {
      const row = document.createElement("div");
      row.className = "agent";

      const agentName = document.createElement("span");
      agentName.className = "agent-name";
      agentName.textContent = name;

      const pill = document.createElement("span");
      const normalized = normalizeStatus(status);
      pill.className = `status-pill ${String(status).replaceAll("_", "-")}`;
      pill.textContent = normalized;

      row.append(agentName, pill);
      return row;
    })
  );
}

function addMessage(type, text) {
  if (messagesEl.classList.contains("empty-state")) {
    messagesEl.replaceChildren();
    messagesEl.className = "";
  }

  const node = document.createElement("div");
  node.className = "message";

  const label = document.createElement("span");
  label.className = "message-type";
  label.textContent = type || "Message";

  const content = document.createElement("div");
  content.className = "message-text";
  content.textContent = text || "";

  node.append(label, content);
  messagesEl.prepend(node);
}

function makeListItem(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
}

function reportTitle(section) {
  const titles = {
    market_report: "Market Analysis",
    sentiment_report: "Sentiment Analysis",
    news_report: "News Analysis",
    fundamentals_report: "Fundamentals Analysis",
    investment_plan: "Research Debate",
    trader_investment_plan: "Trader Plan",
    final_trade_decision: "Portfolio Decision"
  };
  return titles[section] || section.replaceAll("_", " ");
}

function textFromReport(content) {
  if (typeof content === "string") {
    return content;
  }
  return JSON.stringify(content, null, 2);
}

function cleanReportLine(line) {
  return line
    .replace(/^#{1,6}\s*/, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .replace(/\*\*/g, "")
    .trim();
}

function splitReportBlocks(text) {
  return text
    .split(/\n{2,}/)
    .map((block) => cleanReportLine(block.replace(/\s+/g, " ")))
    .filter(Boolean);
}

function extractBullets(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => /^\s*(?:[-*]|\d+[.)])\s+/.test(line))
    .map(cleanReportLine)
    .filter((line) => line.length > 20)
    .slice(0, 5);
}

function extractSummary(text) {
  const blocks = splitReportBlocks(text);
  const summary = blocks.find((block) => block.length > 40) || blocks[0] || "Section details are still streaming.";
  return summary.length > 320 ? `${summary.slice(0, 317).trim()}...` : summary;
}

function extractDecisionLabel(text) {
  const normalized = text.toLowerCase();
  const hasBuy = /\b(buy|bullish|accumulate|long)\b/.test(normalized);
  const hasSell = /\b(sell|bearish|short|reduce)\b/.test(normalized);
  const hasHold = /\b(hold|neutral|wait|watch)\b/.test(normalized);

  if (hasBuy && !hasSell) {
    return "Buy";
  }
  if (hasSell && !hasBuy) {
    return "Sell";
  }
  if (hasHold) {
    return "Hold";
  }
  return "Review";
}

function updateMemoDecision(label) {
  const normalized = label.toLowerCase();
  memoDecision.textContent = label;
  memoDecision.className = `decision-badge ${normalized}`;
}

function collectTakeaways() {
  const takeaways = [];
  const prioritySections = ["final_trade_decision", "investment_plan", "trader_investment_plan"];

  for (const section of prioritySections) {
    const content = reportSections.get(section);
    if (!content) {
      continue;
    }
    takeaways.push(...extractBullets(textFromReport(content)));
  }

  if (takeaways.length === 0) {
    for (const content of reportSections.values()) {
      const summary = extractSummary(textFromReport(content));
      if (summary && summary !== "Section details are still streaming.") {
        takeaways.push(summary);
      }
      if (takeaways.length >= 4) {
        break;
      }
    }
  }

  return takeaways.slice(0, 5);
}

function renderMemoSection(section, content) {
  const text = textFromReport(content);
  const article = document.createElement("article");
  article.className = "memo-section";

  const header = document.createElement("header");
  header.className = "memo-section-header";

  const title = document.createElement("h3");
  title.textContent = reportTitle(section);

  const status = document.createElement("span");
  status.className = "section-status";
  status.textContent = "Complete";

  header.append(title, status);

  const summary = document.createElement("p");
  summary.className = "section-summary";
  summary.textContent = extractSummary(text);

  const bullets = extractBullets(text);
  const list = document.createElement("ul");
  list.className = "section-highlights";
  if (bullets.length > 0) {
    list.replaceChildren(...bullets.map(makeListItem));
  } else {
    list.replaceChildren(makeListItem("No explicit bullets detected; review the section details below."));
  }

  const raw = document.createElement("details");
  raw.className = "raw-details";

  const rawLabel = document.createElement("summary");
  rawLabel.textContent = "Raw output";

  const body = document.createElement("pre");
  body.textContent = text;

  raw.append(rawLabel, body);
  article.append(header, summary, list, raw);
  return article;
}

function renderMemo() {
  if (runContext.ticker) {
    memoTitle.textContent = `${runContext.ticker} Investment Memo`;
    memoSubtitle.textContent = `${runContext.analysisDate || "Selected date"} - ${runContext.assetType || "asset"} research packet`;
  }

  const finalDecision = reportSections.get("final_trade_decision");
  if (finalDecision) {
    const finalText = textFromReport(finalDecision);
    updateMemoDecision(extractDecisionLabel(finalText));
    memoThesis.textContent = extractSummary(finalText);
  } else {
    updateMemoDecision("In Review");
    const firstSection = Array.from(reportSections.values())[0];
    memoThesis.textContent = firstSection
      ? extractSummary(textFromReport(firstSection))
      : "The investment thesis will appear as report sections stream in.";
  }

  const takeaways = collectTakeaways();
  memoTakeaways.replaceChildren(...(takeaways.length > 0 ? takeaways : ["No takeaways yet."]).map(makeListItem));

  if (reportSections.size === 0) {
    memoSections.textContent = "No research sections yet.";
    memoSections.className = "memo-sections empty-state";
    return;
  }

  memoSections.className = "memo-sections";
  memoSections.replaceChildren(
    ...Array.from(reportSections.entries()).map(([section, content]) => renderMemoSection(section, content))
  );
}

function renderReports() {
  reportsEl.className = "report-list";
  reportsEl.replaceChildren(
    ...Array.from(reportSections.entries()).map(([section, content]) => {
      const node = document.createElement("details");
      node.className = "report-section raw-audit";

      const title = document.createElement("summary");
      title.className = "section-title";
      title.textContent = reportTitle(section);

      const body = document.createElement("pre");
      body.className = "report-content";
      body.textContent = textFromReport(content);

      node.append(title, body);
      return node;
    })
  );
}

function setSavedReportsMessage(message) {
  savedReportsList.textContent = message;
  savedReportsList.className = "saved-reports-list empty-state";
}

function renderSavedReports(reports) {
  if (!reports.length) {
    setSavedReportsMessage("No saved reports found.");
    return;
  }

  savedReportsList.className = "saved-reports-list";
  savedReportsList.replaceChildren(
    ...reports.map((report) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "saved-report-button";
      button.dataset.path = report.path;

      const ticker = document.createElement("strong");
      ticker.textContent = report.ticker || "Unknown";

      const meta = document.createElement("span");
      meta.textContent = report.analysis_date || "Unknown date";

      button.append(ticker, meta);
      button.addEventListener("click", () => loadSavedReport(report.path));
      return button;
    })
  );
}

async function loadSavedReports() {
  refreshReportsButton.disabled = true;
  setSavedReportsMessage("Loading saved reports...");

  try {
    const response = await fetch("/api/reports");
    const result = await response.json();
    if (!response.ok) {
      setSavedReportsMessage(result.detail || "Could not load saved reports.");
      return;
    }
    renderSavedReports(result.reports || []);
  } catch (error) {
    setSavedReportsMessage(error instanceof Error ? error.message : String(error));
  } finally {
    refreshReportsButton.disabled = false;
  }
}

function loadReportSectionsFromState(state) {
  const sectionKeys = [
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision"
  ];

  for (const key of sectionKeys) {
    if (state[key]) {
      reportSections.set(key, state[key]);
    }
  }

  if (!reportSections.has("investment_plan") && state.investment_debate_state?.judge_decision) {
    reportSections.set("investment_plan", state.investment_debate_state.judge_decision);
  }

  if (!reportSections.has("final_trade_decision") && state.risk_debate_state?.judge_decision) {
    reportSections.set("final_trade_decision", state.risk_debate_state.judge_decision);
  }
}

async function loadSavedReport(path) {
  setStatus("Loading saved report", path);

  try {
    const response = await fetch(`/api/reports/load?path=${encodeURIComponent(path)}`);
    const state = await response.json();
    if (!response.ok) {
      setStatus(`Error ${response.status}`, state.detail || "Could not load saved report.");
      return;
    }

    resetMemo();
    agentsEl.textContent = "Saved report loaded.";
    agentsEl.className = "empty-state";
    statsEl.textContent = JSON.stringify(
      {
        source: "saved_report",
        ticker: state.company_of_interest || "Unknown",
        trade_date: state.trade_date || "Unknown",
        sections: Object.keys(state).filter((key) => key.endsWith("_report")).length
      },
      null,
      2
    );
    statsEl.className = "";
    messagesEl.textContent = "Loaded from saved TradingAgents state log.";
    messagesEl.className = "empty-state";

    runContext.ticker = state.company_of_interest || "Unknown";
    runContext.analysisDate = state.trade_date || "Unknown date";
    runContext.assetType = "saved report";
    loadReportSectionsFromState(state);
    renderMemo();
    renderReports();
    setStatus("Saved report loaded", `${runContext.ticker} - ${runContext.analysisDate}`);
  } catch (error) {
    setStatus("Load failed", error instanceof Error ? error.message : String(error));
  }
}

function payloadFromForm() {
  const data = new FormData(form);
  const analysts = data.getAll("analysts");

  return {
    ticker: String(data.get("ticker") || "").trim(),
    analysis_date: data.get("analysis_date"),
    output_language: String(data.get("output_language") || "English").trim(),
    analysts,
    research_depth: Number(data.get("research_depth")),
    llm_provider: String(data.get("llm_provider") || "").trim(),
    backend_url: String(data.get("backend_url") || "").trim() || null,
    quick_think_llm: String(data.get("quick_think_llm") || "").trim(),
    deep_think_llm: String(data.get("deep_think_llm") || "").trim(),
    google_thinking_level: String(data.get("google_thinking_level") || "").trim() || null,
    openai_reasoning_effort: String(data.get("openai_reasoning_effort") || "").trim() || null,
    anthropic_effort: String(data.get("anthropic_effort") || "").trim() || null,
    checkpoint_enabled: data.get("checkpoint_enabled") === "on"
  };
}

function validatePayload(payload) {
  if (payload.analysts.length === 0) {
    return "Select at least one analyst.";
  }
  return "";
}

function parseSseChunk(chunk) {
  const dataLines = chunk
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return JSON.parse(dataLines.join("\n"));
  } catch (error) {
    addMessage("Stream", `Skipped malformed event: ${error.message}`);
    return null;
  }
}

async function readEventStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || "";

    for (const part of parts) {
      const event = parseSseChunk(part);
      if (event) {
        handleEvent(event);
      }
    }

    if (done) {
      if (buffer.trim()) {
        const event = parseSseChunk(buffer);
        if (event) {
          handleEvent(event);
        }
      }
      break;
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = payloadFromForm();
  const validationError = validatePayload(payload);
  if (validationError) {
    setStatus(validationError, "Run not started");
    return;
  }

  clearDashboard();
  setStatus("Starting analysis", "Connecting to /api/analyze");
  runButton.disabled = true;
  clearButton.disabled = true;

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok || !response.body) {
      const errorText = await response.text();
      setStatus(`Error ${response.status}`, errorText || "Request failed");
      return;
    }

    await readEventStream(response);
  } catch (error) {
    setStatus("Run failed", error instanceof Error ? error.message : String(error));
  } finally {
    runButton.disabled = false;
    clearButton.disabled = false;
  }
});

clearButton.addEventListener("click", async () => {
  clearButton.disabled = true;
  setStatus("Clearing checkpoints", "POST /api/checkpoints/clear");

  try {
    const response = await fetch("/api/checkpoints/clear", { method: "POST" });
    const result = await response.json();
    if (!response.ok) {
      setStatus(`Error ${response.status}`, JSON.stringify(result));
      return;
    }
    setStatus("Checkpoints cleared", `Cleared ${result.cleared ?? 0} checkpoint(s).`);
  } catch (error) {
    setStatus("Clear failed", error instanceof Error ? error.message : String(error));
  } finally {
    clearButton.disabled = false;
  }
});

providerInput.addEventListener("change", applyProviderDefaults);
refreshReportsButton.addEventListener("click", loadSavedReports);

function handleEvent(event) {
  const payload = event.payload || {};

  if (event.type === "run_started") {
    setStatus(`Running ${payload.ticker}`, `${payload.analysis_date} - ${payload.asset_type || "asset"} - ${payload.run_id}`);
    runContext.ticker = payload.ticker || "";
    runContext.analysisDate = payload.analysis_date || "";
    runContext.assetType = payload.asset_type || "";
    renderMemo();
    renderAgents(payload.agents || payload.statuses || {});
  } else if (event.type === "agent_status") {
    renderAgents(payload.agents || payload.statuses || {});
  } else if (event.type === "message") {
    addMessage(payload.message_type, payload.content);
  } else if (event.type === "tool_call") {
    addMessage("Tool call", `${payload.name || "tool"} ${JSON.stringify(payload.args || {})}`);
  } else if (event.type === "report_section") {
    reportSections.set(payload.section || "report", payload.content);
    renderMemo();
    renderReports();
  } else if (event.type === "stats") {
    statsEl.className = "";
    statsEl.textContent = JSON.stringify(payload, null, 2);
  } else if (event.type === "run_completed") {
    if (payload.decision && !reportSections.has("final_trade_decision")) {
      reportSections.set("final_trade_decision", payload.decision);
      renderMemo();
      renderReports();
    }
    setStatus("Completed", JSON.stringify(payload.decision || "No decision returned"));
  } else if (event.type === "run_failed") {
    setStatus("Failed", payload.error || "Analysis failed");
  }
}

setDefaultDate();
applyProviderDefaults();
loadSavedReports();
