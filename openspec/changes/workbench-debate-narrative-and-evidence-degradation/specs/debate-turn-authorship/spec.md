## ADDED Requirements

### Requirement: A debate agent authors only its own speech

An adversarial debate role (bull researcher, bear researcher, aggressive risk
analyst, conservative risk analyst, neutral risk analyst) SHALL produce output
containing only its own argument. It SHALL NOT author narration, questions, or
argument attributed to any other participant.

The prompt SHALL NOT place the role in a staged panel that implies other speakers
take turns inside its output. Instruction text SHALL address the role as the sole
author of the response.

#### Scenario: Bull researcher output

- **WHEN** the bull researcher produces a turn
- **THEN** the output contains only the bull's own argument
- **AND** it contains no argument attributed to the bear
- **AND** it contains no moderator narration

#### Scenario: Risk debator output

- **WHEN** any of the three risk debators produces a turn
- **THEN** the output contains only that debator's own argument

#### Scenario: Detecting a violation

- **WHEN** a debate role's turn output is scanned for attributions naming another
  participant
- **THEN** any such attribution is reported as a defect rather than accepted

### Requirement: A rebuttal is requested only when there is something to rebut

A debate prompt SHALL request a rebuttal only when the opposing side's argument
is actually present in the state passed to it. On an opening turn, where no
opposing argument exists, the prompt SHALL request an opening case and SHALL NOT
instruct the role to refute, address, or counter the other side.

The prompt SHALL NOT present an empty opposing-argument field as if it held
content.

#### Scenario: Opening turn of a debate

- **WHEN** a debate role runs with an empty opposing argument and empty opposing
  history
- **THEN** the prompt requests an opening case
- **AND** the prompt contains no instruction to refute the opposing side
- **AND** the prompt omits the opposing-argument field rather than rendering it
  empty

#### Scenario: Subsequent turn of a debate

- **WHEN** a debate role runs with a non-empty opposing argument
- **THEN** the prompt requests a rebuttal
- **AND** the prompt includes the opposing argument being rebutted

#### Scenario: Absent opposing argument does not induce invention

- **WHEN** a debate role runs on an opening turn
- **THEN** its output does not contain a fabricated opposing argument

### Requirement: Speaker attribution is structural, not embedded in the turn body

A turn's stored body SHALL NOT be prefixed or headed with its own speaker label.
Attribution SHALL be carried by the turn's role identity in run state, so that a
consumer reads the speaker from structure rather than by parsing prose.

The debate transcript string assembled for prompt input MAY remain a
speaker-labelled transcript, since inline attribution is what makes a multi-turn
transcript readable to a model. Labels SHALL be added when composing that
transcript, not when storing an individual turn's body.

#### Scenario: Stored turn body

- **WHEN** a debate role's turn body is stored in run state
- **THEN** it carries no speaker-name prefix
- **AND** it carries no self-referential speaker heading

#### Scenario: Label is never applied twice

- **WHEN** a debate role's turn body is inspected
- **THEN** its own role name appears at most once as an attribution

#### Scenario: Prompt transcript retains inline attribution

- **WHEN** the debate history transcript is composed for prompt input
- **THEN** each contribution in it is attributed to its speaker

#### Scenario: Consumers of the transcript keep working

- **WHEN** a downstream prompt or projection reads the debate history
- **THEN** it still finds the speaker attributions it depends on

### Requirement: The debate does not reference participants absent from the pipeline

Debate output SHALL NOT address or narrate a participant that has no
corresponding role in the pipeline. Specifically, no debate or judging role SHALL
present a moderator, since no moderator role exists.

A judging role SHALL present its output as its own ruling under its own identity.

#### Scenario: Researcher output addresses no moderator

- **WHEN** a bull or bear researcher produces a turn
- **THEN** the output addresses no moderator

#### Scenario: Judging output is attributed to the judging role

- **WHEN** the research manager produces its verdict
- **THEN** the verdict is presented as the research manager's own ruling
- **AND** it is not framed as a moderator's ruling

### Requirement: Existing recorded turns are not rewritten

Turns already recorded in the run store SHALL remain byte-identical. This change
SHALL NOT backfill, rewrite, or delete historical debate payloads, including the
payloads known to contain foreign-speaker dialogue.

#### Scenario: Historical run opened after the change

- **WHEN** a run recorded before this change is opened
- **THEN** its stored turn bodies are unchanged
- **AND** it remains viewable
