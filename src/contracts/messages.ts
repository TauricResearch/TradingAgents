// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Every fixed string a person reads from the application, by key: command output and errors, notices,
 * reported problems, the questions it asks, and the one-line summary each tool call shows. Text
 * written only for the model is in agents/prompts.ts or, for a tool's results, with the tool, and text a
 * model or a source wrote is shown as written. Values that vary come in as
 * parameters; this module imports nothing.
 * Style: no em-dash and no middle dot.
 */

/** A cap's name as a limit is called. */
const CAP_WORDS: Record<string, string> = {
  steps: "step",
  subagents: "agent-run",
  tokens: "token",
  time: "time",
};

/** Where a person gets a Tauric API key. */
export const SIGN_UP_URL = "https://tauric.ai/signup";
/** What a Tauric API key is for, said the same way wherever its purpose is stated. */
const KEY_PURPOSE = "AI and data";

/**
 * Where to get a Tauric API key, its address last and whole (no punctuation after it), so a terminal that
 * finds addresses in text makes it clickable.
 */
function getOne(): string {
  return `Get one at ${SIGN_UP_URL}`;
}

const catalog = {
  // Command line
  "cli.usage": ({ app }: { app: string }) => usage(app),
  "cli.unknownCommand": ({ command }: { command: string }) => `Unknown command: ${command}`,
  "cli.sayChatgpt": ({ app, command }: { app: string; command: string }) =>
    `Usage: ${app} ${command} chatgpt`,
  "cli.emptyQuestion": () => "The question is empty.",
  "cli.flagNotFor": ({ flag, command }: { flag: string; command: string }) =>
    `--${flag} does not apply to ${command}.`,
  "cli.unexpectedArgument": ({ argument }: { argument: string }) => `Unexpected argument: ${argument}`,
  "cli.jsonNeedsPrompt": () => "--json needs -p.",
  "cli.resumeOrContinue": () => "Give --resume or --continue, not both.",
  "cli.warning": ({ problem }: { problem: string }) => `warning: ${problem}`,
  "cli.needsTerminal": ({ app }: { app: string }) =>
    `A session needs a terminal. To answer one question, use: ${app} -p "question"`,
  "cli.noSessionToContinue": () => "There is no session to continue yet.",
  "cli.updateAvailable": ({ latest, current }: { latest: string; current: string }) =>
    `TradingAgents ${latest} is available (this is ${current}).`,
  "cli.upgradeWith": ({ command }: { command: string }) => `Run ${command} to update.`,
  "update.promptTitle": ({ latest, current }: { latest: string; current: string }) =>
    `TradingAgents ${latest} is available (you have ${current})`,
  "update.now": () => "Update now",
  "update.nowDetail": ({ command }: { command: string }) => `runs ${command}`,
  "update.skip": () => "Skip",
  "update.skipDetail": () => "asks again at the next start",
  "update.skipVersion": () => "Skip until next version",
  "update.skipVersionDetail": ({ latest }: { latest: string }) =>
    `asks again when a release newer than ${latest} is out`,
  "update.restart": ({ app }: { app: string }) => `Start ${app} again to use the new version.`,
  "update.commandFailed": ({ command, code }: { command: string; code: number }) =>
    `${command} exited with code ${code}; nothing else was changed.`,
  "update.updated": ({ from, to }: { from: string; to: string }) => `Updated TradingAgents ${from} to ${to}.`,
  "update.current": ({ version }: { version: string }) => `TradingAgents ${version} is the newest release.`,
  "update.none": () => "No release for this platform was found.",
  "update.notRelease": ({ install }: { install: string }) =>
    `This copy is not an installed release, so it cannot update itself. To install one: ${install}`,
  "update.managed": () => "This copy was installed by a package manager: update it with that manager.",
  "update.npm": ({ command }: { command: string }) =>
    `This copy was installed with npm. Update it with: ${command}`,
  "update.unwritable": ({ dir, install }: { dir: string; install: string }) =>
    `You cannot write to ${dir}, so this copy cannot update itself. Reinstall with: ${install}`,
  "update.busy": ({ path, pid, host }: { path: string; pid?: number; host?: string }) => {
    const holder = pid === undefined ? "" : ` (process ${pid}${host === undefined ? "" : ` on ${host}`})`;
    return `Another update is running${holder}. If it is not, remove ${path} and try again.`;
  },
  "update.badChecksum": () => "The download does not match its checksum; nothing was changed.",
  "update.noChecksum": ({ name }: { name: string }) =>
    `SHA256SUMS has no single checksum for ${name}; nothing was changed.`,
  "update.wontStart": () => "The new version did not start on this system; nothing was changed.",
  "update.failed": ({ reason }: { reason: string }) => `The update failed: ${reason}`,
  "cli.noSessions": () => "No sessions yet.",
  "cli.nameTheSession": ({ app }: { app: string }) =>
    `Name the session to delete: ${app} sessions delete <id>`,
  "cli.deleteNeedsYes": () => "Without a terminal to confirm, deleting needs --yes.",
  "cli.deleteHere": ({ id }: { id: string }) => `Delete session ${id}?`,
  "cli.deleteEverywhere": ({ id }: { id: string }) =>
    `Delete session ${id} here and from your Tauric account?`,
  "cli.nothingDeleted": () => "Nothing deleted.",
  "cli.failed": ({ reason }: { reason: string }) => `Stopped: ${reason}`,
  "cli.untitledSession": () => "(no question)",
  "cli.inAccount": () => "(in your Tauric account)",
  /** A session in the account synced before titles were. */
  "cli.untitledAccount": () => "(untitled)",
  "cli.continueOne": ({ app }: { app: string }) => `Continue one with: ${app} --resume <id>`,
  "cli.nameTheKey": ({ app, names }: { app: string; names: string }) =>
    `Name the key to store: ${app} key <name>, one of ${names}`,
  "cli.keyPrompt": ({ name }: { name: string }) => `${keyLabel(name)} API key (not shown): `,
  "cli.chooseModel": ({ providers, example }: { providers: string; example: string }) =>
    `Keys are set for ${providers}: choose a model with --model, such as --model ${example}`,
  "cli.nothingStored": () => "Nothing stored.",
  "cli.nothingStoredBecause": ({ reason }: { reason: string }) => `Nothing stored: ${reason}`,
  "cli.envKeyWins": ({ variable }: { variable: string }) =>
    `${variable} is set and is used; the stored key is used once it is unset.`,
  "cli.keyStored": ({ name, path }: { name: string; path: string }) =>
    `Stored the ${name === "model" ? "model server" : keyLabel(name)} API key in ${path}.`,
  "cli.setup": ({
    app,
    baseUrlVar,
    modelVar,
    providers,
  }: {
    app: string;
    baseUrlVar: string;
    modelVar: string;
    providers: readonly string[];
  }) =>
    `No model is set yet. Choose one:

  Tauric's AI and data          ${app} key tauric
                                ${getOne()}
  Your ChatGPT plan             ${app} login chatgpt
  An API key                    ${app} key ${providers.join("|")},
                                or its variable in the environment, such as OPENAI_API_KEY
  An OpenAI-compatible server   set ${baseUrlVar} and ${modelVar} (the model as the server names it),
                                and if the server needs a key: ${app} key model

A Tauric API key also brings filings, statements, news and more. Without one, prices come from Yahoo and
event odds from Polymarket; the rest is not available.
`,

  // ChatGPT sign-in commands
  "chatgpt.noModel": ({ email, wanted, models }: { email: string; wanted?: string; models: string[] }) =>
    `Signed in as ${email}, but ${wanted ? `the plan does not offer ${wanted}` : "the plan lists no models"}. Models: ${models.join(", ") || "none"}`,
  "chatgpt.using": ({
    email,
    name,
    id,
    path,
    models,
    app,
  }: {
    email: string;
    name: string;
    id: string;
    path: string;
    models: string[];
    app: string;
  }) =>
    `Signed in as ${email}. Using ${name} (${id}) from your plan (${path}).${
      models.some((other) => other !== id)
        ? `\nOther models: ${models.filter((other) => other !== id).join(", ")}; choose one with: ${app} login chatgpt <model>`
        : ""
    }`,
  "chatgpt.notSignedIn": () => "Not signed in to ChatGPT.",
  "chatgpt.signedOut": () => "Signed out of ChatGPT.",
  "chatgpt.signedOutUnconfirmed": () =>
    "Signed out here; OpenAI could not be reached to revoke the sign-in, which ends when its token expires.",

  // Sync
  "sync.question": () => "Sync sessions to your Tauric account?",
  "sync.questionSubtitle": () => "You can turn it off any time.",
  "sync.turnOn": () => "Turn on",
  "sync.keepOff": () => "Keep off",
  "sync.sends": () =>
    "Sync copies each session to your Tauric account as it is saved: your questions, the answers, the tools' arguments and results (market data, filings, news), the agents' work, anything recalled from memory, and, for DeepSeek models, their reasoning. The complete data behind each result from Tauric is included; for other sources, and for a result too large to sync, only the text the model read. Sessions in your account that are not on this computer show in /resume and in the sessions list; opening one copies it here, with what was synced. Turning it on copies the current session from its start; turning it off deletes nothing already copied.",
  "sync.setButOverridden": ({
    choice,
    path,
    variable,
    effective,
  }: {
    choice: string;
    path: string;
    variable: string;
    effective: string;
  }) => `Sync is set ${choice} in ${path}, but ${variable} keeps it ${effective}.`,
  "sync.isOn": ({ path }: { path: string }) => `Sync is on (${path}).`,
  "sync.isOff": ({ path }: { path: string }) =>
    `Sync is off (${path}). Sessions open now stop copying before their next upload.`,
  "sync.status": ({ state }: { state: "unset" | "on" | "onWithoutKey" | "off" }) =>
    `Sync is ${
      {
        unset: "not set, so nothing is copied; the first session started in a terminal asks",
        on: "on",
        onWithoutKey: "on, but there is no Tauric API key, so nothing is copied",
        off: "off",
      }[state]
    }.`,
  "sync.turnItWith": ({ app, to }: { app: string; to: "on" | "off" }) =>
    `Turn it ${to} with: ${app} sync ${to}`,
  "sync.sayWhich": ({ app }: { app: string }) => `Usage: ${app} sync on|off|status`,
  "sync.onWithoutKey": () => "Sync is on, but there is no Tauric API key, so nothing is copied.",

  // The terminal app
  "app.placeholder": () => "Ask about a company, a market or a filing",
  "app.getKey": () => `Get the Tauric API for ${KEY_PURPOSE}: ${SIGN_UP_URL}`,
  "app.addKey": () => "Add your key with /login.",
  "app.tryLead": () => "Try: ",
  "app.tryExamples": () => "Is NVDA expensive vs its peers? | What's driving Treasury yields?",
  "app.keyHints": ({ separator }: { separator: string }) =>
    ["/help for commands", "esc to stop"].join(separator),
  "report.title": () => "Research report",
  "report.question": () => "Question",
  "report.added": () => "Added while planning",
  "report.sources": () => "Sources",
  "report.written": ({ at }: { at: string }) => `${at.slice(0, 10)} ${at.slice(11, 16)} UTC`,
  "report.page": ({ page, count }: { page: number; count: number }) => `Page ${page} of ${count}`,
  "app.mode": ({ mode }: { mode: "auto" | "plan" }) => `${mode} mode`,
  "app.modeSwitch": () => "shift+tab to switch",
  "app.planAsk": () => "Run this plan?",
  "app.planRun": () => "Run it",
  "app.planRunNote": () => "switches to auto mode",
  "app.planChange": () => "Type changes to the plan",
  /** Sent as the user's question when Enter runs a plan as proposed. */
  "app.runPlan": () => "Carry out the plan.",
  "app.resumeHint": ({ app, id }: { app: string; id: string }) =>
    `Resume this session: ${app} --resume ${id}`,
  "app.unknownCommand": ({ name }: { name: string }) => `/${name} is not a command; /help lists them`,
  "app.afterThisAnswer": ({ name }: { name: string }) => `/${name} can run after this answer`,
  "app.noCommand": () => "no command matches",
  "app.noModelNow": () => "No model can be used now: /login connects a provider.",
  "app.newSession": ({ id }: { id: string }) => `New session ${id}.`,
  "app.resumed": ({ id }: { id: string }) => `Resumed session ${id}.`,
  "app.noOtherSessions": () => "There is no other session here yet.",
  "app.resumeWhich": () => "Resume which session?",
  "app.deleteHere": () => "Delete this session? enter / esc",
  "app.deleteEverywhere": () => "Delete this session here and from your Tauric account? enter / esc",
  "app.deleted.here": () => "Deleted the session.",
  "app.deleted.everywhere": () => "Deleted the session here and from your Tauric account.",
  "app.deleted.pending": () => "Deleted here; your account's copy is deleted when Tauric can be reached.",
  "app.deleted.account": () => "Deleted the session from your Tauric account.",
  "app.deleted.accountPending": () =>
    "Your account's copy of the session is deleted when Tauric can be reached.",
  "app.sessionNote": ({ ago, turns }: { ago: string; turns: number }) =>
    `${ago}, ${turns} ${turns === 1 ? "turn" : "turns"}`,
  "app.sessionInAccount": ({ ago }: { ago: string }) => `${ago}, in your Tauric account`,
  "app.copiedFromAccount": () => "Copied the session from your Tauric account.",
  "app.whatsNew": ({ version, item }: { version: string; item: string }) => `New in ${version}: ${item}`,
  "app.noNotes": ({ version }: { version: string }) => `No notes for ${version}.`,
  "app.justNow": () => "just now",
  "app.ago": ({ amount }: { amount: string }) => `${amount} ago`,
  "app.setupFailed": ({ reason }: { reason: string }) => `Nothing more was saved: ${reason}`,
  // Setup: first run, /login and /model.
  "setup.chooseProvider": () => "Where should answers come from?",
  "setup.chooseLogin": () => "Connect which?",
  "setup.chooseModel": () => "Which model?",
  "setup.chooseReasoning": () => "How hard should it reason?",
  "setup.about.chatgpt": () => "sign in with your ChatGPT account and use your plan",
  "setup.about.openai": () => "an API key from platform.openai.com",
  "setup.about.anthropic": () => "an API key from console.anthropic.com",
  "setup.about.google": () => "an API key from aistudio.google.com",
  "setup.about.deepseek": () => "an API key from platform.deepseek.com",
  "setup.about.openrouter": () => "a key from openrouter.ai",
  "setup.about.openai-compatible": () => "vLLM, Ollama or any server with an OpenAI-style API",
  "setup.about.tauric": () => `${KEY_PURPOSE}, with one key`,
  "setup.ready": () => "ready",
  "setup.signedIn": () => "signed in",
  "setup.current": () => "current",
  "setup.default": () => "default",
  "setup.fast": () => "fast",
  "setup.recommended": () => "recommended",
  "setup.connect": () => "Connect",
  "setup.context": ({ tokens: count }: { tokens: number }) => `${tokens(count)} context`,
  "setup.cost": ({ input, output }: { input: number; output: number }) => `$${input}/$${output} per M tokens`,
  "setup.levels": ({ least, most }: { least: string; most: string }) =>
    least === most ? `reasoning ${least}` : `reasoning ${least} to ${most}`,
  "setup.providerDefault": () => "default",
  "setup.keyFor": ({ provider }: { provider: string }) =>
    `${provider} API key (stored on this computer only)`,
  "setup.keyInEnv": ({ variable }: { variable: string }) => `${variable} is set. Use it?`,
  "setup.keyStored": () => "A key is stored. Use it?",
  "setup.useIt": () => "Use it",
  "setup.enterAnother": () => "Enter another",
  "setup.tauricKey": () => `Paste your Tauric API key for ${KEY_PURPOSE}. ${getOne()}`,
  "setup.skipHint": () => "enter to skip | esc back",
  "setup.serverAddress": () => "The server's address, such as http://localhost:8000/v1",
  "setup.intro": ({ title }: { title: string }) =>
    `${title}: choose where answers come from. Esc goes back a step; Ctrl+C leaves.`,
  "setup.left": ({ app }: { app: string }) => `Setup left. What was saved is kept; run ${app} to continue.`,
  "setup.keyNotSaved": ({ reason }: { reason: string }) => `The key was not saved: ${reason}`,
  "setup.signedInAs": ({ email }: { email: string }) => `Signed in to ChatGPT as ${email}.`,
  "setup.answered": ({ title, answer }: { title: string; answer: string }) => `${title} ${answer}`,
  "setup.serverAddressAgain": ({ problem }: { problem: string }) => `That address cannot be used: ${problem}`,
  "setup.serverModel": () => "The model, as the server names it",
  "setup.serverKey": () => "The server's API key, if it needs one",
  "setup.connected": ({ provider }: { provider: string }) => `Connected ${provider}. /model to use it.`,
  "setup.serverNamedElsewhere": ({ variable }: { variable: string }) =>
    `Saved the server for new sessions, but ${variable} names another address: this session keeps its model.`,
  "setup.serverSaved": ({ model }: { model: string }) =>
    `Saved the server. Using ${model} from the next question, in this session and new ones.`,
  "setup.looksLikeKey": () => "That looks like a key; the key is asked for after the address and the model.",
  "setup.tauricSaved": () =>
    "Connected Tauric. Its data is used from the next question; /model switches to its model.",
  "setup.signInElsewhere": ({ app }: { app: string }) => `Sign in from a terminal with: ${app} login chatgpt`,
  "setup.modelNamedElsewhere": ({ where }: { where: string }) =>
    `${where} names the model for new sessions while it is set.`,
  "setup.modelSaved": ({ model }: { model: string }) =>
    `Using ${model} from the next question, in this session and new ones.`,
  // A setup step's key row, its fields joined by the separator.
  "form.pickHint": ({
    separator,
    filter,
    deletes,
    esc,
  }: {
    separator: string;
    filter: boolean;
    deletes: boolean;
    esc: string;
  }) =>
    [
      "up/down choose",
      ...(filter ? ["type to filter"] : []),
      "enter select",
      ...(deletes ? ["ctrl+d delete"] : []),
      `esc ${esc}`,
    ].join(separator),
  "form.filtering": ({ query, separator, esc }: { query: string; separator: string; esc: string }) =>
    [`matching "${query}"`, "enter select", `esc ${esc}`].join(separator),
  "form.fieldHint": ({ separator }: { separator: string }) => ["enter continue", "esc back"].join(separator),
  "form.questionHint": ({ count, separator, esc }: { count: number; separator: string; esc: string }) =>
    [
      "up/down choose",
      count > 1 ? `1-${count} pick` : "1 pick",
      "type on the last row",
      "enter select",
      `esc ${esc}`,
    ].join(separator),
  /** The last row of each question the agent asks: an answer of one's own. */
  "ask.own": () => "Type something…",
  "form.noMatch": ({ query }: { query: string }) => `nothing matches "${query}"`,
  "app.syncState": ({ state }: { state: "unset" | "on" | "onWithoutKey" | "off" }) =>
    ({ unset: "not set", on: "on", onWithoutKey: "on, but no Tauric API key", off: "off" })[state],
  "app.search": ({ query }: { query: string }) => `search earlier questions: ${query}`,
  "app.searchNone": ({ query }: { query: string }) => `search earlier questions: ${query} (no match)`,
  "app.historyUnsaved": ({ reason }: { reason: string }) => `Earlier questions could not be kept: ${reason}`,
  "app.queued": ({ text }: { text: string }) => `Queued: ${text}`,
  "app.queuedMore": ({ count }: { count: number }) => `+${count} more queued`,
  "app.queuePaused": () => "Queue paused: Enter sends the next one, Up takes it back",
  "app.dataTauric": () => "Tauric Research",
  "app.dataYahoo": () => "Yahoo prices only",
  "app.interrupted": () => "This question did not finish: the session ended while it ran.",
  "app.stoppedUnexpectedly": ({ reason }: { reason: string }) => `The run stopped unexpectedly: ${reason}`,
  "app.stoppedAtLimit": ({ cap }: { cap: string }) => `stopped at its ${CAP_WORDS[cap] ?? cap} limit`,
  "app.stopping": () => "Stopping…",
  "app.escToStop": () => "esc to stop",
  // What the status row says the turn is doing.
  "app.phaseThinking": () => "Thinking…",
  /** The main agent's thinking: its header while it streams, and the line written when it ends. */
  "app.thinkingHeader": () => "Thinking",
  "app.thoughtFor": ({ durationMs }: { durationMs: number }) => `Thought for ${duration(durationMs)}`,
  "app.phaseFetching": () => "Fetching data…",
  "app.phaseWriting": () => "Writing…",
  "app.phaseWorking": () => "Working…",
  "app.phaseSummarizing": () => "Summarizing earlier turns…",
  "app.phaseReconnecting": () => "Reconnecting…",
  /** Which retry of a model step is pending, as the status row and an agent's row say it. */
  "app.retryOf": ({ attempt, of }: { attempt: number; of: number }) => `retry ${attempt} of ${of}`,
  /** Said after a long think, by how long it has gone on. */
  "app.thinkingLong": ({ seconds }: { seconds: number }) =>
    seconds >= 45
      ? "deep in thought"
      : seconds >= 30
        ? "thinking some more"
        : seconds >= 20
          ? "thinking more"
          : "still thinking",
  "app.linesAbove": ({ count }: { count: number }) => `… ${count} ${count === 1 ? "line" : "lines"} above`,
  "app.toolCount": ({ count }: { count: number }) => `${count} tool${count === 1 ? "" : "s"}`,
  /** A step's data calls folded into one row: "Fetched 3 datasets", "1 failed". */
  /** "Fetched 4 from Tauric and Yahoo": how many, from the sources that answered in order of first use. */
  "app.fetched": ({ count, sources = [] }: { count: number; sources?: readonly string[] }) =>
    sources.length
      ? `Fetched ${count} from ${
          sources.length === 1 ? sources[0] : `${sources.slice(0, -1).join(", ")} and ${sources.at(-1)}`
        }`
      : `Fetched ${count} dataset${count === 1 ? "" : "s"}`,
  "app.failedCount": ({ count }: { count: number }) => `${count} failed`,
  "app.exported": ({ path, what }: { path: string; what: "transcript" | "report" }) =>
    `Saved the ${what} to ${path}.`,
  "app.exportFailed": ({
    path,
    reason,
    what,
  }: {
    path: string;
    reason: string;
    what: "transcript" | "report";
  }) => `Could not write the ${what} to ${path} (${reason}).`,
  "app.uncovered": ({ count }: { count: number }) =>
    `${count} character${count === 1 ? "" : "s"} (in a script such as Chinese) ${count === 1 ? "has" : "have"} no embedded font and show${count === 1 ? "s" : ""} as ${count === 1 ? "an empty box" : "empty boxes"}.`,
  "app.noReport": () => "No answer to export yet: the report is made from the last answer.",
  "app.exportWhat": () => "Export what?",
  "app.exportPdf": () => "PDF report",
  "app.exportPdfNote": () => "the last answer, set as a report",
  "app.exportMd": () => "Markdown",
  "app.exportMdNote": () => "the whole transcript",
  "app.exportBoth": () => "Both",
  "app.exportBothNote": () => "the report and the transcript, as two files",
  "app.exportNoAnswer": () => "no answer yet",
  "app.exportWhere": () => "Save to",
  "app.exportWhereBoth": () => "Save to (.pdf and .md are added)",
  "app.exportWhereHint": ({ separator }: { separator: string }) => ["enter save", "esc back"].join(separator),
  "app.noAnswerToCopy": () => "No answer to copy yet.",
  "app.copied": () => "Copied the last answer.",
  "app.copiedThroughTerminal": () =>
    "Copied the last answer through the terminal (it must allow programs to set the clipboard).",
  "app.copyTooLong": () =>
    "The last answer is too long to copy through the terminal: /export md writes it to a file.",
  "app.copyUnsupported": () =>
    "This terminal does not let programs set the clipboard: /export md writes the answer to a file.",
  "app.agentsRunning": ({ count }: { count: number }) => `Running ${count} agents`,
  "app.agentsFinished": ({ count }: { count: number }) => `${count} agents finished`,
  "app.agentsStopped": ({ count }: { count: number }) => `${count} agents stopped`,
  "app.agentStopped": () => "stopped",
  /** Under a finished sub-agent's row: what it did, "7 tool uses | 41s". */
  "app.someTool": () => "tool",
  "app.reportWritten": () => "report written",
  "app.moreRunning": ({ count }: { count: number }) => `  +${count} more running`,
  "app.tokens": ({ count }: { count: number }) => `${tokens(count)} tokens`,
  // The line that closes a turn, its fields joined by the separator: "Worked for 1m 31s", "4.2k in",
  // "1.8k out", "plan 5/6".
  "app.worked": ({ durationMs }: { durationMs: number }) => `Worked for ${duration(durationMs)}`,
  "app.tokensIn": ({ count }: { count: number }) => `${tokens(count)} in`,
  "app.tokensOut": ({ count }: { count: number }) => `${tokens(count)} out`,
  "app.planCount": ({ done, total }: { done: number; total: number }) => `plan ${done}/${total}`,
  "app.planHeading": () => "Plan",
  "app.planDone": ({ done, total }: { done: number; total: number }) => `${done} of ${total} done`,
  "app.planMore": ({ count }: { count: number }) => `and ${count} more`,
  "app.stopped": () => "Stopped.",
  /** What a question took, for headless runs (scripts may read it): "8m 41s, 296k tokens in, 85k out". */
  "app.usagePlain": ({
    durationMs,
    inputTokens,
    outputTokens,
  }: {
    durationMs?: number;
    inputTokens: number;
    outputTokens: number;
  }) =>
    `${durationMs !== undefined ? `${duration(durationMs)}, ` : ""}${tokens(inputTokens)} tokens in, ${tokens(outputTokens)} out`,

  // Runs
  "run.cap": ({ cap }: { cap: "steps" | "tokens" | "time" | "subagents" }) =>
    `The ${CAP_WORDS[cap]} limit was reached, so the answer is written from what was gathered.`,
  "run.answerCutAtLimit": () =>
    "The answer was cut at the time limit; it ends with what was written by then.",
  "run.tooMuchContext": () =>
    "This question needs more context than the model has; ask a narrower one or start a new session.",
  "run.olderResultsSetAside": () =>
    "Older data results were set aside to keep within the model's context; it can fetch them again.",
  "run.declined": () => "The model declined to answer.",
  "run.stepError": () => "The model ended its step with an error.",
  "run.answerCut": () => "The answer was cut at the model's output limit.",
  "run.retrying": ({ reason }: { reason: string }) => `The model did not answer (${reason}); trying again.`,
  "run.cancelled": () => "Cancelled.",
  "run.memoryHeld": ({ name }: { name: string }) => `${name} is held by another process`,
  "model.streamUnfinished": () => "the stream ended without a finish",
  "signin.yourAccount": () => "your ChatGPT account",
  "limits.notSettings": ({ path }: { path: string }) =>
    `limits.${path}: settings for a run, such as { "steps": 10 }`,
  "limits.notALimit": ({ path }: { path: string }) => `limits.${path}: not a limit (steps, tokens or time)`,
  "limits.invalid": ({ path, reason }: { path: string; reason: string }) => `limits.${path}: ${reason}`,
  "limits.byAgent": () => "limits.agents: settings by agent name",
  "limits.mainUnderQuestion": () => "limits.agents.main: set the main agent's limits under question",
  "limits.notAnAgent": ({ name }: { name: string }) => `limits.agents.${name}: not an agent's name`,
  "app.catalogBuiltIn": () => "Built-in",
  "app.catalogBuiltInAside": () => "built-in",
  "app.catalogUser": () => "Yours",
  "app.catalogUnavailable": () => "not available in this session",
  "app.catalogNone": ({ kind, name }: { kind: "agent" | "skill"; name: string }) =>
    `No ${kind} named ${name}: /${kind}s lists them.`,
  "app.catalogOne": ({ kind }: { kind: "agent" | "skill" }) => `/${kind}s <name> shows one in full.`,
  "app.helpCommands": () => "Commands",
  "app.helpKeys": () => "Keys",
  "agentFiles.skipped": ({ path, problem }: { path: string; problem: string }) =>
    `${path} is not used: ${problem}`,
  "agentFiles.warning": ({ path, problem }: { path: string; problem: string }) => `${path}: ${problem}`,
  "agentFiles.shadows": ({ path, name, other }: { path: string; name: string; other: string }) =>
    `${path} is used for ${name} in place of ${other === "built-in" ? "the built-in one" : other}`,
  "agentFiles.modelReserved": ({ path }: { path: string }) =>
    `${path}: model is ignored; the agent runs on the session's model`,
  "limits.noSuchAgent": ({ name, agents }: { name: string; agents: string }) =>
    `limits.agents.${name}: no such agent (agents: ${agents})`,
  "limits.notAnOutputLimit": ({ field }: { field: string }) =>
    `limits.output.${field}: not a limit (stepTokens or finalTokens)`,
  "limits.flagShape": ({ flag }: { flag: string }) =>
    `--limit ${flag}: write it as key=value, such as question.time=20m`,
  "limits.flagUnknown": ({ flag }: { flag: string }) => `--limit ${flag}: not a limit`,
  "run.failed": () => "The run failed.",
  "run.noReportCut": () => "it ended without writing a report (its answer was cut off at the output limit)",
  "run.noReportTime": () => "it ended without writing a report (its time limit left no time to write one)",
  "run.noReportEmpty": () => "it ended without writing a report (its answer was empty)",
  "run.noReason": () => "no reason given",
  "answer.sources": () => "Sources:",
  "run.busy": () => "a turn is already running in this session",
  "run.timeLimitReached": () => "the time limit was reached",
  "run.timeTooShort": () =>
    "The time limit was too short to write an answer. Set a longer one, such as --limit question.time=5m.",
  "run.timeTooShortThinking": () =>
    "The time limit was too short to write an answer. Set a longer one, such as --limit question.time=5m, or set providers.openai-compatible.thinking so the answer can skip thinking.",
  "run.decisionNotSaved": ({ reason }: { reason: string }) => `The decision could not be saved (${reason}).`,
  "run.summaryFailed": ({ reason }: { reason: string }) =>
    `Earlier turns could not be summarized (${reason}); older results are set aside instead.`,
  "run.summarized": ({ turns, kept }: { turns: number; kept: number }) =>
    `Summarized ${turns === 1 ? "1 earlier turn" : `${turns} earlier turns`} to stay within the model's context${kept ? "; the latest turn is kept as it was" : ""}.`,
  "run.memoryUnreadable": ({ name, reason }: { name: string; reason: string }) =>
    `The memory file ${name} cannot be read (${reason}).`,

  // Model setup
  "model.keyRefused": ({ provider, url, said }: { provider: string; url: string; said: string }) =>
    `${provider} refused the key (${said}). Store a new key with /login. Get one at ${url}`,
  "model.noCredit": ({ provider, said }: { provider: string; said: string }) =>
    `${provider} says the account has no credit left (${said}). Add credit with ${provider}, then ask again.`,
  "model.creditsSpent": ({ resets }: { resets?: string }) =>
    `Your Tauric AI credits for today are spent${resets ? `; they reset at ${resets}` : ""}.`,
  "model.windowAssumedPlan": ({ tokens }: { tokens: string }) =>
    `The plan model's context window is not reported, so ${tokens} tokens is assumed; set providers.chatgpt.contextWindow in the config to use more.`,
  "model.windowAssumed": ({ tokens, provider }: { tokens: string; provider: string }) =>
    `The model's context window is unknown, so ${tokens} tokens is assumed; set providers.${provider}.contextWindow in the config to use more.`,

  // Sessions
  "session.switchFailed": ({ reason }: { reason: string }) =>
    `The model could not be switched (${reason}); the session keeps the one it had.`,
  "session.unsaved": ({ reason }: { reason: string }) =>
    `This session cannot be saved (${reason}); it continues unsaved.`,
  "session.payloadNotKept": ({ reason }: { reason: string }) =>
    `A result's data could not be kept on this computer (${reason}); the session keeps its preview.`,
  "session.noLongerSaved": ({ reason }: { reason: string }) =>
    `This session can no longer be saved (${reason}); it continues unsaved.`,
  "session.badId": ({ id }: { id: string }) => `"${id}" is not a session id`,
  "session.missing": ({ id }: { id: string }) => `There is no session ${id}.`,
  "session.repaired": ({ id }: { id: string }) =>
    `The end of session ${id} was cut short by a crash; it was repaired.`,
  "session.damaged": ({ id, line }: { id: string; line: number }) =>
    `Session ${id} is damaged at line ${line} and cannot be resumed.`,
  "session.lockStuck": ({ id, path }: { id: string; path: string }) =>
    `Session ${id} was left locked by a process that ended; remove ${path} to open it.`,
  "session.openElsewhere": ({ id, pid }: { id: string; pid: number }) =>
    `Session ${id} is open in another terminal (process ${pid}).`,
  "session.openOnHost": ({ id, host, pid, path }: { id: string; host: string; pid: number; path: string }) =>
    `Session ${id} is open on ${host} (process ${pid}); if it is not, remove ${path} to open it here.`,
  "session.lockUnreadable": ({ id, path }: { id: string; path: string }) =>
    `Session ${id} is locked by ${path}, which cannot be read; if no terminal has it open, remove it.`,

  // Session sync while running
  "sync.stoppedKey": ({ reason }: { reason: string }) =>
    `Session sync stopped: Tauric refused the key (${reason}).`,
  "sync.stoppedQuota": ({ reason }: { reason: string }) =>
    `Session sync stopped: Tauric quota is spent (${reason}).`,
  "sync.storageFull": ({ remainingBytes }: { remainingBytes?: number | undefined }) =>
    `Session sync stopped: your Tauric storage is full${remainingBytes !== undefined ? ` (${formatBytes(remainingBytes)} left)` : ""}. Sessions already copied are kept; deleting old ones makes room.`,
  "sync.copyFailed": ({ reason }: { reason: string }) =>
    `The session could not be copied from your Tauric account (${reason}). Nothing was kept; try again.`,
  "sync.copyNotThis": ({ id }: { id: string }) =>
    `The copy of session ${id} in your Tauric account does not start as that session does. Nothing was kept.`,
  "sync.deleteUnconfirmed": ({ id, reason }: { id: string; reason: string }) =>
    `Session ${id} is not on this computer, and your Tauric account could not be asked for it (${reason}). Nothing was deleted.`,
  "sync.listFailed": ({ reason }: { reason: string }) =>
    `Your Tauric account's sessions could not be listed (${reason}); these are the ones on this computer.`,
  "sync.copyIncomplete": ({ id, got, size }: { id: string; got: number; size: number }) =>
    `Session ${id} could not be copied from your Tauric account: ${got} of its ${size} bytes came back. Nothing was kept; try again.`,
  "sync.copyDamaged": ({ id, line }: { id: string; line: number }) =>
    `Session ${id} in your Tauric account is not one this version can read (${line ? `line ${line}` : "its last line is incomplete"}). Nothing was kept.`,
  "sync.paused": ({ reason }: { reason: string }) =>
    `Session sync paused for this session: Tauric's copy differs from this file (${reason}). Both are kept.`,
  "sync.refused": ({ reason }: { reason: string }) =>
    `Session sync stopped: Tauric refused the request (${reason}).`,
  "sync.unreachable": ({ reason }: { reason: string }) =>
    `Session sync could not reach Tauric; it will try again after the next answer (${reason}).`,
  "sync.lineTooLarge": () => "Session sync stopped: a line of this session is larger than one upload allows.",
  "sync.turnedOff": () => "Session sync stopped: it was turned off.",
  "sync.notOffered": ({ app }: { app: string }) =>
    `Session sync is off for now: your Tauric account does not keep ${app} sessions, so nothing is copied.`,

  // ChatGPT sign-in
  "signin.hint": ({ app }: { app: string }) => `Not signed in to ChatGPT; run \`${app} login chatgpt\`.`,
  "signin.renewFailedNow": () => "OpenAI could not renew your ChatGPT sign-in just now; try again.",
  "signin.renewFailedRecently": () =>
    "OpenAI could not renew your ChatGPT sign-in a moment ago; try again in a minute.",
  "signin.cannotRenew": ({ hint }: { hint: string }) => `Your ChatGPT sign-in cannot be renewed. ${hint}`,
  "signin.renewTask": () => "renew your ChatGPT sign-in",
  "signin.signInTask": () => "sign you in to ChatGPT",
  "signin.modelsTask": () => "list the plan's models",
  "signin.signInAgainAction": ({ app }: { app: string }) => `run \`${app} login chatgpt\` again`,
  "signin.signInAgain": () => "sign in again",
  "signin.renewUnreadable": ({ app }: { app: string }) =>
    `OpenAI's answer to renewing your ChatGPT sign-in could not be read; run \`${app} login chatgpt\` again.`,
  "signin.otherAccountRenewed": () => "The renewed ChatGPT sign-in belongs to another account.",
  "signin.cancelled": () => "The sign-in was cancelled.",
  "signin.timedOut": ({ app }: { app: string }) =>
    `Signing in with ChatGPT timed out; run \`${app} login chatgpt\` again.`,
  "signin.returnToTerminal": ({ product }: { product: string }) =>
    `Return to the terminal to finish signing in to ${product}.`,
  "signin.openAddress": () => "Continue with ChatGPT: open this address and sign in with your ChatGPT plan:",
  "signin.pasteIfNeeded": () =>
    "If the browser cannot reach this machine, paste here the address it ends up on.",
  "signin.notThatAddress": () => "That is not the address this sign-in ends on; paste the whole address.",
  "signin.cannotListen": ({ reason }: { reason: string }) =>
    `Signing in with ChatGPT needs to listen on this machine, and it cannot (${reason}).`,
  "signin.notCompleted": ({ code }: { code?: string }) =>
    `ChatGPT sign-in was not completed${code ? ` (${code})` : ""}.`,
  "signin.notRegistered": ({ app, product }: { app: string; product: string }) =>
    `ChatGPT sign-in did not register ${product}; run \`${app} logout chatgpt\`, then sign in again.`,
  "signin.otherAccount": ({ email, app }: { email?: string; app: string }) =>
    `This machine is signed in as ${email ?? "another account"}; run \`${app} logout chatgpt\` first.`,
  "signin.planDenied": ({ product }: { product: string }) =>
    `ChatGPT did not allow ${product} to use your plan; sign in again and approve plan usage.`,
  "signin.planNotAllowed": ({ app, product }: { app: string; product: string }) =>
    `ChatGPT has not allowed ${product} to use your plan; run \`${app} login chatgpt\` and approve plan usage.`,
  "signin.modelsUnlisted": ({ status }: { status: number }) =>
    `OpenAI did not list the plan's models (HTTP ${status}).`,
  "signin.cannotCheck": () => "Could not reach OpenAI to check the sign-in; try again.",
  "signin.tokenUnverified": () => "ChatGPT sign-in returned an id token OpenAI's keys do not verify.",
  "signin.tokenMismatch": () => "ChatGPT sign-in returned an id token that does not match this sign-in.",
  "signin.unreachable": ({ task }: { task: string }) => `Could not reach OpenAI to ${task}; try again.`,
  "signin.busy": ({ task, code }: { task: string; code: string }) =>
    `OpenAI could not ${task} now (${code}); try again.`,
  "signin.refused": ({ task, code, action }: { task: string; code: string; action: string }) =>
    `OpenAI did not ${task} (${code}); ${action}.`,
  "signin.unreadable": ({ task }: { task: string }) =>
    `OpenAI's answer could not be read when asked to ${task}; try again.`,
  "signin.lockStuck": ({ path }: { path: string }) =>
    `The ChatGPT sign-in was left locked by a process that ended; remove ${path} and try again.`,
  "signin.lockBusy": ({ product }: { product: string }) =>
    `Another ${product} process is renewing the ChatGPT sign-in; try again.`,
  "model.stalled": ({ durationMs }: { durationMs: number }) =>
    `The model sent nothing for ${duration(durationMs)}; the request was ended.`,
  "model.usageLimit": () =>
    "The ChatGPT plan's usage limit is reached; try again later or use another model.",

  // Settings and private files
  "config.emptyVariable": ({ name }: { name: string }) =>
    `${name} is set but empty; unset it or give it a value`,
  "config.keyTooShort": ({ name }: { name: string }) => `${name} is too short to be a key`,
  "config.keyOneLine": () => "a key is one non-empty line",
  "config.badModel": ({ where, problem }: { where: string; problem: string }) => `${where}: ${problem}`,
  "config.modelForm": ({ providers }: { providers: string }) =>
    `the model is named as provider/id, where the provider is one of ${providers}`,
  "config.unknownProvider": ({ providers }: { providers: string }) =>
    `the model's provider is not one of ${providers}`,
  "config.unknownProviderBlock": ({ path, providers }: { path: string; providers: string }) =>
    `${path}: providers holds a block for a provider that is not one of ${providers}`,
  "session.routeUnusable": ({ was, reason, now }: { was: string; reason: string; now?: string }) =>
    `the session ran on ${was}, which cannot be used now${reason ? ` (${reason})` : ""}${now ? `; it continues on ${now}` : ""}`,
  "session.signedOut": ({ app }: { app: string }) => `not signed in to ChatGPT: ${app} login chatgpt`,
  "session.changedWhileOpening": () => "the session changed while it was being opened; open it again",
  "config.noKey": ({ provider, vars, app }: { provider: string; vars: string; app: string }) =>
    `the ${keyLabel(provider)} model needs an API key: set ${vars}, or store one with ${app} key ${provider}`,
  "config.badReasoning": ({ where, levels }: { where: string; levels: string }) =>
    `${where}: reasoning must be one of ${levels}`,
  "config.keyForOtherServer": ({ endpoint, app }: { endpoint: string; app: string }) =>
    `the stored server key was stored for ${endpoint || "another server"}, so it is not sent to this one: store this server's with ${app} key model`,
  "config.serverFirst": ({ var: name }: { var: string }) =>
    `set the server's address first (providers.openai-compatible.baseURL in the config, or ${name}); its key is kept for that server`,
  "config.noBaseUrl": ({ var: name }: { var: string }) =>
    `an OpenAI-compatible model needs the server's base URL: set providers.openai-compatible.baseURL in the config, or ${name}`,
  "config.invalidProviders": ({ path }: { path: string }) => `${path}: invalid providers`,
  "config.invalidProvider": ({ path, provider }: { path: string; provider: string }) =>
    `${path}: invalid providers.${provider}`,
  "config.invalidProviderField": ({
    path,
    provider,
    field,
  }: {
    path: string;
    provider: string;
    field: string;
  }) => `${path}: invalid providers.${provider}.${field}`,
  "config.badBaseUrl": ({ problem }: { problem: string }) => `the model base URL ${problem}`,
  "config.notAUrl": () => "is not a URL",
  "config.urlScheme": () => "must start with http:// or https://",
  "config.urlCredentials": () => "must not hold credentials; set the model key instead",
  "config.badSync": ({ where }: { where: string }) => `sync must be "on" or "off" (${where}); sync stays off`,
  "config.keyLength": ({ min }: { min: number }) => `a key has at least ${min} characters`,
  "config.fixFirst": ({ path }: { path: string }) => `${path} is not valid; fix or remove it first`,
  "config.notObjectFixFirst": ({ path }: { path: string }) =>
    `${path} is not a JSON object; fix or remove it first`,
  "config.unreadable": ({ path }: { path: string }) => `${path} could not be read`,
  "config.notObject": ({ path }: { path: string }) => `${path} is not a JSON object`,
  "config.invalidModel": ({ path }: { path: string }) => `${path}: invalid model`,
  "config.keysUnused": ({ reason }: { reason: string }) => `${reason}; its keys are not used`,
  "config.credentialsNotObject": ({ path }: { path: string }) =>
    `${path} is not a JSON object; its keys are not used`,
  "config.unusableKey": ({ path, field }: { path: string; field: string }) =>
    `${path}: unusable key ${field}`,
  "config.homeNotAbsolute": ({ variable }: { variable: string }) => `${variable} must be an absolute path`,
  "file.symlink": ({ path }: { path: string }) => `${path} is a symbolic link`,
  "file.notRegular": ({ path }: { path: string }) => `${path} is not a regular file`,
  "file.otherOwner": ({ path }: { path: string }) => `${path} belongs to another user`,
  "file.tooOpen": ({ path }: { path: string }) => `${path} can be read or changed by others (chmod 600 it)`,
  "file.notDirectory": ({ path }: { path: string }) => `${path} is not a directory`,
  "file.damaged": ({ path, line }: { path: string; line: number }) => `${path} is damaged at line ${line}`,
  "file.damagedAt": ({ line }: { line: number }) => `damaged at line ${line}`,

  // Data
  "data.notAvailable": ({ capability }: { capability: string }) =>
    `${capability}: not available in this setup.`,
  "data.needsKey": ({ capability, app }: { capability: string; app: string }) =>
    `${capability}: needs a Tauric API key. Add one with \`${app} key tauric\` or TAURIC_API_KEY. ${getOne()}`,
  "data.listingNotServed": () => "it does not serve this listing",
  "data.attempt": ({ source, outcome, detail }: { source: string; outcome: string; detail: string }) =>
    `${source} ${
      {
        unsupported: "does not cover this",
        unavailable: "could not be reached",
        rate_limited: "was busy",
        quota: "is out of quota",
        rejected: "refused the key",
        not_configured: "is not set up",
        no_data: "has no data for this",
        invalid: "could not answer this as asked",
        full: "has no storage left",
      }[outcome] ?? "failed"
    } (${detail})`,
  "data.fellBack": ({ failed, source }: { failed: string; source: string }) =>
    `${failed}; this is from ${source}.`,
  "data.signUp": ({ app }: { app: string }) =>
    `A Tauric API key for ${KEY_PURPOSE} brings filings, statements, news and more. Add one with \`${app} key tauric\` or TAURIC_API_KEY. ${getOne()}`,
  "data.batchFellBack": ({
    instruments,
    source,
    failed,
  }: {
    instruments: string;
    source: string;
    failed: string;
  }) => `${instruments} from ${source}: ${failed} could not answer for them.`,
  // The source that answered first: a group's header names it (transcript-state groupSources).
  "data.sourceAfter": ({ source, failed }: { source: string; failed: string }) =>
    `${source}, after ${failed} failed`,
  "data.source": ({ source }: { source: string }) => `source: ${source}`,
  "data.answerTooLong": ({ source, bytes }: { source: string; bytes: number }) =>
    `${source} answered more than ${bytes} bytes.`,

  // Tool summaries in the transcript
  "tool.skill": ({ name }: { name: string }) => `skill ${name}`,
  "tool.skillLoaded": ({ name }: { name: string }) =>
    `The ${name} skill was loaded earlier in this turn; its method is above.`,
  "tool.plan": ({ count }: { count: number }) => `plan: ${count} steps`,
  "tool.asked": ({ count }: { count: number }) =>
    count === 1 ? "asked 1 question" : `asked ${count} questions`,
  "tool.askedAlready": () =>
    "The questions already asked this turn are the ones shown; put everything to ask in one call.",
  "tool.askShown": () => "The questions are shown to the user; their reply comes as their next message.",
  /** The questions as the closing message of the run that asked them, and its answer. */
  "ask.questions": ({
    questions,
  }: {
    questions: readonly {
      question: string;
      options: readonly { label: string; note?: string | undefined }[];
    }[];
  }) =>
    questions
      .map((q) =>
        [
          q.question,
          ...q.options.map(
            (option, index) => `${index + 1}. ${option.label}${option.note ? `: ${option.note}` : ""}`,
          ),
        ].join("\n"),
      )
      .join("\n\n"),
  "tool.noteSaved": () => "note saved",
  "tool.decision": ({ rating, instrument }: { rating: string; instrument: string }) =>
    `decision ${rating} ${instrument}`,
  // A call's result in a few words, beside its label (which names what was asked): only what came back.
  "tool.recalled": ({ entries }: { entries: number }) => `${entries} past entries`,
  "tool.notRun": () => "not run (too many calls in one step)",
  "tool.quoteClose": ({ date }: { date: string }) => `(close ${date})`,
  "tool.bars": ({
    count,
    through,
    interval = "daily",
  }: {
    count: number;
    through: string;
    interval?: string;
  }) => `${count} ${interval} bars to ${through}`,
  "tool.rates": ({ count, through }: { count: number; through: string }) =>
    `${count} reference rates to ${through}`,
  "tool.market": ({ count }: { count?: number }) =>
    count === undefined ? "snapshot" : `${count} row${count === 1 ? "" : "s"}`,
  "tool.instruments": ({ count }: { count: number }) => `${count} instrument${count === 1 ? "" : "s"}`,
  "tool.statement": ({ count }: { count: number }) => `${count} period${count === 1 ? "" : "s"}`,
  "tool.filings": ({ count }: { count: number }) => `${count} filing${count === 1 ? "" : "s"}`,
  "tool.section": ({ state }: { state: string }) => `no text (${state})`,
  "tool.sectionPart": ({ chars }: { chars: number }) => `${chars.toLocaleString("en-US")} characters`,
  "tool.articles": ({ count, more }: { count: number; more: boolean }) =>
    `${count} article${count === 1 ? "" : "s"}${more ? " (more exist)" : ""}`,
  "tool.profile": ({ sector }: { sector?: string }) => sector ?? "profile",
  "tool.corporateActions": ({ count }: { count: number }) =>
    `${count} corporate action${count === 1 ? "" : "s"}`,
  "tool.comps": ({ count }: { count: number }) => `${count} peers compared`,
  "tool.tauricView": ({ written }: { written?: string }) =>
    `Tauric AI's synthesis${written ? `, written ${written}` : ""}`,
  "tool.estimates": () => "consensus and calendar",
  "tool.holders": ({ count, quarter }: { count: number; quarter: string }) =>
    `${count} holders, quarter ending ${quarter}`,
  "tool.insider": ({ count, more }: { count: number; more: boolean }) =>
    `${count} transaction${count === 1 ? "" : "s"}${more ? " (more exist)" : ""}`,
  "tool.technicals": ({ through }: { through: string }) => `through ${through}`,
  "tool.seriesCandidates": ({ count }: { count: number }) => `${count} candidate series`,
  "tool.seriesEmpty": () => "no periods",
  "tool.series": ({ count, latest }: { count: number; latest: string }) => `${count} periods to ${latest}`,
  "tool.markets": ({ count }: { count: number }) => (count ? `${count} open markets` : "no open markets"),

  // Tool calls
  "call.cancelled": () => "The call was cancelled.",
  "call.failed": ({ tool, reason }: { tool: string; reason: string }) => `${tool} failed: ${reason}`,
  "call.noData": ({ source, detail }: { source: string; detail: string }) =>
    `${source} has no data for this request: ${detail}`,
  "call.invalid": ({ source, detail, candidates }: { source: string; detail: string; candidates?: string }) =>
    `${source} cannot answer this request as asked: ${detail}${candidates ? ` Candidates: ${candidates}.` : ""}`,
  "call.unsupported": ({ source, detail }: { source: string; detail: string }) =>
    `${source} does not cover this request (${detail}); this is not a fact about the market.`,
  "call.quota": ({ source, until }: { source: string; until?: string }) =>
    `${source} is out of quota${until ? ` until ${until}` : ""}; this is not a fact about the market.`,
  "call.rateLimited": ({ source }: { source: string }) =>
    `${source} is rate limiting requests; this is not a fact about the market. Try again later or use another tool.`,
  "call.credentials": ({ source }: { source: string }) =>
    `${source} is not available with the current credentials; this is not a fact about the market.`,
  "call.everySourceFailed": ({ detail }: { detail: string }) =>
    `${detail}. None of this is a fact about the market.`,
  "call.storageFull": ({ source }: { source: string }) =>
    `${source}'s storage allowance is full; this is not a fact about the market.`,
  "call.unreachable": ({ source, detail }: { source: string; detail: string }) =>
    `${source} could not be reached or answered unreadably; this is not a fact about the market. ${detail}`,
} satisfies Record<string, (params: never) => string>;

