// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What a turn adds to the main agent's tools: `run_agent`, which runs one of the turn's agents on a
 * brief, `use_skill`, `update_plan`, and `ask_user` when a person is there to answer. The turn owns its
 * agents: their run ids, a budget of runs and a shared limit on data calls, so delegation cannot multiply
 * the load on a source. An agent's report is recorded like any result, so later briefs hand it on by its id.
 */

import { dirname } from "node:path";
import { z } from "zod";
import type { AgentFile } from "../agents/agent-file.js";
import type { CatalogEntry } from "../agents/catalog.js";
import { type AgentOutcome, type AgentSpec, type Caps, cacheKeyOf, runAgent } from "../agents/index.js";
import { AGENT_REPORT, briefWith, DATA_NOT_INSTRUCTIONS, REFERENCES } from "../agents/prompts.js";
import { readSkillFile, SKILL_PATH_CHARS } from "../agents/skill-dir.js";
import type { SkillFile } from "../agents/skill-file.js";
import {
  AGENT_TOOL,
  ASK_TOOL,
  type Clock,
  type Event,
  errorText,
  type Message,
  type ModelClient,
  message,
} from "../contracts/index.js";
import type { Limits } from "../contracts/limits.js";
import { CALLS, questionReserve } from "../contracts/limits.js";
import { type Writer, writersOf } from "../tools/evidence.js";
import type { EvidenceStore } from "../tools/evidence-store.js";
import { defineTool, type Tool, type ToolContext, ToolRefusalError, ToolRegistry } from "../tools/index.js";
import { resolveReferences } from "../tools/references.js";
import { renderResult } from "../tools/render.js";
import { REPORT, renderReport } from "../tools/report.js";

/** A skill with where it comes from: built-in (its files compiled in), or the path of its SKILL.md. */
export type Skill = CatalogEntry<SkillFile>;

/** One of a skill's files: compiled in, or read from the skill's directory. */
function skillFile(skill: Skill, file: string): string | undefined {
  if (skill.resources) return skill.files.includes(file) ? skill.resources[file] : undefined;
  return readSkillFile(dirname(skill.source), skill.files, file);
}

export type RunRecord = {
  run: string;
  agent: string;
  status: AgentOutcome["status"];
  messages: Message[];
};

type TurnRuntimeOptions = {
  session: string;
  turn: string;
  /** The main agent's run id: the parent of every sub-agent run. */
  main: string;
  client: ModelClient;
  /** The data tools; the turn wraps those that fetch (kind data) in its shared call limit. */
  data: readonly Tool[];
  /** Tools every agent has (compute and the evidence tool), outside the call limit. */
  core: readonly Tool[];
  /** The session's recorded results, which every run of the turn publishes to. */
  evidence: EvidenceStore;
  agents: readonly AgentFile[];
  skills: readonly Skill[];
  /** The calendar lines of the turn, given to every sub-agent as they are given to the main agent. */
  calendar: string;
  /** What every sub-agent's spec shares with the main agent's: its sampling and the model's window and input limit. */
  model: Pick<AgentSpec, "sampling" | "hurriedSampling" | "contextWindow" | "inputLimit">;
  /** Emit an event for a run (the engine wraps it in an envelope with that run and its parent). */
  emit: (run: string, parent: string | undefined, event: Event) => void;
  /** What the question and each agent may use. */
  limits: Limits;
  /** When the question's time runs out (Date.now() milliseconds), if it has a time limit. */
  questionEnds?: number;
  /** The whole turn's tokens so far, which the question's token limit counts. */
  spentTokens: () => number;
  /** Whether a person is there to answer the main agent's questions (the terminal UI). */
  asks?: boolean;
  /** The engine's clock, which every sub-agent's tools run on too. */
  clock: Clock;
};

export class TurnRuntime {
  readonly runs: RunRecord[] = [];
  private started = 0;
  /** The skills loaded this turn. */
  private readonly loaded = new Set<string>();
  /** Whether the main agent asked the person this turn: once, as the person answers one set of questions. */
  private asked = false;
  private closed = false;
  private readonly pending = new Set<Promise<unknown>>();
  /** Runs started and not yet finished, by run id, with their agent's name. */
  private readonly unfinished = new Map<string, string>();
  private readonly dataTools: Tool[];
  /** How each tool writes a recorded result a brief hands on. */
  private readonly writers: Map<string, Writer>;

