"use client";

import { useEffect, useState, useRef, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./task.module.css";

interface EventPayload {
  type: string;
  payload: string | { message?: string; status?: string; command?: string; output?: string };
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
  const [copied, setCopied] = useState(false);
  const [followupText, setFollowupText] = useState("");
  const [isSendingFollowup, setIsSendingFollowup] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || apiBase.replace(/^http/, "ws");

  // 1. Fetch initial task details & historical events with 1.5s background polling reconciler
  useEffect(() => {
    const fetchTask = () => {
      fetch(`${apiBase}/api/tasks/${id}`)
        .then((res) => {
          if (!res.ok) throw new Error("Task not found");
          return res.json();
        })
        .then((data) => setTask(data))
        .catch((err) => console.error("Failed to fetch task", err));
    };

    const fetchEvents = () => {
      fetch(`${apiBase}/api/tasks/${id}/events`)
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            setEvents((prev) => {
              if (data.length !== prev.length) {
                return data;
              }
              return prev;
            });
          }
        })
        .catch((err) => console.error("Failed to fetch task events", err));
    };

    fetchTask();
    fetchEvents();

    // Active polling reconciler while task is running/pending
    const poller = setInterval(() => {
      fetchEvents();
      fetchTask();
    }, 1500);

    return () => clearInterval(poller);
  }, [id, apiBase]);

  // 2. Connect WebSocket for sub-second instant streaming
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: any = null;

    const connectWS = () => {
      try {
        ws = new WebSocket(`${wsBase}/ws/tasks/${id}`);
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "status") {
              const parsed = typeof data.payload === "string" ? JSON.parse(data.payload) : data.payload;
              setTask((prev) => prev ? { ...prev, status: parsed.status } : null);
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

        ws.onclose = () => {
          reconnectTimeout = setTimeout(connectWS, 3000);
        };
      } catch (wsErr) {
        console.warn("WebSocket connection notice:", wsErr);
      }
    };

    connectWS();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [id, apiBase, wsBase]);

  // Auto-scroll to bottom of events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const handleCopyLogs = () => {
    const logText = events
      .map((ev) => {
        let parsed: any = {};
        try {
          parsed = typeof ev.payload === "string" ? JSON.parse(ev.payload) : ev.payload;
        } catch {
          parsed = { message: String(ev.payload) };
        }
        const time = new Date(ev.timestamp).toLocaleTimeString();
        if (ev.type === "command") return `[${time}] $ ${parsed.command}`;
        if (ev.type === "result") return parsed.output;
        return `[${time}] ${parsed.message || `Status: ${parsed.status}`}`;
      })
      .join("\n");

    navigator.clipboard.writeText(logText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleCancel = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/cancel`, { method: "POST" });
      if (res.ok) {
        setTask((prev) => prev ? { ...prev, status: "cancelled" } : null);
      }
    } catch (err) {
      console.error("Failed to cancel task", err);
    }
  };

  const handleRetry = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/retry`, { method: "POST" });
      if (res.ok) {
        setTask((prev) => prev ? { ...prev, status: "pending" } : null);
        fetch(`${apiBase}/api/tasks/${id}/events`)
          .then((r) => r.ok ? r.json() : [])
          .then((data) => { if (Array.isArray(data)) setEvents(data); })
          .catch(() => {});
      }
    } catch (err) {
      console.error("Failed to retry task", err);
    }
  };

  const handleSendFollowup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!followupText.trim() || isSendingFollowup) return;
    setIsSendingFollowup(true);

    try {
      // Launch a new follow-up task targeting the same repo & context
      const newPrompt = `Follow-up on Task #${id}:\nOriginal Goal: ${task?.prompt}\n\nAdditional Directive: ${followupText.trim()}`;
      const res = await fetch(`${apiBase}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: newPrompt,
          repo_url: task?.repo_url || null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        router.push(`/tasks/${data.id}`);
      }
    } catch (err) {
      console.error("Failed to send follow-up prompt", err);
    } finally {
      setIsSendingFollowup(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete Task #${id}?`)) return;
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}`, { method: "DELETE" });
      if (res.ok) {
        router.push("/");
      }
    } catch (err) {
      console.error("Failed to delete task", err);
    }
  };

  const isStopable = task?.status === "running" || task?.status === "pending";

  return (
    <div className={styles.layout}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link href="/" className={styles.backButton}>← Back</Link>
          <div className={styles.taskId}>Task #{id}</div>
          {task?.git_branch && (
            <span style={{ fontSize: "0.82rem", color: "#a5b4fc", fontFamily: "var(--font-geist-mono), monospace" }}>
              🌱 {task.git_branch}
            </span>
          )}
        </div>
        <div className={styles.headerRight}>
          {isStopable ? (
            <button
              onClick={handleCancel}
              style={{
                background: "rgba(234, 179, 8, 0.15)",
                border: "1px solid rgba(234, 179, 8, 0.4)",
                color: "#fde047",
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "0.8rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px"
              }}
              title="Stop Agent Execution"
            >
              ⏹ Stop Task
            </button>
          ) : (
            <button
              onClick={handleRetry}
              style={{
                background: "rgba(99, 102, 241, 0.15)",
                border: "1px solid rgba(99, 102, 241, 0.4)",
                color: "#a5b4fc",
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "0.8rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px"
              }}
              title="Retry / Restart this Task"
            >
              🔄 Retry Task
            </button>
          )}

          <button
            onClick={handleDelete}
            style={{
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "#fca5a5",
              padding: "6px 10px",
              borderRadius: "6px",
              fontSize: "0.8rem",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px"
            }}
            title="Delete this task record"
          >
            🗑 Delete
          </button>

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
        {/* Left Pane: Goal, Repo, Follow-Up Prompt & Patch Diff */}
        <div className={styles.leftPane}>
          {/* User Goal & Target Repo */}
          <div className="glass-panel" style={{ padding: "18px", background: "rgba(18, 19, 28, 0.75)", border: "1px solid rgba(255, 255, 255, 0.1)" }}>
            <h3 className={styles.paneTitle}>User Goal</h3>
            <p className={styles.promptText}>
              {task?.prompt || "Loading directive..."}
            </p>

            {task?.repo_url && (
              <div style={{ marginTop: "14px", paddingTop: "10px", borderTop: "1px solid rgba(255, 255, 255, 0.08)" }}>
                <span style={{ fontSize: "0.75rem", color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: "var(--font-geist-mono), monospace" }}>Target Repository</span>
                <p style={{ fontSize: "0.88rem", color: "#93c5fd", wordBreak: "break-all", marginTop: "4px", fontFamily: "var(--font-geist-mono), monospace" }}>
                  <a href={task.repo_url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "underline" }}>
                    {task.repo_url}
                  </a>
                </p>
              </div>
            )}
          </div>

          {/* Follow-up Prompt Section */}
          <div className={styles.followupSection}>
            <h3 className={styles.paneTitle}>💬 Send Follow-Up Directive</h3>
            <form onSubmit={handleSendFollowup}>
              <textarea
                className={styles.followupTextarea}
                placeholder="Give additional instructions (e.g., Also fix imports in test_metrics.py or add docstrings)..."
                rows={3}
                value={followupText}
                onChange={(e) => setFollowupText(e.target.value)}
              />
              <button
                type="submit"
                className={styles.followupBtn}
                disabled={!followupText.trim() || isSendingFollowup}
              >
                {isSendingFollowup ? "Dispatching..." : "Send Follow-Up Directives ➔"}
              </button>
            </form>
          </div>

          {/* Generated Patch Diff (if available) */}
          {task?.patch_diff && (
            <div className="glass-panel" style={{ flex: 1, padding: "18px", display: "flex", flexDirection: "column", overflow: "hidden", background: "rgba(18, 19, 28, 0.75)", border: "1px solid rgba(255, 255, 255, 0.1)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                <h3 className={styles.paneTitle} style={{ margin: 0 }}>Generated Patch Diff</h3>
                <button
                  onClick={() => setShowDiff(!showDiff)}
                  style={{
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid var(--surface-border)",
                    color: "#c7d2fe",
                    padding: "3px 8px",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "0.75rem"
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
                    fontFamily: "var(--font-geist-mono), monospace",
                    background: "#08080c",
                    padding: "12px",
                    borderRadius: "6px",
                    color: "#98c379",
                    whiteSpace: "pre-wrap",
                    lineHeight: "1.4",
                    border: "1px solid rgba(255, 255, 255, 0.08)"
                  }}
                >
                  {task.patch_diff}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Right Pane: High-Contrast Terminal / Live Event Stream */}
        <div className={styles.rightPane}>
          <div className={styles.terminal} ref={scrollRef}>
            <div className={styles.terminalHeader}>
              <div className={styles.terminalHeaderLeft}>
                <div className={styles.macButtons}>
                  <span></span><span></span><span></span>
                </div>
                <span className={styles.terminalTitle}>Agent Execution Terminal</span>
              </div>
              <button
                className={styles.copyBtn}
                onClick={handleCopyLogs}
                title="Copy full terminal flight logs to clipboard"
              >
                {copied ? "✓ Copied!" : "📋 Copy Logs"}
              </button>
            </div>
            
            <div className={styles.terminalBody}>
              {events.length === 0 && (
                <div style={{ color: "#71717a", fontSize: "0.85rem", fontStyle: "italic", padding: "12px 0" }}>
                  Provisioning isolated workspace &amp; waiting for agent output...
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
