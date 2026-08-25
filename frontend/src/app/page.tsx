"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

const PROMPT_PRESETS = [
  {
    title: "🧪 Add Unit Tests",
    prompt: "Inspect the repository structure, identify untested edge cases, and implement comprehensive unit tests with passing assertions.",
  },
  {
    title: "🐛 Debug & Fix Bug",
    prompt: "Analyze the codebase for bugs or failing tests, implement the minimal correct fix, verify with test execution, and generate a tested patch.",
  },
  {
    title: "📝 Documentation",
    prompt: "Examine the repository modules, add detailed function docstrings, and update README.md with clear architecture diagrams and setup steps.",
  },
  {
    title: "🚀 Refactor & Optimize",
    prompt: "Refactor core modules for cleaner separation of concerns and higher performance while ensuring all existing tests pass.",
  },
];

interface RecentTask {
  id: number;
  prompt: string;
  status: string;
  repo_url?: string | null;
  git_branch?: string | null;
  pr_url?: string | null;
}

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);
  const router = useRouter();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  // Fetch recent tasks on mount
  useEffect(() => {
    fetch(`${apiBase}/api/tasks?limit=6`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setRecentTasks(data);
      })
      .catch((err) => console.error("Failed to load recent tasks", err));
  }, [apiBase]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const res = await fetch(`${apiBase}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          repo_url: repoUrl.trim() || null,
        }),
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Server returned ${res.status}: ${errorText || res.statusText}`);
      }

      const data = await res.json();
      router.push(`/tasks/${data.id}`);
    } catch (err: any) {
      console.error(err);
      setErrorMessage(
        err.message || "Failed to connect to backend control plane. Please try again in a few moments."
      );
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.main}>
      <div className={`${styles.hero} animate-fade-in`}>
        <div className={styles.logo}>
          <div className={styles.orb}></div>
          <h1>Nimbus</h1>
        </div>
        <p className={styles.subtitle}>
          Autonomous Cloud Software Engineer
        </p>

        {/* Quick Presets */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "center", marginBottom: "16px", maxWidth: "680px" }}>
          {PROMPT_PRESETS.map((preset) => (
            <button
              key={preset.title}
              type="button"
              onClick={() => setPrompt(preset.prompt)}
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--surface-border)",
                borderRadius: "9999px",
                padding: "6px 14px",
                color: "#e0e0e0",
                fontSize: "0.82rem",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.12)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.05)")}
            >
              {preset.title}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={`glass-panel ${styles.inputWrapper}`}>
            <textarea
              className={`premium-input ${styles.textarea}`}
              placeholder="Describe your coding task (e.g., Create a new file test.txt with lorem ipsum, or fix a specific bug)..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />

            <div style={{ padding: "8px 12px", borderTop: "1px solid var(--surface-border)" }}>
              <input
                type="text"
                className="premium-input"
                style={{
                  width: "100%",
                  fontSize: "0.9rem",
                  padding: "8px 10px",
                  borderRadius: "6px",
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid var(--surface-border)",
                  color: "var(--foreground)",
                }}
                placeholder="Target GitHub Repo URL (e.g. https://github.com/owner/repo)"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
            </div>

            {errorMessage && (
              <div style={{
                margin: "8px 12px",
                padding: "8px 12px",
                borderRadius: "6px",
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                color: "#fca5a5",
                fontSize: "0.85rem",
                textAlign: "left"
              }}>
                ⚠️ {errorMessage}
              </div>
            )}

            <div className={styles.actions}>
              <span className={styles.hint}>
                🔒 <strong>Zero-Trust Sandbox:</strong> Clones into an ephemeral container and opens a <strong>Draft PR</strong> for review.
              </span>
              <button
                type="submit"
                className="premium-button"
                disabled={!prompt.trim() || isSubmitting}
              >
                {isSubmitting ? "Launching..." : "Start Agent"}
              </button>
            </div>
          </div>
        </form>

        {/* Recent Tasks List */}
        {recentTasks.length > 0 && (
          <div style={{ marginTop: "36px", width: "100%", maxWidth: "680px", textAlign: "left" }}>
            <h3 style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
              📋 Recent Agent Tasks
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {recentTasks.map((t) => (
                <div
                  key={t.id}
                  onClick={() => router.push(`/tasks/${t.id}`)}
                  className="glass-panel"
                  style={{
                    padding: "12px 16px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                    borderRadius: "8px"
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.08)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.03)")}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px", overflow: "hidden", paddingRight: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--foreground)" }}>Task #{t.id}</span>
                      {t.repo_url && (
                        <span style={{ fontSize: "0.75rem", color: "#a0a0ff", fontFamily: "monospace" }}>
                          {t.repo_url.replace("https://github.com/", "")}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: "0.82rem", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "450px" }}>
                      {t.prompt}
                    </span>
                  </div>
                  <span style={{
                    fontSize: "0.72rem",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    textTransform: "uppercase",
                    fontWeight: 600,
                    background: t.status === "completed" ? "rgba(34, 197, 94, 0.15)" : t.status === "running" ? "rgba(59, 130, 246, 0.15)" : "rgba(234, 179, 8, 0.15)",
                    color: t.status === "completed" ? "#86efac" : t.status === "running" ? "#93c5fd" : "#fde047"
                  }}>
                    {t.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