  constructor(private readonly options: TurnRuntimeOptions) {
    const limit = new Semaphore(CALLS.turnDataCalls);
    this.dataTools = options.data.map((tool) =>
      tool.kind !== "data"
        ? tool
        : ({
            ...tool,
            run: (input: never, context: never) =>
              limit.with(
                () => (tool.run as (input: never, context: never) => Promise<never>)(input, context),
                (context as { signal: AbortSignal }).signal,
              ),
          } as Tool),
    );
    this.writers = writersOf([...options.data, ...options.core]);
  }

  /** Every tool the main agent may call this turn. */
  tools(): Tool[] {
    const { agents, skills } = this.options;
    return [
      ...this.dataTools,
      ...this.options.core,
      ...(agents.length ? [this.agentTool()] : []),
      ...(skills.length ? [this.skillTool()] : []),
      ...(agents.length ? [this.planTool()] : []),
      ...(this.options.asks ? [this.askTool()] : []),
    ];
  }

  /** The agents the main agent's prompt lists. */
  agentList(): string {
    if (!this.options.agents.length) return "";
    return [
      "Your agents, research teams that each own a discipline and its tools (ask them with run_agent):",
      ...this.options.agents.map((agentFile) => `- ${agentFile.name}: ${agentFile.description}`),
    ].join("\n");
  }

  /** The skills the main agent's prompt lists. */
  skillList(): string {
    if (!this.options.skills.length) return "";
    return [
      "Skills you can load with use_skill when a request calls for one:",
      ...this.options.skills.map((skill) => `- ${skill.name}: ${skill.description}`),
    ].join("\n");
  }

  private agentTool() {
    const { agents } = this.options;
    const names = agents.map((agentFile) => agentFile.name) as [string, ...string[]];
    return defineTool({
      name: AGENT_TOOL,
      description:
        "Ask one of your agents (listed in your instructions) to research a brief: it works in its own context with its own tools, records its results like yours, and returns a report that cites them by id.",
      kind: "agent",
      parallelSafe: true,
      input: z.object({
        agent: z.enum(names).describe("The agent to ask"),
        title: z
          .string()
          .trim()
          .min(3)
          .max(CALLS.agentTitleChars)
          .describe(
            'What the person watching sees on this agent\'s row while it works: a few words naming its part of the question, such as "JPM valuation vs peers" or "Rates and the credit cycle". The agent never reads it; the brief is what it works from.',
          ),
        brief: z
          .string()
          .trim()
          .min(10)
          .max(CALLS.briefChars)
          .describe(
            "The agent starts fresh, so the brief is all it knows of the question: the objective, what its report needs to answer, the sources to prefer or leave aside, and what lies outside its part (another agent's, or already known). Name the instrument and any date.",
          ),
        evidence: z
          .array(z.string().regex(/^e[1-9]\d*$/))
          .max(CALLS.briefRecords)
          .optional()
          .describe(
            "Ids of recorded results to give the agent whole with its brief, such as the analysts' reports it should argue from (e12)",
          ),
      }),
      output: REPORT,
      label: ({ agent }) => agent,
      render: renderReport,
      run: async ({ agent, brief, evidence = [] }, context) => {
        const agentFile = agents.find((item) => item.name === agent) as AgentFile;
        // The slot is taken before anything is awaited, so parallel calls cannot overrun a set limit.
        const most = this.options.limits.subagentsPerQuestion;
        if (most !== undefined && this.started >= most) {
          throw new ToolRefusalError(`This turn has used its ${most} agent runs; answer with what you have.`);
        }
        const given = this.given(evidence, context);
        const run = `${this.options.turn}.${agentFile.name}.${++this.started}`;
        const { client, main, emit } = this.options;
        emit(run, main, {
          type: "agent.started",
          agent: agentFile.name,
          label: agentFile.label,
          tier: agentFile.tier,
          model: client.model,
          ...(context.call ? { call: context.call } : {}),
        });
        const child: AgentSpec = {
          name: agentFile.name,
          system: [
            agentFile.prompt,
            ...(this.options.core.length ? [REFERENCES] : []),
            DATA_NOT_INSTRUCTIONS,
            AGENT_REPORT,
            this.options.calendar,
          ].join("\n\n"),
          tools: [...agentFile.tools, ...this.options.core.map((tool) => tool.name)],
          caps: this.capsFor(agentFile),
          maxOutputTokens: this.options.limits.output.stepTokens,
          finalOutputTokens: this.options.limits.output.finalTokens,
          ...this.options.model,
        };
        const registry = new ToolRegistry([
          ...this.dataTools.filter((tool) => agentFile.tools.includes(tool.name)),
          ...this.options.core,
        ]);
        this.unfinished.set(run, agentFile.name);
        const task = this.settle(agentFile, run, () =>
          runAgent(child, briefWith(brief, given), {
            client,
            registry,
            emit: (event) => {
              if (!this.closed) emit(run, main, event);
            },
            signal: context.signal,
            spentTokens: this.options.spentTokens,
            evidence: (step, signal) => this.options.evidence.scope(this.options.turn, run, step, signal),
            cacheKey: cacheKeyOf(this.options.session, agentFile.name),
            clock: this.options.clock,
          }),
        );
        this.pending.add(task);
        try {
          const result = await task;
          if (result.status !== "completed" && result.status !== "capped") throw new Error(result.reason);
          return {
            payload: { agent: agentFile.name, status: result.status, report: result.report },
            // The report's text is in the session's events, which sync, so its record may sync too.
            provenance: { source: agentFile.label, syncs: true },
            summary: result.summary,
          };
        } finally {
          this.pending.delete(task);
        }
      },
    });
  }

