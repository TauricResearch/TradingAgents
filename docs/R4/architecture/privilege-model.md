# R4 Coding Agent File Access Policy

This is a working agreement for R4, not an operating-system or sandbox permission mechanism. The team must decide the final project-wide policy; enforcement still depends on the agent tool and human review.

| Role | Read scope | Write scope | Out of scope |
| --- | --- | --- | --- |
| R4 implementation agent | Requirements, current source, R4 tests, and architecture material | R4 source, tests, example configuration, and documents explicitly authorized by the task | Private keys, other members' implementations, and live trading accounts |
| R4 review agent | R4 diff, test commands and results, requirement trace | Explicitly assigned corrections or review notes | Fabricated tests, conversations, CI status, or investment results |
| Student owner | The above material and local run evidence | Requirement choices, cost policy, review decisions, and submission scope | Presenting individual work as a team decision or labeling Codex records as OpenCode |

Each task should list the paths it needs to read and change; files outside that list are not accessed or edited by default. R4 work starts with `RE.md`, `docs/R4/req/requirements.yaml`, and the architecture documents, followed by relevant source and tests. This allowlist is a review convention; the repository does not technically enforce it. Write scope does not authorize an agent to push, merge, or publish material. Prompt summaries do not replace an original conversation export.

The local `.env.enterprise` contains course API credentials. Git ignores it, but a ZIP archive must exclude it separately. Live test output may contain model text; review it before publication and retain only necessary evidence.