/** Bytes as people say them: 1 GB, 1.5 GB, 512 MB. */
export function formatBytes(bytes: number): string {
  const units = ["bytes", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  const shown =
    Number.isInteger(value) || unit === 0 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  return `${shown} ${units[unit]}`;
}

/** A length of time as people read it: "41s", "8m 41s", "1h 2m". */
function duration(ms: number): string {
  const seconds = Math.round(ms / 1_000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** A token count as people read it: "850", "12.4k", "296k", "1.2M". */
function tokens(count: number): string {
  if (count < 1_000) return String(count);
  if (count < 100_000) return `${(count / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  if (count < 1_000_000) return `${Math.round(count / 1_000)}k`;
  return `${(count / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

type MessageKey = keyof typeof catalog;
type Params<K extends MessageKey> = Parameters<(typeof catalog)[K]>;

/** The text for `key`, with its parameters. */
export function message<K extends MessageKey>(key: K, ...params: Params<K>): string {
  return (catalog[key] as (...args: Params<K>) => string)(...params);
}

/** Each provider as people see it named. */
export const PROVIDER_LABELS = {
  tauric: "Tauric",
  chatgpt: "ChatGPT plan",
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
  deepseek: "DeepSeek",
  openrouter: "OpenRouter",
  "openai-compatible": "OpenAI-compatible server",
} as const;

/** How a stored key is named when asked for: its provider's name, or the model server's. */
function keyLabel(name: string): string {
  return name === "model" ? "Model server" : ((PROVIDER_LABELS as Record<string, string>)[name] ?? name);
}

/** The command list, each description starting in one column. */
function usage(app: string): string {
  const commands: [string, string][] = [
    ["", "start a session in this terminal"],
    ['-p "question"', "answer one question and print the answer"],
    ['-p "question" --json', "print every event as a JSON line instead"],
    ["--continue", "continue the latest session (with -p too)"],
    ["--resume <id>", "continue a session, here or in your Tauric account (with -p too)"],
    ["--limit key=value", "set a limit for this run, such as question.time=20m (repeatable)"],
    ["sessions", "list sessions, newest first, with those in your Tauric account when sync is on"],
    ["sessions delete <id> [--yes]", "delete a session (and its copy in your Tauric account)"],
    ["sync on|off|status", "sync sessions with your Tauric account"],
    ["key <name>", "store a key: tauric, model (a server's), or a provider's (typed hidden, or piped in)"],
    ["--model provider/id", "use this model for this run"],
    ["--reasoning level", "how hard the model reasons this run: none to max"],
    ["login chatgpt", "use your ChatGPT plan's models (prints an address to open)"],
    ["logout chatgpt", "sign out of ChatGPT"],
    ["update", "update to the newest release"],
  ];
  const width = Math.max(...commands.map(([command]) => `${app} ${command}`.trimEnd().length)) + 2;
  const lines = commands.map(([command, what]) => `  ${`${app} ${command}`.trimEnd().padEnd(width)}${what}`);
  return ["Usage:", ...lines, `  ${app} --version`].join("\n");
}
