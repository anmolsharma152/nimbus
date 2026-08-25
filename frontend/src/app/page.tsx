"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./page.module.css";

const PROMPT_PRESETS = [
  {
    title: "🧪 Add Unit Tests",
    prompt: "Inspect the repository structure, identify untested edge cases, and implement comprehensive unit tests with passing assertions.",
  },
  {
    title: "🐛 Debug & Fix Bug",
    prompt: "Analyze the codebase for failing tests or bugs, implement the minimal correct fix, verify with test execution, and generate a clean patch.",
  },
  {
    title: "📝 Docs & Architecture",
    prompt: "Examine repository modules, add detailed function docstrings, and update README.md with clear architecture diagrams and setup instructions.",
  },
  {
    title: "⚡ Performance Refactor",
    prompt: "Refactor core functions for cleaner separation of concerns and higher throughput while guaranteeing all existing unit tests pass.",
  },
];

interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  html_url: string;
  stargazers_count: number;
  language: string | null;
}

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Dynamic GitHub Repos State
  const [ghUser, setGhUser] = useState("anmolsharma152");
  const [customGhUser, setCustomGhUser] = useState("anmolsharma152");
  const [isEditingUser, setIsEditingUser] = useState(false);
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);

  const router = useRouter();
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  // Dynamically fetch live repositories from GitHub REST API
  useEffect(() => {
    let isMounted = true;
    setIsLoadingRepos(true);

    fetch(`https://api.github.com/users/${ghUser}/repos?sort=updated&per_page=6`)
      .then((res) => {
        if (!res.ok) throw new Error("Could not load GitHub repositories");
        return res.json();
      })
      .then((data) => {
        if (isMounted && Array.isArray(data)) {
          setRepos(data);
        }
      })
      .catch((err) => {
        console.warn("GitHub fetch notice:", err);
      })
      .finally(() => {
        if (isMounted) setIsLoadingRepos(false);
      });

    return () => {
      isMounted = false;
    };
  }, [ghUser]);

  const handleFetchUserRepos = (e: React.FormEvent) => {
    e.preventDefault();
    if (customGhUser.trim()) {
      setGhUser(customGhUser.trim());
      setIsEditingUser(false);
    }
  };

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
        err.message || "Failed to connect to backend control plane. Please check connection and try again."
      );
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.main}>
      <div className={styles.contentWrapper}>
        {/* Hero Section */}
        <section className={styles.hero}>
          <div className={styles.brandLogo}>
            <svg className={styles.cloudSvg} viewBox="0 0 64 64" fill="none">
              <defs>
                <filter id="heroCloudGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3.5" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>
              <path
                d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z"
                fill="#ffffff"
                opacity="0.35"
                filter="url(#heroCloudGlow)"
              />
              <path
                d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z"
                fill="#ffffff"
              />
            </svg>
            <h1 className={styles.brandTitle}>Nimbus</h1>
          </div>

          <p className={styles.subtitle}>
            Autonomous Cloud Software Engineer
          </p>
        </section>

        {/* Task Form Terminal Card */}
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.terminalCard}>
            <div className={styles.terminalHeader}>
              <div className={styles.terminalDots}>
                <span className={`${styles.dot} ${styles.dotRed}`} />
                <span className={`${styles.dot} ${styles.dotYellow}`} />
                <span className={`${styles.dot} ${styles.dotGreen}`} />
              </div>
              <span className={styles.terminalTitle}>agent-control-plane // prompt-input</span>
              <span style={{ fontSize: "0.75rem", color: "#818cf8", fontFamily: "monospace" }}>3-Tier LLM</span>
            </div>

            <textarea
              className={styles.textarea}
              placeholder="Describe your coding task (e.g., Create unit tests, fix a bug, implement a new feature)..."
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

            {/* Target Repo Input with Dynamic GitHub Fetcher */}
            <div className={styles.repoSection}>
              <div className={styles.repoHeaderRow}>
                <span className={styles.repoLabel}>
                  🐙 Live GitHub Repos ({ghUser}):
                </span>
                <button
                  type="button"
                  className={styles.userToggleBtn}
                  onClick={() => setIsEditingUser(!isEditingUser)}
                >
                  {isEditingUser ? "Close" : "Change User / Org"}
                </button>
              </div>

              {isEditingUser && (
                <div className={styles.userInputRow}>
                  <input
                    type="text"
                    className={styles.userHandleInput}
                    placeholder="GitHub username or org"
                    value={customGhUser}
                    onChange={(e) => setCustomGhUser(e.target.value)}
                  />
                  <button
                    type="button"
                    className={styles.fetchBtn}
                    onClick={handleFetchUserRepos}
                  >
                    Fetch
                  </button>
                </div>
              )}

              {/* Dynamic Repos Chips */}
              <div className={styles.repoChipsRow}>
                {isLoadingRepos && (
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                    Fetching repositories from GitHub...
                  </span>
                )}
                {!isLoadingRepos && repos.length > 0 && repos.map((repo) => (
                  <button
                    key={repo.id}
                    type="button"
                    className={styles.repoChip}
                    onClick={() => setRepoUrl(repo.html_url)}
                    title={`Click to target ${repo.full_name} (${repo.language || "Code"})`}
                  >
                    <span>{repo.name}</span>
                    {repo.stargazers_count > 0 && (
                      <span style={{ color: "#fbbf24", fontSize: "0.7rem" }}>⭐{repo.stargazers_count}</span>
                    )}
                  </button>
                ))}
              </div>

              <input
                type="text"
                className={styles.repoInput}
                placeholder="Target GitHub Repo URL (e.g. https://github.com/owner/repo)"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
            </div>

            {errorMessage && (
              <div className={styles.errorBanner}>
                ⚠️ {errorMessage}
              </div>
            )}

            <div className={styles.actionsRow}>
              <span className={styles.sandboxHint}>
                🔒 <strong>Zero-Trust Sandbox:</strong> Clones into ephemeral container &amp; opens Draft PR.
              </span>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={!prompt.trim() || isSubmitting}
              >
                {isSubmitting ? "Launching..." : "Start Agent ➔"}
              </button>
            </div>
          </div>
        </form>

        {/* Suggested Prompt Presets (Positioned Below Terminal Form) */}
        <div className={styles.presetsRow}>
          {PROMPT_PRESETS.map((preset) => (
            <button
              key={preset.title}
              type="button"
              className={styles.presetBtn}
              onClick={() => setPrompt(preset.prompt)}
            >
              {preset.title}
            </button>
          ))}
        </div>
      </div>

      {/* Minimal Clean Footer (Pinned to Bottom) */}
      <footer className={styles.footer}>
        <span>Nimbus &copy; {new Date().getFullYear()}</span>
        <div className={styles.footerLinks}>
          <Link href="/architecture" className={styles.footerLink}>Architecture</Link>
          <Link href="/security" className={styles.footerLink}>Security</Link>
          <Link href="/about" className={styles.footerLink}>About Creator</Link>
          <a href="https://github.com/anmolsharma152/nimbus" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>GitHub</a>
        </div>
      </footer>
    </main>
  );
}
