// Turns the flat task event stream into a conversation: one turn per run (the original goal,
// then each follow-up or retry), each holding its log lines and command blocks.

import { parsePayload } from "./taskStream";

export interface ThreadEvent {
  id?: number | null;
  type: string;
  payload: unknown;
  timestamp: string;
}

export type TurnKind = "goal" | "follow_up" | "retry";
export type RunState = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface CommandItem {
  kind: "command";
  key: string;
  timestamp: string;
  command: string;
  /** Output without the "[Exit code: N]" header; undefined while the command is still running. */
  output?: string;
  exitCode?: number | null;
}

export interface LogItem {
  kind: "log";
  key: string;
  timestamp: string;
  text: string;
}

export interface ScreenshotItem {
  kind: "screenshot";
  key: string;
  timestamp: string;
  caption: string;
}

export type ThreadItem = CommandItem | LogItem | ScreenshotItem;

export interface Turn {
  kind: TurnKind;
  /** What the user asked for in this turn (the goal, the follow-up text, or nothing for a retry). */
  text: string;
  startedAt?: string;
  items: ThreadItem[];
  /** Last status seen in this turn; earlier turns always ended before the next one started. */
  state?: RunState;
}

const EXIT_HEADER = /^\[Exit code: (-?\d+)\]\n?/;
const LEGACY_FOLLOW_UP = "💬 Follow-up: ";
const LEGACY_RETRY = "🔄 Task restarted by user";

interface TurnMarker {
  kind: Exclude<TurnKind, "goal">;
  text: string;
}

function turnMarker(payload: Record<string, unknown>): TurnMarker | null {
  const turn = payload.turn;
  if (turn === "follow_up") return { kind: "follow_up", text: String(payload.text ?? "") };
  if (turn === "retry") return { kind: "retry", text: "" };
  // Events written before the API tagged turn markers
  const message = typeof payload.message === "string" ? payload.message : "";
  if (message.startsWith(LEGACY_FOLLOW_UP)) return { kind: "follow_up", text: message.slice(LEGACY_FOLLOW_UP.length) };
  if (message.startsWith(LEGACY_RETRY)) return { kind: "retry", text: "" };
  return null;
}

export function splitExitCode(raw: string): { output: string; exitCode: number | null } {
  const match = raw.match(EXIT_HEADER);
  if (!match) return { output: raw, exitCode: null };
  return { output: raw.slice(match[0].length), exitCode: Number(match[1]) };
}

function asRunState(status: unknown): RunState | undefined {
  const s = typeof status === "string" ? status.toLowerCase() : "";
  return ["pending", "running", "completed", "failed", "cancelled"].includes(s) ? (s as RunState) : undefined;
}

export function buildThread(prompt: string, events: ThreadEvent[]): Turn[] {
  const turns: Turn[] = [{ kind: "goal", text: prompt, items: [] }];
  let current = turns[0];

  events.forEach((ev, idx) => {
    const payload = parsePayload(ev.payload) as Record<string, unknown>;
    const type = (ev.type || "").toLowerCase();
    const key = typeof ev.id === "number" ? `e${ev.id}` : `i${idx}`;

    if (type === "log") {
      const marker = turnMarker(payload);
      if (marker) {
        current = { kind: marker.kind, text: marker.text, startedAt: ev.timestamp, items: [] };
        turns.push(current);
        return;
      }
      const text = typeof payload.message === "string" ? payload.message : "";
      if (text) current.items.push({ kind: "log", key, timestamp: ev.timestamp, text });
      return;
    }

    if (type === "status") {
      current.state = asRunState(payload.status) ?? current.state;
      if (!current.startedAt) current.startedAt = ev.timestamp;
      return;
    }

    if (type === "command") {
      current.items.push({ kind: "command", key, timestamp: ev.timestamp, command: String(payload.command ?? "") });
      return;
    }

    if (type === "result") {
      if (typeof payload.screenshot === "string") {
        const caption = typeof payload.caption === "string" ? payload.caption : String(payload.filename ?? "Screenshot");
        current.items.push({ kind: "screenshot", key, timestamp: ev.timestamp, caption });
        return;
      }
      const raw = typeof payload.output === "string" ? payload.output : "";
      const parsed = splitExitCode(raw);
      const exitCode = typeof payload.exit_code === "number" ? payload.exit_code : parsed.exitCode;
      // Attach to the newest command still waiting for output
      for (let i = current.items.length - 1; i >= 0; i--) {
        const item = current.items[i];
        if (item.kind === "command") {
          if (item.output === undefined) {
            item.output = parsed.output;
            item.exitCode = exitCode;
            return;
          }
          break;
        }
      }
      current.items.push({ kind: "log", key, timestamp: ev.timestamp, text: parsed.output });
    }
  });

  return turns;
}

export type SummaryTone = "active" | "success" | "warning" | "error" | "neutral";

export interface StatusSummary {
  tone: SummaryTone;
  title: string;
  detail?: string;
}

interface TaskLike {
  pr_url?: string | null;
  patch_diff?: string | null;
  repo_url?: string | null;
}

function lastLog(turn?: Turn): string | undefined {
  if (!turn) return undefined;
  for (let i = turn.items.length - 1; i >= 0; i--) {
    const item = turn.items[i];
    if (item.kind === "log") return item.text;
  }
  return undefined;
}

function lastCommand(turn?: Turn): CommandItem | undefined {
  if (!turn) return undefined;
  for (let i = turn.items.length - 1; i >= 0; i--) {
    const item = turn.items[i];
    if (item.kind === "command") return item;
  }
  return undefined;
}

/** One-line state of the task for the banner under the conversation. */
export function summarizeStatus(status: string | null | undefined, task: TaskLike, latest?: Turn): StatusSummary {
  const s = (status || "").toLowerCase();
  if (!s) return { tone: "neutral", title: "Loading task…" };
  if (s === "pending") return { tone: "active", title: "Queued", detail: "Waiting for a worker to pick this up." };
  if (s === "running") {
    const cmd = lastCommand(latest);
    if (cmd && cmd.output === undefined) return { tone: "active", title: "Running a command", detail: cmd.command };
    return { tone: "active", title: "Working", detail: lastLog(latest) };
  }
  if (s === "cancelled") return { tone: "neutral", title: "Stopped", detail: "You stopped this run. Send a follow-up or retry to continue." };
  if (s === "failed") {
    return { tone: "error", title: "Failed", detail: lastLog(latest) || "The run ended with an error." };
  }
  if (s === "completed") {
    if (task.pr_url) return { tone: "success", title: "Draft PR ready", detail: task.pr_url };
    if (task.patch_diff) {
      return task.repo_url
        ? { tone: "warning", title: "Changes made, but no PR", detail: lastLog(latest) || "See the Patch Diff tab." }
        : { tone: "success", title: "Changes ready", detail: "See the Patch Diff tab." };
    }
    return { tone: "neutral", title: "Finished with no file changes", detail: lastLog(latest) };
  }
  return { tone: "neutral", title: s };
}
