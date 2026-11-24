// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0

export { BUILT_IN, type Catalog, loadCatalog } from "../agents/catalog.js";
export { offeredLevels } from "../models/catalog.js";
export {
  defaultModel,
  defaultOf,
  type ModelOption,
  modelsOf,
  RECOMMENDED,
} from "../models/model-default.js";
export { dataToolNames } from "../tools/catalog.js";
export type { EvidenceRecord } from "../tools/evidence-store.js";
export { renderResult } from "../tools/render.js";
export {
  type AskOptions,
  Engine,
  type EngineOptions,
  type RestoredState,
  type Turn,
  type TurnOutcome,
} from "./engine.js";
export {
  agentLimitProblems,
  chatgptAuth,
  createEngine,
  dataProviders,
  modelReplayKey,
  resolveContextWindow,
  routeOf,
  tauricSessions,
} from "./factory.js";
export { allSessions, download, isHere } from "./restore.js";
export {
  type Deleted,
  deleteSession,
  type EngineBuilder,
  listSessions,
  Session,
  SessionError,
  type SessionSummary,
  type SyncSetup,
  savedRoute,
  sendPendingDeletions,
} from "./session.js";
