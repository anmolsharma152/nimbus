"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch("http://localhost:8000/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          repo_url: repoUrl.trim() || null,
        }),
      });

      if (!res.ok) throw new Error("Failed to create task");

      const data = await res.json();
      router.push(`/tasks/${data.id}`);
    } catch (err) {
      console.error(err);
      alert("Failed to start agent session. Is the backend running?");
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

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={`glass-panel ${styles.inputWrapper}`}>
            <textarea
              className={`premium-input ${styles.textarea}`}
              placeholder="e.g. Add unit tests for auth middleware, fix the broken login endpoint, and submit a PR..."
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
                placeholder="Target GitHub Repo URL (optional, e.g. https://github.com/owner/repo)"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
            </div>

            <div className={styles.actions}>
              <span className={styles.hint}>Press Enter or click to launch isolated agent</span>
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
