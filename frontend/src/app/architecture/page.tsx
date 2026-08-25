import React from "react";
import Link from "next/link";
import styles from "./architecture.module.css";

export const metadata = {
  title: "Architecture & Multi-Tier Resilience | Nimbus",
  description: "Explore Nimbus's distributed control-plane/data-plane architecture, 3-tier LLM fallback routing, and zero-trust sandbox isolation.",
};

export default function ArchitecturePage() {
  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        <Link href="/" className={styles.backLink}>
          ← Back to Agent Console
        </Link>

        <header className={styles.header}>
          <div className={styles.badge}>🏛️ System Architecture</div>
          <h1 className={styles.title}>High-Assurance Autonomous Engine</h1>
          <p className={styles.subtitle}>
            Nimbus implements a Hexagonal (Ports &amp; Adapters) architecture separating lightweight control-plane orchestration 
            from isolated, sandboxed execution planes.
          </p>
        </header>

        {/* 4 Pillars Grid */}
        <div className={styles.grid}>
          <div className={styles.card}>
            <div className={styles.cardIcon}>🛡️</div>
            <h2 className={styles.cardTitle}>Zero-Trust Sandboxing</h2>
            <p className={styles.cardDesc}>
              Untrusted code runs inside ephemeral subshells and Docker containers. The entire workspace directory is created 
              dynamically per task and purged immediately upon completion to avoid host file leakage.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>⚡</div>
            <h2 className={styles.cardTitle}>3-Tier Resilient LLM Routing</h2>
            <p className={styles.cardDesc}>
              Hierarchical fallback strategy spanning Google Gemini 3.6 Flash (Primary), Groq (<code>gpt-oss-120b</code> Secondary), 
              and OpenRouter (Tertiary) with automatic exponential backoff retry on transient 503/429 spikes.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>📡</div>
            <h2 className={styles.cardTitle}>Real-Time Flight Recorder</h2>
            <p className={styles.cardDesc}>
              Immutable event-sourced logging. Every shell execution, stdout/stderr chunk, tool choice, and status transition 
              is broadcast over WebSockets and stored in PostgreSQL for complete post-execution auditability.
            </p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardIcon}>🌿</div>
            <h2 className={styles.cardTitle}>Automated Git &amp; Draft PRs</h2>
            <p className={styles.cardDesc}>
              Isolates all code modifications into a dedicated <code>nimbus/task-{`{id}`}</code> branch, verifies passing assertions, 
              and pushes a GitHub Draft Pull Request ready for human code review.
            </p>
          </div>
        </div>

        {/* Interactive Architecture Flow Diagram */}
        <section className={styles.flowSection}>
          <h2 className={styles.flowHeading}>Execution Lifecycle Flow</h2>
          <div className={styles.flowGrid}>
            <div className={styles.flowStep}>
              <span className={styles.stepNum}>1</span>
              <h3>Task Ingestion</h3>
              <p>User submits natural language prompt &amp; target repository into FastAPI control plane.</p>
            </div>
            <div className={styles.flowStep}>
              <span className={styles.stepNum}>2</span>
              <h3>Sandbox Provision</h3>
              <p>Clones repository into ephemeral sandbox and creates dedicated task branch.</p>
            </div>
            <div className={styles.flowStep}>
              <span className={styles.stepNum}>3</span>
              <h3>Reasoning Loop</h3>
              <p>3-Tier LLM router executes multi-turn tool commands ($ls, $cat, $edit, $pytest).</p>
            </div>
            <div className={styles.flowStep}>
              <span className={styles.stepNum}>4</span>
              <h3>Draft PR Delivery</h3>
              <p>Computes git diff, commits changes, and opens a GitHub Draft Pull Request for review.</p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
