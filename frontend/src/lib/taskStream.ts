// Helpers for the live task event stream (WebSocket + polling fallback).

export const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

export function isTerminalStatus(status?: string | null): boolean {
  return !!status && TERMINAL_STATUSES.includes(status.toLowerCase());
}

/**
 * Merges incoming events into the list, dropping persisted events already present (same id).
 * The same event can arrive from history replay, the live stream, and polling.
 * Persisted events are kept in id order; unpersisted ones (no id) stay where they arrived.
 * Returns `prev` unchanged when nothing new arrived, so React can skip the re-render.
 */
export function mergeEvents<T extends { id?: number | null }>(prev: T[], incoming: T[]): T[] {
  const seen = new Set<number>();
  for (const ev of prev) {
    if (typeof ev.id === "number") seen.add(ev.id);
  }

  let next: T[] | null = null;
  for (const ev of incoming) {
    if (typeof ev.id === "number") {
      if (seen.has(ev.id)) continue;
      seen.add(ev.id);
    }
    next = next ?? [...prev];
    if (typeof ev.id !== "number") {
      next.push(ev);
      continue;
    }
    // History replay and live events can interleave: insert after the last smaller id
    let i = next.length;
    while (i > 0) {
      const prevId = next[i - 1].id;
      if (typeof prevId !== "number" || prevId < ev.id) break;
      i--;
    }
    next.splice(i, 0, ev);
  }
  return next ?? prev;
}

export function lastEventId(events: { id?: number | null }[]): number {
  return events.reduce((max, ev) => (typeof ev.id === "number" && ev.id > max ? ev.id : max), 0);
}

/** Exponential backoff with jitter: ~1s, 2s, 4s ... capped at 30s. */
export function reconnectDelay(attempt: number): number {
  const ceiling = Math.min(30_000, 1_000 * 2 ** attempt);
  return ceiling / 2 + Math.random() * (ceiling / 2);
}

/** Close code the server uses for "task not found / not authorized"; retrying won't help. */
export const STREAM_REJECTED_CODE = 1008;

export function streamUrl(wsBase: string, taskId: string | number, after: number, ticket: string | null): string {
  const params = new URLSearchParams();
  if (ticket) params.set("ticket", ticket);
  if (after > 0) params.set("after", String(after));
  const query = params.toString();
  return `${wsBase}/ws/tasks/${taskId}${query ? `?${query}` : ""}`;
}

export interface TaskEventPayload {
  message?: string;
  status?: string;
  command?: string;
  output?: string;
  screenshot?: string;
  filename?: string;
  caption?: string;
}

/** Event payloads arrive as JSON strings (REST/WS) or objects; non-JSON text becomes a message. */
export function parsePayload(payload: unknown): TaskEventPayload {
  if (typeof payload !== "string") {
    return payload && typeof payload === "object" ? (payload as TaskEventPayload) : {};
  }
  try {
    const parsed = JSON.parse(payload);
    return parsed && typeof parsed === "object" ? parsed : { message: String(parsed) };
  } catch {
    return { message: payload };
  }
}
