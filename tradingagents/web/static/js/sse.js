// EventSource wrapper for /api/runs/{id}/events.
//
// Contract: the server ends the stream after a terminal event, and we MUST
// close the EventSource then — otherwise the browser reconnects forever.
// On auto-reconnect the browser sends Last-Event-ID and the server resumes;
// a fresh page load replays from 0 (reducers are idempotent, so that's safe).

const EVENT_TYPES = [
  'run_status',
  'agent_status',
  'report_section',
  'tool_call',
  'message',
  'stats',
  'done',
  'error',
  'cancelled',
];

const TERMINAL = new Set(['done', 'error', 'cancelled']);

let current = null;

export function connectRunEvents(runId, onEvent) {
  disconnectRunEvents();
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  current = source;

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (event) => {
      let data = {};
      try {
        data = JSON.parse(event.data);
      } catch {
        /* skip malformed frame */
      }
      onEvent(type, data);
      if (TERMINAL.has(type)) disconnectRunEvents();
    });
  }
  return source;
}

export function disconnectRunEvents() {
  if (current) {
    current.close();
    current = null;
  }
}
