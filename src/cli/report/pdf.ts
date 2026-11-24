// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * A report set as a PDF with PDFKit: a letterhead, the title, when and by what it was written, the question,
 * the answer (headings, paragraphs, lists, tables, code, quotes), then the numbered sources; each page's foot
 * names the product and its site in plain text (each a link), to read on paper too, with the page number.
 * The type is the figures' (Encode Sans Expanded, with JetBrains Mono for code and for any character the
 * text face lacks), embedded so the file reads the same everywhere. Calm on purpose: dark grey text on
 * white, the brand green only on the rules and the product's name.
 */
import PDFDocument from "pdfkit";
import { APP_TITLE, MAKER, message } from "../../contracts/index.js";
import { REPO, SITE } from "../links.js";
import fonts from "./fonts.generated.json" with { type: "json" };
import type { Part, Run } from "./layout.js";
import type { Report } from "./report.js";

const INK = "#1f2328";
const MUTED = "#6b7280";
/** Grey dark enough to read on paper, for the small type at each page's foot. */
const FOOT = "#4b5563";
const FAINT = "#e3e5e8";
const PANEL = "#f4f5f6";
const BRAND = "#14c290";
/** The brand green deep enough to read as text on white. */
const BRAND_TEXT = "#0b8a66";

const MARGIN = 64;
const BODY = 9.5;
const SMALL = 8;
const LINE_GAP = 2.5;
/** Space after a block, and how far a list item's text sits in from its mark. */
const AFTER = 7;
const INDENT = 14;
const HEADING = { 1: 15, 2: 12.5, 3: 11 } as Record<number, number>;

type Face = "regular" | "bold" | "mono";

/** Each page's foot, beside its number: the product and its site, each linking to its address. */
const FOOT_LINKS: { text: string; link?: string }[] = [
  { text: APP_TITLE, link: REPO.url },
  { text: " | " },
  { text: SITE.text, link: SITE.url },
];

/** The letterhead: the product and its maker, each linking to its address. */
const LETTERHEAD: { text: string; face: Face; color: string; link?: string }[] = [
  { text: APP_TITLE, face: "bold", color: BRAND_TEXT, link: REPO.url },
  { text: " by ", face: "regular", color: MUTED },
  { text: MAKER, face: "regular", color: MUTED, link: SITE.url },
];

/**
 * No ligatures: a ligature's glyph copies out of the PDF as other letters ("filing" as "fling"). Fontkit takes
 * features as tags to turn on or as an object of on and off, which PDFKit's types do not list.
 */
const FEATURES = { liga: false, clig: false } as unknown as PDFKit.Mixins.OpenTypeFeatures[];

/** Whether `ranges` (sorted, inclusive) hold `point`. */
function within(ranges: readonly (readonly number[])[], point: number): boolean {
  let low = 0;
  let high = ranges.length - 1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    const [first = 0, last = 0] = ranges[middle] ?? [];
    if (point < first) high = middle - 1;
    else if (point > last) low = middle + 1;
    else return true;
  }
  return false;
}

/** Whether the text face (both weights) has a glyph for `point`. */
const covered = (point: number) => within(fonts.covered, point);

/**
 * How many characters of `report` neither face can set (a script such as Chinese): they show as empty boxes,
 * which the export says.
 */
export function uncovered(report: Report): number {
  const texts = [
    report.title,
    report.question,
    report.earlier ?? "",
    ...report.sources,
    ...partTexts(report.parts),
  ];
  let count = 0;
  for (const text of texts)
    for (const char of text) {
      const point = char.codePointAt(0) ?? 0;
      if (!/\s/.test(char) && !covered(point) && !within(fonts.monoCovered, point)) count++;
    }
  return count;
}

function partTexts(parts: readonly Part[]): string[] {
  return parts.flatMap((part): string[] => {
    switch (part.kind) {
      case "heading":
      case "paragraph":
        return part.runs.map((run) => run.text);
      case "list":
        return part.items.flatMap(partTexts);
      case "table":
        return [...part.header, ...part.rows.flat()];
      case "code":
        return [part.text];
      case "quote":
        return partTexts(part.parts);
      default:
        return [];
    }
  });
}

/** `text` in `face`, split where the text face lacks a character: those stretches are set in the mono face. */
function faced(text: string, face: Face): { text: string; face: Face }[] {
  if (face === "mono") return [{ text, face }];
  const out: { text: string; face: Face }[] = [];
  for (const char of text) {
    const want: Face = char === "\n" || covered(char.codePointAt(0) ?? 0) ? face : "mono";
    const last = out.at(-1);
    if (last?.face === want) last.text += char;
    else out.push({ text: char, face: want });
  }
  return out;
}

/** The face a whole string can be set in: the mono face when the text face lacks any of it. */
function faceFor(text: string, face: Face): Face {
  return [...text].every((char) => covered(char.codePointAt(0) ?? 0)) ? face : "mono";
}

