"use client";

import React from "react";
import styles from "./MakerCard.module.css";

export default function MakerCard() {
  return (
    <section className={styles.makerCard} aria-label="Creator Information">
      <div className={styles.glowAura} />
      
      <div className={styles.headerRow}>
        <div className={styles.avatar}>AS</div>
        <div className={styles.makerDetails}>
          <div className={styles.nameRow}>
            <span className={styles.name}>Anmol Sharma</span>
            <span className={styles.handle}>@anmolsharma152</span>
            <span className={styles.badge}>Creator &amp; Architect</span>
          </div>
          <span className={styles.role}>AI Systems &amp; Full-Stack Software Engineer</span>
        </div>
      </div>

      <p className={styles.bio}>
        Nimbus was engineered to bring true zero-trust autonomy to repository-level software development—featuring 
        a 3-tier resilient LLM routing stack, ephemeral Docker &amp; Subprocess workspace isolation, and automated Git pull request pipelines.
      </p>

      <div className={styles.linksRow}>
        <a
          href="https://anmolsharma152.vercel.app"
          target="_blank"
          rel="noopener noreferrer"
          className={`${styles.socialBtn} ${styles.primarySocialBtn}`}
          title="Visit Anmol Sharma's Personal Portfolio"
        >
          🌐 Portfolio Website
        </a>

        <a
          href="https://github.com/anmolsharma152"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.socialBtn}
          title="View Anmol Sharma on GitHub"
        >
          🐙 GitHub Profile
        </a>

        <a
          href="https://www.linkedin.com/in/anmolsharma152/"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.socialBtn}
          title="Connect with Anmol Sharma on LinkedIn"
        >
          💼 LinkedIn
        </a>

        <a
          href="https://github.com/anmolsharma152/nimbus"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.socialBtn}
          title="View Nimbus Open-Source Repository"
        >
          ⭐ Star on GitHub
        </a>
      </div>
    </section>
  );
}
