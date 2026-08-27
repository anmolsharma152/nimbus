"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";
import SettingsModal from "./SettingsModal";
import { useAuth } from "../context/AuthContext";

export interface TaskItem {
  id: number;
  prompt: string;
  status: string;
  repo_url?: string | null;
  git_branch?: string | null;
  pr_url?: string | null;
}

export default function Sidebar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  const fetchTasks = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks?limit=25`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setTasks(data);
        }
      }
    } catch (e) {
      console.warn("Could not load tasks in sidebar:", e);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 4000);
    return () => clearInterval(interval);
  }, [apiBase, user]);

  const handleStopTask = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/cancel`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        setTasks((prev) =>
          prev.map((t) => (t.id === id ? { ...t, status: "cancelled" } : t))
        );
      }
    } catch (err) {
      console.error("Failed to cancel task", err);
    }
  };

  const handleDeleteTask = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok) {
        setTasks((prev) => prev.filter((t) => t.id !== id));
        if (pathname === `/tasks/${id}`) {
          router.push("/");
        }
      }
    } catch (err) {
      console.error("Failed to delete task", err);
    }
  };

  const handleRetryTask = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/retry`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        setTasks((prev) =>
          prev.map((t) => (t.id === id ? { ...t, status: "pending" } : t))
        );
        router.push(`/tasks/${id}`);
      }
    } catch (err) {
      console.error("Failed to retry task", err);
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Are you sure you want to delete all tasks and execution logs?")) return;
    try {
      const res = await fetch(`${apiBase}/api/tasks`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok) {
        setTasks([]);
        router.push("/");
      }
    } catch (err) {
      console.error("Failed to clear tasks", err);
    }
  };

  const getStatusDotClass = (status: string) => {
    switch (status.toLowerCase()) {
      case "running":
        return styles.dotRunning;
      case "completed":
        return styles.dotCompleted;
      case "failed":
        return styles.dotFailed;
      case "cancelled":
        return styles.dotCancelled;
      default:
        return styles.dotPending;
    }
  };

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`}>
      {/* Brand & Toggle */}
      <div className={styles.sidebarHeader}>
        {!collapsed && (
          <Link href="/" className={styles.brand}>
            <svg width="22" height="22" viewBox="0 0 64 64" fill="none" style={{ flexShrink: 0, filter: "drop-shadow(0 0 6px rgba(255,255,255,0.4))" }}>
              <path d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z" fill="#ffffff"/>
            </svg>
            <span className={styles.brandName}>Nimbus</span>
          </Link>
        )}
        {collapsed && (
          <div style={{ margin: "0 auto" }}>
            <svg width="22" height="22" viewBox="0 0 64 64" fill="none" style={{ filter: "drop-shadow(0 0 6px rgba(255,255,255,0.4))" }}>
              <path d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z" fill="#ffffff"/>
            </svg>
          </div>
        )}
        <button
          className={styles.collapseBtn}
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {collapsed ? "→" : "←"}
        </button>
      </div>

      {/* New Task Button */}
      <div className={styles.actionSection}>
        <Link href="/" className={styles.newTaskBtn} title="Create New Task">
          <span>+</span>
          {!collapsed && <span>New Agent Task</span>}
        </Link>
      </div>

      {/* List Header */}
      {!collapsed && (
        <div className={styles.listHeader}>
          <span className={styles.listTitle}>Tasks ({tasks.length})</span>
          {tasks.length > 0 && (
            <button className={styles.clearAllBtn} onClick={handleClearAll} title="Clear all tasks">
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Task List */}
      <div className={styles.taskList}>
        {tasks.map((t) => {
          const isActive = pathname === `/tasks/${t.id}`;
          const isStopable = t.status === "running" || t.status === "pending";

          return (
            <div
              key={t.id}
              onClick={() => router.push(`/tasks/${t.id}`)}
              className={`${styles.taskItem} ${isActive ? styles.activeTask : ""}`}
              title={t.prompt}
            >
              <div className={styles.taskInfo}>
                <div className={styles.taskMeta}>
                  <div className={`${styles.statusDot} ${getStatusDotClass(t.status)}`} />
                  <span className={styles.taskId}>#{t.id}</span>
                  {!collapsed && t.repo_url && (
                    <span className={styles.taskRepo}>
                      {t.repo_url.replace("https://github.com/", "")}
                    </span>
                  )}
                </div>
                {!collapsed && (
                  <span className={styles.taskPrompt}>{t.prompt}</span>
                )}
              </div>

              {!collapsed && (
                <div className={styles.taskActions}>
                  {isStopable ? (
                    <button
                      className={`${styles.actionIconBtn} ${styles.stopBtn}`}
                      onClick={(e) => handleStopTask(e, t.id)}
                      title="Stop / Cancel Task"
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="4" y="4" width="16" height="16" rx="2" />
                      </svg>
                    </button>
                  ) : (
                    <button
                      className={`${styles.actionIconBtn} ${styles.retryBtn}`}
                      onClick={(e) => handleRetryTask(e, t.id)}
                      title="Retry / Restart Task"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                      </svg>
                    </button>
                  )}
                  <button
                    className={`${styles.actionIconBtn} ${styles.deleteBtn}`}
                    onClick={(e) => handleDeleteTask(e, t.id)}
                    title="Delete Task"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* User Info & Footer */}
      {!collapsed && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "8px 12px 12px 12px", borderTop: "1px solid var(--border-color)" }}>
          {isAuthenticated && user ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255, 255, 255, 0.03)", padding: "6px 8px", borderRadius: "8px", border: "1px solid rgba(255, 255, 255, 0.06)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden" }}>
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.username}
                    style={{ width: "22px", height: "22px", borderRadius: "50%", flexShrink: 0 }}
                  />
                ) : (
                  <div style={{ width: "22px", height: "22px", borderRadius: "50%", background: "#4f46e5", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.7rem", color: "#fff" }}>
                    {user.username.charAt(0).toUpperCase()}
                  </div>
                )}
                <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
                  <span style={{ fontSize: "0.75rem", color: "#f4f4f5", fontWeight: 600, whiteSpace: "nowrap", textOverflow: "ellipsis", overflow: "hidden" }}>
                    {user.display_name || user.username}
                  </span>
                  <span style={{ fontSize: "0.68rem", color: "#a1a1aa" }}>
                    @{user.username}
                  </span>
                </div>
              </div>
              <button
                onClick={logout}
                title="Sign out"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#71717a",
                  cursor: "pointer",
                  fontSize: "0.7rem",
                  padding: "2px 4px"
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "6px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "#e4e4e7",
                fontSize: "0.75rem",
                padding: "6px 10px",
                borderRadius: "6px",
                textDecoration: "none",
                fontWeight: 500
              }}
            >
              🐙 Sign In with GitHub
            </Link>
          )}

          <div className={styles.sidebarFooter}>
            <button
              onClick={() => setIsSettingsOpen(true)}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--text-muted)",
                fontSize: "0.75rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "5px",
                padding: 0,
                fontFamily: "inherit"
              }}
              title="Configure LLM Keys & GitHub PAT"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <span>Settings</span>
            </button>
            <Link href="/security" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "4px" }}>
              🛡️ Security
            </Link>
            <span style={{ fontSize: "0.7rem", color: "#818cf8", fontFamily: "monospace" }}>v2.0</span>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </aside>
  );
}
