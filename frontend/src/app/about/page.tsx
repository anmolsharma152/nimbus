import React from "react";
import Link from "next/link";
import styles from "./about.module.css";
import MakerCard from "../../components/MakerCard";

export const metadata = {
  title: "About the Creator | Anmol Sharma & Nimbus",
  description: "Learn about Anmol Sharma, the creator and architect of Nimbus Autonomous Cloud Software Engineer.",
};

export default function AboutPage() {
  return (
    <main className={styles.container}>
      <div className={styles.inner}>
        <Link href="/" className={styles.backLink}>
          ← Back to Agent Console
        </Link>

        <header className={styles.header}>
          <div className={styles.badge}>👨‍💻 Creator &amp; Architect</div>
          <h1 className={styles.title}>About Nimbus &amp; The Maker</h1>
          <p className={styles.subtitle}>
            Nimbus was designed and built by Anmol Sharma to demonstrate true autonomous cloud software engineering 
            with resilient multi-tier LLM routing, real-time WebSocket flight recorders, and zero-trust sandboxed isolation.
          </p>
        </header>

        <MakerCard />
      </div>
    </main>
  );
}