  /**
   * The recorded results a brief hands on, each written as its tool writes it; refused, before the run
   * starts, when one cannot be read from this call (unknown, from the same step, or kept elsewhere).
   */
  private given(ids: readonly string[], context: ToolContext): string[] {
    if (!ids.length) return [];
    const scope = context.evidence;
    if (!scope) throw new ToolRefusalError("Recorded results cannot be handed on here.");
    return [...new Set(ids)].map((id) => {
      const resolved = resolveReferences({ ref: id }, scope, scope);
      const record = scope.get(id);
      if (!resolved.ok || !record)
        throw new ToolRefusalError(resolved.ok ? `There is no result ${id}.` : resolved.error);
      const writer = this.writers.get(record.tool);
      return renderResult({
        id,
        tool: record.tool,
        label: record.label,
        provenance: record.provenance,
        payload: resolved.value,
        ...(writer?.table ? { table: writer.table } : {}),
        ...(writer?.render ? { render: writer.render } : {}),
      });
    });
  }

  /**
   * Run one sub-agent to its end and finish it once: its record and exactly one terminal event, however
   * it ends (a report, a cap, no report, a failure, cancellation, or an exception inside it).
   */
  private async settle(
    agentFile: AgentFile,
    run: string,
    work: () => Promise<AgentOutcome>,
  ): Promise<{ status: AgentOutcome["status"]; report: string; summary: string; reason: string }> {
    const { main, emit } = this.options;
    let outcome: AgentOutcome;
    try {
      outcome = await work();
    } catch (error) {
      outcome = {
        status: "failed",
        answer: "",
        usage: { inputTokens: 0, outputTokens: 0 },
        messages: [],
        error: { kind: "internal", message: errorText(error) },
      };
    }
    // A run close() already finished, having waited for it long enough, has no more to report.
    if (!this.unfinished.delete(run))
      return { status: "cancelled", report: "", summary: "", reason: "cancelled" };
    const report = outcome.answer.trim();
    // A run that ends without a report has not reported, whatever its status says.
    if (!report && (outcome.status === "completed" || outcome.status === "capped")) {
      outcome = {
        ...outcome,
        status: "failed",
        error: { kind: "no_report", message: message(noReportReason(outcome)) },
      };
    }
    this.runs.push({ run, agent: agentFile.name, status: outcome.status, messages: outcome.messages });
    const finish = (event: Event) => emit(run, main, event);
    switch (outcome.status) {
      case "completed":
      case "capped": {
        if (outcome.status === "completed") finish({ type: "agent.completed", report });
        else finish({ type: "agent.capped", cap: outcome.cap ?? "steps", report });
        return { status: outcome.status, report, summary: firstLine(report), reason: "" };
      }
      case "cancelled":
        finish({ type: "agent.failed", error: { kind: "cancelled", message: message("run.cancelled") } });
        return { status: "cancelled", report: "", summary: "", reason: "cancelled" };
      case "failed": {
        const error = outcome.error ?? { kind: "failed" as const, message: message("run.noReason") };
        finish({ type: "agent.failed", error });
        return {
          status: "failed",
          report: "",
          summary: "",
          reason: `the ${agentFile.name} agent failed: ${error.message}`,
        };
      }
    }
  }

