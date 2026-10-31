"use client";

import styles from "./TaskThread.module.css";
import type { CommandItem, StatusSummary, ThreadItem, Turn } from "@/lib/taskThread";

const TURN_LABEL: Record<Turn["kind"], string> = {
  goal: "Goal",
  follow_up: "Follow-up",
  retry: "Retry",
};

/** Output longer than this starts collapsed even when its block is open. */
const LONG_OUTPUT_LINES = 40;

function time(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString();
}

function CommandBlock({ item, defaultOpen }: { item: CommandItem; defaultOpen: boolean }) {
  const running = item.output === undefined;
  const failed = typeof item.exitCode === "number" && item.exitCode !== 0;
  const output = item.output ?? "";
  const lineCount = output ? output.split("\n").length : 0;

  return (
    <details className={`${styles.command} ${failed ? styles.commandFailed : ""}`} open={defaultOpen || undefined}>
      <summary className={styles.commandSummary}>
        <span className={styles.chevron} aria-hidden="true">▸</span>
        <span className={styles.dollar}>$</span>
        <code className={styles.commandText}>{item.command}</code>
        <span className={styles.commandMeta}>
          {running ? (
            <span className={`${styles.badge} ${styles.badgeRunning}`}>running</span>
          ) : typeof item.exitCode === "number" ? (
            <span className={`${styles.badge} ${failed ? styles.badgeError : styles.badgeOk}`}>exit {item.exitCode}</span>
          ) : null}
          {lineCount > 0 && <span className={styles.lines}>{lineCount} lines</span>}
        </span>
      </summary>
      {running ? (
        <div className={styles.outputPending}>Waiting for output…</div>
      ) : output.trim() ? (
        lineCount > LONG_OUTPUT_LINES ? (
          <details className={styles.longOutput}>
            <summary>Show all {lineCount} lines</summary>
            <pre className={styles.output}>{output}</pre>
          </details>
        ) : (
          <pre className={styles.output}>{output}</pre>
        )
      ) : (
        <div className={styles.outputPending}>No output</div>
      )}
    </details>
  );
}

function Item({ item, open }: { item: ThreadItem; open: boolean }) {
  if (item.kind === "command") return <CommandBlock item={item} defaultOpen={open} />;
  if (item.kind === "screenshot") {
    return (
      <div className={styles.log}>
        <span className={styles.time}>{time(item.timestamp)}</span>
        <span>📸 {item.caption} <span className={styles.muted}>(Visual Preview tab)</span></span>
      </div>
    );
  }
  return (
    <div className={styles.log}>
      <span className={styles.time}>{time(item.timestamp)}</span>
      <span className={styles.logText}>{item.text}</span>
    </div>
  );
}

function TurnView({ turn, isLatest, isActive }: { turn: Turn; isLatest: boolean; isActive: boolean }) {
  const commands = turn.items.filter((i) => i.kind === "command") as CommandItem[];
  const lastCommand = commands[commands.length - 1];
  const failedCount = commands.filter((c) => typeof c.exitCode === "number" && c.exitCode !== 0).length;

  const body = (
    <div className={styles.items}>
      {turn.items.length === 0 && (
        <div className={styles.muted}>{isLatest && isActive ? "Provisioning workspace and waiting for the agent…" : "No output."}</div>
      )}
      {turn.items.map((item) => (
        // Keep the running command (and a failed last command) expanded; everything else starts folded
        <Item
          key={item.key}
          item={item}
          open={
            item === lastCommand &&
            isLatest &&
            (item.output === undefined || (typeof item.exitCode === "number" && item.exitCode !== 0))
          }
        />
      ))}
      {isLatest && isActive && <div className={styles.cursor} aria-hidden="true">█</div>}
    </div>
  );

  return (
    <section className={styles.turn}>
      <div className={`${styles.bubble} ${turn.kind === "retry" ? styles.bubbleRetry : ""}`}>
        <div className={styles.bubbleHeader}>
          <span className={styles.bubbleLabel}>{TURN_LABEL[turn.kind]}</span>
          <span className={styles.time}>{time(turn.startedAt)}</span>
        </div>
        {turn.kind === "retry" ? (
          <p className={styles.bubbleText}>Started over from a clean checkout with the goal and all follow-ups.</p>
        ) : (
          <p className={styles.bubbleText}>{turn.text || "…"}</p>
        )}
      </div>
      {isLatest ? (
        body
      ) : (
        // Earlier runs fold into one line so the latest run stays in view
        <details className={styles.pastRun}>
          <summary>
            {commands.length} command{commands.length === 1 ? "" : "s"}
            {failedCount > 0 && <span className={styles.pastFailed}> · {failedCount} failed</span>}
            {turn.state && <span> · {turn.state}</span>}
          </summary>
          {body}
        </details>
      )}
    </section>
  );
}

export default function TaskThread({
  turns,
  isActive,
  summary,
}: {
  turns: Turn[];
  isActive: boolean;
  summary: StatusSummary;
}) {
  return (
    <div className={styles.thread}>
      {turns.map((turn, idx) => (
        <TurnView key={idx} turn={turn} isLatest={idx === turns.length - 1} isActive={isActive} />
      ))}
      <div className={`${styles.summary} ${styles[`tone_${summary.tone}`]}`} role="status" aria-live="polite">
        <span className={styles.summaryTitle}>
          {summary.tone === "active" && <span className={styles.spinner} aria-hidden="true" />}
          {summary.title}
        </span>
        {summary.detail &&
          (summary.detail.startsWith("https://") ? (
            <a className={styles.summaryDetail} href={summary.detail} target="_blank" rel="noopener noreferrer">
              {summary.detail}
            </a>
          ) : (
            <span className={styles.summaryDetail}>{summary.detail}</span>
          ))}
      </div>
    </div>
  );
}
