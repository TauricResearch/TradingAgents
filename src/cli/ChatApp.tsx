// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The interactive session: the header, the transcript of every turn, the input box and the footer.
 *
 * A turn runs until it settles: Esc or Ctrl+C asks it to stop once, and its events are read to the
 * end either way, so the transcript always closes the turn. A Ctrl+C after a turn has had a while to
 * stop leaves without it. Ctrl+C or Ctrl+D with nothing running
 * leaves; with text typed, Ctrl+C clears it first. The input stays live while a turn runs: a question
 * sent then waits in a queue shown above the input and goes when the turn completes, one turn each;
 * a stopped or failed turn pauses the queue until Enter on an empty input. Up on an empty input takes
 * the last queued question back. A question may hold line breaks: a paste keeps its own, and Ctrl+J, Alt+Enter, Shift+Enter
 * (where the terminal reports it) or a `\` before Enter add one. Up and Down move between lines, and
 * past the first or last one through the questions asked before (the unsent draft is kept); Ctrl+R
 * searches them. A long question shows the rows around the cursor. A `/` at the start opens the
 * command menu, which has the first say over the keys while it is open.
 * Questions the agent asked take the input's place when their turn completes (a question queued while it
 * ran goes instead), and the choices are sent as the next question; Esc leaves them unanswered.
 */
import { Text, useApp, useInput, usePaste, useStdout, useWindowSize } from "ink";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { withQuestion } from "../config/index.js";
import {
  type EventEnvelope,
  errorText,
  MODES,
  type Mode,
  message,
  type Question,
} from "../contracts/index.js";
import { APP } from "../contracts/limits.js";
import type { AskOptions, Deleted, SessionSummary, Turn } from "../engine/index.js";
import { CommandMenu, menuHeight } from "./CommandMenu.js";
import { Composer, composerHeight } from "./Composer.js";
import { copyText } from "./clipboard.js";
import { COMMANDS, matching, parseCommand, type SessionInfo } from "./commands.js";
import { Footer } from "./Footer.js";
import { Form, formHeight } from "./form/Form.js";
import { fieldBuffer } from "./form/field-state.js";
import {
  type Ask,
  type Ended,
  fieldResult,
  type OpenStep,
  openStep,
  pickResult,
  questionResult,
  stepKey,
  stepPaste,
  stepView,
} from "./form/form-step.js";
import { BACK, FlowCancelledError, type FormUI } from "./form/form-ui.js";
import type { QuestionAnswer } from "./form/question-state.js";
import { frameRows } from "./frame.js";
import { burstKeys, editLine, emptyLine, insertText, type LineState, moveLine } from "./line-editor.js";
import { answerQuestions, pendingQuestions } from "./questions.js";
import { lastReport } from "./report/report.js";
import { StatusRow } from "./Status.js";
import { loginFlow, modelFlow, type SetupActions, type SetupFacts } from "./setup/setup-flows.js";
import { askSync } from "./setup/sync-question.js";
import { liveLines, Transcript } from "./Transcript.js";
import { useRoles } from "./theme-context.js";
import { lastAnswerMarkdown, transcriptMarkdown } from "./transcript-export.js";
import { emptyTranscript, liveMarkdown, reduceTranscript, type TranscriptState } from "./transcript-state.js";

/** How long ago `then` was, as a list shows it: "just now", "5m ago", "2h ago", "3d ago", else the date. */
function ago(then: number, now: number): string {
  const minutes = Math.floor((now - then) / 60_000);
  if (minutes < 1) return message("app.justNow");
  if (minutes < 60) return message("app.ago", { amount: `${minutes}m` });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return message("app.ago", { amount: `${hours}h` });
  const days = Math.floor(hours / 24);
  if (days < 30) return message("app.ago", { amount: `${days}d` });
  return new Date(then).toISOString().slice(0, 10);
}

/** Text on one line: runs of whitespace, line breaks included, as one space. */
function flat(text: string): string {
  return text.replace(/\s+/g, " ");
}

type Key = Parameters<Parameters<typeof useInput>[0]>[1];

/**
 * Keys the kitty protocol reports as themselves, read as the keys they stand for in a classic terminal:
 * Ctrl+H is Backspace, Ctrl+[ is Esc, Ctrl+M is Enter.
 */
function legacyAliases(character: string, key: Key): { character: string; key: Key } {
  if (!key.ctrl) return { character, key };
  if (character === "h") return { character: "", key: { ...key, ctrl: false, backspace: true } };
  if (character === "[") return { character: "", key: { ...key, ctrl: false, escape: true } };
  if (character === "m") return { character: "\r", key: { ...key, ctrl: false, return: true } };
  return { character, key };
}

/** A question sent while a turn runs, with the mode it was sent in. */
type Queued = { question: string; mode: Mode };

/** Most rows the queue takes above the input. */
const QUEUE_ROWS = 4;

/** The queue's rows above the input, at most `rows`: a pause line first, then the questions, then a count. */
function queueLines(queue: readonly string[], paused: boolean, rows: number): string[] {
  if (!queue.length || rows <= 0) return [];
  // The pause line keeps its row; the questions get the rest, the last row counting those left out.
  const pause = paused ? [`  ${message("app.queuePaused")}`] : [];
  const room = rows - pause.length;
  if (room <= 0) return pause.slice(0, rows);
  const questions = queue.map((question) => `  ${message("app.queued", { text: flat(question) })}`);
  if (questions.length <= room) return [...pause, ...questions];
  const kept = questions.slice(0, room - 1);
  return [...pause, ...kept, `  ${message("app.queuedMore", { count: questions.length - kept.length })}`];
}

/** Questions asked before, oldest first, and how to keep a new one. */
export type InputHistory = { entries: readonly string[]; add(question: string): void };

/** What the app needs of the engine. */
export type Asker = { ask(question: string, options?: AskOptions): Turn };

/**
 * How the process talks to the app: `interrupt` for a SIGINT from outside the keyboard; `notice`
 * for a problem found outside a turn (a session that can no longer be saved); `settled`, after the
 * app has gone, resolves once a turn it left running has stopped; `abandoned`, after the app has
 * gone, when it left a turn that would not stop, whose timers and requests the process must not
 * wait for.
 */
export type ChatControls = {
  interrupt?: () => void;
  /** Set once a question was asked, so the process knows the session has something to resume. */
  asked?: boolean;
  notice?: (text: string) => void;
  settled?: Promise<unknown>;
  abandoned?: boolean;
};

/**
 * What `/login` and `/model` need: what the setup knows now, and what it does (its lines said in the
 * transcript; what the session runs on once it changed, shown at once).
 */
export type ChatSetup = {
  facts(): Promise<SetupFacts>;
  actions(say: (line: string) => void, shown: (info: SessionInfo) => void): SetupActions;
};

/** The model a session runs on, as /status and the footer show it. */
type RunsOn = { model: string; provider: string; contextWindow?: number };

/** Switching the session the chat talks to: `/new` and `/resume`. */
export type ChatSessions = {
  /**
   * The sessions to go on with, with those only in the Tauric account when sync is on; `problem` when the
   * account could not be listed.
   */
  list(): Promise<{ sessions: SessionSummary[]; problem?: string }>;
  current(): string;
  /** Whether deleting a session deletes its copy in the Tauric account too (sync is on). */
  deletesFromAccount: boolean;
  /** Delete session `id`: where it took effect (Deleted). */
  delete(id: string): Promise<Deleted>;
  /** Each gives the session switched to and the model it runs on. */
  startNew(): Promise<{ id: string } & RunsOn>;
  /** `copied` when the session was copied from the account first. */
  open(id: string): Promise<{ id: string; earlier: Earlier; copied?: true } & RunsOn>;
};

/**
 * Whether to sync sessions to the Tauric account, asked once in the app: `wanted`, whether to ask now (a key
 * and no answer yet, and the account keeps this application's sessions); `answer` keeps the choice, and with
 * sync turned on copies the running session from its start.
 */
export type ChatSync = { wanted(): Promise<boolean>; answer(on: boolean): Promise<void> };

/** A resumed session's earlier turns, shown again; `interrupted` when its last turn never ended. */
export type Earlier = { events: readonly EventEnvelope[]; interrupted: boolean };

/** The mode a session's questions were last asked in: its last turn's, else `auto`. */
function sessionMode(events: readonly EventEnvelope[] = []): Mode {
  for (const { event } of events.toReversed()) if (event.type === "turn.started") return event.mode;
  return "auto";
}

/** The events that end a turn. */
const ENDS = new Set(["turn.completed", "turn.cancelled", "turn.failed"]);

/** `settled`: the turn's last event is drawn; its outcome is still being read. */
type Phase = "idle" | "running" | "cancelling" | "settled";

export function ChatApp({
  engine,
  notices = [],
  earlier,
  controls,
  info,
  history,
  setup,
  sessions,
  sync,
  news,
}: {
  engine: Asker;
  notices?: readonly string[];
  earlier?: Earlier;
  controls?: ChatControls;
  /** The session as `/status` and the header describe it. */
  info: SessionInfo;
  /** Questions asked before, oldest first, and where to keep them. */
  history: InputHistory;
  /** `/login` and `/model`. */
  setup: ChatSetup;
  /** `/new` and `/resume`. */
  sessions: ChatSessions;
  /** The question whether to sync sessions, asked once the app is idle. */
  sync: ChatSync;
  /** The welcome block's one line of news: what's new in this version (once), else a newer release. */
  news?: string | undefined;
}) {
  const roles = useRoles();
  const { exit } = useApp();
  const { columns, rows } = useWindowSize();
  const { stdout } = useStdout();
  const [state, dispatch] = useReducer(reduceTranscript, undefined, (): TranscriptState => {
    // The header is the scrollback's first block; earlier turns follow it.
    const start = reduceTranscript(emptyTranscript, {
      type: "local.header",
      version: info.version,
      model: info.model,
      keyed: info.tauricKey,
      news,
    });
    let state = (earlier?.events ?? []).reduce(reduceTranscript, start);
    if (earlier?.interrupted) {
      state = reduceTranscript(state, {
        type: "stream.failed",
        message: message("app.interrupted"),
      });
    }
    return notices.reduce(
      (current, text) => reduceTranscript(current, { type: "local.notice", level: "warn", text }),
      state,
    );
  });
  const [phase, setPhase] = useState<Phase>("idle");
  // The mode the next question is asked in: the session's own, switched with Shift+Tab.
  const mode = useRef<Mode>(sessionMode(earlier?.events));
  // Refs, not state: keys, a paste followed by Enter, or a second Ctrl+C can all arrive before React
  // renders the effect of the one before, and each must see it.
  const line = useRef<LineState>(emptyLine);
  // The command menu: which match is selected, and the input it was closed for (Esc) until that changes.
  const menu = useRef<{ selected: number; closedFor?: string }>({ selected: 0 });
  // Earlier questions: the list, how far back Up has gone (0 = the draft), and the draft kept meanwhile.
  const asked = useRef<string[]>([...history.entries]);
  const browse = useRef<{ back: number; draft: LineState }>({ back: 0, draft: emptyLine });
  // Ctrl+R: what is searched for, which match (0 = newest), and the input to go back to on Esc.
  const search = useRef<{ query: string; skip: number; draft: LineState } | undefined>(undefined);
  // Questions sent while a turn runs, oldest first, each with the mode it was sent in, and whether a stopped
  // or failed turn paused them.
  const queue = useRef<Queued[]>([]);
  const paused = useRef(false);
  // The send function, for `run` to call when a turn ends (it is defined after `run`).
  const sendNext = useRef<(queued: Queued) => void>(() => {});
  // Shows the questions a turn ended with, and sends the reply (set once `send` is defined).
  const answerNext = useRef<(questions: readonly Question[]) => void>(() => {});
  // Set once the app is leaving: nothing more is sent. And a stop asked for the running turn, which
  // pauses the queue even when the turn had already finished by then.
  const closing = useRef(false);
  const stopAsked = useRef(false);
  /** Leave the app: nothing queued goes after this. */
  const leave = useCallback(() => {
    closing.current = true;
    exit();
  }, [exit]);
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  // The transcript as last drawn, for what reads it outside a render (/export).
  const latest = useRef(state);
  // Turns run in this app, and the one whose proposed plan was last offered: a plan is offered once.
  const planTurn = useRef(0);
  const planAskedFor = useRef(-1);
  latest.current = state;
  const active = useRef<Turn | undefined>(undefined);
  const cancelling = useRef(false);
  // When the running turn was asked to stop, and whether the app then left without waiting for it.
  const cancelledAt = useRef(0);
  const abandoned = useRef(false);
  const edit = useCallback((next: LineState) => {
    line.current = next;
    redraw();
  }, []);

  // A setup (/login, /model) while it runs, and the step it shows: that step's keys come before all others.
  const flowing = useRef(false);
  const form = useRef<{ open: OpenStep; done: (ended: Ended) => void } | undefined>(undefined);
  // A Ctrl+C or SIGINT while a setup is between steps: it ends at its next step.
  const cancelAsked = useRef(false);
  // Until when a paste is dropped: the rest of one that began as a step ended is not the input's.
  const quietUntil = useRef(0);
  /** Show `ask` as the setup's step until it ends; a cancel asked between steps ends it at once. */
  const showStep = (ask: Ask) =>
    new Promise<Ended>((resolve, reject) => {
      if (cancelAsked.current) {
        cancelAsked.current = false;
        return reject(new FlowCancelledError());
      }
      form.current = { open: openStep(ask), done: resolve };
      redraw();
    });
  const formUI = useRef<FormUI>({
    pick: (step) => showStep({ kind: "pick", step }).then(pickResult),
    question: (step) => showStep({ kind: "question", step }).then(questionResult),
    field: (step) => {
      const buffer = fieldBuffer(step.kind, step.initial);
      return showStep({ kind: "field", step, buffer }).then((ended) => fieldResult(ended, buffer));
    },
  });
  /** End the step up now: its flow goes on, back, or is cancelled. */
  const endForm = useCallback((ended: Ended) => {
    const current = form.current;
    form.current = undefined;
    quietUntil.current = Date.now() + APP.pasteQuietMs;
    current?.done(ended);
    redraw();
  }, []);
  // The session's id and model as /status and the footer show them: those it started with, until /new or
  // /resume, or /model or /login moves it.
  const sessionId = useRef(info.session);
  // What /status says of the session: as it started, until /model or /login changes what it uses.
  const infoNow = useRef(info);
  const modelNow = useRef<RunsOn>({
    model: info.model,
    provider: info.provider,
    ...(info.contextWindow ? { contextWindow: info.contextWindow } : {}),
  });
  /** Show the session switched to: a line, then its earlier turns as they were. */
  const switched = useCallback(
    (id: string, runsOn: RunsOn, earlier?: Earlier) => {
      sessionId.current = id;
      modelNow.current = {
        model: runsOn.model,
        provider: runsOn.provider,
        ...(runsOn.contextWindow ? { contextWindow: runsOn.contextWindow } : {}),
      };
      queue.current = [];
      paused.current = false;
      mode.current = sessionMode(earlier?.events);
      if (controls) controls.asked = false;
      dispatch({
        type: "local.notice",
        level: "info",
        text: earlier ? message("app.resumed", { id }) : message("app.newSession", { id }),
      });
      for (const envelope of earlier?.events ?? []) dispatch(envelope);
      if (earlier?.interrupted) dispatch({ type: "stream.failed", message: message("app.interrupted") });
    },
    [controls],
  );
  /** `/new`: a new session in place of this one. */
  const startNew = useCallback(async () => {
    flowing.current = true;
    try {
      const started = await sessions.startNew();
      switched(started.id, started);
    } catch (error) {
      dispatch({ type: "local.notice", level: "error", text: errorText(error) });
    } finally {
      flowing.current = false;
      redraw();
    }
  }, [sessions, switched]);
  /**
   * Run `steps` in place of the input, one flow at a time (false when another is up): a cancel ends them
   * quietly, a failure is an error notice (`failed` words its reason); then the input comes back, keys typed
   * just before it ignored for a moment.
   */
  const inFlow = useCallback(
    async (steps: () => Promise<void>, failed: (reason: string) => string = (reason) => reason) => {
      if (flowing.current) return false;
      flowing.current = true;
      try {
        await steps();
      } catch (error) {
        if (!(error instanceof FlowCancelledError))
          dispatch({ type: "local.notice", level: "error", text: failed(errorText(error)) });
      } finally {
        flowing.current = false;
        form.current = undefined;
        cancelAsked.current = false;
        quietUntil.current = Date.now() + APP.pasteQuietMs;
        redraw();
      }
      return true;
    },
    [],
  );
  /** `/resume`: a list of the sessions here, newest first; the one chosen in place of this one. */
  const resumePick = useCallback(async () => {
    // The questions the session chosen ended with, asked again once the list is gone.
    let unanswered: readonly Question[] | undefined;
    await inFlow(async () => {
      // Deleting one lists the rest again; choosing one goes on with it.
      for (;;) {
        const { sessions: all, problem } = await sessions.list();
        if (problem) dispatch({ type: "local.notice", level: "warn", text: problem });
        const listed = all.filter((summary) => summary.id !== sessions.current());
        if (!listed.length) {
          dispatch({ type: "local.notice", level: "info", text: message("app.noOtherSessions") });
          return;
        }
        const now = Date.now();
        const ended = await new Promise<Ended>((resolve) => {
          form.current = {
            open: openStep({
              kind: "pick",
              step: {
                title: message("app.resumeWhich"),
                filter: true,
                esc: "close",
                options: listed.map((summary) => ({
                  id: summary.id,
                  label:
                    flat(summary.title) ||
                    message(summary.where === "account" ? "cli.untitledAccount" : "cli.untitledSession"),
                  note:
                    summary.where === "account"
                      ? message("app.sessionInAccount", { ago: ago(summary.updated.getTime(), now) })
                      : message("app.sessionNote", {
                          ago: ago(summary.updated.getTime(), now),
                          turns: summary.turns,
                        }),
                  detail: summary.id,
                })),
                deleteConfirm: message(
                  sessions.deletesFromAccount ? "app.deleteEverywhere" : "app.deleteHere",
                ),
              },
            }),
            done: resolve,
          };
          redraw();
        });
        if (ended.kind === "delete") {
          const where = await sessions.delete(ended.id);
          dispatch({ type: "local.notice", level: "info", text: message(`app.deleted.${where}` as const) });
          continue;
        }
        if (ended.kind !== "chosen") return;
        const opened = await sessions.open(ended.id);
        if (opened.copied)
          dispatch({ type: "local.notice", level: "info", text: message("app.copiedFromAccount") });
        switched(opened.id, opened, opened.earlier);
        if (!opened.earlier.interrupted) unanswered = pendingQuestions(opened.earlier.events);
        return;
      }
    });
    if (unanswered) answerNext.current(unanswered);
  }, [sessions, switched, inFlow]);
  /** A command's steps in place of the input (`/export`'s choice and path). */
  const runFlow = useCallback(
    async (steps: (ui: FormUI) => Promise<void>) => {
      await inFlow(() => steps(formUI.current));
    },
    [inFlow],
  );
  /** Run `/login` or `/model` in place of the input, then say what it did. */
  const openSetup = useCallback(
    async (kind: "login" | "model") => {
      const say = (lineText: string) => dispatch({ type: "local.lines", lines: [lineText] });
      await inFlow(
        async () => {
          const run = kind === "login" ? loginFlow : modelFlow;
          const shown = (now: SessionInfo) => {
            infoNow.current = now;
            modelNow.current = {
              model: now.model,
              provider: now.provider,
              ...(now.contextWindow ? { contextWindow: now.contextWindow } : {}),
            };
            redraw();
          };
          const lines = await run(formUI.current, await setup.facts(), setup.actions(say, shown));
          if (lines.length) dispatch({ type: "local.lines", lines });
        },
        (reason) => message("app.setupFailed", { reason }),
      );
    },
    [setup, inFlow],
  );

  // Leaving with a turn still running stops it; the process waits for it through `settled`, unless
  // the app left one that would not stop.
  useEffect(
    () => () => {
      closing.current = true;
      const turn = active.current;
      if (!turn) return;
      turn.cancel();
      if (!controls) return;
      if (abandoned.current) controls.abandoned = true;
      else controls.settled = turn.outcome.catch(() => undefined);
    },
    [controls],
  );

  const run = useCallback(
    (turn: Turn) => {
      planTurn.current++;
      active.current = turn;
      cancelling.current = false;
      stopAsked.current = false;
      setPhase("running");
      void (async () => {
        // The questions the turn ended with, for the person to answer.
        let questions: readonly Question[] | undefined;
        try {
          for await (const envelope of turn.events) {
            // A turn that started is in the session: there is something to resume.
            if (controls && envelope.event.type === "turn.started") controls.asked = true;
            if (envelope.event.type === "question.asked" && !envelope.parent)
              questions = envelope.event.questions;
            dispatch(envelope);
            // Drawn in the same render as the turn's end, so no frame shows it still running.
            if (ENDS.has(envelope.event.type)) setPhase("settled");
          }
        } catch (error) {
          dispatch({
            type: "stream.failed",
            message: message("app.stoppedUnexpectedly", {
              reason: errorText(error),
            }),
          });
        }
        const outcome = await turn.outcome.catch(() => undefined);
        active.current = undefined;
        setPhase("idle");
        // Questions are answered next, unless a question queued while the turn ran goes first.
        if (questions && outcome?.status === "completed" && !queue.current.length && !closing.current)
          answerNext.current(questions);
        // The next queued question goes when this one completed; a stop or failure pauses the queue.
        if (queue.current.length && !closing.current) {
          const went =
            (outcome?.status === "completed" || outcome?.status === "capped") && !stopAsked.current;
          if (went && !paused.current) sendNext.current(queue.current.shift() as Queued);
          else paused.current = true;
          redraw();
        }
      })();
    },
    [controls],
  );

  /** Run a command by name, with what followed it. */
  const command = useCallback(
    (name: string, args: string) => {
      const found = COMMANDS.find((candidate) => candidate.name === name);
      if (!found) {
        dispatch({ type: "local.notice", level: "warn", text: message("app.unknownCommand", { name }) });
        return;
      }
      if (active.current && !found.whileRunning) {
        dispatch({ type: "local.notice", level: "info", text: message("app.afterThisAnswer", { name }) });
        return;
      }
      found.run(
        {
          info: {
            ...(infoNow.current ?? {
              version: "",
              model: "",
              provider: "",
              data: "",
              tauricKey: false,
              sync: "",
            }),
            ...(sessionId.current ? { session: sessionId.current } : {}),
            ...(modelNow.current.model ? modelNow.current : {}),
          },
          say: (lines, links) => dispatch({ type: "local.lines", lines, ...(links ? { links } : {}) }),
          notice: (level, text) => dispatch({ type: "local.notice", level, text }),
          list: (list, links) => dispatch({ type: "local.list", list, ...(links ? { links } : {}) }),
          flow: (steps) => void runFlow(steps),
          answer: () => lastAnswerMarkdown(latest.current.done),
          copy: (text) => copyText(text, { write: (sequence) => stdout.write(sequence) }),
          exit: leave,
          transcript: () => transcriptMarkdown(latest.current.done),
          report: () =>
            lastReport(latest.current.done, {
              session: sessionId.current ?? "",
              model: modelNow.current.model,
              version: info.version,
            }),
          setup: (kind) => void openSetup(kind),
          newSession: () => void startNew(),
          resume: () => void resumePick(),
        },
        args,
      );
    },
    [info, leave, openSetup, startNew, resumePick, runFlow, stdout],
  );

  /** Ask `question` now in `mode`: written as it is sent, before anything of its turn. */
  const send = useCallback(
    ({ question, mode }: Queued) => {
      if (closing.current) return;
      dispatch({ type: "local.question", text: question });
      try {
        run(engine.ask(question, { mode }));
        // Kept for Up and Ctrl+R once the engine took it.
        asked.current = withQuestion(asked.current, question);
        history.add(question);
      } catch (error) {
        // What is still queued waits for Enter rather than following a question that did not go.
        if (queue.current.length) paused.current = true;
        dispatch({ type: "local.unsent" });
        dispatch({
          type: "local.notice",
          level: "error",
          text: errorText(error),
        });
      }
    },
    [engine, run, history],
  );
  sendNext.current = send;

  /** Show `questions` in place of the input, then send the reply; left unanswered, the input comes back. */
  const answerQuestionsAsked = useCallback(
    async (questions: readonly Question[]) => {
      if (closing.current) return;
      let reply: string | undefined;
      await inFlow(async () => {
        reply = await answerQuestions(formUI.current, questions);
      });
      if (reply) send({ question: reply, mode: mode.current });
    },
    [send, inFlow],
  );
  answerNext.current = (questions) => void answerQuestionsAsked(questions);
  // A session resumed at start that ended with questions asks them again.
  // biome-ignore lint/correctness/useExhaustiveDependencies: once, for the session the app opened with
  useEffect(() => {
    const unanswered = earlier?.interrupted ? undefined : pendingQuestions(earlier?.events);
    if (unanswered) answerNext.current(unanswered);
  }, []);

  /**
   * Whether this session's last turn proposed a plan that can run as it stands: nothing runs or waits in the
   * queue (queued questions go first), and no setup step holds the input.
   */
  const planOffered = useCallback(() => {
    const ready = latest.current.planReady;
    return (
      ready !== undefined &&
      (sessionId.current === undefined || ready === sessionId.current) &&
      !active.current &&
      !queue.current.length &&
      !form.current
    );
  }, []);

  const submit = useCallback(() => {
    const question = line.current.value.trim();
    if (!question) {
      // Enter on an empty input sends a paused queue on.
      if (!active.current && paused.current && queue.current.length) {
        paused.current = false;
        send(queue.current.shift() as Queued);
      }
      return;
    }
    edit(emptyLine);
    menu.current = { selected: 0 };
    browse.current = { back: 0, draft: emptyLine };
    const parsed = parseCommand(question);
    if (parsed) return command(parsed.name, parsed.args);
    // While a turn runs (or the queue waits), the question joins the queue.
    if (active.current || queue.current.length) {
      queue.current.push({ question, mode: mode.current });
      return redraw();
    }
    send({ question, mode: mode.current });
  }, [send, edit, command]);

  /**
   * A plan proposed and ready to run, offered as a step in place of the input: run it (in auto mode from then
   * on, since the user has agreed what is to be done), or type a change, sent in plan mode for a revised plan.
   * Esc leaves it for the input.
   */
  const offerPlan = useCallback(async () => {
    if (flowing.current || closing.current || !planOffered()) return;
    planAskedFor.current = planTurn.current;
    let answer: QuestionAnswer | typeof BACK | undefined;
    await inFlow(async () => {
      answer = await formUI.current.question({
        title: message("app.planAsk"),
        options: [{ id: "run", label: message("app.planRun"), note: message("app.planRunNote") }],
        own: message("app.planChange"),
        esc: "close",
      });
    });
    if (answer === undefined || answer === BACK) return;
    if ("choice" in answer) {
      mode.current = "auto";
      send({ question: message("app.runPlan"), mode: "auto" });
    } else send({ question: answer.own, mode: mode.current });
  }, [planOffered, send, inFlow]);
  // Offered once the turn that proposed it has settled, and at start for a session resumed with one. Read
  // again as each turn's blocks are written: a turn quick enough leaves the phase idle and planReady the same.
  const written = state.done.length;
  useEffect(() => {
    if (phase === "idle" && state.planReady && written && planAskedFor.current !== planTurn.current)
      void offerPlan();
  }, [phase, state.planReady, written, offerPlan]);

  // The sync question: asked once the account is known to keep sessions, when nothing else is in the
  // way (a turn, another step). Left unanswered (Esc, Ctrl+C), it is asked at the next start.
  const [syncDue, setSyncDue] = useState(false);
  // biome-ignore lint/correctness/useExhaustiveDependencies: asked about once, for the app's first session
  useEffect(() => {
    void sync.wanted().then(
      (wanted) => wanted && setSyncDue(true),
      () => {},
    );
  }, []);
  const stepOpen = form.current !== undefined;
  useEffect(() => {
    if (!syncDue || phase !== "idle" || stepOpen || closing.current) return;
    setSyncDue(false);
    void inFlow(async () => {
      const on = await askSync(formUI.current);
      if (on !== undefined) await sync.answer(on);
    }).then((asked) => asked || setSyncDue(true));
  }, [syncDue, phase, stepOpen, inFlow, sync]);

  /** Stop the running turn once; with nothing running, leave. */
  const interrupt = useCallback(
    (leaveWhenIdle: boolean) => {
      const turn = active.current;
      if (turn) {
        if (cancelling.current) {
          // A turn that has not stopped by now may never: a further Ctrl+C leaves without it.
          if (leaveWhenIdle && Date.now() - cancelledAt.current >= APP.leaveGraceMs) {
            abandoned.current = true;
            leave();
          }
          return;
        }
        cancelling.current = true;
        stopAsked.current = true;
        cancelledAt.current = Date.now();
        setPhase("cancelling");
        turn.cancel();
      } else if (leaveWhenIdle) leave();
    },
    [leave],
  );
  if (controls) {
    // A SIGINT ends a setup as Ctrl+C does (between its steps, at the next one); else it stops the answer, or leaves.
    controls.interrupt = () => {
      if (form.current) endForm({ kind: "cancel" });
      else if (flowing.current) cancelAsked.current = true;
      else interrupt(true);
    };
    controls.notice = (text) => dispatch({ type: "local.notice", level: "warn", text });
  }

  /** The menu as the input stands now: read from the refs, so keys that arrive together each see the last. */
  const menuNow = () => {
    const typed = line.current.value;
    const open = !active.current && /^\/\S*$/.test(typed) && menu.current.closedFor !== typed;
    return { typed, open, matches: open ? matching(typed) : [] };
  };
  const { open: menuOpen, matches } = menuNow();

  // An open menu has the first say over the keys, then the app's own keys; nothing else is typed while
  // a turn runs.
  /** The earlier question Ctrl+R finds now, newest first, skipping `skip` matches (line breaks as spaces). */
  const found = (query: string, skip: number): string | undefined => {
    const wanted = flat(query).toLowerCase();
    return asked.current
      .toReversed()
      .filter((entry) => flat(entry).toLowerCase().includes(wanted))
      .at(skip);
  };

  /** Put a line break in at the cursor. */
  const newline = () => edit(insertText(line.current, "\n"));

  // A paste is text with its line breaks; while searching, it searches.
  usePaste((text) => {
    // A setup's step takes the paste; between its steps, and just after one, nothing does.
    if (Date.now() < quietUntil.current) return;
    if (form.current) {
      form.current = { ...form.current, open: stepPaste(form.current.open, text) };
      return redraw();
    }
    if (flowing.current) return;
    if (search.current) {
      search.current = {
        ...search.current,
        query: flat(search.current.query + text),
        skip: 0,
      };
      return redraw();
    }
    edit(insertText(line.current, text));
  });

  // Each key of a read that held several (typed text and its Enter together) is handled in turn.
  useInput((typed, pressed) => {
    // A read stops where a setup's step opens or ends: what follows is not the next step's, nor the input's.
    const step = form.current;
    const running = flowing.current;
    for (const [input, key] of burstKeys(typed, pressed)) {
      onKey(input, key);
      if (form.current !== step || flowing.current !== running) break;
    }
  });

  function onKey(typed: string, pressed: Key) {
    if (form.current) {
      const next = stepKey(form.current.open, typed, pressed);
      if ("ended" in next) return endForm(next.ended);
      form.current.open = next.open;
      return redraw();
    }
    // Between a setup's steps (it is saving), keys wait for the next step; Ctrl+C ends it there.
    if (flowing.current) {
      if (pressed.ctrl && typed === "c") cancelAsked.current = true;
      return;
    }
    // Under the kitty protocol Ctrl+H, Ctrl+[ and Ctrl+M arrive as themselves: they keep their old meaning.
    const { character, key } = legacyAliases(typed, pressed);
    // Ctrl+R's search has the keys while it is open.
    if (search.current) {
      const current = search.current;
      // A modified Enter may be Esc and Enter read together: it leaves the search, as Esc does.
      if (key.escape || (key.ctrl && character === "c") || (key.return && (key.meta || key.shift))) {
        search.current = undefined;
        return edit(current.draft);
      }
      if (key.ctrl && character === "r") {
        if (found(current.query, current.skip + 1) !== undefined)
          search.current = { ...current, skip: current.skip + 1 };
        return redraw();
      }
      if (key.backspace || key.delete) {
        search.current = { ...current, query: current.query.slice(0, -1), skip: 0 };
        return redraw();
      }
      if (key.return || key.upArrow || key.downArrow || key.leftArrow || key.rightArrow || key.tab) {
        const match = found(current.query, current.skip);
        search.current = undefined;
        browse.current = { back: 0, draft: emptyLine };
        return edit(match === undefined ? current.draft : { value: match, cursor: match.length });
      }
      if (!key.ctrl && !key.meta && character && character !== "\n") {
        search.current = { ...current, query: current.query + character, skip: 0 };
        return redraw();
      }
      return;
    }
    // Shift+Tab switches the mode the next question is asked in.
    if (key.tab && key.shift) {
      mode.current = MODES[(MODES.indexOf(mode.current) + 1) % MODES.length] as Mode;
      return redraw();
    }
    const { typed: input, open, matches } = menuNow();
    if (open) {
      const count = matches.length;
      // A modified Enter may be Esc and Enter read together: it closes the menu, as Esc does.
      if (key.escape || (key.return && (key.meta || key.shift))) {
        menu.current = { selected: 0, closedFor: input };
        return redraw();
      }
      if ((key.upArrow || key.downArrow) && count) {
        menu.current = { selected: (menu.current.selected + (key.upArrow ? count - 1 : 1)) % count };
        return redraw();
      }
      const chosen = matches[Math.min(menu.current.selected, count - 1)];
      if (key.tab && chosen) return edit({ value: `/${chosen.name} `, cursor: chosen.name.length + 2 });
      if (key.return && chosen) {
        edit(emptyLine);
        menu.current = { selected: 0 };
        return command(chosen.name, "");
      }
    }
    if (key.escape) return interrupt(false);
    if (key.ctrl && character === "c") {
      // Typed text is cleared first; then Ctrl+C stops the answer, or leaves.
      if (line.current.value !== "") {
        menu.current = { selected: 0 };
        browse.current = { back: 0, draft: emptyLine };
        return edit(emptyLine);
      }
      return interrupt(true);
    }
    if (key.ctrl && character === "d") {
      if (!active.current && line.current.value === "") leave();
      return;
    }
    // Line breaks: Ctrl+J (a bare line feed, or its kitty form), Alt+Enter, Shift+Enter, or `\` + Enter.
    if (character === "\n" || (key.ctrl && character === "j")) return newline();
    if (key.return && (key.meta || key.shift)) return newline();
    if (key.return) {
      const { value, cursor } = line.current;
      if (cursor > 0 && value[cursor - 1] === "\\") {
        return edit(
          insertText({ value: value.slice(0, cursor - 1) + value.slice(cursor), cursor: cursor - 1 }, "\n"),
        );
      }
      return submit();
    }
    if (key.ctrl && character === "r") {
      search.current = { query: "", skip: 0, draft: line.current };
      return redraw();
    }
    // Up on an empty input takes the last queued question back to edit.
    if (key.upArrow && line.current.value === "" && queue.current.length) {
      const last = (queue.current.pop() as Queued).question;
      if (!queue.current.length) paused.current = false;
      return edit({ value: last, cursor: last.length });
    }
    if (key.upArrow || key.downArrow) {
      const moved = moveLine(line.current, key.upArrow ? "up" : "down");
      if (moved) return edit(moved);
      // Past the first or last line: through the questions asked before, and back to the draft.
      const { back, draft } = browse.current;
      const to = key.upArrow ? Math.min(asked.current.length, back + 1) : Math.max(0, back - 1);
      if (to === back) return;
      browse.current = { back: to, draft: back === 0 ? line.current : draft };
      const entry = asked.current.at(-to);
      return edit(to === 0 ? browse.current.draft : { value: entry ?? "", cursor: (entry ?? "").length });
    }
    const next = editLine(line.current, character, key);
    if (next !== line.current) {
      if (next.value !== line.current.value) {
        // A new name starts the selection over; an edited earlier question becomes the draft.
        menu.current = { selected: 0 };
        if (browse.current.back) browse.current = { back: 0, draft: next };
      }
      edit(next);
    }
  }

  // While searching, the input shows the match (or what it was), and the footer row says what is searched.
  const searching = search.current;
  const match = searching ? found(searching.query, searching.skip) : undefined;
  const shown = searching
    ? match === undefined
      ? searching.draft
      : { value: match, cursor: match.length }
    : line.current;
  // A setup's step takes the input's place and the footer's.
  const step = form.current ? stepView(form.current.open) : undefined;
  // A question is running (its end is drawn once it settles).
  const running = phase === "running" || phase === "cancelling";
  // Exactly one blank row between the transcript and what is under it: a transcript that ends in a blank row
  // of its own (a question's band, the welcome), with nothing live after it, needs no other.
  const last = state.done.at(-1)?.kind;
  const endsBlank =
    (last === "question" || last === "header") && liveLines(state, columns, rows).length === 0;
  // One budget for the frame (see frame.ts); the transcript's live rows get what is left.
  const budget = frameRows({
    rows,
    input: step ? formHeight(step, columns) : composerHeight(shown, columns, rows),
    status: running,
    gap: !endsBlank,
    below: step ? 0 : menuOpen ? Math.max(1, menuHeight(matches)) : 1,
    answer: liveMarkdown(state.live).trim() !== "",
    queue: queueLines(
      queue.current.map((queued) => queued.question),
      paused.current,
      QUEUE_ROWS,
    ).length,
  });
  const queued = queueLines(
    queue.current.map((entry) => entry.question),
    paused.current,
    budget.queue,
  );
  return (
    <>
      <Transcript state={state} reserved={rows - 1 - budget.live} />
      {budget.gap ? <Text> </Text> : null}
      {queued.map((text, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: each row is a position above the input
        <Text key={index} {...roles.detail} wrap="truncate">
          {text}
        </Text>
      ))}
      {budget.status ? <StatusRow state={state} stopping={phase === "cancelling"} /> : null}
      {step ? (
        budget.input > 0 ? (
          <Form step={step} rows={budget.input} />
        ) : null
      ) : budget.input ? (
        <Composer line={shown} columns={columns} rows={rows} busy={running} />
      ) : null}
      {!budget.below ? null : searching ? (
        <Text {...roles.detail} wrap="truncate">
          {"  "}
          {message(match === undefined && searching.query ? "app.searchNone" : "app.search", {
            query: searching.query,
          })}
        </Text>
      ) : menuOpen ? (
        <CommandMenu
          matches={matches}
          selected={Math.min(menu.current.selected, Math.max(0, matches.length - 1))}
          typed={line.current.value}
          rows={budget.below}
        />
      ) : (
        <Footer
          state={state}
          columns={columns}
          mode={mode.current}
          model={modelNow.current.model}
          version={info.version}
        />
      )}
    </>
  );
}