  /**
   * Wait for every sub-agent this turn started to finish (each stops soon once the turn's signal is
   * aborted), at most `ms`; after that nothing they emit reaches the turn. A run still going then is
   * finished as cancelled, with its terminal event and a record.
   */
  async close(ms: number = CALLS.subagentsStopMs): Promise<RunRecord[]> {
    await Promise.race([
      Promise.allSettled([...this.pending]),
      new Promise((resolve) => setTimeout(resolve, ms).unref?.()),
    ]);
    this.closed = true;
    for (const [run, agent] of this.unfinished) {
      this.runs.push({ run, agent, status: "cancelled", messages: [] });
      this.options.emit(run, this.options.main, {
        type: "agent.failed",
        error: { kind: "cancelled", message: message("run.cancelled") },
      });
    }
    this.unfinished.clear();
    return [...this.runs];
  }

  /** A sub-agent's caps: its own limits, and done in time for the main agent to write its answer. */
  private capsFor(agentFile: AgentFile): Caps {
    const own = this.options.limits.agents[agentFile.name] ?? {};
    const ends = this.options.questionEnds;
    // Done before the main agent stops gathering (a quarter of its reserve earlier), so its report reaches the main agent.
    const reserve = questionReserve(this.options.limits);
    const left =
      ends === undefined ? undefined : Math.max(0, Math.floor(ends - reserve - reserve / 4 - Date.now()));
    const timeMs =
      own.timeMs === undefined ? left : left === undefined ? own.timeMs : Math.min(own.timeMs, left);
    return {
      steps: own.steps ?? agentFile.steps,
      ...(own.tokens !== undefined ? { tokens: own.tokens } : {}),
      ...(this.options.limits.question.tokens !== undefined
        ? { turnTokens: this.options.limits.question.tokens }
        : {}),
      ...(timeMs !== undefined ? { timeMs } : {}),
    };
  }

  private skillTool() {
    const { skills } = this.options;
    const names = skills.map((skill) => skill.name) as [string, ...string[]];
    return defineTool({
      name: "use_skill",
      description:
        "Load a skill: a method for a kind of request, which you then follow with your other tools. Its files " +
        "(references, assets) are listed with it; read one by giving its path as `file`. A long one comes in " +
        "parts: continue with the `from` its part names.",
      input: z.object({
        name: z.enum(names).describe("The skill"),
        file: z
          .string()
          .min(1)
          .max(SKILL_PATH_CHARS)
          .optional()
          .describe("One of the skill's files, by the path it lists"),
        from: z.number().int().min(0).default(0).describe("Where the previous part said to continue"),
      }),
      kind: "control",
      parallelSafe: true,
      run: async ({ name, file, from }) => {
        const skill = skills.find((item) => item.name === name) as Skill;
        const summary = message("tool.skill", { name: skill.name });
        const part = (tag: string, text: string, head: string[]) => {
          const end = Math.min(text.length, from + CALLS.textChars);
          const rest = end < text.length;
          return [
            `<${tag}>`,
            ...head,
            text.slice(from, end),
            ...(rest
              ? [`continue: use_skill with name=${name}${file ? `, file=${file}` : ""}, from=${end}`]
              : []),
            `</${tag.split(" ")[0]}>`,
          ].join("\n");
        };
        if (file !== undefined) {
          const text = skillFile(skill, file);
          if (text === undefined) {
            throw new ToolRefusalError(
              skill.files.length
                ? `${skill.name} has no file ${file}; its files are ${skill.files.join(", ")}.`
                : `${skill.name} has no files.`,
            );
          }
          return { text: part(`skill_file name="${skill.name}" path="${file}"`, text, []), summary };
        }
        // A skill loaded earlier in the turn is in the conversation already.
        if (from === 0 && this.loaded.has(name))
          return { text: message("tool.skillLoaded", { name }), summary };
        if (from === 0) this.loaded.add(name);
        const files = skill.files.length && from === 0 ? [`Files: ${skill.files.join(", ")}`, ""] : [];
        return { text: part(`skill_content name="${skill.name}"`, skill.body, files), summary };
      },
    });
  }

