## ADDED Requirements

### Requirement: Agent-authored markdown is parsed and rendered as formatted prose

The workbench SHALL parse agent-authored markdown into semantic HTML elements
(headings, paragraphs, ordered and unordered lists, tables, blockquotes, inline
and fenced code, links, emphasis) before display. Rendering agent reports as
unparsed preformatted text is prohibited.

GitHub-flavored markdown extensions SHALL be supported, at minimum tables,
strikethrough, and task lists, because agent report templates use them.

#### Scenario: Report containing headings and lists

- **WHEN** an agent report whose text contains `## 技术面`, a bulleted list, and a
  markdown table is displayed in the workbench
- **THEN** the rendered output contains a heading element, a list element with
  one list item per source bullet, and a table element with header and body rows
- **AND** no element in the rendered subtree presents that content as
  preformatted monospace text

#### Scenario: Report containing a markdown table with pipe alignment row

- **WHEN** a report contains a GFM table using `|---|:--:|` alignment syntax
- **THEN** the alignment row is consumed as table formatting and is not rendered
  as literal text

### Requirement: Rendered markdown is sanitized against active content

All markdown rendering SHALL pass through a sanitizing transform that strips
script elements, event-handler attributes, and non-http(s) URI schemes before
the content reaches the DOM. Raw HTML embedded in agent output SHALL NOT be
executed.

Sanitization SHALL be applied in the render pipeline itself, not by pre-escaping
the source text, so that markdown syntax remains parseable while embedded markup
remains inert.

#### Scenario: Report containing a script tag

- **WHEN** report text contains `<script>alert(1)</script>`
- **THEN** no script element exists in the rendered subtree
- **AND** no script executes

#### Scenario: Report containing an event handler attribute

- **WHEN** report text contains `<img src=x onerror="alert(1)">`
- **THEN** the rendered output contains no `onerror` attribute

#### Scenario: Report containing a javascript: link

- **WHEN** report text contains a markdown link whose target is a
  `javascript:` URI
- **THEN** the rendered anchor does not carry that URI as its href

### Requirement: Prose and machine payloads use distinct render modes

The workbench SHALL provide exactly two long-form render modes and SHALL NOT mix
them:

- **prose mode**, for LLM-authored narrative (analyst reports, debate turns,
  manager verdicts, final decisions): body text at a comfortable reading size,
  line height suited to sustained reading, a visible heading scale, and a
  constrained measure so that lines do not span the full panel width.
- **data mode**, for machine payloads (prompt snapshots, JSON artifacts, vendor
  raw values, tool arguments): monospace, whitespace-preserving, with the
  original bytes recoverable.

Prose mode SHALL NOT use monospace type for body text. Data mode SHALL NOT parse
its content as markdown.

#### Scenario: Debate turn body

- **WHEN** a debate turn's response text is displayed
- **THEN** it renders in prose mode

#### Scenario: Prompt snapshot artifact

- **WHEN** a `prompt_snapshot` artifact is displayed
- **THEN** it renders in data mode with whitespace preserved
- **AND** its content is not interpreted as markdown

#### Scenario: JSON artifact payload

- **WHEN** an artifact whose content is JSON is displayed
- **THEN** it renders in data mode

### Requirement: Every long-form text surface uses a shared renderer

Every workbench surface that displays multi-paragraph text SHALL render it
through the shared renderer in the mode appropriate to its content type. No
surface may render long-form text with an ad-hoc element.

The surfaces in scope are: the debate transcript turn body, the artifact content
viewer, and the prompt snapshot viewer.

#### Scenario: Artifact viewer renders a markdown report artifact

- **WHEN** a user opens an artifact whose kind denotes an agent report
- **THEN** its content renders through the shared renderer in prose mode

#### Scenario: No surface bypasses the shared renderer

- **WHEN** the frontend source is inspected for long-form text surfaces
- **THEN** each such surface delegates to the shared renderer
- **AND** the shared renderer is referenced by production code, not only by tests

### Requirement: Debate turn content is visible without interaction

A debate turn's response text SHALL be presented on arrival, without requiring
the user to click the turn to reveal it. Where a turn's text exceeds a display
budget, the surface SHALL show a leading excerpt and offer expansion to full
text; it SHALL NOT show a bare interaction prompt in place of content.

#### Scenario: Turn arrives with an available artifact

- **WHEN** a turn reaches a status carrying a response artifact
- **THEN** the transcript shows that turn's text or a leading excerpt of it
- **AND** the turn body does not read only as an instruction to click

#### Scenario: Turn is still in progress

- **WHEN** a turn has started but produced no response artifact
- **THEN** the transcript shows an in-progress indicator for that turn
