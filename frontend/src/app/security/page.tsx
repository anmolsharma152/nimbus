import React from "react";
import Link from "next/link";
import styles from "./security.module.css";
import MakerCard from "../../components/MakerCard";

export const metadata = {
  title: "Security & Zero-Trust Isolation Architecture | Nimbus",
  description: "Learn how Nimbus secures autonomous cloud software engineering with ephemeral sandboxing, secret redaction, and multi-tier resiliency.",
};

export default function SecurityPage() {
  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        {/* Back Link */}
        <Link href="/" className={styles.backLink}>
          ← Back to Agent Console
        </Link>

        {/* Header */}
        <header className={styles.header}>
          <div className={styles.badge}>🛡️ Security Architecture &amp; Trust Model</div>
          <h1 className={styles.title}>Zero-Trust Autonomous Execution</h1>
          <p className={styles.subtitle}>
            Nimbus is engineered from the ground up to treat all user repositories and generated code as untrusted,
            enforcing strict isolation across every stage of the execution lifecycle.
          </p>
        </header>

        {/* Security Pillars */}
        <div className={styles.grid}>
          <div className={styles.card}>
            <div className={styles.cardIcon}>📦</div>
            <h2 className={styles.cardTitle}>Ephemeral Sandbox Isolation</h2>
            <p className={styles.cardDesc}>
              Every agent task executes inside an ephemeral Docker container or isolated Linux subshell.
              No persistent disk access, no host root access, and the workspace directory is completely purged immediately after execution.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>🔐</div>
            <h2 className={styles.cardTitle}>Secret Redaction &amp; BYOK Isolation</h2>
            <p className={styles.cardDesc}>
              API keys and tokens (Gemini, Groq, OpenRouter, GitHub PATs) remain strictly in backend environment variables.
              They are never transmitted over WebSockets, never stored in client browser state, and are redacted from public event logs.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>🌿</div>
            <h2 className={styles.cardTitle}>Zero-Pollution Git Branches</h2>
            <p className={styles.cardDesc}>
              Nimbus never commits directly to your production or <code>main</code> branch.
              All code modifications are committed to an isolated <code>nimbus/task-{`{id}`}</code> branch and delivered as a
              GitHub Draft Pull Request for human code review.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>⚡</div>
            <h2 className={styles.cardTitle}>Multi-Tier Circuit Resiliency</h2>
            <p className={styles.cardDesc}>
              The 3-tier routing stack incorporates exponential backoff and jittered retries to protect against upstream outages and rate limits,
              guaranteeing zero execution crashes during LLM demand spikes.
            </p>
          </div>
        </div>

        {/* Maker attribution */}
        <MakerCard />
      </div>
    </main>
  );
}
