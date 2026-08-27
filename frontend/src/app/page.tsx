"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./page.module.css";
import SettingsModal from "../components/SettingsModal";
import { useAuth } from "../context/AuthContext";

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
  description: string | null;
  private?: boolean;
}

export default function Home() {
  const { user, isAuthenticated, isLoading: isAuthLoading, login, logout } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Dynamic GitHub Repos State
  const [ghUser, setGhUser] = useState("");
  const [customGhUser, setCustomGhUser] = useState("");
  const [isEditingUser, setIsEditingUser] = useState(false);
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoSearchFilter, setRepoSearchFilter] = useState("");

  // Settings Modal State
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const router = useRouter();
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  // Sync ghUser with authenticated user when logged in
  useEffect(() => {
    if (user?.username) {
      setGhUser(user.username);
    }
  }, [user]);

  // Dynamically fetch repositories from backend /api/repos proxy
  useEffect(() => {
    if (!ghUser && !user) {
      setRepos([]);
      return;
    }

    let isMounted = true;
    setIsLoadingRepos(true);

    const queryUrl = `${apiBase}/api/repos${ghUser ? `?username_override=${encodeURIComponent(ghUser)}` : ""}`;
    fetch(queryUrl, {
      credentials: "include", // send session cookie if authenticated
    })
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
  }, [ghUser, apiBase, user]);

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
        credentials: "include", // send session cookie
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

  const filteredRepos = repos.filter((r) =>
    r.name.toLowerCase().includes(repoSearchFilter.toLowerCase()) ||
    (r.description && r.description.toLowerCase().includes(repoSearchFilter.toLowerCase()))
  );

  // 1. GUEST / FIRST-TIME VISITOR LANDING PAGE
  if (!isAuthenticated && !isAuthLoading) {
    return (
      <main className={styles.main}>
        <div className={styles.landingContainer}>
          {/* Top Nav */}
          <nav className={styles.landingNav}>
            <div className={styles.brandLogo} style={{ marginBottom: 0 }}>
              <svg className={styles.cloudSvg} viewBox="0 0 64 64" fill="none" style={{ width: "32px", height: "32px" }}>
                <path
                  d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z"
                  fill="#ffffff"
                />
              </svg>
              <span className={styles.brandTitle} style={{ fontSize: "1.5rem" }}>Nimbus</span>
            </div>

            <div className={styles.landingNavLinks}>
              <Link href="/architecture" className={styles.footerLink}>Architecture</Link>
              <Link href="/security" className={styles.footerLink}>Security</Link>
              <Link href="/about" className={styles.footerLink}>About</Link>
              <button
                type="button"
                className={styles.primaryGithubBtn}
                onClick={login}
                style={{ padding: "8px 18px", fontSize: "0.85rem" }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <span>Sign In with GitHub</span>
              </button>
            </div>
          </nav>

          {/* Hero Section */}
          <section className={styles.landingHero}>
            <div className={styles.landingBadge}>
              <span>✨ Autonomous Cloud Software Engineer</span>
            </div>
            <h1 className={styles.landingHeadline}>
              Delegate Codebases to <span className={styles.landingHeadlineGradient}>Zero-Trust AI Sandboxes</span>
            </h1>
            <p className={styles.landingSubtitle}>
              Nimbus autonomously inspects repositories, modifies code on disk, runs assertions, and dispatches verified Draft Pull Requests authored under your GitHub identity.
            </p>
            <div className={styles.landingCtaRow}>
              <button type="button" className={styles.primaryGithubBtn} onClick={login}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <span>Get Started with GitHub ➔</span>
              </button>
              <Link href="/architecture" className={styles.secondaryLinkBtn}>
                Explore Architecture →
              </Link>
            </div>
          </section>

          {/* Features Grid */}
          <div className={styles.featuresGrid}>
            <div className={styles.featureCard}>
              <span className={styles.featureIcon}>🐳</span>
              <h3 className={styles.featureTitle}>Hardened Sandboxes</h3>
              <p className={styles.featureDesc}>
                Each task executes inside an ephemeral microVM container with strict cgroups memory & CPU limits, dropped capabilities, and no-new-privileges flags.
              </p>
            </div>
            <div className={styles.featureCard}>
              <span className={styles.featureIcon}>🧠</span>
              <h3 className={styles.featureTitle}>3-Tier Multi-LLM Routing</h3>
              <p className={styles.featureDesc}>
                Intra-Gemini primary flash pool with instant automatic failover to Groq (GPT-OSS-120B) and OpenRouter fallback for zero downtime.
              </p>
            </div>
            <div className={styles.featureCard}>
              <span className={styles.featureIcon}>📡</span>
              <h3 className={styles.featureTitle}>Live Flight Telemetry</h3>
              <p className={styles.featureDesc}>
                Sub-second log streaming, terminal command playback, live git diff generation, and visual screenshot verification via WebSockets.
              </p>
            </div>
            <div className={styles.featureCard}>
              <span className={styles.featureIcon}>🚀</span>
              <h3 className={styles.featureTitle}>Automated Draft PRs</h3>
              <p className={styles.featureDesc}>
                Seamless GitHub OAuth 2.0 integration — no manual personal access tokens required. Commits are authored under your verified developer account.
              </p>
            </div>
          </div>

          {/* 3-Step Workflow */}
          <section className={styles.workflowSection}>
            <h2 className={styles.sectionTitle}>How Nimbus Works</h2>
            <div className={styles.stepsRow}>
              <div className={styles.stepCard}>
                <span className={styles.stepNumber}>Step 01</span>
                <h3 className={styles.stepTitle}>Connect Repository</h3>
                <p className={styles.stepDesc}>
                  Sign in with GitHub and select any public or private repository. Nimbus clones the repo into an isolated sandbox environment.
                </p>
              </div>
              <div className={styles.stepCard}>
                <span className={styles.stepNumber}>Step 02</span>
                <h3 className={styles.stepTitle}>Delegate Directive</h3>
                <p className={styles.stepDesc}>
                  Describe your task in natural language. The autonomous agent inspects source code, edits files, and runs tests to verify assertions.
                </p>
              </div>
              <div className={styles.stepCard}>
                <span className={styles.stepNumber}>Step 03</span>
                <h3 className={styles.stepTitle}>Review &amp; Merge</h3>
                <p className={styles.stepDesc}>
                  Inspect live terminal execution logs, view the generated patch diff, and merge the automatically created Draft Pull Request.
                </p>
              </div>
            </div>
          </section>

          {/* CTA Banner */}
          <div className={styles.ctaBanner}>
            <h2 className={styles.ctaBannerTitle}>Ready to delegate your next coding task?</h2>
            <p className={styles.ctaBannerSub}>
              Connect your GitHub account in seconds. Zero complex local setup required.
            </p>
            <button type="button" className={styles.primaryGithubBtn} onClick={login}>
              <span>Launch Nimbus with GitHub ➔</span>
            </button>
          </div>
        </div>

        {/* Footer */}
        <footer className={styles.footer}>
          <span>Nimbus &copy; {new Date().getFullYear()}</span>
          <div className={styles.footerLinks}>
            <Link href="/architecture" className={styles.footerLink}>Architecture</Link>
            <Link href="/security" className={styles.footerLink}>Security</Link>
            <Link href="/about" className={styles.footerLink}>About</Link>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>GitHub</a>
          </div>
        </footer>
      </main>
    );
  }

  // 2. AUTHENTICATED AGENT CONTROL PLANE
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
              
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {isAuthenticated && user ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", background: "rgba(255, 255, 255, 0.05)", padding: "2px 8px", borderRadius: "6px", border: "1px solid rgba(255, 255, 255, 0.08)" }}>
                    {user.avatar_url && (
                      <img
                        src={user.avatar_url}
                        alt={user.username}
                        style={{ width: "16px", height: "16px", borderRadius: "50%" }}
                      />
                    )}
                    <span style={{ fontSize: "0.75rem", color: "#e4e4e7", fontWeight: 500 }}>
                      @{user.username}
                    </span>
                    <button
                      type="button"
                      onClick={logout}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#a1a1aa",
                        fontSize: "0.7rem",
                        cursor: "pointer",
                        padding: "0 2px"
                      }}
                      title="Sign Out"
                    >
                      (Sign Out)
                    </button>
                  </div>
                ) : (
                  <Link
                    href="/login"
                    style={{
                      background: "rgba(99, 102, 241, 0.18)",
                      border: "1px solid rgba(99, 102, 241, 0.4)",
                      color: "#c7d2fe",
                      fontSize: "0.72rem",
                      padding: "3px 8px",
                      borderRadius: "4px",
                      textDecoration: "none",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      fontWeight: 500
                    }}
                  >
                    🐙 Sign In with GitHub
                  </Link>
                )}

                <button
                  type="button"
                  onClick={() => setIsSettingsOpen(true)}
                  style={{
                    background: "rgba(99, 102, 241, 0.15)",
                    border: "1px solid rgba(99, 102, 241, 0.35)",
                    color: "#c7d2fe",
                    fontSize: "0.72rem",
                    padding: "3px 8px",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontFamily: "var(--font-geist-mono), monospace",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px"
                  }}
                >
                  ⚙️ Settings
                </button>
              </div>
            </div>

            {/* High-Contrast Prompt Input Container */}
            <div className={styles.promptInputWrapper}>
              <div className={styles.inputHeader}>
                <label htmlFor="promptInput" className={styles.inputLabel}>
                  <span className={styles.promptIcon}>✨</span> Task Directive / Instructions:
                </label>
                <span className={styles.inputHint}>Enter to launch • Shift+Enter for newline</span>
              </div>
              <textarea
                id="promptInput"
                className={styles.textarea}
                placeholder="Describe your coding task (e.g. Inspect the codebase, add missing unit tests for core modules, and verify with pytest)..."
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
            </div>

            {/* High-Contrast Target Repo Input with Complete Dropdown Menu */}
            <div className={styles.repoSection}>
              <div className={styles.repoHeaderRow}>
                <span className={styles.repoLabel}>
                  {ghUser ? (
                    `🐙 Select Repository (${isAuthenticated && user?.username === ghUser ? `Connected as @${ghUser}` : `Fetched for @${ghUser}`} • ${repos.length} repos):`
                  ) : (
                    "🐙 Target Repository (Public or Private):"
                  )}
                </span>
                <button
                  type="button"
                  className={styles.userToggleBtn}
                  onClick={() => setIsEditingUser(!isEditingUser)}
                >
                  {isEditingUser ? "Close User Search" : (ghUser ? "Change User / Org" : "Browse by GitHub Username")}
                </button>
              </div>

              {isEditingUser && (
                <div className={styles.userInputRow}>
                  <input
                    type="text"
                    className={styles.userHandleInput}
                    placeholder="Enter GitHub username or org (e.g. anmolsharma152)"
                    value={customGhUser}
                    onChange={(e) => setCustomGhUser(e.target.value)}
                  />
                  <button
                    type="button"
                    className={styles.fetchBtn}
                    onClick={handleFetchUserRepos}
                  >
                    Fetch Repos
                  </button>
                </div>
              )}

              {/* Complete Repository Dropdown Select */}
              {repos.length > 0 && (
                <div style={{ marginBottom: "10px" }}>
                  <select
                    className={styles.repoInput}
                    style={{ cursor: "pointer", background: "#0b0c15", padding: "10px 12px", marginBottom: "8px" }}
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                  >
                    <option value="">-- Choose from {repos.length} repositories of @{ghUser} --</option>
                    {repos.map((repo) => (
                      <option key={repo.id} value={repo.html_url}>
                        {repo.name} {repo.language ? `[${repo.language}]` : ""} {repo.stargazers_count > 0 ? `(⭐${repo.stargazers_count})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Quick 5 Recent Chips */}
              <div className={styles.repoChipsRow}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginRight: "4px" }}>Recent:</span>
                {isLoadingRepos && (
                  <span style={{ fontSize: "0.75rem", color: "#a1a1aa", fontStyle: "italic" }}>
                    Fetching repositories from GitHub...
                  </span>
                )}
                {!isLoadingRepos && repos.slice(0, 5).map((repo) => (
                  <button
                    key={repo.id}
                    type="button"
                    className={styles.repoChip}
                    onClick={() => setRepoUrl(repo.html_url)}
                    title={`Click to target ${repo.full_name}`}
                  >
                    <span>{repo.name}</span>
                    {repo.stargazers_count > 0 && (
                      <span style={{ color: "#fbbf24", fontSize: "0.7rem" }}>⭐{repo.stargazers_count}</span>
                    )}
                  </button>
                ))}
              </div>

              {/* Direct GitHub URL Text Input (Allows pasting private/custom URLs) */}
              <input
                type="text"
                className={styles.repoInput}
                placeholder="Or type/paste any custom or private repo URL (e.g. https://github.com/owner/repo)"
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
                🔒 <strong>Zero-Trust Sandbox:</strong> Works on Public &amp; Private repos with PAT.
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
          <button
            onClick={() => setIsSettingsOpen(true)}
            style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.82rem", padding: 0 }}
          >
            ⚙️ Provider Settings
          </button>
          <Link href="/architecture" className={styles.footerLink}>Architecture</Link>
          <Link href="/security" className={styles.footerLink}>Security</Link>
          <Link href="/about" className={styles.footerLink}>About Creator</Link>
          <a href="https://github.com/anmolsharma152/nimbus" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>GitHub</a>
        </div>
      </footer>

      {/* Settings Modal */}
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </main>
  );
}
