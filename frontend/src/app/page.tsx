"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./page.module.css";
import MakerCard from "../components/MakerCard";

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

const POPULAR_REPOS = [
  "https://github.com/anmolsharma152/CodexEngine",
  "https://github.com/anmolsharma152/RecSys_RL",
  "https://github.com/anmolsharma152/nimbus",
];

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const router = useRouter();

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

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
          <div className={styles.badge}>
            <span className={styles.badgeDot} />
            <span>Autonomous Cloud Software Engineer v2.0</span>
          </div>

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
            Turn natural language prompts into tested git pull requests with zero-trust sandboxing and 3-tier resilient multi-LLM routing.
          </p>

          {/* Quick Prompt Presets */}
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
              placeholder="Describe your coding task (e.g. Implement comprehensive unit tests for auth middleware, fix edge cases in data parser)..."
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

            {/* Target Repo Input with Quick Chips */}
            <div className={styles.repoSection}>
              <div className={styles.repoChipsRow}>
                <span className={styles.repoLabel}>Quick Repos:</span>
                {POPULAR_REPOS.map((url) => (
                  <button
                    key={url}
                    type="button"
                    className={styles.repoChip}
                    onClick={() => setRepoUrl(url)}
                  >
                    {url.replace("https://github.com/", "")}
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
                🔒 <strong>Zero-Trust Sandbox:</strong> Clones into ephemeral subshell &amp; creates draft PR.
              </span>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={!prompt.trim() || isSubmitting}
              >
                {isSubmitting ? "Launching Agent..." : "Start Agent ➔"}
              </button>
            </div>
          </div>
        </form>

        {/* Feature Grid */}
        <h2 className={styles.sectionTitle}>Built for High-Assurance Autonomy</h2>
        <p className={styles.sectionSubtitle}>
          Isolated workspace execution with enterprise-grade resilience and observability.
        </p>

        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🛡️</div>
            <h3 className={styles.featureHeading}>Zero-Trust Sandboxing</h3>
            <p className={styles.featureDesc}>
              Runs untrusted code inside ephemeral subshells and Docker containers. Full directory cleanup on termination.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>⚡</div>
            <h3 className={styles.featureHeading}>3-Tier Multi-LLM Routing</h3>
            <p className={styles.featureDesc}>
              Automatic failover across Gemini 3.6 Flash, Groq (<code>gpt-oss-120b</code>), and OpenRouter with jittered retries.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>📡</div>
            <h3 className={styles.featureHeading}>Real-Time Flight Recorder</h3>
            <p className={styles.featureDesc}>
              Live WebSocket streaming of shell execution, stdout/stderr logs, tool decisions, and real-time diff inspection.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🌿</div>
            <h3 className={styles.featureHeading}>Automated Git &amp; Draft PRs</h3>
            <p className={styles.featureDesc}>
              Automated branch checkout, test validation, git commit, and GitHub Draft Pull Request creation.
            </p>
          </div>
        </div>

        {/* Maker Attribution Card */}
        <MakerCard />

        {/* Footer */}
        <footer className={styles.footer}>
          <span>Nimbus Agent &copy; {new Date().getFullYear()}</span>
          <div className={styles.footerLinks}>
            <Link href="/security" className={styles.footerLink}>Security Architecture</Link>
            <a href="https://github.com/anmolsharma152/nimbus" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>GitHub</a>
            <a href="https://anmolsharma152.vercel.app" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>Creator Portfolio</a>
          </div>
        </footer>
      </div>
    </main>
  );
}
