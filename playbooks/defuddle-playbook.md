# Defuddle Playbook

**Defuddle** — Extract the main content of any page as Markdown.
By [kepano](https://github.com/kepano/defuddle). MIT license.

> de·fud·dle /diˈfʌdl/ — *to remove unnecessary elements from a web page, and make it easily readable.*

---

## What It Is

Defuddle is a content extraction library (alternative to Mozilla Readability).
It takes a URL or HTML and returns cleaned Markdown with rich metadata:
title, author, description, image, published date, favicon, schema.org data.

**Why over readability.js:**
- More forgiving — removes fewer uncertain elements
- Better metadata extraction (schema.org, OpenGraph)
- Standardized output for footnotes, math, code blocks, callouts
- Mobile-style guessing for unnecessary elements

---

## Quick Reference

### CLI (no install needed)

```bash
# URL → Markdown
npx defuddle parse https://example.com/article --markdown

# URL → JSON (full metadata)
npx defuddle parse https://example.com/article --json

# Local HTML file
npx defuddle parse page.html --markdown

# Extract single property
npx defuddle parse https://example.com/article --property title

# Save to file
npx defuddle parse https://example.com/article --markdown -o article.md
```

### Web API (defuddle.md)

```bash
# Append any URL path to get Markdown with YAML frontmatter
curl defuddle.md/https://example.com/article
```

This is a hosted service — runs locally in the browser extension but also
available as a public endpoint. Useful when you don't want to install anything.

### Node.js

```bash
npm install defuddle linkedom
```

```typescript
import { parseHTML } from "linkedom";
import { Defuddle } from "defuddle/node";

const { document } = parseHTML(html);
const result = await Defuddle(document, url, { markdown: true });

console.log(result.title);      // "Article Title"
console.log(result.author);     // "Jane Doe"
console.log(result.content);    // Clean markdown
console.log(result.image);      // Main image URL
console.log(result.published);  // "2026-01-15"
console.log(result.wordCount);  // 1234
```

---

## Response Object

| Property | Type | Description |
|----------|------|-------------|
| `content` | string | Cleaned HTML or Markdown |
| `title` | string | Article title |
| `author` | string | Author name |
| `description` | string | Page description/summary |
| `image` | string | Main image URL |
| `favicon` | string | Site favicon URL |
| `domain` | string | Domain name |
| `published` | string | Publication date |
| `language` | string | BCP 47 language tag |
| `site` | string | Site name |
| `wordCount` | number | Word count |
| `parseTime` | number | Parse time in ms |
| `schemaOrgData` | object | Raw schema.org data |
| `metaTags` | object | All meta tags |

---

## Key Options

| Option | Default | Purpose |
|--------|---------|---------|
| `markdown` | false | Convert content to Markdown |
| `separateMarkdown` | false | Keep `content` as HTML, add `contentMarkdown` |
| `contentSelector` | — | CSS selector to force content area |
| `removeHiddenElements` | true | Remove display:none / visibility:hidden |
| `removeLowScoring` | true | Remove non-content blocks by scoring |
| `removeSmallImages` | true | Remove icons, tracking pixels |
| `useAsync` | true | Allow third-party API fallback for SPAs |
| `debug` | false | Return debug info (selectors, removals) |

---

## Usage in This Project

### Research Pipeline

Use defuddle to convert research articles, blog posts, and news into
clean Markdown before feeding to analyst agents:

```bash
# In scripts or just recipes
defuddle_to_markdown() {
    npx defuddle parse "$1" --markdown
}
```

### SPA / JS-rendered Pages

Defuddle's `useAsync: true` (default) fetches from third-party APIs
when no server-rendered content is found (e.g., Twitter/X via FxTwitter API).
Set `useAsync: false` to disable this fallback.

### Forcing Content Area

If auto-detection picks the wrong content, use `contentSelector`:

```typescript
const result = await Defuddle(document, url, {
    markdown: true,
    contentSelector: "article.post-content"
});
```

---

## Caveats

- **Active development** — API may change between minor versions (0.18 as of Apr 2026)
- **Requires DOM implementation** in Node.js — `linkedom` (recommended) or `jsdom`
- **Module format** — `package.json` must have `"type": "module"` for `defuddle/node`
- **SPA fallback** uses external APIs (FxTwitter) — may have rate limits
