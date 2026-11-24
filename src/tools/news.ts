// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** News about a company or a theme. */
import { z } from "zod";
import { isCalendarDate, message } from "../contracts/index.js";
import {
  NEWS_EVENT_TYPES,
  NEWS_IMPACTS,
  NEWS_SENTIMENTS,
  NEWS_TOPICS,
  type News,
} from "../data/capabilities.js";
import { hint } from "./preview.js";
import { referenceTo } from "./references.js";
import { defineTool } from "./tool.js";
import { indented, oneLine, provenanceOf, roomIn, shownOf, symbol } from "./tool-text.js";

/** A date or a UTC time; a date alone means the start of that day, or its end when it ends a range. */
const instantAt = (edge: "start" | "end") =>
  z
    .string()
    .regex(
      /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z)?$/,
      "a date YYYY-MM-DD or a UTC time YYYY-MM-DDTHH:MM:SSZ",
    )
    .refine((value) => isCalendarDate(value.slice(0, 10)), "a date on the calendar")
    .transform((value) =>
      value.length === 10 ? `${value}${edge === "start" ? "T00:00:00Z" : "T23:59:59.999Z"}` : value,
    );

const ARTICLE = z.object({
  id: z.string(),
  published_at: z.string().nullable(),
  publisher: z.string().nullable(),
  title: z.string().nullable(),
  sentiment: z.string().nullable(),
  impact: z.string().nullable(),
  summary: z.string().nullable(),
  url: z.string().nullable(),
});
const OUT = z.object({
  symbol: z.string().optional(),
  query: z.string().optional(),
  until: z.string().optional(),
  articles: z.array(ARTICLE),
  next_cursor: z.string().nullable(),
});

export function newsTool(news: News) {
  return defineTool({
    name: "news",
    description:
      "News articles, newest first: the market's latest (no symbol or query), about one company (symbol), matching a " +
      "question (query), narrowed by topic, event type, tone or expected impact. Each has its id, publisher, time, " +
      "link, a short summary, and its tone and impact; article reads one in full. Page with `after`.",
    kind: "data",
    parallelSafe: true,
    input: z.object({
      symbol: symbol.optional(),
      query: z
        .string()
        .trim()
        .min(3)
        .max(300)
        .optional()
        .describe("What the articles should be about, in words"),
      since: instantAt("start").optional(),
      until: instantAt("end").optional(),
      topic: z.enum(NEWS_TOPICS).optional().describe("Only articles on this topic"),
      event_type: z
        .enum(NEWS_EVENT_TYPES)
        .optional()
        .describe("Only articles reporting an event of this type"),
      sentiment: z.enum(NEWS_SENTIMENTS).optional(),
      impact: z.enum(NEWS_IMPACTS).optional().describe("Only articles of this expected market impact"),
      limit: z.number().int().min(1).max(10).default(8),
      after: z
        .string()
        .min(1)
        .optional()
        .describe("The cursor a previous call returned, with the same filters"),
    }),
    output: OUT,
    // Under its count: the newest articles, each its day, publisher and headline.
    preview: [hint(OUT, { list: "articles", fields: ["published_at", "publisher", "title"] })],
    async run(
      { symbol, query, since, until, limit, after, topic, event_type, sentiment, impact },
      { signal },
    ) {
      const sourced = await news.articles(
        {
          limit,
          ...(topic ? { topic } : {}),
          ...(event_type ? { eventType: event_type } : {}),
          ...(sentiment ? { sentiment } : {}),
          ...(impact ? { impact } : {}),
          ...(symbol ? { symbol } : {}),
          ...(query ? { query } : {}),
          ...(since ? { since } : {}),
          ...(until ? { until } : {}),
          ...(after ? { after } : {}),
        },
        { signal },
      );
      const articles = sourced.data.articles.map((article) => ({
        id: article.id,
        published_at: article.published_at ?? null,
        publisher: article.publisher ?? null,
        title: article.title ?? null,
        sentiment: article.annotations?.sentiment ?? null,
        impact: article.annotations?.impact ?? null,
        summary: article.annotations?.summary ?? null,
        url: article.url ?? null,
      }));
      const cursor = sourced.data.next_cursor ?? null;
      return {
        payload: {
          ...(symbol ? { symbol } : {}),
          ...(query ? { query } : {}),
          ...(until ? { until } : {}),
          articles,
          next_cursor: cursor,
        },
        provenance: provenanceOf(sourced, { subject: symbol }),
        summary: message("tool.articles", {
          count: articles.length,
          ...(symbol ? { symbol } : {}),
          more: Boolean(cursor),
        }),
      };
    },
    render({ symbol, query, until, articles, next_cursor }, { id, room }) {
      const head = [
        `${articles.length} article${articles.length === 1 ? "" : "s"} on this page${symbol ? ` about ${symbol}` : ""}${query ? ` on "${query}"` : ""}${until ? ` up to ${until}` : ""}`,
      ];
      const rows = articles.map((article) => {
        const tone = [article.sentiment, article.impact && `${article.impact} impact`]
          .filter(Boolean)
          .join(", ");
        return [
          `${article.published_at ?? "undated"} ${oneLine(article.publisher ?? "unknown publisher")}: ${oneLine(article.title ?? "untitled")}${tone ? ` (${oneLine(tone)})` : ""} [article ${article.id}]`,
          ...(article.summary ? [indented(article.summary)] : []),
          ...(article.url ? [`  ${oneLine(article.url)}`] : []),
        ].join("\n");
      });
      const next = next_cursor ? [`more: news with after=${next_cursor} and the same filters`] : [];
      return [
        ...head,
        ...shownOf(rows, roomIn(room, head, next), id ? referenceTo(id, "articles") : undefined),
        ...next,
      ];
    },
  });
}

