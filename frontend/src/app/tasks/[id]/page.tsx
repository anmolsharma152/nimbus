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

interface ScreenshotItem {
  id: number;
  task_id: number;
  filename: string;
  caption: string;
  data: string;
  created_at: string;
}

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const { id } = resolvedParams;
  
  const [task, setTask] = useState<TaskData | null>(null);
  const [events, setEvents] = useState<EventPayload[]>([]);
  const [screenshots, setScreenshots] = useState<ScreenshotItem[]>([]);
  const [activeTab, setActiveTab] = useState<"terminal" | "diff" | "visual">("terminal");
  const [selectedImageModal, setSelectedImageModal] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(true);
  const [copied, setCopied] = useState(false);
  const [followupText, setFollowupText] = useState("");
  const [isSendingFollowup, setIsSendingFollowup] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || apiBase.replace(/^http/, "ws");

  // 1. Fetch initial task details, historical events & screenshots
  useEffect(() => {
    const fetchTask = () => {
      fetch(`${apiBase}/api/tasks/${id}`, { credentials: "include" })
        .then((res) => {
          if (!res.ok) throw new Error("Task not found");
          return res.json();
        })
        .then((data) => setTask(data))
        .catch((err) => console.error("Failed to fetch task", err));
    };

    const fetchEvents = () => {
      fetch(`${apiBase}/api/tasks/${id}/events`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            setEvents((prev) => (data.length !== prev.length ? data : prev));
          }
        })
        .catch((err) => console.error("Failed to fetch task events", err));
    };

    const fetchScreenshots = () => {
      fetch(`${apiBase}/api/tasks/${id}/screenshots`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => {
          if (Array.isArray(data)) {
            setScreenshots(data);
          }
        })
        .catch((err) => console.warn("Failed to fetch screenshots", err));
    };

    fetchTask();
    fetchEvents();
    fetchScreenshots();

    // Active polling reconciler while task is running/pending
    const poller = setInterval(() => {
      fetchEvents();
      fetchTask();
      fetchScreenshots();
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
                fetch(`${apiBase}/api/tasks/${id}`, { credentials: "include" })
                  .then((res) => res.json())
                  .then((d) => setTask(d))
                  .catch(() => {});
              }
            }
            
            // Check for real-time screenshot payload
            try {
              const parsedPayload = typeof data.payload === "string" ? JSON.parse(data.payload) : data.payload;
              if (parsedPayload && parsedPayload.screenshot) {
                setScreenshots((prev) => [
                  ...prev,
                  {
                    id: Date.now(),
                    task_id: Number(id),
                    filename: parsedPayload.filename || "screenshot.png",
                    caption: parsedPayload.caption || "Live visual capture",
                    data: parsedPayload.screenshot,
                    created_at: new Date().toISOString(),
                  },
                ]);
              }
            } catch {}

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
      const res = await fetch(`${apiBase}/api/tasks/${id}/cancel`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        setTask((prev) => (prev ? { ...prev, status: "cancelled" } : null));
      }
    } catch (err) {
      console.error("Failed to cancel task", err);
    }
  };

  const handleRetry = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/retry`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        setTask((prev) => (prev ? { ...prev, status: "pending" } : null));
        fetch(`${apiBase}/api/tasks/${id}/events`, { credentials: "include" })
          .then((r) => (r.ok ? r.json() : []))
          .then((data) => {
            if (Array.isArray(data)) setEvents(data);
          })
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
        credentials: "include",
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
      const res = await fetch(`${apiBase}/api/tasks/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
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
            <span style={{ fontSize: "0.82rem", color: "#a5b4fc", fontFamily: "var(--font-geist-mono), monospace", display: "inline-flex", alignItems: "center", gap: "5px" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="6" y1="3" x2="6" y2="15"></line>
                <circle cx="18" cy="6" r="3"></circle>
                <circle cx="6" cy="18" r="3"></circle>
                <path d="M18 9a9 9 0 0 1-9 9"></path>
              </svg>
              {task.git_branch}
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
                display: "inline-flex",
                alignItems: "center",
                gap: "6px"
              }}
              title="Stop Agent Execution"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
              <span>Stop Task</span>
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
                display: "inline-flex",
                alignItems: "center",
                gap: "6px"
              }}
              title="Retry / Restart this Task"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
              </svg>
              <span>Retry Task</span>
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
              display: "inline-flex",
              alignItems: "center",
              gap: "6px"
            }}
            title="Delete this task record"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            <span>Delete</span>
          </button>

          {task?.pr_url && (
            <a
              href={task.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="premium-button"
              style={{ padding: "6px 14px", fontSize: "0.85rem", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "6px" }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="18" r="3"></circle>
                <circle cx="6" cy="6" r="3"></circle>
                <path d="M13 6h3a2 2 0 0 1 2 2v7"></path>
                <line x1="6" y1="9" x2="6" y2="21"></line>
              </svg>
              <span>View Draft PR</span>
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

        {/* Right Pane: Tabbed Flight Logs, Diff & Visual Preview */}
        <div className={styles.rightPane}>
          {/* Tab Switcher Bar */}
          <div className={styles.tabBar}>
            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === "terminal" ? styles.tabBtnActive : ""}`}
              onClick={() => setActiveTab("terminal")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="4 17 10 11 4 5"></polyline>
                <line x1="12" y1="19" x2="20" y2="19"></line>
              </svg>
              <span>Terminal Flight Recorder</span>
            </button>

            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === "diff" ? styles.tabBtnActive : ""}`}
              onClick={() => setActiveTab("diff")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="6" y1="3" x2="6" y2="15"></line>
                <circle cx="18" cy="6" r="3"></circle>
                <circle cx="6" cy="18" r="3"></circle>
                <path d="M18 9a9 9 0 0 1-9 9"></path>
              </svg>
              <span>Patch Diff</span>
            </button>

            <button
              type="button"
              className={`${styles.tabBtn} ${activeTab === "visual" ? styles.tabBtnActive : ""}`}
              onClick={() => setActiveTab("visual")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              <span>Visual Preview</span>
              {screenshots.length > 0 && (
                <span className={styles.tabCountBadge}>{screenshots.length}</span>
              )}
            </button>
          </div>

          {/* TAB 1: Terminal Flight Recorder */}
          {activeTab === "terminal" && (
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
          )}

          {/* TAB 2: Full Patch Diff Viewer */}
          {activeTab === "diff" && (
            <div className={styles.screenshotContainer}>
              <h3 className={styles.paneTitle} style={{ margin: 0 }}>Generated Patch Diff</h3>
              {task?.patch_diff ? (
                <pre
                  style={{
                    flex: 1,
                    overflow: "auto",
                    fontSize: "0.85rem",
                    fontFamily: "var(--font-geist-mono), monospace",
                    background: "#08080c",
                    padding: "16px",
                    borderRadius: "8px",
                    color: "#98c379",
                    whiteSpace: "pre-wrap",
                    lineHeight: "1.5",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                  }}
                >
                  {task.patch_diff}
                </pre>
              ) : (
                <div style={{ color: "#71717a", fontSize: "0.88rem", fontStyle: "italic", padding: "20px 0" }}>
                  No patch modifications generated yet. When the agent alters files on disk, the diff will appear here.
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Visual Preview (Screenshots & Artifacts) */}
          {activeTab === "visual" && (
            <div className={styles.screenshotContainer}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 className={styles.paneTitle} style={{ margin: 0 }}>Visual Verification Snapshots</h3>
                <span style={{ fontSize: "0.78rem", color: "#a1a1aa" }}>{screenshots.length} captured</span>
              </div>

              {screenshots.length === 0 ? (
                <div style={{ textAlign: "center", padding: "48px 24px", color: "#71717a" }}>
                  <div style={{ fontSize: "2rem", marginBottom: "12px" }}>🖼️</div>
                  <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#f4f4f5", marginBottom: "6px" }}>No visual snapshots generated yet</div>
                  <p style={{ fontSize: "0.82rem", maxWidth: "420px", margin: "0 auto", lineHeight: 1.5 }}>
                    When Nimbus renders UI components, runs Playwright assertions, or captures screenshots, high-resolution snapshots will be streamed here in real-time.
                  </p>
                </div>
              ) : (
                <div className={styles.screenshotGrid}>
                  {screenshots.map((s, idx) => (
                    <div
                      key={s.id || idx}
                      className={styles.screenshotCard}
                      onClick={() => setSelectedImageModal(s.data)}
                    >
                      <img src={s.data} alt={s.filename} className={styles.screenshotThumbnail} />
                      <div className={styles.screenshotInfo}>
                        <span className={styles.screenshotFilename}>{s.filename}</span>
                        <span className={styles.screenshotCaption}>{s.caption}</span>
                        <span className={styles.screenshotTime}>{s.created_at ? new Date(s.created_at).toLocaleTimeString() : ""}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Lightbox Fullscreen Modal */}
          {selectedImageModal && (
            <div className={styles.lightbox} onClick={() => setSelectedImageModal(null)}>
              <button className={styles.lightboxClose} onClick={() => setSelectedImageModal(null)}>✕</button>
              <img src={selectedImageModal} alt="Enlarged snapshot" className={styles.lightboxImg} onClick={(e) => e.stopPropagation()} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
