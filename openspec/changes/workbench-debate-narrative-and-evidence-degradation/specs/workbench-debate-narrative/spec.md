## ADDED Requirements

### Requirement: The workflow map shows stages, edges, and direction

The workbench SHALL present the multi-agent pipeline as a directed flow of
grouped stages, not as an unconnected grid of role cards. The map SHALL make
visible:

- stage grouping, with each of the six stages (analysts, evidence, research,
  trading, risk, portfolio) rendered as a labelled container holding its roles;
- the handoff edges between consecutive stages, drawn with an explicit direction
  indicator;
- the adversarial edge inside the research stage between the bull and bear
  roles, and inside the risk stage among the three risk roles, distinguished
  from handoff edges;
- the convergence edge from each debate stage into its judging role.

Every role in the registry SHALL occupy exactly one position in the map,
including when no run is selected.

#### Scenario: No run selected

- **WHEN** the workbench is opened with no run selected
- **THEN** the map renders all registry roles grouped into their six stages
- **AND** the stage-to-stage edges are present

#### Scenario: Stage grouping is labelled

- **WHEN** the map is rendered
- **THEN** each stage container carries its stage label

#### Scenario: Adversarial edge is distinguishable

- **WHEN** the research stage is rendered
- **THEN** the bull-to-bear relationship is rendered as an edge distinct in
  presentation from a stage handoff edge

### Requirement: The workflow map reflects live run progress

When a run is selected, the map SHALL derive every role's displayed state from
run state, distinguishing at minimum: not yet reached, running, completed,
failed, and skipped-because-not-selected. The stage or edge currently carrying
execution SHALL be visually marked as active.

The map SHALL NOT display a role as running when run state reports it terminal,
and SHALL NOT fabricate progress for roles absent from run state.

#### Scenario: A role is executing

- **WHEN** run state reports a role's latest turn as started
- **THEN** that role renders in the running state
- **AND** its stage renders as the active stage

#### Scenario: An analyst was not selected for the run

- **WHEN** run state reports a role status of skipped
- **THEN** that role renders as not selected, distinct from both pending and
  completed

#### Scenario: Run completes

- **WHEN** run state reports every reached role terminal
- **THEN** no role renders in the running state

### Requirement: Debate turns are grouped by round with round progress visible

The transcript SHALL group opposing turns into rounds using the turn index
carried in run state, and SHALL render an explicit boundary between rounds. The
configured round budget for the stage (`max_debate_rounds` for research,
`max_risk_discuss_rounds` for risk) SHALL be visible alongside the rounds
elapsed.

Round grouping SHALL be derived from run state, never from arrival order alone.

#### Scenario: Two-round research debate

- **WHEN** run state contains bull and bear turns at turn index 1 and 2 and the
  run's `max_debate_rounds` is 2
- **THEN** the transcript renders two round groups
- **AND** the round budget of 2 is visible

#### Scenario: Debate in progress on round 1 of 3

- **WHEN** only round 1 turns exist and `max_debate_rounds` is 3
- **THEN** the transcript shows round 1 as current and the budget as 3

### Requirement: Opposing roles are rendered in opposed lanes

Turns from roles in an adversarial relationship SHALL be laid out in distinct
lanes rather than a single shared column, so that opposition is readable from
layout. The research debate SHALL use two lanes (bull, bear). The risk debate
SHALL use three lanes (aggressive, neutral, conservative).

Lane assignment SHALL be derived from the role registry, not from per-turn
heuristics.

#### Scenario: Bull and bear turns in the same round

- **WHEN** a round contains one bull turn and one bear turn
- **THEN** the two turns render in different lanes

#### Scenario: Three-way risk debate

- **WHEN** a risk round contains aggressive, neutral, and conservative turns
- **THEN** each renders in its own lane

#### Scenario: Non-adversarial turn

- **WHEN** an analyst turn is rendered
- **THEN** it is not assigned to an opposed lane

### Requirement: A lane never presents another role's speech as its own

Lane-based rendering presumes one turn carries one speaker. Turn bodies recorded
before this change violate that premise and are never rewritten, so the debate
view SHALL defend against it at render time.

Where a turn body carries an attribution naming a participant other than the
authoring role, the view SHALL NOT present that foreign speech as the authoring
role's own words, and SHALL mark the turn as containing foreign attribution
rather than silently removing it. Surfacing the defect is required: this
workbench exists to make agent behavior auditable, and a silent repair would hide
the defect from the reader best placed to act on it.

The constraint on what agents may author is specified separately under
`debate-turn-authorship`.

#### Scenario: Historical bull turn containing bear argument

- **WHEN** a bull researcher's turn body opens with moderator narration and bear
  argument before its own argument
- **THEN** the bull lane does not present the bear's argument as the bull's
- **AND** the turn is marked as containing foreign attribution

#### Scenario: Well-formed adversarial turn

- **WHEN** a debate role's turn body contains only its own argument
- **THEN** it renders in that role's lane in full
- **AND** it carries no foreign-attribution marking

#### Scenario: Redundant self-label is not shown twice

- **WHEN** a turn body opens with its own role's speaker label
- **THEN** the lane does not display that label in addition to the role identity
  it already shows

### Requirement: Judging turns are rendered as convergence points

A turn produced by a judging role (research manager, portfolio manager) SHALL be
rendered as a full-width convergence element that terminates the round group it
resolves, visually distinct from the opposed lanes above it.

#### Scenario: Research manager verdict after debate rounds

- **WHEN** the research manager produces a verdict turn following bull and bear
  rounds
- **THEN** that turn renders full-width beneath the final round group
- **AND** it is presented distinctly from lane turns

#### Scenario: Portfolio manager final decision

- **WHEN** the portfolio manager produces the final decision turn
- **THEN** it renders as the terminal convergence element of the transcript

### Requirement: Candidate and committed turns are distinguishable

The transcript SHALL distinguish a turn whose output exists but has not been
committed to the graph checkpoint from a turn that is committed, and SHALL label
the uncommitted state explicitly.

#### Scenario: Output ready but not committed

- **WHEN** run state reports a turn with output ready and no commit
- **THEN** the transcript marks that turn as a candidate

#### Scenario: Turn committed

- **WHEN** run state reports the turn as completed
- **THEN** the candidate marking is absent

### Requirement: Selecting a turn drives the inspector

Selecting a turn in the transcript, or a role in the workflow map, SHALL set the
inspector's scope to the corresponding turn. Selecting a role whose latest turn
is unknown SHALL leave the current inspector scope unchanged rather than clearing
it.

#### Scenario: Turn selected from the transcript

- **WHEN** a user selects a transcript turn
- **THEN** the inspector scope becomes that turn

#### Scenario: Role selected from the map

- **WHEN** a user selects a role with a known latest turn
- **THEN** the inspector scope becomes that turn

#### Scenario: Role with no turns selected

- **WHEN** a user selects a role that has produced no turns
- **THEN** the inspector scope is unchanged
