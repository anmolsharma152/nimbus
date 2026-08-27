"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./onboarding.module.css";
import { useAuth } from "../../context/AuthContext";

interface RepoItem {
  id: number;
  name: string;
  full_name: string;
  html_url: string;
  stargazers_count: number;
}

export default function OnboardingPage() {
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [repos, setRepos] = useState<RepoItem[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [customKey, setCustomKey] = useState<string>("");
  const [provider, setProvider] = useState<string>("gemini");
  const [starterPrompt, setStarterPrompt] = useState<string>(
    "Inspect the codebase, identify missing test coverage, write comprehensive unit tests, and verify passing assertions with pytest."
  );
  const [isLaunching, setIsLaunching] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  // Fetch repositories for step 2
  useEffect(() => {
    if (!isAuthenticated) return;

    fetch(`${apiBase}/api/repos`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setRepos(data);
          setSelectedRepo(data[0].html_url);
        }
      })
      .catch((err) => console.warn("Failed to fetch repos for onboarding:", err));
  }, [isAuthenticated, apiBase]);

  const handleSaveKey = async () => {
    if (customKey.trim()) {
      try {
        await fetch(`${apiBase}/api/settings/credentials/${provider}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ value: customKey.trim() }),
        });
      } catch (e) {
        console.warn("Could not save key during onboarding:", e);
      }
    }
    setStep(4);
  };

  const handleLaunchFirstTask = async () => {
    setIsLaunching(true);
    try {
      // 1. Mark onboarding completed
      await fetch(`${apiBase}/api/users/onboarding-complete`, {
        method: "POST",
        credentials: "include",
      });

      // 2. Launch starter task
      const res = await fetch(`${apiBase}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          prompt: starterPrompt.trim(),
          repo_url: selectedRepo || null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        router.push(`/tasks/${data.id}`);
        return;
      }
      router.push("/");
    } catch (err) {
      console.error("Failed to complete onboarding launch:", err);
      router.push("/");
    } finally {
      setIsLaunching(false);
    }
  };

  return (
    <main className={styles.container}>
      <header className={styles.header}>
        <div className={styles.brandRow}>
          <svg width="32" height="32" viewBox="0 0 64 64" fill="none">
            <path
              d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z"
              fill="#ffffff"
            />
          </svg>
          <h1 className={styles.title}>Welcome to Nimbus</h1>
        </div>
        <p className={styles.subtitle}>Set up your cloud software engineering workspace in 4 easy steps</p>
      </header>

      {/* Progress Stepper */}
      <div className={styles.stepper}>
        <div className={`${styles.stepNode} ${step === 1 ? styles.stepActive : step > 1 ? styles.stepCompleted : ""}`}>
          <div className={styles.stepCircle}>{step > 1 ? "✓" : "1"}</div>
          <span className={styles.stepLabel}>Profile</span>
        </div>
        <div className={`${styles.stepNode} ${step === 2 ? styles.stepActive : step > 2 ? styles.stepCompleted : ""}`}>
          <div className={styles.stepCircle}>{step > 2 ? "✓" : "2"}</div>
          <span className={styles.stepLabel}>Repository</span>
        </div>
        <div className={`${styles.stepNode} ${step === 3 ? styles.stepActive : step > 3 ? styles.stepCompleted : ""}`}>
          <div className={styles.stepCircle}>{step > 3 ? "✓" : "3"}</div>
          <span className={styles.stepLabel}>AI Keys</span>
        </div>
        <div className={`${styles.stepNode} ${step === 4 ? styles.stepActive : ""}`}>
          <div className={styles.stepCircle}>4</div>
          <span className={styles.stepLabel}>First Task</span>
        </div>
      </div>

      {/* Step 1: Profile Confirmation */}
      {step === 1 && (
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Step 1: Confirm Your Developer Identity</h2>
          <p className={styles.cardDesc}>
            Nimbus uses your GitHub account to author git commits inside the sandbox and open reviewable Pull Requests under your name.
          </p>

          {isAuthenticated && user ? (
            <div style={{ display: "flex", alignItems: "center", gap: "16px", background: "rgba(255, 255, 255, 0.03)", padding: "16px", borderRadius: "10px", border: "1px solid rgba(255, 255, 255, 0.08)" }}>
              {user.avatar_url && (
                <img src={user.avatar_url} alt={user.username} style={{ width: "52px", height: "52px", borderRadius: "50%" }} />
              )}
              <div>
                <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "#fff" }}>{user.display_name || user.username}</div>
                <div style={{ fontSize: "0.85rem", color: "#a1a1aa" }}>@{user.username} • {user.email || "Primary email verified"}</div>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "20px" }}>
              <p style={{ color: "#a1a1aa", fontSize: "0.9rem", marginBottom: "16px" }}>Please sign in to sync your GitHub repositories.</p>
              <Link
                href="/login"
                style={{ background: "#fff", color: "#000", padding: "10px 20px", borderRadius: "8px", fontWeight: 600, textDecoration: "none" }}
              >
                Sign In with GitHub
              </Link>
            </div>
          )}

          <div className={styles.navRow}>
            <div />
            <button type="button" className={styles.nextBtn} onClick={() => setStep(2)}>
              Next: Select Repository →
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Repository Selection */}
      {step === 2 && (
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Step 2: Choose a Target Repository</h2>
          <p className={styles.cardDesc}>
            Select a repository for your initial agent workspace. Nimbus provisions a disposable sandbox and works on an isolated feature branch.
          </p>

          <div className={styles.repoList}>
            {repos.map((r) => (
              <div
                key={r.id}
                className={`${styles.repoItem} ${selectedRepo === r.html_url ? styles.repoSelected : ""}`}
                onClick={() => setSelectedRepo(r.html_url)}
              >
                <span className={styles.repoName}>📦 {r.full_name}</span>
                <span className={styles.repoStars}>⭐ {r.stargazers_count}</span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "0.78rem", color: "#a1a1aa" }}>Or enter any public/private repo URL:</label>
            <input
              type="text"
              style={{ background: "#09090b", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "0.85rem" }}
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              placeholder="https://github.com/owner/repo"
            />
          </div>

          <div className={styles.navRow}>
            <button type="button" className={styles.backBtn} onClick={() => setStep(1)}>
              ← Back
            </button>
            <button type="button" className={styles.nextBtn} onClick={() => setStep(3)}>
              Next: AI Keys (Optional) →
            </button>
          </div>
        </div>
      )}

      {/* Step 3: AI Model Provider Keys */}
      {step === 3 && (
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Step 3: Optional BYOK AI Keys</h2>
          <p className={styles.cardDesc}>
            Nimbus provides resilient multi-tier LLM routing out of the box. If you have your own personal Google Gemini, Groq, or OpenRouter keys, you can encrypt them in your vault now.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ display: "flex", gap: "10px" }}>
              <select
                style={{ background: "#09090b", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "0.85rem" }}
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="gemini">Google Gemini (Tier 1)</option>
                <option value="groq">Groq Cloud (Tier 2)</option>
                <option value="openrouter">OpenRouter (Tier 3)</option>
              </select>
              <input
                type="password"
                style={{ flex: 1, background: "#09090b", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "0.85rem" }}
                placeholder="Paste API key (optional)..."
                value={customKey}
                onChange={(e) => setCustomKey(e.target.value)}
              />
            </div>
            <span style={{ fontSize: "0.75rem", color: "#71717a" }}>
              Keys are encrypted with Fernet AES-256 before being stored in PostgreSQL.
            </span>
          </div>

          <div className={styles.navRow}>
            <button type="button" className={styles.backBtn} onClick={() => setStep(2)}>
              ← Back
            </button>
            <button type="button" className={styles.nextBtn} onClick={handleSaveKey}>
              {customKey.trim() ? "Save Key & Continue →" : "Skip & Use Default Routing →"}
            </button>
          </div>
        </div>
      )}

      {/* Step 4: First Task Launch */}
      {step === 4 && (
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Step 4: Launch Your First Agent Task</h2>
          <p className={styles.cardDesc}>
            Review your starter directive. When you click Launch, Nimbus will spin up an isolated Docker container, clone the repository, execute reasoning turns, and stream the live flight recording.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ fontSize: "0.85rem", color: "#c7d2fe", background: "rgba(99, 102, 241, 0.1)", padding: "10px 14px", borderRadius: "8px", border: "1px solid rgba(99, 102, 241, 0.25)" }}>
              🎯 <strong>Target:</strong> {selectedRepo || "Local Sandbox"}
            </div>

            <textarea
              style={{ background: "#09090b", border: "1px solid rgba(255, 255, 255, 0.12)", color: "#fff", padding: "12px", borderRadius: "8px", fontSize: "0.88rem", minHeight: "100px", resize: "vertical" }}
              value={starterPrompt}
              onChange={(e) => setStarterPrompt(e.target.value)}
            />
          </div>

          <div className={styles.navRow}>
            <button type="button" className={styles.backBtn} onClick={() => setStep(3)}>
              ← Back
            </button>
            <button
              type="button"
              className={styles.launchBtn}
              onClick={handleLaunchFirstTask}
              disabled={isLaunching}
            >
              {isLaunching ? "Provisioning Sandbox..." : "🚀 Launch First Task"}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
