"use client";

import { useState } from "react";
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

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";
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
      </div>
    </main>
  );
}
