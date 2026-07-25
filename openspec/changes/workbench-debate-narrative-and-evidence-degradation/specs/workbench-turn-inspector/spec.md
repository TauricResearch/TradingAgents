## ADDED Requirements

### Requirement: The inspector has a single scope: the selected turn

The inspector SHALL answer exactly one question — how the currently selected
statement came to be — and SHALL therefore be scoped to exactly one turn at a
time. Every section the inspector renders SHALL describe that turn.

Run-scoped information SHALL NOT appear inside the inspector. Specifically, the
run input snapshot and the run's full artifact list SHALL be presented outside
the inspector, reachable from the run header.

#### Scenario: Switching the selected turn

- **WHEN** the user selects a different turn
- **THEN** every section of the inspector updates to describe the newly selected
  turn
- **AND** no section retains content from the previous turn

#### Scenario: Run input is requested

- **WHEN** the user wants to review the immutable run input snapshot
- **THEN** it is reachable from the run header
- **AND** it is not a section of the inspector

#### Scenario: No turn selected

- **WHEN** no turn is selected
- **THEN** the inspector shows a single empty state explaining how to select a
  turn

### Requirement: The inspector is a flat sequence of collapsible sections

The inspector SHALL present its content as a single flat sequence of labelled
sections in a fixed order. Nested tab hierarchies are prohibited: no section may
itself contain a tab strip.

The section order SHALL be:

1. **identity** — which role, which round, turn status, duration, and the model
   that produced it;
2. **evidence** — everything the turn read;
3. **prompt** — the prompt snapshot, collapsed by default;
4. **output** — what the turn wrote.

Sections whose content is bulky SHALL be collapsible. The identity section SHALL
always be expanded.

#### Scenario: Inspector structure

- **WHEN** the inspector renders a selected turn
- **THEN** the four sections appear in the specified order
- **AND** no section contains a nested tab strip

#### Scenario: Prompt section default state

- **WHEN** the inspector first renders a turn
- **THEN** the prompt section is collapsed

#### Scenario: Identity section is always visible

- **WHEN** the inspector renders a turn
- **THEN** the identity section content is visible without expansion

### Requirement: Every inspector view is reachable with real content

No inspector view may filter on a capture kind the backend does not emit. Each
view the inspector presents SHALL correspond to a capture kind that the
observability layer actually produces, verified against emitted events rather
than against the type contract alone.

Where a view has no producer, it SHALL be removed rather than left rendering a
permanent empty state.

#### Scenario: View filtered on a never-emitted capture kind

- **WHEN** the inspector's view set is compared against the capture kinds the
  observability layer emits
- **THEN** every view maps to an emitted capture kind

#### Scenario: Completed turn with recorded inputs

- **WHEN** a fully completed turn with recorded state and prompt captures is
  selected
- **THEN** the inspector's default view shows content rather than an empty state

### Requirement: Upstream material is rendered as content, not envelope keys

When an input capture's payload wraps the material in an envelope, the inspector
SHALL render the material itself, not the envelope's top-level key names. Field
identifiers such as the actor id, node id, projection version, and nested
artifact references are provenance, not upstream material, and SHALL NOT be
presented as the upstream view's content.

Each upstream field SHALL be presented with its name and its value, with
long-form values rendered through the shared prose renderer.

#### Scenario: State capture wrapping fields in an envelope

- **WHEN** a state capture's payload nests the upstream fields one level below
  the envelope's top-level keys
- **THEN** the upstream view lists the nested field names, not the envelope keys

#### Scenario: Upstream field holding a full report

- **WHEN** an upstream field's value is a multi-paragraph report
- **THEN** its content is reachable in the upstream view and rendered as prose

#### Scenario: Provenance identifiers

- **WHEN** the capture envelope carries actor, node, or projection identifiers
- **THEN** those appear as provenance metadata, not as the upstream material list

### Requirement: The evidence section unifies everything the turn read

The evidence section SHALL merge, in one section, all inputs the turn consumed,
regardless of which backend event carried them:

- upstream state fields the turn read (from state snapshots);
- resolved data fields supplied to the turn (from data snapshots);
- tool calls the turn issued, each with its name, status, and outcome;
- vendor provenance for those calls, including vendor identity, content hash, and
  locator;
- the effective configuration values that governed the turn.

Splitting these across separate top-level destinations is prohibited: they answer
one question and SHALL be co-located.

#### Scenario: Turn with both upstream state and tool calls

- **WHEN** a turn read upstream reports and issued two tool calls
- **THEN** both the upstream fields and both tool calls appear within the single
  evidence section

#### Scenario: Turn with vendor-backed data

- **WHEN** a turn consumed data fetched from an external vendor
- **THEN** the evidence section shows the vendor identity, the content hash, and
  the locator for that data

#### Scenario: Turn that issued no tool calls

- **WHEN** a turn issued no tool calls
- **THEN** the evidence section states that explicitly rather than omitting the
  subsection silently

### Requirement: The identity section reports execution facts from run state

The identity section SHALL show the role's display name, the round the turn
belongs to, the turn status, the observed duration where run state provides one,
and the provider and model of the model call that produced it.

Values absent from run state SHALL be rendered as explicitly unavailable. The
inspector SHALL NOT substitute defaults or estimates for missing execution facts.

#### Scenario: Completed turn with a recorded duration

- **WHEN** run state reports a duration for the turn
- **THEN** the identity section shows that duration

#### Scenario: Turn with no recorded duration

- **WHEN** run state reports no duration
- **THEN** the identity section marks duration unavailable rather than showing
  zero

#### Scenario: Model attribution

- **WHEN** run state contains a model call for the turn
- **THEN** the identity section shows that call's provider and model

### Requirement: Run-scoped surfaces are reachable from the run header

The run header SHALL provide access to run-scoped information: the immutable run
input snapshot and the run's full artifact list. These surfaces SHALL remain
available regardless of which turn is selected, and selecting a turn SHALL NOT
alter them.

#### Scenario: Artifact list opened while a turn is selected

- **WHEN** the user opens the run artifact list with a turn selected
- **THEN** the full run artifact list is shown
- **AND** the inspector's turn scope is unchanged

#### Scenario: Run input remains stable across turn selection

- **WHEN** the user selects different turns
- **THEN** the run input snapshot content does not change