  private askTool() {
    return defineTool({
      name: ASK_TOOL,
      description: [
        "Ask the user up to three short questions, each with choices, when their answer changes what research is done and it can neither be assumed reasonably nor found with a lookup: which of several listings a name means, the horizon or position a question is about, which variant of a plan they want.",
        "Make a question precise before asking it (look up the listings a name could mean, so the choices are real ones).",
        "Asking ends your turn: the user sees each question with its choices and a field for an answer of their own, and their reply comes as their next message.",
        "One question is usually enough; put the choice you recommend first.",
      ].join(" "),
      input: z.object({
        questions: z
          .array(
            z.object({
              header: z
                .string()
                .trim()
                .min(1)
                .max(16)
                .describe("A label of a word or two, such as Instrument"),
              question: z.string().trim().min(1).max(300),
              options: z
                .array(
                  z.object({
                    label: z.string().trim().min(1).max(60).describe("The choice in one to five words"),
                    note: z.string().trim().max(120).optional().describe("What the choice means, briefly"),
                  }),
                )
                .min(2)
                .max(4),
            }),
          )
          .min(1)
          .max(3),
      }),
      kind: "control",
      parallelSafe: false,
      run: async ({ questions }) => {
        if (this.asked) throw new ToolRefusalError(message("tool.askedAlready"));
        this.asked = true;
        this.options.emit(this.options.main, undefined, { type: "question.asked", questions });
        return {
          text: message("tool.askShown"),
          summary: message("tool.asked", { count: questions.length }),
          ends: message("ask.questions", { questions }),
        };
      },
    });
  }

  private planTool() {
    return defineTool({
      name: "update_plan",
      description:
        "Show the user your plan for this request as a short list of steps, and update it as steps finish.",
      input: z.object({
        steps: z
          .array(
            z.object({
              text: z.string().trim().min(1).max(200),
              status: z.enum(["pending", "active", "done", "skipped"]),
            }),
          )
          .min(1)
          .max(12),
      }),
      kind: "control",
      parallelSafe: false,
      run: async ({ steps }) => {
        this.options.emit(this.options.main, undefined, { type: "plan.updated", steps });
        return { text: "Plan shown.", summary: message("tool.plan", { count: steps.length }) };
      },
    });
  }
}

/** Why a run that ended wrote no report: cut at the output limit, out of time at the wall, or empty. */
function noReportReason(outcome: AgentOutcome): "run.noReportCut" | "run.noReportTime" | "run.noReportEmpty" {
  if (outcome.finish === "length") return "run.noReportCut";
  if (outcome.finish === undefined) return "run.noReportTime";
  return "run.noReportEmpty";
}

function firstLine(text: string): string {
  const line = text.split("\n").find((l) => l.trim()) ?? "";
  const plain = line.replace(/[#*_`>]/g, "").trim();
  return plain.length > 120 ? `${plain.slice(0, 119)}…` : plain || message("app.reportWritten");
}

/**
 * At most `limit` tasks at a time; the rest wait in order. A finished task hands its permit straight
 * to the next waiter (nobody can slip in between), and a waiter whose signal aborts leaves the queue
 * without running.
 */
export class Semaphore {
  private active = 0;
  private readonly waiting: { start: () => void; cancel: () => void }[] = [];

  constructor(private readonly limit: number) {}

  async with<T>(task: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    if (signal?.aborted) throw new Error("cancelled");
    if (this.active < this.limit) this.active++;
    else {
      await new Promise<void>((resolve, reject) => {
        const waiter = {
          start: () => {
            signal?.removeEventListener("abort", waiter.cancel);
            resolve();
          },
          cancel: () => {
            this.waiting.splice(this.waiting.indexOf(waiter), 1);
            reject(new Error("cancelled"));
          },
        };
        this.waiting.push(waiter);
        signal?.addEventListener("abort", waiter.cancel, { once: true });
      });
    }
    try {
      return await task();
    } finally {
      const next = this.waiting.shift();
      if (next) next.start();
      else this.active--;
    }
  }
}
