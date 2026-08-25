"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

export interface TaskItem {
  id: number;
  prompt: string;
  status: string;
  repo_url?: string | null;
  git_branch?: string | null;
  pr_url?: string | null;
}

export default function Sidebar() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  const fetchTasks = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks?limit=25`);
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
  }, [apiBase]);

  const handleStopTask = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/tasks/${id}/cancel`, { method: "POST" });
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
      const res = await fetch(`${apiBase}/api/tasks/${id}`, { method: "DELETE" });
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
      const res = await fetch(`${apiBase}/api/tasks/${id}/retry`, { method: "POST" });
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
      const res = await fetch(`${apiBase}/api/tasks`, { method: "DELETE" });
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
            <div className={styles.orb} />
            <span className={styles.brandName}>Nimbus</span>
          </Link>
        )}
        {collapsed && (
          <div style={{ margin: "0 auto" }}>
            <div className={styles.orb} />
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
                      ⏹
                    </button>
                  ) : (
                    <button
                      className={`${styles.actionIconBtn} ${styles.retryBtn}`}
                      onClick={(e) => handleRetryTask(e, t.id)}
                      title="Retry / Restart Task"
                    >
                      🔄
                    </button>
                  )}
                  <button
                    className={`${styles.actionIconBtn} ${styles.deleteBtn}`}
                    onClick={(e) => handleDeleteTask(e, t.id)}
                    title="Delete Task"
                  >
                    🗑
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {!collapsed && (
        <div className={styles.sidebarFooter}>
          <span>Zero-Trust Sandbox</span>
          <span style={{ fontSize: "0.7rem", color: "#818cf8" }}>v2.0</span>
        </div>
      )}
    </aside>
  );
}