const DETAIL = z.object({
  id: z.string(),
  title: z.string().nullable(),
  publisher: z.string().nullable(),
  url: z.string().nullable(),
  published_at: z.string().nullable(),
  /** What the time is: published, or failing a stated publication time, when it was listed or obtained. */
  time_kind: z.string().nullable(),
  available_at: z.string().nullable(),
  sentiment: z.string().nullable(),
  impact: z.string().nullable(),
  summary: z.string().nullable(),
  topics: z.array(z.string()),
  instruments: z.array(z.string()),
  events: z.array(
    z.object({
      event_type: z.string(),
      headline: z.string().nullable(),
      date_stated: z.string().nullable(),
      instruments: z.array(z.string()),
    }),
  ),
  figures: z.array(
    z.object({
      metric: z.string().nullable(),
      value: z.string().nullable(),
      period: z.string().nullable(),
      instruments: z.array(z.string()),
    }),
  ),
  quotations: z.array(z.object({ speaker: z.string().nullable(), text: z.string().nullable() })),
});

export function articleTool(news: News) {
  return defineTool({
    name: "article",
    description:
      "One news article by its id (as news lists it): its main points, the events it reports, the figures it states " +
      "and who it quotes, each as the article words it.",
    kind: "data",
    parallelSafe: true,
    input: z.object({ id: z.string().trim().min(1).max(80).describe("The article's id, such as art_1GOZ") }),
    output: DETAIL,
    label: ({ id }, article) => article?.title ?? id,
    // Under its id: the article's day, publisher and headline, as news lists them.
    preview: [hint(DETAIL, { record: ["published_at", "publisher", "title"], replacesSummary: true })],
    async run({ id }, { signal }) {
      const sourced = await news.article(id, { signal });
      const a = sourced.data;
      return {
        payload: {
          id: a.id,
          title: a.title ?? null,
          publisher: a.publisher ?? null,
          url: a.url ?? null,
          published_at: a.published_at ?? null,
          time_kind: a.time_kind,
          available_at: a.available_at,
          sentiment: a.annotations?.sentiment ?? null,
          impact: a.annotations?.impact ?? null,
          summary: a.annotations?.summary ?? null,
          topics: a.topics,
          instruments: a.instruments,
          events: a.events.map((event) => ({
            event_type: event.event_type,
            headline: event.headline,
            date_stated: event.date_stated ?? null,
            instruments: event.instruments,
          })),
          figures: a.figures.map((figure) => ({
            metric: figure.metric,
            value: figure.value_stated,
            period: figure.period_stated ?? null,
            instruments: figure.instruments,
          })),
          quotations: a.quotations,
        },
        provenance: provenanceOf(sourced, { subject: a.id }),
        summary: oneLine(a.title ?? id),
      };
    },
    render(a, { id, room }) {
      const head = [
        `${a.published_at ?? "undated"}${a.time_kind && a.time_kind !== "published" ? ` (${a.time_kind}, no publication time stated)` : ""} ${oneLine(a.publisher ?? "unknown publisher")}: ${oneLine(a.title ?? "untitled")}`,
        ...(a.url ? [oneLine(a.url)] : []),
        `tone ${a.sentiment ?? "not stated"}, expected impact ${a.impact ?? "not stated"}${a.topics.length ? `; topics ${a.topics.join(", ")}` : ""}${a.instruments.length ? `; about ${a.instruments.join(", ")}` : ""}`,
        ...(a.summary ? ["points:", indented(a.summary)] : []),
      ];
      const rows = [
        ...a.events.map(
          (e) =>
            `event (${e.event_type}): ${oneLine(e.headline ?? "")}${e.date_stated ? `, dated "${oneLine(e.date_stated)}"` : ""}${about(e.instruments)}`,
        ),
        ...a.figures.map(
          (f) =>
            `figure: ${oneLine(f.metric ?? "?")} ${oneLine(f.value ?? "?")}${f.period ? ` (${oneLine(f.period)})` : ""}${about(f.instruments)}`,
        ),
        ...a.quotations.map((q) => `quote: ${oneLine(q.speaker ?? "unnamed")}: "${oneLine(q.text ?? "")}"`),
      ];
      return [...head, ...shownOf(rows, roomIn(room, head), id ? referenceTo(id) : undefined)];
    },
  });
}

/** Which instruments an item is about, when the article says. */
function about(instruments: readonly string[]): string {
  return instruments.length ? ` [about ${instruments.join(", ")}]` : "";
}