/** The report as PDF bytes. */
export async function reportPdf(report: Report): Promise<Uint8Array> {
  const doc = new PDFDocument({
    size: "LETTER",
    margin: MARGIN,
    bufferPages: true,
    font: null as unknown as string,
    info: {
      Title: report.title,
      Author: APP_TITLE,
      Creator: `${APP_TITLE} ${report.version}`,
      CreationDate: new Date(report.at),
    },
  });
  doc.registerFont("regular", Buffer.from(fonts.regular, "base64"));
  doc.registerFont("bold", Buffer.from(fonts.bold, "base64"));
  doc.registerFont("mono", Buffer.from(fonts.mono, "base64"));
  const chunks: Buffer[] = [];
  doc.on("data", (chunk: Buffer) => chunks.push(chunk));
  const ended = new Promise<void>((resolve, reject) => {
    doc.on("end", resolve);
    doc.on("error", reject);
  });

  const left = MARGIN;
  const width = doc.page.width - 2 * MARGIN;
  const bottom = () => doc.page.height - MARGIN;
  /** A new page when less than `height` is left on this one. */
  const room = (height: number) => {
    if (doc.y + height > bottom()) doc.addPage();
  };
  const rule = (y: number, color: string, thickness = 0.5) =>
    doc
      .save()
      .moveTo(left, y)
      .lineTo(left + width, y)
      .lineWidth(thickness)
      .strokeColor(color)
      .stroke()
      .restore();

  /** Runs set as one paragraph at `x`, `w` wide. */
  const paragraph = (runs: readonly Run[], x: number, w: number, size: number, color: string) => {
    const pieces = runs.flatMap((run) =>
      faced(run.text, run.code ? "mono" : run.bold ? "bold" : "regular").map((piece) => ({ run, ...piece })),
    );
    if (!pieces.length) return;
    doc.x = x;
    pieces.forEach(({ run, text, face }, index) => {
      doc
        .font(face)
        .fontSize(run.code || run.cite ? size - 1 : size)
        .fillColor(run.cite ? MUTED : run.link ? BRAND_TEXT : color);
      const options = {
        continued: index < pieces.length - 1,
        features: FEATURES,
        lineGap: LINE_GAP,
        ...(run.italic ? { oblique: 10 } : {}),
        ...(run.link ? { link: run.link, underline: true } : { link: null, underline: false }),
      };
      if (index === 0) doc.text(text, x, doc.y, { ...options, width: w });
      else doc.text(text, options);
    });
  };

  const table = (part: Extract<Part, { kind: "table" }>, x: number, w: number) => {
    const cell = (text: string, column: number, header: boolean) => ({
      text,
      font: { src: faceFor(text, header ? "bold" : "regular"), size: SMALL },
      align: { x: part.align[column] ?? "left", y: "top" as const },
      textOptions: { features: FEATURES },
    });
    doc.fillColor(INK);
    doc.table({
      position: { x, y: doc.y },
      maxWidth: w,
      defaultStyle: {
        border: { top: 0, left: 0, right: 0, bottom: 0.5 },
        borderColor: FAINT,
        padding: [3, 5],
        textColor: INK,
      },
      rowStyles: (row) =>
        row === 0 ? { backgroundColor: PANEL, border: { bottom: 0.8 }, borderColor: BRAND } : undefined,
      data: [
        part.header.map((text, column) => cell(text, column, true)),
        ...part.rows.map((row) => part.header.map((_, column) => cell(row[column] ?? "", column, false))),
      ],
    });
    doc.x = left;
  };

  const draw = (list: readonly Part[], x: number, w: number, color: string) => {
    for (const part of list) {
      switch (part.kind) {
        case "heading": {
          const size = HEADING[part.depth] ?? BODY + 0.5;
          // A heading keeps a few lines of what it heads on its page.
          room(size * 4);
          doc.moveDown(0.4);
          paragraph(
            part.runs.map((run) => ({ ...run, bold: true })),
            x,
            w,
            size,
            part.depth <= 2 ? INK : color,
          );
          doc.y += 3;
          break;
        }
        case "paragraph":
          paragraph(part.runs, x, w, BODY, color);
          doc.y += AFTER;
          break;
        case "list": {
          part.items.forEach((item, index) => {
            const mark = part.ordered ? `${part.start + index}.` : "•";
            room(BODY * 2);
            const top = doc.y;
            doc
              .font("regular")
              .fontSize(BODY)
              .fillColor(MUTED)
              .text(mark, x, top, { width: INDENT, lineBreak: false, features: FEATURES });
            doc.y = top;
            const [first, ...rest] = item;
            // An item's own text sits close to the next; a nested list or a second paragraph follows it.
            if (first?.kind === "paragraph") {
              paragraph(first.runs, x + INDENT, w - INDENT, BODY, color);
              doc.y += 3;
              draw(rest, x + INDENT, w - INDENT, color);
            } else draw(item, x + INDENT, w - INDENT, color);
          });
          doc.y += AFTER - 3;
          break;
        }
        case "table":
          room(SMALL * 6);
          table(part, x, w);
          doc.y += AFTER;
          break;
        case "code": {
          doc.font("mono").fontSize(SMALL);
          const height =
            doc.heightOfString(part.text, { width: w - 16, lineGap: 1.5, features: FEATURES }) + 12;
          // A block that fits on a page starts on one; a longer one starts here once a few lines fit.
          room(height <= bottom() - MARGIN ? height : SMALL * 8);
          const top = doc.y;
          // A block that fits gets its panel; a longer one runs on across pages without it.
          const fits = top + height <= bottom();
          if (fits) doc.save().rect(x, top, w, height).fill(PANEL).restore();
          doc
            .fillColor(INK)
            .text(part.text, x + 8, top + 6, { width: w - 16, lineGap: 1.5, features: FEATURES });
          doc.y = (fits ? top + height : doc.y) + AFTER;
          break;
        }
        case "quote": {
          const top = doc.y;
          draw(part.parts, x + 12, w - 12, MUTED);
          const end = doc.y - AFTER;
          if (end > top)
            doc
              .save()
              .rect(x, top, 2, end - top)
              .fill(FAINT)
              .restore();
          break;
        }
        case "rule":
          doc.y += 3;
          rule(doc.y, FAINT);
          doc.y += AFTER + 3;
          break;
      }
    }
  };

  // The letterhead, the title, and when and by what it was written.
  doc.fontSize(9);
  LETTERHEAD.forEach(({ text, face, color, link }, index) => {
    const options = { continued: index < LETTERHEAD.length - 1, lineBreak: false, features: FEATURES, link };
    doc.font(face).fillColor(color);
    if (index === 0) doc.text(text, left, MARGIN - 22, options);
    else doc.text(text, options);
  });
  rule(MARGIN - 6, BRAND, 1);
  doc.y = MARGIN + 8;
  paragraph([{ text: report.title, bold: true }], left, width, 19, INK);
  doc.y += 4;
  doc
    .font("regular")
    .fontSize(SMALL)
    .fillColor(MUTED)
    .text(
      [message("report.written", { at: report.at }), report.model, `${APP_TITLE} ${report.version}`]
        .filter(Boolean)
        .join("  |  "),
      left,
      doc.y,
      { width, features: FEATURES },
    );
  doc.y += 14;

  // The question (after the one before it, when that one's plan may be what it carries out), set off in a
  // panel; a question too long for a page runs on without the panel.
  const asked = [
    ...(report.earlier ? [{ label: message("report.earlier"), text: report.earlier }] : []),
    { label: message("report.question"), text: report.question },
  ].filter((entry) => entry.text);
  if (asked.length) {
    const inner = width - 28;
    const heights = asked.map(({ text }) => {
      doc.font("regular").fontSize(BODY);
      return doc.heightOfString(text, { width: inner, lineGap: LINE_GAP, features: FEATURES }) + 11;
    });
    const height = heights.reduce((sum, each) => sum + each, 0) + 6 * (asked.length - 1) + 19;
    const panel = height <= bottom() - MARGIN;
    if (panel) room(height);
    const top = doc.y;
    if (panel) doc.save().rect(left, top, width, height).fill(PANEL).restore();
    doc.y = top + 9;
    for (const { label, text } of asked) {
      doc
        .font("bold")
        .fontSize(6.5)
        .fillColor(MUTED)
        .text(label.toUpperCase(), left + 14, doc.y, {
          characterSpacing: 1,
          lineBreak: false,
          features: FEATURES,
        });
      doc.y += 11;
      paragraph([{ text }], left + 14, inner, BODY, INK);
      doc.y += 6;
    }
    doc.y = (panel ? top + height : doc.y) + 16;
  }

  draw(report.parts, left, width, INK);

  if (report.sources.length) {
    room(SMALL * 6);
    doc.y += 6;
    rule(doc.y, FAINT);
    doc.y += 10;
    doc
      .font("bold")
      .fontSize(10)
      .fillColor(INK)
      .text(message("report.sources"), left, doc.y, { width, features: FEATURES });
    doc.y += 4;
    for (const line of report.sources) {
      paragraph([{ text: line }], left, width, SMALL, MUTED);
      doc.y += 1;
    }
  }

  // Each page's foot: the product and its site, and the page of how many.
  const { start, count } = doc.bufferedPageRange();
  for (let page = start; page < start + count; page++) {
    doc.switchToPage(page);
    const foot = doc.page.height - MARGIN + 22;
    const margins = doc.page.margins;
    doc.page.margins = { ...margins, bottom: 0 };
    rule(foot - 7, FAINT);
    doc.font("regular").fontSize(7.5).fillColor(FOOT);
    FOOT_LINKS.forEach(({ text, link }, index) => {
      const options = {
        continued: index < FOOT_LINKS.length - 1,
        lineBreak: false,
        features: FEATURES,
        link,
      };
      if (index === 0) doc.text(text, left, foot, options);
      else doc.text(text, options);
    });
    const pageText = message("report.page", { page: page - start + 1, count });
    doc.text(pageText, left + width - doc.widthOfString(pageText, { features: FEATURES }), foot, {
      lineBreak: false,
      features: FEATURES,
    });
    doc.page.margins = margins;
  }
  doc.end();
  await ended;
  return new Uint8Array(Buffer.concat(chunks));
}
