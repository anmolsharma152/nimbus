"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./login.module.css";
import { useAuth } from "../../context/AuthContext";

export default function LoginPage() {
  const { user, isLoading, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.push("/");
    }
  }, [user, isLoading, router]);

  return (
    <main className={styles.container}>
      <div className={styles.loginCard}>
        <div className={styles.brandHeader}>
          <svg className={styles.cloudSvg} viewBox="0 0 64 64" fill="none">
            <path
              d="M47 45C52.5228 45 57 40.5228 57 35C57 29.7909 53.0125 25.5126 47.9404 25.0487C46.6105 17.0381 39.6836 11 31.3333 11C22.0506 11 14.3752 18.2023 13.7212 27.3533C9.94825 28.5029 7 32.0267 7 36.3333C7 41.12 10.88 45 15.6667 45H47Z"
              fill="#ffffff"
            />
          </svg>
          <h1 className={styles.title}>Nimbus</h1>
        </div>

        <p className={styles.subtitle}>
          Autonomous Cloud Software Engineer with Zero-Trust Isolation
        </p>

        <button
          type="button"
          onClick={login}
          className={styles.githubBtn}
          disabled={isLoading}
        >
          <svg className={styles.githubIcon} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
          </svg>
          {isLoading ? "Authenticating..." : "Continue with GitHub"}
        </button>

        <div className={styles.divider}>Zero-Trust Guarantees</div>

        <div className={styles.securityList}>
          <div className={styles.securityItem}>
            <span className={styles.checkIcon}>✓</span>
            <span>Ephemeral Docker containers per coding task</span>
          </div>
          <div className={styles.securityItem}>
            <span className={styles.checkIcon}>✓</span>
            <span>Encrypted OAuth credentials at rest (Fernet AES-256)</span>
          </div>
          <div className={styles.securityItem}>
            <span className={styles.checkIcon}>✓</span>
            <span>Automated branch isolation &amp; Draft Pull Requests</span>
          </div>
        </div>

        <p className={styles.footerNote}>
          By continuing, you agree to Nimbus&apos;s{" "}
          <Link href="/security" className={styles.footerLink}>
            Security Architecture
          </Link>.
        </p>
      </div>
    </main>
  );
}
