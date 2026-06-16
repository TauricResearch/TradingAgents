# Project Plan - Continuous Trading Analyst MVP

## Strategy
This plan coordinates the development of the continuous trading analyst MVP by running two parallel tracks: the E2E Testing Track and the Implementation Track, according to the Project Pattern.

1. **E2E Testing Track**:
   - Spawns a dedicated subagent to design E2E test infra, feature list, and test cases covering Tiers 1-4.
   - Outputs: `TEST_INFRA.md`, test cases, and `TEST_READY.md`.

2. **Implementation Track**:
   - Decomposes implementation into milestones based on module boundaries:
     - Milestone 2: Core Watcher & CLI loop foundation.
     - Milestone 3: Opportunity Scanner scoring logic.
     - Milestone 4: Portfolio Memory, Risk Guard, and ROI review.
     - Milestone 5: Full integration, passing 100% of E2E tests.
     - Milestone 6: Challenger-driven adversarial testing and coverage hardening.

## Verification
- Ephemeral subagents (Workers) will run target build and unit/integration tests and provide handoffs.
- E2E tests must be run against the final integrated MVP.
- Forensic Auditor will run to verify there is no hardcoding, facade logic, or cheating.
