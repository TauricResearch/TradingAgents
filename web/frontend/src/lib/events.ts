// Hand-synced mirror of web/server/events.py EventType.
// If you add/remove a type, update BOTH files AND the test.
export const EventType = {
  RUN_STARTED: "run_started",
  RUN_FINISHED: "run_finished",
  RUN_FAILED: "run_failed",
  ANALYST_STARTED: "analyst_started",
  ANALYST_THINKING: "analyst_thinking",
  ANALYST_COMPLETED: "analyst_completed",
  TOOL_CALL: "tool_call",
  TOOL_RESULT: "tool_result",
  TOOL_CALL_WARNING: "tool_call_warning",
  DEBATE_MESSAGE: "debate_message",
  RISK_MESSAGE: "risk_message",
  DECISION: "decision",
  PRICE_UPDATE: "price_update",
  SERVER_NOTICE: "server_notice",
} as const;

export type EventTypeValue = typeof EventType[keyof typeof EventType];

export interface WsEvent<T = unknown> {
  v: 1;
  type: EventTypeValue;
  ts: string;
  run_id: number;
  data: T;
  id?: number;
}

export const ALL_EVENT_TYPES: EventTypeValue[] = Object.values(EventType);
