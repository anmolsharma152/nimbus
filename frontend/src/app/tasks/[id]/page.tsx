"use client";

import { useEffect, useState, useRef, use } from "react";
import Link from "next/link";
import styles from "./task.module.css";

interface EventPayload {
  type: string;
  payload: string;
  timestamp: string;
}

interface TaskData {
  id?: number;
  prompt: string;
  status: string;
  repo_url?: string | null;
  git_branch?: string | null;
  pr_url?: string | null;
  patch_diff?: string | null;
}

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const { id } = resolvedParams;
  
  const [task, setTask] = useState<TaskData | null>(null);
  const [events, setEvents] = useState<EventPayload[]>([]);
  const [showDiff, setShowDiff] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || apiBase.replace(/^http/, "ws");

  // Fetch initial task details & historical events
  useEffect(() => {
    // 1. Fetch task details
    fetch(`${apiBase}/api/tasks/${id}`)
      .then((res) => {
        if (!res.ok) throw new Error("Task not found");
        return res.json();
      })
      .then((data) => setTask(data))
      .catch((err) => console.error("Failed to fetch task", err));

    // 2. Fetch all recorded events
    fetch(`${apiBase}/api/tasks/${id}/events`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setEvents(data);
        }
      })
      .catch((err) => console.error("Failed to fetch task events", err));
  }, [id, apiBase]);

  // Connect WebSocket for live streaming updates
  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${wsBase}/ws/tasks/${id}`);
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "status") {
            const parsed = typeof data.payload === "string" ? JSON.parse(data.payload) : data.payload;
            setTask((prev) => prev ? { ...prev, status: parsed.status } : null);
            // Refresh full task to get patch/PR if completed
            if (parsed.status === "completed" || parsed.status === "failed") {
              fetch(`${apiBase}/api/tasks/${id}`)
                .then((res) => res.json())
                .then((d) => setTask(d))
                .catch(() => {});
            }
          }
          setEvents((prev) => [...prev, data]);
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };
    } catch (wsErr) {
      console.warn("WebSocket connection notice:", wsErr);
    }

    return () => {
      if (ws) ws.close();
    };
  }, [id, apiBase, wsBase]);

  // Auto-scroll to bottom of events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div className={styles.layout}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link href="/" className={styles.backButton}>← Back</Link>
          <div className={styles.taskId}>Task #{id}</div>
          {task?.git_branch && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
              🌱 {task.git_branch}
            </span>
          )}
        </div>
        <div className={styles.headerRight} style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          {task?.pr_url && (
            <a
              href={task.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="premium-button"
              style={{ padding: "6px 14px", fontSize: "0.85rem", textDecoration: "none" }}
            >
              🚀 View Draft PR
            </a>
          )}
          <span className={`${styles.statusBadge} ${task?.status === 'running' ? styles.statusActive : ''}`}>
            {task?.status || 'loading...'}
          </span>
        </div>
      </header>

      <main className={styles.main}>
        {/* Left Pane: Prompt, Repo Context & Patch Diff */}
        <div className={styles.leftPane} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="glass-panel" style={{ padding: "20px" }}>
            <h3 className={styles.paneTitle}>User Goal</h3>
            <p className={styles.promptText}>
              {task?.prompt || "Loading prompt..."}
            </p>

            {task?.repo_url && (
              <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px solid var(--surface-border)" }}>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Repository</span>
                <p style={{ fontSize: "0.9rem", color: "#a0a0ff", wordBreak: "break-all", marginTop: "4px" }}>
                  {task.repo_url}
                </p>
              </div>
            )}
          </div>

          {task?.patch_diff && (
            <div className="glass-panel" style={{ flex: 1, padding: "20px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <h3 className={styles.paneTitle} style={{ margin: 0 }}>Generated Patch Diff</h3>
                <button
                  onClick={() => setShowDiff(!showDiff)}
                  style={{
                    background: "transparent",
                    border: "1px solid var(--surface-border)",
                    color: "var(--foreground)",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "0.8rem"
                  }}
                >
                  {showDiff ? "Collapse" : "Expand"}
                </button>
              </div>
              {showDiff && (
                <pre
                  style={{
                    flex: 1,
                    overflow: "auto",
                    fontSize: "0.8rem",
                    fontFamily: "monospace",
                    background: "#08080c",
                    padding: "12px",
                    borderRadius: "6px",
                    color: "#98c379",
                    whiteSpace: "pre-wrap",
                    lineHeight: "1.4"
                  }}
                >
                  {task.patch_diff}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Right Pane: Terminal / Event Stream */}
        <div className={styles.rightPane}>
          <div className={`glass-panel ${styles.terminal}`} ref={scrollRef}>
            <div className={styles.terminalHeader}>
              <div className={styles.macButtons}>
                <span></span><span></span><span></span>
              </div>
              <span className={styles.terminalTitle}>Agent Execution Terminal</span>
            </div>
            
            <div className={styles.terminalBody}>
              {events.length === 0 && (
                <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", fontStyle: "italic", padding: "12px 0" }}>
                  Waiting for agent output...
                </div>
              )}
              {events.map((ev, idx) => {
                let parsed: any = {};
                try {
                  parsed = typeof ev.payload === "string" ? JSON.parse(ev.payload) : ev.payload;
                } catch {
                  parsed = { message: String(ev.payload) };
                }

                const evType = (ev.type || "").toLowerCase();
                if (evType === "log" || evType === "status") {
                  return (
                    <div key={idx} className={styles.logLine}>
                      <span className={styles.timestamp}>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      <span className={styles.logText}>{parsed.message || `Status changed to ${parsed.status}`}</span>
                    </div>
                  );
                } else if (evType === "command") {
                  return (
                    <div key={idx} className={styles.commandLine}>
                      <span className={styles.prompt}>$</span> {parsed.command}
                    </div>
                  );
                } else if (evType === "result") {
                  return (
                    <div key={idx} className={styles.resultLine}>
                      {parsed.output}
                    </div>
                  );
                }
                return null;
              })}
              {task?.status === 'running' && (
                <div className={styles.blinkingCursor}>█</div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
